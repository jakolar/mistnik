"""Occupation cards: CZ-ISCO sub-major groups across municipal elections 2002-2026 (aggregates only, no names).

Needs data/derived/occupations.csv (src/occupations.py, top 5 000 texts) and optionally data/derived/occ_gemini.csv.
Texts beyond the top 5 000 get the group of known texts they share a job title or key word with (tail_group);
what stays unclear is shown as "nezařazeno". Review: docs/povolani-review-2026-10-09.md.
Run: python3 src/occ_cards.py   -> data/mockup/povolani.html, data/derived/occ_groups.json
     python3 src/occ_cards.py --check   (rule smoke test, seconds)
"""
import collections, glob, json, pathlib, re, statistics
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER, OUT = ROOT / "data/raw", ROOT / "data/derived", ROOT / "data/mockup"
DATES = {2002: "20021101", 2006: "20061020", 2010: "20101015", 2014: "20141010", 2018: "20181005", 2022: "20220923", 2026: "20261009"}
# Deterministic overrides where Jev was systematically wrong (checked 2026-10-09 on the top texts of each group).
OVERRIDES = [
    (r"\b(policist|policie|strážn|strážník|městská policie|hasič)", "54"),
    (r"\b(zemědělec|zemědělkyně|farmář|rolník|rolnice)", "61"),
    (r"^(?!.*\b(tj|sdh|sokol|spolk\w*|klub\w*)\b)(\d\. ?)?(místo)?starost\w*|^primátor\w*|^náměst\w* primátor|^zástup\w* starost|^poslan\w*|^senátor\w*|^hejtman\w*|"
     r"^radní|^uvolněn\w* (zastupitel|člen)|^člen\w* rady (obce|města|kraje)|^předsed\w* (finančního |kontrolního )?(výboru|komise)",
     "funkce"),
]
# Our own reader-facing groups, built from CZ-ISCO sub-major groups (traceable, not 1:1 with the codebook).
GROUPS = {
    "Armáda, policie a hasiči": ["01", "02", "03", "54"],
    "Ostraha a bezpečnostní služby": [],  # filled by GROUP_OVERRIDES (private security, guards, lifeguards)
    "Vedoucí a ředitelé": ["11", "12", "13", "14"],
    "Vědci a inženýři": ["21"],
    "Lékaři a zdravotníci": ["22", "32"],
    "Učitelé a vychovatelé": ["23"],
    "Ekonomika, účetnictví a úřady": ["24", "33", "41", "42", "43", "44"],
    "IT": ["25", "35"],
    "Právo, kultura a média": ["26", "34"],
    "Technici": ["31"],
    "Obchod, gastronomie a služby": ["51", "52", "95"],
    "Sociální práce a péče": ["53"],
    "Zemědělství a lesnictví": ["61", "62", "63", "92"],
    "Řemesla a stavebnictví": ["71", "72", "73", "74", "75"],
    "Dělníci a obsluha strojů": ["81", "82", "93"],
    "Řidiči a strojvedoucí": ["83"],
    "Úklid a pomocné práce": ["91", "94", "96"],
}
# Jev sometimes answered only the 1-digit major group; these map to the closest reader group.
MAJOR_GROUP = {"g0": "Armáda, policie a hasiči", "g1": "Vedoucí a ředitelé", "g2": "Vědci a inženýři", "g3": "Technici",
               "g4": "Ekonomika, účetnictví a úřady", "g5": "Obchod, gastronomie a služby", "g6": "Zemědělství a lesnictví",
               "g7": "Řemesla a stavebnictví", "g8": "Dělníci a obsluha strojů", "g9": "Úklid a pomocné práce"}
GROUP_OF = {c: g for g, cs in GROUPS.items() for c in cs} | MAJOR_GROUP
# Names used before 2026-10-09 (occ_gemini.csv stores Gemini's answers under these).
OLD_NAMES = {"Armáda, policie a hasiči": "Armáda, policie a hasiči", "Obchod a služby": "Obchod, gastronomie a služby",
             "Právo, kultura, média a sociální práce": "Právo, kultura a média", "Péče a sociální služby": "Sociální práce a péče",
             "Řidiči": "Řidiči a strojvedoucí", "Politici a veřejné funkce": "Veřejné funkce (starosta, radní, poslanec)"}
# Group-level corrections where a 2-digit code mixes fields or Jev misplaced a common text (checked on top texts).
GROUP_OVERRIDES = [
    (r"sanitář|^ošetřovatel(ka)?$|ošetřovatel(ka)? (v|ve|na|u) |zdravotní sestra|dětská sestra|zdravotn\w*\W+záchranář|záchranář\w*\W+(zzs|rzp|zdravotn)|porodní asist", "Lékaři a zdravotníci"),
    (r"vychovatel|učitel|mistr odborného výcviku|mistrová odborného výcviku", "Učitelé a vychovatelé"),
    (r"vedoucí školní jídelny|vedoucí jídelny", "Vedoucí a ředitelé"),
    (r"^ministersk\w* rad|^vrchní rad|^státní úředn|^úřednice?$|^úředník", "Ekonomika, účetnictví a úřady"),
    (r"^školní(k|ce)\b", "Úklid a pomocné práce"),
    # 2026-10-09 review: firefighter-paramedics stay with firefighters; private security sits with CZ-ISCO 54;
    # social workers (CZ-ISCO 2635) join care so that "social" is not split across two groups
    (r"^hasič", "Armáda, policie a hasiči"),
    (r"ostrah|ochrank|bezpečnostní (pracovn|služb|agentur|referent)|^strážn[áý]|strážní služb|hlídač|^bodyguard", "Ostraha a bezpečnostní služby"),  # owner: private security is not police
    (r"sociální pracovn|sociálního pracovn", "Sociální práce a péče"),
    (r"ošetřovat\w* .*(skot|dojnic|zvířat|koní|prasat|drůbež|telat|krav|selat|býk)", "Zemědělství a lesnictví"),
    (r"^(osvč|osvc|živnostní\w*|podnikatel\w*)\W+((v|ve) )?(oboru )?(stavebnictví|stavební|elektro|zednick|instalatér|tesař|truhl)",
     "Řemesla a stavebnictví"),
    (r"vodní záchranář|plavčík", "Ostraha a bezpečnostní služby"),  # lifeguards: protective services, last so it wins
    # owner 2026-10-09: generic public-sector employees read as clerks, not as "unclear"
    (r"^státní zaměstnan(?!.*(polic|pčr|hasič|hzs|ačr|armád|voják|celn|vězeňsk))|^zaměstnan\w* (obce|města|městyse|kraje|státní správy|veřejné správy|úřadu|magistrátu)|^pracovn\w* (obecního|městského|krajského) úřadu",
     "Ekonomika, účetnictví a úřady"),
]
NOT_HUMAN_CARE = r"skot|dojnic|zvířat|koní|prasat|drůbež|řidič"
STATUS_CS = {"funkce": "Veřejné funkce (starosta, radní, poslanec)", "duchodce": "Důchodci", "student": "Studenti",
             "domacnost": "Rodičovská dovolená a domácnost", "nezamestnany": "Nezaměstnaní",
             "podnikatel": "Podnikatelé bez uvedeného oboru", "nejasne": "Nejasně uvedené povolání", "": "Nezařazeno (vzácné zápisy)"}
# Statuses that override a named job in the same text ("technik v důchodu" is a pensioner) vs. weak ones that yield
# to a named job ("osvč - kovář" is a smith).
STRONG = {"duchodce", "student", "domacnost", "nezamestnany"}
STATUS_WORDS = [
    (r"\bv\. ?v\.?$|důchod(ce|kyně|u)\b|\binv(al|alid)?\w*\.? ?důch|výslužb|\bemeritní", "duchodce"),
    (r"\bstudent(ka)?\b|\bstudující", "student"),
    (r"(mateřsk|rodičovsk)\w* dovol|^(na )?(mateřsk|rodičovsk)(á|é)$|v domácnosti|^péče o dítě|\bna (md|rd)\b", "domacnost"),
    (r"nezaměstnan|uchazeč o zam|^nezam\.?$", "nezamestnany"),
]
WEAK = {"podnikatel", "funkce", "nejasne"}
NOTES = {
    "funkce": "Tito kandidáti uvedli místo povolání veřejnou funkci, většinou jde o úřadující starosty a místostarosty. "
              "Proto jsou zvoleni tak často. Nejde o obor, ale o funkci, kterou už zastávají.",
    "podnikatel": "Jen zápisy bez oboru (podnikatel, OSVČ, živnostník). Kdo obor uvedl, například „OSVČ – truhlář“, je zařazen do oboru.",
    "duchodce": "Včetně zápisů typu „učitel v důchodu“; dřívější povolání se do oboru nepočítá.",
    "nejasne": "Zápisy, ze kterých obor nepoznáme, například „zaměstnanec“, „THP“ nebo „provozní“.",
    "": "Řídké zápisy, které se nepodařilo zařadit ani podle klíčových slov. Zůstávají stranou, aby nezkreslily obory.",
}
SIZE = [(0, 1000, "do 1 000"), (1000, 5000, "1 000–5 000"), (5000, 50000, "5 000–50 000"), (50000, 10**8, "nad 50 000")]
SPLIT = re.compile(r"\s*[,;/()+]\s*|\s+[-–]\s*|\s*[-–]\s+")
WORD = re.compile(r"[^\W\d_]{2,}")
ADJ = re.compile(r"(ý|á|é|ých|ého|ým|ou|ní)$")
# a word votes only if >= 3 known texts use it (>= 6 for a 5-letter stem) and >= 85 % of them share one group
MIN_WORD, MIN_STEM, MIN_SHARE = 3, 6, 0.85
# chairing a club or association is a hobby, not the job ("předsedkyně raketomodelářského klubu")
HOBBY = re.compile(r"^(před|místopřed)\w*\.? .*(klub|oddíl|spol[ek]|sdružen|z\. ?s|\btj\b|sokol|svaz|hasič|fanoušk)")


def has(t, pat):
    return t.str.contains(re.sub(r"\((?!\?)", "(?:", pat), regex=True)  # non-capturing groups, no pandas warning


def stem(w):
    return w[:5]


class Keywords:
    """Word and stem statistics over classified texts (each distinct text is one vote)."""

    def __init__(self, labels):
        self.c = collections.defaultdict(collections.Counter)
        for t, g in labels.items():
            for k in self.keys(t):
                self.c[k][g] += 1

    @staticmethod
    def keys(t):
        ws = WORD.findall(t)
        return set(ws) | {"~" + stem(w) for w in ws}

    def vote(self, key, own=None, among=None):
        c = self.c.get(key)
        if not c:
            return None
        if own:
            c = c - collections.Counter({own: 1})
        if among is not None:
            c = collections.Counter({g: n for g, n in c.items() if g in among})
        n = sum(c.values())
        if n < (MIN_STEM if key.startswith("~") else MIN_WORD):
            return None
        g, top = c.most_common(1)[0]
        return g if top / n >= MIN_SHARE else None

    def word_group(self, w, own=None, among=None):
        return self.vote(w, own, among) or self.vote("~" + stem(w), own, among)


def tail_group(t, known, kw, own=None):
    """Group for a text outside the classified top: status words, then the first named job, then a weak status.

    own: group of t itself when evaluating on a known text (leave-one-out)."""
    for pat, g in STATUS_WORDS:
        if re.search(pat, t):
            return g, "status"
    weak = None
    for part in [p for p in SPLIT.split(t) if p and not HOBBY.search(p)]:
        if part != t and part in known:
            g = known[part]
            if g not in WEAK and g not in STRONG:
                return g, "part"
            weak = weak or g
        ws = part.split()
        for i in range(len(ws) - 1, 0, -1):  # longest known word-prefix
            g = known.get(" ".join(ws[:i]))
            if g and g not in WEAK and g not in STRONG:
                return g, "prefix"
        for i in range(1, len(ws)):  # known job after uninformative adjectives ("revizní elektrotechnik")
            if all(ADJ.search(w) or w.endswith(".") for w in ws[:i]) and (g := known.get(" ".join(ws[i:]))):
                if any(kw.word_group(w, own) not in (None, g) for w in ws[:i]):
                    break  # the adjective points elsewhere ("zubní technik"): let the word votes decide
                if g not in WEAK and g not in STRONG:
                    return g, "suffix"
                if g == "podnikatel":
                    weak = weak or g
                break
        ws = WORD.findall(part)
        # head nouns first, then adjectives from the right ("skladová účetní" is an accountant)
        for w in [w for w in ws if not ADJ.search(w)] + [w for w in ws if ADJ.search(w)][::-1]:
            g = kw.word_group(w, own)
            if g in GROUPS:
                return g, "word"
            if g in WEAK:
                weak = weak or g
    return (weak, "weak") if weak else ("", "")


def classify(texts):
    """Final group and provenance for each distinct occupation text."""
    occ = pd.read_csv(DER / "occupations.csv", dtype=str, keep_default_na=False).set_index("text")
    C = pd.DataFrame(index=pd.Index(sorted(set(texts) | set(occ.index)), name="text"))
    C["code"] = C.index.map(occ.submajor.where(occ.submajor != "", occ.major)).fillna("")
    C["conf"] = pd.to_numeric(C.index.map(occ.major_conf), errors="coerce")
    C["src"] = (C.code != "").map({True: "jev", False: ""})
    t = C.index.to_series()
    skip = has(t, r"dobrovoln|výslužb|bývalý|důchod|\bv\. ?v\.?$")
    for pat, code in OVERRIDES:
        hit = has(t, pat) & ~skip
        C.loc[hit & (C.code != code), "src"] = "rule"
        C.loc[hit, "code"] = code
    C["group"] = C.code.map(lambda c: GROUP_OF.get(c, c))
    gem = DER / "occ_gemini.csv"
    C["gem_ok"] = False
    if gem.exists():
        G = pd.read_csv(gem, keep_default_na=False)
        back = {v: k for k, v in STATUS_CS.items()} | {g: g for g in GROUPS}
        back |= {o: back[n] for o, n in OLD_NAMES.items()}
        C.loc[C.index.isin(G.text[G.agree.astype(str) == "True"]), "gem_ok"] = True
        fix = {x: back[g] for x, g, ok in zip(G.text, G.gemini, G.agree) if str(ok) == "False" and g in back}
        hit = C.index.isin(list(fix)) & (C.src != "rule")
        C.loc[hit, "group"] = C.index[hit].map(fix)
        C.loc[hit, "src"] = "gemini"
    animals = has(t, NOT_HUMAN_CARE)
    for pat, grp in GROUP_OVERRIDES:
        hit = has(t, pat) & ~skip & ~(animals & (grp == "Lékaři a zdravotníci"))
        C.loc[hit & (C.group != grp), "src"] = "rule"
        C.loc[hit, "group"] = grp
    # an explicit status in the text wins over a named job, for every text ("zdravotní sestra v důchodu" is retired)
    for pat, g in STATUS_WORDS:
        hit = has(t, pat) & (C.group != g)
        C.loc[hit, "src"] = "status"
        C.loc[hit, "group"] = g
    known = C.group[C.index.isin(occ.index) & (C.group != "")].to_dict()
    kw = Keywords(known)
    tail = C.index[C.group == ""]
    res = [tail_group(x, known, kw) for x in tail]
    C.loc[tail, "group"] = [g for g, _ in res]
    C.loc[tail, "src"] = ["tail-" + h if g else "" for g, h in res]
    # owner 2026-10-09: "vedoucí X" belongs to the field of X ("vedoucí prodejny" -> trade); bare "vedoucí" stays a manager
    for x in C.index[has(C.index.to_series(), r"^vedouc\w*\s+\S")]:
        rest = re.sub(r"^vedouc\w*\s+", "", x)
        g, _ = tail_group(rest, known, kw)
        if g in GROUPS and g != "Vedoucí a ředitelé":
            C.at[x, "group"], C.at[x, "src"] = g, "rule"
    # honest uncertainty: the final group still rests only on a low-confidence Jev answer
    C["lowconf"] = (C.src == "jev") & (C.conf < 0.5) & ~C.gem_ok
    C["kw"] = C.src.str.startswith("tail")
    return C, known, kw


def od(year, name):
    return glob.glob(str(RAW / f"kv{year}/**/csv_od/{name}.csv"), recursive=True)[0]


def read(year, name):
    d = pd.read_csv(od(year, name), dtype=str, keep_default_na=False)
    return d[d.DATUMVOLEB == DATES[year]] if "DATUMVOLEB" in d else d


def load():
    frames = []
    for y in DATES:
        k = read(y, "kvrk")
        k = k[k.PLATNOST == "A"]
        cpp = read(y, "cpp").set_index("PSTRANA").ZKRATKAP8
        rz = read(y, "kvrzcoco").drop_duplicates("KODZASTUP").set_index("KODZASTUP").POCOBYV
        frames.append(pd.DataFrame({"year": y, "text": k.POVOLANI.str.lower().str.replace(r"\s+", " ", regex=True).str.strip(" ,.;-"),
                                    "elected": k.MANDAT == "A", "age": pd.to_numeric(k.VEK, errors="coerce"),
                                    "party": k.PSTRANA.map(cpp).fillna(""), "bezpp": k.PSTRANA == "99",
                                    "pop": pd.to_numeric(k.KODZASTUP.map(rz), errors="coerce")}))
    return pd.concat(frames, ignore_index=True)


RANK_MIN = 1000  # candidacies 2002-2022 per occupation text; below that the share elected is noise


def main():
    occ = pd.read_csv(DER / "occupations.csv", dtype=str, keep_default_na=False).set_index("text")
    D = load()
    C, _, _ = classify(D.text.unique())
    for col in ("group", "kw"):
        D[col] = D.text.map(C[col])
    D["cat"] = D.group
    D["func"] = D.text.map(occ.functions).fillna("") != ""

    # export for candidate profiles: occupation text -> reader-facing group, and 2026 counts per group
    D["gname"] = D.cat.map(lambda c: STATUS_CS.get(c, c))
    # home page: most / least often elected occupation texts 2002-2022; public offices left out (elected by definition)
    past = D[(D.year < 2026) & ~D.func & (D.text != "")].groupby("text").agg(n=("elected", "size"), rate=("elected", "mean"))
    past = past[past.n >= RANK_MIN].sort_values("rate")
    past.assign(group=[D.gname[D.text == t].iat[0] for t in past.index]).round(4).to_csv(DER / "occ_rank.csv")  # open data
    row = lambda t, r: [t, int(r.n), round(float(r.rate), 3), D.gname[D.text == t].iat[0]]
    rank = {"min": RANK_MIN, "base": round(float(D[D.year < 2026].elected.mean()), 3),
            "top": [row(t, r) for t, r in past[::-1].head(6).iterrows()], "bottom": [row(t, r) for t, r in past.head(6).iterrows()]}
    json.dump({"text": dict(zip(D.text, D.gname)), "n2026": D[D.year == 2026].gname.value_counts().to_dict(), "rank": rank},
              open(DER / "occ_groups.json", "w"), ensure_ascii=False)
    per_year = D.groupby("year").size()
    base_rate = D[D.year < 2026].groupby("year").elected.mean()
    cards = []
    for cat, g in D.groupby("cat"):
        past = g[g.year < 2026]
        members = g[~g.bezpp & (g.party != "")].party.value_counts()
        sizes = [((g["pop"] >= lo) & (g["pop"] < hi)).mean() for lo, hi, _ in SIZE]
        cards.append({
            "code": cat, "name": STATUS_CS.get(cat, cat),
            "kind": "group" if cat in GROUPS else "none" if cat in ("", "nejasne") else "status",
            "ages": [int(((g.age >= lo) & (g.age < hi)).sum()) for lo, hi in ((0, 30), (30, 45), (45, 60), (60, 200))],
            "n": len(g), "years": [{"y": int(y), "n": int((g.year == y).sum()), "share": float((g.year == y).sum() / per_year[y]),
                                    "rate": float(past[past.year == y].elected.mean()) if y < 2026 and (past.year == y).any() else None,
                                    "base": float(base_rate.get(y)) if y < 2026 else None} for y in DATES],
            "rate": float(past.elected.mean()) if len(past) else None, "base": float(D[D.year < 2026].elected.mean()),
            "age": statistics.median(g.age.dropna()) if g.age.notna().any() else None,
            "bezpp": float(g.bezpp.mean()), "parties": [[p, int(c)] for p, c in members.head(4).items()],
            "sizes": [[lab, float(s)] for (_, _, lab), s in zip(SIZE, sizes)],
            # per text: candidacies 2002-2026 and share elected 2002-2022 (2026 not decided yet)
            "texts": [[t_, int(c_), round(float(past[past.text == t_].elected.mean()), 3) if (past.text == t_).any() else None]
                      for t_, c_ in g.text.value_counts().head(8).items()],
            "variants": int(g.text.nunique()), "kw": float(g.kw.mean()),
            "func": float(g.func.mean()), "note": NOTES.get(cat, ""),
        })
    order = {"group": 0, "status": 1, "none": 2}
    cards.sort(key=lambda c: (order[c["kind"]], c["code"] == "", -c["n"]))
    OUT.mkdir(parents=True, exist_ok=True)
    page = (ROOT / "src/occ_template.html").read_text().replace("__DATA__", json.dumps(cards, ensure_ascii=False).replace("</", "<\\/"))
    (OUT / "povolani.html").write_text(page)
    occupied = D.cat.isin(list(GROUPS))
    print(f"{len(cards)} categories, classified share {1 - (D.cat == '').mean():.1%} (occupation groups {occupied.mean():.1%}, "
          f"keyword-classified tail {D.kw.mean():.1%}) -> {OUT / 'povolani.html'}")


def check():
    """Smoke test of the classification rules on texts from the 2026-10-09 review (fast, no raw data)."""
    want = {"osvč - kovář": "Řemesla a stavebnictví", "zemědělská podnikatelka": "Zemědělství a lesnictví",
            "elektrikář v důchodu": "duchodce", "hasič - záchranář": "Armáda, policie a hasiči",
            "ostraha objektu": "Ostraha a bezpečnostní služby", "sociální pracovnice": "Sociální práce a péče",
            "osvč v oboru elektro": "Řemesla a stavebnictví", "ředitelka zvš": "Vedoucí a ředitelé",
            "předsedkyně raketomodelářského klubu": "", "prodavačka na md": "domacnost",
            "zdravotní sestra v důchodu": "duchodce", "zdravotní sestra, důchodkyně": "duchodce",
            "student lékařské fakulty": "student", "vodní záchranář": "Ostraha a bezpečnostní služby",
            "hasič, záchranář": "Armáda, policie a hasiči", "zdravotnický záchranář": "Lékaři a zdravotníci",
            "zdravotník-záchranář": "Lékaři a zdravotníci", "1. místostarosta města": "funkce"}
    C, _, _ = classify(list(want))
    bad = {t: C.group[t] for t, g in want.items() if C.group[t] != g}
    assert not bad, bad
    print("check ok")


if __name__ == "__main__":
    import sys
    check() if "--check" in sys.argv else main()
