"""Link municipal-election candidacies 2002-2026 into persons (spec: docs/parovani-kandidatu-v2.md).

Per election pair (A earlier, B later), per candidate pair with the same first name + surname:
  odds(B is A) = r * prod m_f(level) / ( E_eff * c * prod u_f(level) )
    r      P(an A candidate runs again in B), measured on the seed (names with E < SEED_E)
    E      expected living namesakes (first name, surname, birth year) in CZ at election A:
           MV ČR counts (Jan 2017) divided by survival from the election to 2017 (ČSÚ life tables)
    E_eff  E x local surname concentration among candidates, for same-city pairs
    c      share of population that is a B candidate
    m      field level distribution among seed matches, u among strangers
           (national random pairs, or random same-council pairs for same-city comparisons)
Candidacies of one name + city + age in one election form a person-event (city + city part double run).
p is normalised against all competing namesakes on both sides. m, u, r are estimated per election pair,
so long gaps get their own (weaker) occupation / co-candidate evidence.

Scores only; decisions and clustering are in cluster.py (Clusters class below is shared).
Run: python3 src/linkage.py   (~1 h, writes data/derived/linkage_edges.csv.gz, linkage_age_conflicts, linkage_params)
"""
import csv, datetime as dt, glob, itertools, json, pathlib, re, unicodedata
import numpy as np
import pandas as pd
from gender import gender

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data/raw", ROOT / "data/derived"
JMENOVAC = pathlib.Path.home() / "projekty/jmenovac/data"
DATES = {2002: "20021101", 2006: "20061020", 2010: "20101015", 2014: "20141010",
         2018: "20181005", 2022: "20220923", 2026: "20261009"}
SEED_E = 0.02
GEO_LEVELS = ["zast", "city", "orp", "okres", "kraj", "other"]
FIELDS = ["cocand", "party", "titles", "occ", "list_party"]
LOCAL = ("zast", "city")
EPS = 1e-4
VOTERS = 8_300_000  # ponytail: flat population for c; age-specific candidacy rate if calibration needs it


def strip(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).lower().strip()


def name_norm(s):
    """Blocking form of a name: no diacritics, lower case, hyphens and spaces unified (Nováková - Svobodová = Nováková-Svobodová)."""
    return re.sub(r"[\s\-‐–]+", " ", strip(s)).strip()


def od(year, name):
    return glob.glob(str(RAW / f"kv{year}/**/csv_od/{name}.csv"), recursive=True)[0]


def edate(year):
    return dt.datetime.strptime(DATES[year], "%Y%m%d").date()


def birth_window(date, age):
    """Birth date interval, inclusive, for someone `age` years old on the 2nd election day."""
    d = date + dt.timedelta(days=1)
    return d.replace(year=d.year - age - 1) + dt.timedelta(days=1), d.replace(year=d.year - age)


def titles(pre, post):
    return frozenset(re.findall(r"[a-z]+", strip(f"{pre} {post}").replace("ph.d", "phd")))


# Common abbreviations in candidates' occupations, expanded before comparing (KHS = krajská hygienická stanice).
ABBR = {"khs": "krajska hygienicka stanice", "hzs": "hasicsky zachranny sbor", "pcr": "policie", "mp": "mestska policie",
        "zs": "zakladni skola", "ms": "materska skola", "ss": "stredni skola", "sou": "stredni odborne uciliste",
        "vs": "vysoka skola", "zd": "zemedelske druzstvo", "ou": "obecni urad", "mu": "mestsky urad", "mmu": "magistrat",
        "ku": "krajsky urad", "fu": "financni urad", "up": "urad prace", "cssz": "ceska sprava socialniho zabezpeceni",
        "ossz": "okresni sprava socialniho zabezpeceni", "cd": "ceske drahy", "acr": "armada", "osvc": "osoba samostatne vydelecne cinna",
        "dps": "dum s pecovatelskou sluzbou", "zzs": "zdravotnicka zachranna sluzba", "ddm": "dum deti a mladeze"}


def occ_stems(s):
    # ponytail: 5-char prefix stem merges advokát/advokátka; abbreviations expanded first; CZ-ISCO field covers the rest
    words = re.findall(r"[a-z]+", strip(s).replace(".", " "))
    words = " ".join(ABBR.get(w, w) for w in words).split()
    return frozenset(w[:5] for w in words if len(w) >= 3)


_FIELD = {}


def occ_field(text):
    """CZ-ISCO sub-major group of an occupation text (Jev classification, src/occupations.py); '' if unknown or a status."""
    if not _FIELD:
        f = DER / "occupations.csv"
        if f.exists():
            for r in csv.DictReader(open(f, encoding="utf-8")):
                _FIELD[r["text"]] = r["submajor"] or ""
        _FIELD.setdefault("", "")
    return _FIELD.get(re.sub(r"\s+", " ", text.lower()).strip(" ,.;-"), "")


def regular(df, year):
    return df[df.DATUMVOLEB == DATES[year]] if "DATUMVOLEB" in df else df


def read(year, name):
    return regular(pd.read_csv(od(year, name), dtype=str, keep_default_na=False), year)


_ORP = {}


def orp_map():
    """KODZASTUP -> ORP from the newest registries (ČSÚ left ORP empty in 2002-2014)."""
    if not _ORP:
        for y in (2002, 2006, 2010, 2014, 2018, 2022, 2026):
            rz = read(y, "kvrzcoco")
            _ORP.update({k: v for k, v in zip(rz.KODZASTUP, rz.ORP) if v})
    return _ORP


def load(year):
    k = read(year, "kvrk")
    k = k[(k.VEK != "") & (k.PLATNOST == "A")]
    ros = read(year, "kvros")[["KODZASTUP", "COBVODU", "POR_STR_HL", "NAZEVCELK", "SLOZENI"]]
    # parties composing the list, by name (codes are reused across years); 80/90 = independents, not a party
    cvs = read(year, "cvs").drop_duplicates("VSTRANA").set_index("VSTRANA").ZKRATKAV8.map(strip)
    ros["parties"] = [frozenset(cvs.get(str(int(c)), "") for c in s.split(",") if c.strip().isdigit() and int(c) not in (80, 90)) - {""}
                      for s in ros.SLOZENI]
    coco = read(year, "kvcoco").drop_duplicates("KODZASTUP")[["KODZASTUP", "NADRZASTUP", "TYPZASTUP", "KRAJ"]]
    rz = read(year, "kvrzcoco").drop_duplicates("KODZASTUP")[["KODZASTUP", "ORP", "POCOBYV"]]
    k = k.merge(ros, on=["KODZASTUP", "COBVODU", "POR_STR_HL"], how="left").merge(coco, on="KODZASTUP", how="left").merge(rz, on="KODZASTUP", how="left")
    for col in ("NADRZASTUP", "TYPZASTUP", "KRAJ", "ORP", "POCOBYV", "NAZEVCELK", "SLOZENI"):
        k[col] = k[col].fillna("")
    # 12 regular 2006 candidacies have no council row for that date
    k["parties"] = k.parties.map(lambda x: x if isinstance(x, frozenset) else frozenset())
    k["ORP"] = k.ORP.where(k.ORP != "", k.KODZASTUP.map(orp_map())).fillna("")
    k["year"] = year
    k["id"] = f"{year}:" + k.KODZASTUP + ":" + k.COBVODU + ":" + k.POR_STR_HL + ":" + k.PORCISLO
    k["first"] = k.JMENO.str.split().str[0].fillna("")
    k["surname"] = k.PRIJMENI.map(name_norm)
    k["key"] = k["first"].map(name_norm) + "|" + k.surname
    k["age"] = k.VEK.astype(int)
    w = [birth_window(edate(year), a) for a in k.age]
    k["blo"] = np.array([x[0] for x in w], dtype="datetime64[D]")
    k["bhi"] = np.array([x[1] for x in w], dtype="datetime64[D]")
    k["city"] = k.NADRZASTUP.where(k.NADRZASTUP != "", k.KODZASTUP)
    k["pe"] = f"{year}|" + k.key + "|" + k.city + "|" + k.VEK
    clash = k.duplicated(["pe", "TYPZASTUP"], keep=False)  # same name+age twice in one council type = two people
    k.loc[clash, "pe"] = k.pe[clash] + "|" + k.id[clash]
    listkey = k.KODZASTUP + "|" + k.COBVODU + "|" + k.POR_STR_HL
    mates = k.groupby(listkey).key.agg(frozenset)
    k["cocand"] = [mates[l] - {own} for l, own in zip(listkey, k.key)]
    k["titles"] = [titles(a, b) for a, b in zip(k.TITULPRED, k.TITULZA)]
    k["occ"] = k.POVOLANI.map(occ_stems)
    low = k.POVOLANI.str.lower()
    k["field"] = k.POVOLANI.map(occ_field)
    k["retired"] = low.str.contains(r"důchod|penzist|v penzi", regex=True)
    k["student"] = low.str.contains(r"student|žák|žačka", regex=True)
    k["female"] = [gender(a, b) == "Z" for a, b in zip(k.JMENO, k.PRIJMENI)]  # unknown counts as male cohort
    cpp = read(year, "cpp").set_index("PSTRANA").ZKRATKAP8.map(strip)
    k["party_name"] = k.PSTRANA.map(cpp).fillna("")
    return k.reset_index(drop=True)


class Namesakes:
    """Expected living namesakes in CZ at a given election, from MV ČR 2017 counts and ČSÚ life tables."""

    def __init__(self):
        self.fn, self.sn = {}, {}
        for path, dct in ((DER / "mv_jmena_dnar.csv", self.fn), (DER / "mv_prijmeni_dnar.csv", self.sn)):
            for r in csv.DictReader(open(path, encoding="utf-8")):
                dct[(r["name"], int(r["year"]))] = int(r["count"])
        self.pop = {int(r["rok"]): (int(r["M"]), int(r["Z"])) for r in csv.DictReader(open(JMENOVAC / "jmena_mv_rocniky.csv"))}
        self.qx = json.load(open(JMENOVAC / "umrtnost.json"))["obdobi"]

    def survival(self, born, sex, year):
        """P(alive Jan 2017 | alive at `year`), born in `born`; 1 for elections after 2017."""
        s = 1.0
        for yr in range(year, 2017):
            per = str(min(max(yr - yr % 5, 1920), 2020))
            q = self.qx[per][sex]
            s *= 1 - q[min(max(yr - born, 0), len(q) - 1)]
        return max(s, 0.01)

    def __call__(self, df, year):
        d = edate(year)
        w_late = (dt.date(d.year, 12, 31) - d).days / 365  # born after election day -> earlier birth year
        out = []
        for f, s, a, fem in zip(df["first"].str.upper(), df.PRIJMENI.str.upper(), df.age, df.female):
            e = 0.0
            for y, wt in ((year - a - 1, w_late), (year - a, 1 - w_late)):
                n = self.pop.get(max(y, 1920), self.pop[1920])[1 if fem else 0]
                e += wt * (self.fn.get((f, y), 0) + 0.5) * (self.sn.get((s, y), 0) + 0.5) / max(n, 1) / self.survival(y, "Z" if fem else "M", year)
            out.append(e)
        return np.array(out)


def levels(P):
    """Comparison levels for a frame of pairs with _a/_b columns."""
    sa = lambda c: P[f"{c}_a"].values
    sb = lambda c: P[f"{c}_b"].values
    eq = lambda c: sa(c) == sb(c)
    known = lambda c: (sa(c) != "") & (sb(c) != "")  # empty code must not count as a match
    geo = np.select([eq("KODZASTUP"), eq("city"), eq("ORP") & known("ORP"), eq("OKRES"), eq("KRAJ") & known("KRAJ")],
                    GEO_LEVELS[:-1], "other")
    shared = np.array([len(a & b) for a, b in zip(sa("cocand"), sb("cocand"))])
    coc = np.where(~eq("city"), "na", np.select([shared >= 2, shared == 1], ["2+", "1"], "0"))
    party = np.select([(sa("PSTRANA") == "99") & (sb("PSTRANA") == "99"), eq("party_name") & (sa("party_name") != "")],
                      ["both_bezpp", "same"], "diff")  # codes get reused for other parties across years
    tl = ["none" if not a and not b else "same" if a == b else "gained" if a < b else "other" for a, b in zip(sa("titles"), sb("titles"))]
    oc = []
    for a, b, ra, rb, st_a, st_b, fa, fb in zip(sa("occ"), sb("occ"), sa("retired"), sb("retired"), sa("student"), sb("student"),
                                                 sa("field"), sb("field")):
        if not a or not b:
            oc.append("missing")
            continue
        j = len(a & b) / len(a | b)
        if j == 1:
            oc.append("same")
        elif rb and not ra:
            oc.append("to_retired")    # life course: job -> pension is not a contradiction
        elif st_a and not st_b:
            oc.append("from_student")  # life course: school -> job
        elif j >= 0.5 or (a <= b or b <= a):
            oc.append("similar")       # e.g. lékárník -> vedoucí lékárník
        elif fa and fa == fb:
            oc.append("same_field")    # same CZ-ISCO group: lékárnice / odborný zástupce v lékárně
        else:
            oc.append("diff")
    lp = ["na" if not a or not b else "shared" if a & b else "none" for a, b in zip(sa("parties"), sb("parties"))]
    return {"geo": geo, "cocand": coc, "party": party, "titles": np.array(tl), "occ": np.array(oc), "list_party": np.array(lp)}


def dist(values):
    return pd.Series(values).value_counts(normalize=True).to_dict()


def geo_u(P, B):
    """Share of B candidacies in each geo ring around A (nested rings, inner ring subtracted)."""
    prev, u = np.zeros(len(P)), {}
    for lvl, col in zip(GEO_LEVELS, ["KODZASTUP", "city", "ORP", "OKRES", "KRAJ", None]):
        n = P[f"{col}_a"].map(B[col].value_counts()).fillna(0).values if col else np.full(len(P), len(B))
        u[lvl] = np.maximum(n - prev, 1) / len(B)
        prev = np.maximum(n, prev)
    return u


def score_pair(A, B, rng):
    """Score every same-name pair between elections A < B. Returns person-event edges, age-conflict pairs, params."""
    P = A.reset_index().merge(B.reset_index(), on="key", suffixes=("_a", "_b"))
    P["overlap"] = (np.minimum(P.bhi_a, P.bhi_b) - np.maximum(P.blo_a, P.blo_b)).dt.days + 1
    P = P[P.overlap > -366].reset_index(drop=True)  # farther apart is a different person or a gross data error
    for f, v in levels(P).items():
        P[f] = v

    R = pd.concat([A.iloc[rng.integers(0, len(A), 200_000)].reset_index(drop=True).add_suffix("_a"),
                   B.iloc[rng.integers(0, len(B), 200_000)].reset_index(drop=True).add_suffix("_b")], axis=1)
    u = {f: dist(v) for f, v in levels(R).items() if f in FIELDS}
    u["cocand"] = {"na": 1.0}
    by_zast = A.groupby("KODZASTUP").indices
    bs = B[B.KODZASTUP.isin(by_zast)].sample(200_000, replace=True, random_state=0)
    same = pd.concat([A.iloc[[by_zast[z][rng.integers(len(by_zast[z]))] for z in bs.KODZASTUP]].reset_index(drop=True).add_suffix("_a"),
                      bs.reset_index(drop=True).add_suffix("_b")], axis=1)
    u_loc = {f: dist(v) for f, v in levels(same[same.key_a != same.key_b]).items() if f in FIELDS}

    # local surname concentration: other same-surname candidates (distinct first names) in A's city, both elections
    both = pd.concat([A[["city", "surname", "first"]], B[["city", "surname", "first"]]]).drop_duplicates()
    fam = both.groupby(["city", "surname"]).size()
    nat = both.drop_duplicates(["surname", "first"]).surname.value_counts(normalize=True)
    others = np.array([fam.get((c, s), 1) - 1 for c, s in zip(P.city_a, P.surname_a)])
    expected = P.city_a.map(both.groupby("city").size()).values * P.surname_a.map(nat).values
    P["E_eff"] = np.where(P.geo.isin(LOCAL), P.E_a * np.clip((others + 1) / (expected + 1), 1, 50), P.E_a)

    ok = P.overlap > 0
    seed = P[ok & (P.E_a < SEED_E)].sort_values("geo", key=lambda s: s.map(GEO_LEVELS.index)).drop_duplicates("index_a")
    r = len(seed) / max((A.E < SEED_E).sum(), 1)
    m = {f: dist(seed[f]) for f in ["geo", *FIELDS]}
    m["cocand"] = dist(seed[seed.geo.isin(LOCAL)].cocand)
    m["cocand"]["na"] = 1.0
    c = len(B) / VOTERS

    gu = geo_u(P, B)
    P["w_prior"] = np.log2(r) - np.log2(P.E_eff * c)
    P["w_geo"] = np.log2([m["geo"].get(g, EPS) for g in P.geo]) - np.log2(np.choose([GEO_LEVELS.index(g) for g in P.geo], [gu[l] for l in GEO_LEVELS]))
    w = P.w_prior + P.w_geo
    loc = P.geo.isin(LOCAL).values
    for f in FIELDS:
        P[f"w_{f}"] = [np.log2(m[f].get(x, EPS) / (u_loc if l else u)[f].get(x, EPS)) for x, l in zip(P[f], loc)]
        w = w + P[f"w_{f}"]
    P["weight"] = w

    conflicts = P[~ok & (P.weight - P.w_prior > 10)]
    keep = ["pe_a", "pe_b", "year_a", "year_b", "id_a", "id_b", "E_a", "E_eff", "overlap", "geo", *FIELDS,
            "w_prior", "w_geo", *[f"w_{f}" for f in FIELDS], "weight"]
    G = P[ok].sort_values("weight", ascending=False).drop_duplicates(["pe_a", "pe_b"])[keep]
    odds = 2.0 ** G.weight.clip(-60, 60)
    G["p"] = odds / (1 + odds.groupby(G.pe_a).transform("sum") + odds.groupby(G.pe_b).transform("sum") - odds)
    return G, conflicts[keep], {"r": r, "c": c, "seed": len(seed), "m": m, "u": u, "u_loc": u_loc}


class Clusters:
    """Union-find over person-events; a cluster keeps its elections and the intersection of birth windows."""

    def __init__(self, nodes):
        self.parent = {n: n for n in nodes.index}
        self.years = {n: {y} for n, y in nodes.year.items()}
        self.lo, self.hi = nodes.blo.to_dict(), nodes.bhi.to_dict()

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def why_not(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return "same"
        if self.years[ra] & self.years[rb]:
            return "election_clash"
        if max(self.lo[ra], self.lo[rb]) > min(self.hi[ra], self.hi[rb]):
            return "birth_clash"
        return None

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        self.parent[rb] = ra
        self.years[ra] |= self.years.pop(rb)
        self.lo[ra], self.hi[ra] = max(self.lo[ra], self.lo[rb]), min(self.hi[ra], self.hi[rb])


def main():
    DER.mkdir(exist_ok=True)
    ns, rng = Namesakes(), np.random.default_rng(0)
    data = {}
    for y in DATES:
        data[y] = load(y)
        data[y]["E"] = ns(data[y], y)
        print(f"{y}: {len(data[y])} candidacies, {data[y].pe.nunique()} person-events", flush=True)

    edges, conflicts, params = [], [], {}
    for ya, yb in itertools.combinations(DATES, 2):
        G, C, prm = score_pair(data[ya], data[yb], rng)
        edges.append(G), conflicts.append(C)
        params[f"{ya}-{yb}"] = prm
        print(f"{ya}->{yb}: edges {len(G)}, r={prm['r']:.3f}, seed {prm['seed']}, "
              f"m(occ same)={prm['m']['occ'].get('same', 0):.2f}, m(cocand 2+)={prm['m']['cocand'].get('2+', 0):.2f}, "
              f"p>=0.999 {(G.p >= 0.999).sum()}", flush=True)
    E = pd.concat(edges, ignore_index=True)
    E.to_csv(DER / "linkage_edges.csv.gz", index=False, compression="gzip")
    pd.concat(conflicts, ignore_index=True).to_csv(DER / "linkage_age_conflicts.csv.gz", index=False, compression="gzip")
    json.dump(params, open(DER / "linkage_params.json", "w"), indent=1, default=str)
    print(f"edges {len(E)}, p>=0.999 {(E.p >= 0.999).sum()} -> {DER / 'linkage_edges.csv.gz'}; cluster with src/cluster.py")


if __name__ == "__main__":
    main()
