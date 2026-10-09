"""Mockup of candidate cards for one municipality's 2026 ballot, from linkage output. Local only (real names).

Run: python3 src/card_mockup.py [KODZASTUP|mesto|vesnice]   -> data/mockup/<kod>.html
Serve: python3 -m http.server 8093 --bind 0.0.0.0 -d data/mockup
"""
import bisect, collections, glob, html, json, pathlib, sys
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import linkage as L
from gender import gender

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER, RAW, OUT = ROOT / "data/derived", ROOT / "data/raw", ROOT / "data/mockup"
YEARS = [2002, 2006, 2010, 2014, 2018, 2022, 2026]


def party_names():
    names = {}
    for y in YEARS:
        p = glob.glob(str(RAW / f"kv{y}/**/csv_od/cpp.csv"), recursive=True)[0]
        for r in pd.read_csv(p, dtype=str, keep_default_na=False).itertuples():
            names[(str(y), r.PSTRANA)] = r.ZKRATKAP8
    return names


_LIST_ID = {}


def list_id(name):
    """Comparable identity of a candidate list: a party's full name and its abbreviation map to the same id."""
    if not _LIST_ID:
        for y in YEARS:
            cvs = pd.read_csv(glob.glob(str(RAW / f"kv{y}/**/csv_od/cvs.csv"), recursive=True)[0], dtype=str, keep_default_na=False)
            for r in cvs.itertuples():
                abbr = L.name_norm(r.ZKRATKAV8)
                for n in (r.NAZEVCELK, r.NAZEV_STRV, r.ZKRATKAV30, r.ZKRATKAV8):
                    if n:
                        _LIST_ID.setdefault(L.name_norm(n), abbr)
    n = L.name_norm(name.strip('"„“'))
    return _LIST_ID.get(n, n)


_PARTIES = {}


def list_parties(cid):
    """Parties composing the list of a candidacy id (names, not codes; independents 80/90 left out)."""
    if not _PARTIES:
        for y in YEARS:
            ros = L.read(y, "kvros")
            cvs = L.read(y, "cvs").drop_duplicates("VSTRANA").set_index("VSTRANA").ZKRATKAV8.map(L.name_norm)
            for k, s in zip(f"{y}:" + ros.KODZASTUP + ":" + ros.COBVODU + ":" + ros.POR_STR_HL, ros.SLOZENI):
                _PARTIES[k] = sorted({cvs.get(str(int(c)), "") for c in s.split(",") if c.strip().isdigit() and int(c) not in (80, 90)} - {""})
    return _PARTIES.get(cid.rsplit(":", 1)[0], [])


def list_age_stats(C):
    """{(KODZASTUP, list_no): (median age, share of lists in CZ that are older)} for 2026 lists with >= 5 candidates."""
    b = C[C.year == "2026"].assign(list_no=lambda d: d.id.str.split(":").str[3].astype(int), age=lambda d: d.VEK.astype(int))
    g = b.groupby(["KODZASTUP", "list_no"]).age.agg(["median", "size"])
    g = g[g["size"] >= 5]
    ranks = g["median"].rank(pct=True, method="average")
    return {k: (float(m), float(1 - r)) for k, m, r in zip(g.index, g["median"], ranks)}


def extra_fields():
    """id -> (votes, elected thanks to preference votes, rank by votes on the list, list size, share of list votes).

    PRESKOCENI only says the votes were enough to jump the order; it means "elected thanks to preference votes"
    only for an elected candidate placed below the number of seats the list won (MAND_STR)."""
    out = {}
    for y in YEARS:
        k = L.read(y, "kvrk")  # regular election only: repeat elections reuse the same ids
        k = k[k.PLATNOST == "A"].copy()
        ros = L.read(y, "kvros")
        mand = dict(zip(ros.KODZASTUP + ":" + ros.COBVODU + ":" + ros.POR_STR_HL, pd.to_numeric(ros.MAND_STR, errors="coerce")))
        k["v"] = pd.to_numeric(k.POCHLASU, errors="coerce")
        grp = k.KODZASTUP + ":" + k.COBVODU + ":" + k.POR_STR_HL
        k["rank"] = k.groupby(grp).v.rank(ascending=False, method="min")
        k["n"] = k.groupby(grp).v.transform("size")
        k["share"] = k.v / k.groupby(grp).v.transform("sum")
        k["pref"] = (k.PRESKOCENI == "A") & (k.MANDAT == "A") & (pd.to_numeric(k.PORCISLO, errors="coerce") > grp.map(mand).fillna(0))
        ids = f"{y}:" + grp + ":" + k.PORCISLO
        for i, v, pr, r, n, sh in zip(ids, k.POCHLASU, k.pref, k["rank"], k["n"], k["share"]):
            out[i] = (v, bool(pr), None if pd.isna(r) else int(r), int(n), None if pd.isna(sh) else round(float(sh), 4))
    return out


def profile_context(C):
    """Occupation group (text -> group, national 2026 count) and the 2026 age distribution for candidate profiles."""
    og = json.load(open(DER / "occ_groups.json", encoding="utf-8"))
    ages = sorted(C[C.year == "2026"].VEK.astype(int))
    return og, ages


def occ_norm(s):
    import re
    return re.sub(r"\s+", " ", s.lower()).strip(" ,.;-")


def reasons(e):
    """Plain-language evidence for one link."""
    r = ["stejné jméno a věk sedí"]
    r.append("stejná obec" if e.geo == "zast" else "stejné město, jiná část" if e.geo == "city" else "jiná obec")
    if e.cocand in ("1", "2+"):
        r.append("společný spolukandidát" if e.cocand == "1" else "aspoň dva stejní spolukandidáti")
    if e.same_list:
        r.append("stejná kandidátka")
    if e.party == "same":
        r.append("stejná strana")
    if e.occ in ("same", "similar"):
        r.append("stejné povolání")
    if e.titles == "same":
        r.append("stejné tituly")
    if e.same_res:
        r.append("stejné bydliště")
    if getattr(e, "list_party", "") == "shared":
        r.append("stejná strana ve složení kandidátky")
    if e.occ in ("same_field", "to_retired", "from_student"):
        r.append({"same_field": "stejný obor povolání", "to_retired": "odchod do důchodu", "from_student": "ze studia do práce"}[e.occ])
    if e.second == "jev_field":
        r.append("příbuzné povolání nebo kandidátka podle Jev")
    return r


SIZES = {"mesto": (40, 90), "vesnice": (7, 25)}


def pick_council(C, size="mesto"):
    """Council of the given ballot size with the most 2026 candidates who have a long linked history."""
    hist = C.groupby("person").year.nunique()
    c26 = C[C.year == "2026"].assign(h=lambda d: d.person.map(hist))
    s = c26.groupby("KODZASTUP").agg(n=("id", "size"), long=("h", lambda h: (h >= 4).sum()))
    s = s[s.n.between(*SIZES[size])]
    return s.long.idxmax()


def main(kod="mesto"):
    C = pd.read_csv(DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False)
    E = pd.read_csv(DER / "cluster_edges.csv.gz")
    kod = pick_council(C, kod) if kod in SIZES else kod
    pn = party_names()
    extra = extra_fields()
    age_stats = list_age_stats(C)
    og, all_ages = profile_context(C)
    ballot = C[(C.year == "2026") & (C.KODZASTUP == kod)].copy()
    ballot["list_no"] = ballot.id.str.split(":").str[3].astype(int)
    ballot["pos"] = ballot.id.str.split(":").str[4].astype(int)
    council_name = {}
    for y in YEARS:
        council_name.update(L.read(y, "kvrzcoco").set_index("KODZASTUP").NAZEVZAST.to_dict())
    town = council_name.get(kod, kod)
    # namesakes for the 2026 ballot itself (edges carry E only for the earlier side, so first-timers had none)
    b = ballot.assign(first=ballot.JMENO.str.split().str[0], age=ballot.VEK.astype(int),
                      female=[gender(x, y) == "Z" for x, y in zip(ballot.JMENO, ballot.PRIJMENI)])
    rarity = dict(zip(ballot.id, L.Namesakes()(b, 2026)))

    people = []
    for r in ballot.sort_values(["list_no", "pos"]).itertuples():
        hist = C[C.person == r.person].sort_values("year")
        ids = set(hist.id)
        links = E[(E.id_a.isin(ids) & E.id_b.isin(ids)) & E.decision.isin(["auto_match", "auto_jev", "implied"])]
        maybe = E[(E.id_a.isin(ids) ^ E.id_b.isin(ids)) & (E.decision == "manual_review")]
        maybe_rows = []
        for m in maybe.itertuples():
            other = m.id_b if m.id_a in ids else m.id_a
            o = C[C.id == other].iloc[0]
            maybe_rows.append({"year": o.year, "town": o.BYDLISTEN, "list": o.NAZEVCELK, "occ": o.POVOLANI, "age": o.VEK,
                               "elected": o.MANDAT == "A", "why": reasons(m)})
        why_by_year = {}
        for l in links.itertuples():
            why_by_year[C.loc[C.id == l.id_b, "year"].iat[0]] = reasons(l) + (["potvrdil Jev"] if l.decision == "auto_jev" else [])
        rows = []
        for y, hy in hist.groupby("year", sort=True):  # one person may run for city and city part in one election
            h = hy.sort_values("MANDAT").iloc[0]  # "A" (elected) first
            votes, skip, vrank, vn, vshare = extra.get(h.id, ("", "", None, None, None))
            rows.append({"why": why_by_year.get(y, []), "year": y, "age": h.VEK, "town": h.BYDLISTEN, "occ": h.POVOLANI,
                         "pos": int(h.id.split(":")[4]), "votes": int(votes) if votes.isdigit() and y != "2026" else None,
                         "skip": bool(skip) and y != "2026", "member": h.PSTRANA not in ("99", ""),
                         "vrank": vrank if y != "2026" else None, "vn": vn, "vshare": vshare if y != "2026" else None,
                         "list": " a ".join(dict.fromkeys(hy.NAZEVCELK)), "lid": list_id(h.NAZEVCELK), "parties": list_parties(h.id), "party": pn.get((y, h.PSTRANA), ""),
                         "elected": bool((hy.MANDAT == "A").any()), "councils": list(hy.KODZASTUP),
                         "elected_here": bool(((hy.MANDAT == "A") & (hy.KODZASTUP == kod)).any())})
        past = [x for x in rows if x["year"] != "2026"]
        e_name = rarity.get(r.id, 99)
        people.append({
            "id": r.id, "name": f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip(), "age": int(r.VEK), "occ": r.POVOLANI,
            "town": r.BYDLISTEN, "list": r.NAZEVCELK, "list_no": r.list_no, "pos": r.pos,
            "party": pn.get(("2026", r.PSTRANA), ""), "member": r.PSTRANA not in ("99", ""),
            "gender": gender(r.JMENO, r.PRIJMENI), "female": gender(r.JMENO, r.PRIJMENI) == "Z",
            "history": rows, "ran": len(past), "elected": sum(x["elected"] for x in past),
            "since": past[0]["year"] if past else None, "family": bool((hist.family == "True").any()),
            "rare": bool(e_name < 0.05), "maybe": maybe_rows[:3],
            "incumbent": any(x["elected_here"] and x["year"] == "2022" for x in rows),
            "field": og["text"].get(occ_norm(r.POVOLANI), ""),
            "age_older": round(1 - bisect.bisect_right(all_ages, int(r.VEK)) / len(all_ages), 3),
        })
    here = collections.Counter(p["field"] for p in people)
    for p in people:
        p["field_n"], p["field_here"] = og["n2026"].get(p["field"], 0), here[p["field"]]
    # councillors elected 2022 here who are not on this 2026 ballot
    elected22 = C[(C.year == "2022") & (C.KODZASTUP == kod) & (C.MANDAT == "A")]
    running = set(ballot.person)
    leaving = []
    for e in elected22.itertuples():
        now = C[(C.person == e.person) & (C.year == "2026")]
        leaving += [] if e.person in running else [{
            "name": f"{e.TITULPRED} {e.JMENO} {e.PRIJMENI}".strip(), "list": e.NAZEVCELK,
            "elsewhere": council_name.get(now.KODZASTUP.iat[0]) if len(now) else None}]
    meta = {"elected22": len(elected22), "running": int(sum(p["incumbent"] for p in people)), "leaving": leaving, "contact": "jan@klr.cz",
            "ages": {str(no): age_stats[(kod, no)] for (k, no) in age_stats if k == kod}}
    OUT.mkdir(parents=True, exist_ok=True)
    page = (ROOT / "src/obec_template.html").read_text()
    page = page.replace("__TOWN__", html.escape(town)).replace("__DATA__", json.dumps(people, ensure_ascii=False).replace("</", "<\\/")).replace("__META__", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))
    (OUT / f"{kod}.html").write_text(page)
    print(f"{town} ({kod}): {len(people)} candidates, {sum(p['ran'] > 0 for p in people)} with history -> {OUT / f'{kod}.html'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mesto")
