"""Jev pair referee v3: richer context for the manual_review queue.

v1 saw two bare profiles and answered ~0.6 on almost everything. v3 adds what the model can weigh but a person
would look up: shared co-candidates by name, list position, party membership, how common the name is among all
candidates nationwide and in the municipality, years apart. Election results are left out (not identity evidence).
Ages stay hidden: production pairs all have compatible birth windows, the eval negatives are age-proven namesakes.

Run: python3 src/jev_pair3.py eval [n]   -> v1 vs v3 on seed matches vs father/son-type namesakes
     python3 src/jev_pair3.py run       -> data/derived/jev_pair3.csv for every manual_review edge
"""
import sys, pathlib
import concurrent.futures as cf
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import linkage as L
import jev_fields as J

DER = J.DER
J.QUESTIONS["pair3"] = (
    "Two candidacies in Czech municipal elections in different years. Both have the same first name and surname and "
    "birth years that are compatible (ages are not shown). Context about the name and the lists is given below.",
    "Did the same person run both times? Evidence for the same person: shared co-candidates, the same list or its "
    "continuation under a new name, the same residence or city part, an occupation that fits one career (including "
    "promotion, a new job or retirement over the years), titles that match or were added later, a name that is rare "
    "among candidates. Evidence for two people: a common name with many candidacies in the area, different residences "
    "within a large city, unrelated occupations with no plausible career path, titles that disappeared, different "
    "lists with no shared co-candidates. Relatives (parent and child) often share a name in the same small municipality.",
    {"true": "the same person ran both times", "false": "two different people with the same name"})
QKIND = "pair3@v3"  # cache kind; QUESTIONS lookup uses the part before '@' -> "pair3"


def load_all():
    allc = pd.concat([L.load(y) for y in L.DATES], ignore_index=True)
    allc["listkey"] = allc.year.astype(str) + "|" + allc.KODZASTUP + "|" + allc.POR_STR_HL
    allc["list_n"] = allc.groupby("listkey").id.transform("size")
    return allc.set_index("id", drop=False)


def context(a, b, nat, nat_m, loc):
    def side(r):
        t = f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".split()
        party = "" if r.party_name in ("bezpp", "") else f"; party member: {r.party_name}"
        return (f"{' '.join(t)}; election {r.year}; municipality code {r.city}; residence: {r.BYDLISTEN}; "
                f"occupation: {r.POVOLANI or 'not given'}; list: {r.NAZEVCELK} (position {r.PORCISLO} of {r.list_n}){party}")
    shared = sorted(a.cocand & b.cocand)
    co = f"{len(shared)} ({', '.join(s.replace('|', ' ').title() for s in shared[:8])})" if shared else "none"
    k = a.key
    return side(a), (f"{side(b)}\n"
            f"Years apart: {abs(int(b.year) - int(a.year))}. Co-candidates appearing with both A and B: {co}.\n"
            f"This exact name appears in {nat.get(k, 0)} candidacies nationwide 2002-2026 in {nat_m.get(k, 0)} municipalities, "
            f"{loc.get((k, a.city), 0)} of them in A's municipality.")


def ask3(pairs):
    with cf.ThreadPoolExecutor(8) as ex:
        return list(ex.map(lambda ab: J.ask(QKIND, *ab), pairs))


def stats(allc):
    nat = allc.groupby("key").size().to_dict()
    nat_m = allc.groupby("key").city.nunique().to_dict()
    loc = allc.groupby(["key", "city"]).size().to_dict()
    return nat, nat_m, loc


def ev(allc, n):
    E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=["id_a", "id_b", "E_a", "decision", "geo", "big", "family"])
    rng = np.random.default_rng(0)
    # positives: auto links in the hard settings (big city / same-name family), the seed the referee must not reject
    pos = E[(E.decision == "implied") & E.geo.isin(L.LOCAL) & (E.big.astype(str).eq("True") | E.family.astype(str).eq("True"))]
    pos = pos.sample(n, random_state=1)[["id_a", "id_b"]].values.tolist()
    # negatives: same name, same municipality, birth windows disjoint by 5+ years -> provably different people
    s = allc[allc.duplicated(["city", "key"], keep=False)][["id", "city", "key", "year", "blo"]]
    m = s.merge(s, on=["city", "key"], suffixes=("_a", "_b"))
    m = m[(m.year_a < m.year_b) & ((m.blo_a - m.blo_b).abs().dt.days > 5 * 365)]
    neg = m.sample(n, random_state=2)[["id_a", "id_b"]].values.tolist()
    nat, nat_m, loc = stats(allc)
    v1 = lambda r: (f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip() + f"; election {r.year}; residence: {r.BYDLISTEN}; "
                    f"occupation: {r.POVOLANI}; list: {r.NAZEVCELK}")
    for name, pairs in (("same (auto, hard settings)", pos), ("different (age-proven namesakes)", neg)):
        A = [(allc.loc[a], allc.loc[b]) for a, b in pairs]
        with cf.ThreadPoolExecutor(8) as ex:
            p1 = np.array([x for x in ex.map(lambda ab: J.ask("pair@v2", v1(ab[0]), v1(ab[1])), A) if x is not None])
        p3 = np.array([x for x in ask3([context(a, b, nat, nat_m, loc) for a, b in A]) if x is not None])
        print(f"{name}: n={len(p3)}")
        for t in (0.5, 0.8, 0.9):
            print(f"  p>={t}:  v1 {(p1 >= t).mean():.2f}   v3 {(p3 >= t).mean():.2f}")
        print(f"  median v1 {np.median(p1):.2f}  v3 {np.median(p3):.2f}")


def run(allc):
    E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=["id_a", "id_b", "decision"])
    E = E[E.decision.str.startswith("manual_review")]
    nat, nat_m, loc = stats(allc)
    texts = [context(allc.loc[a], allc.loc[b], nat, nat_m, loc) for a, b in zip(E.id_a, E.id_b)]
    print(f"asking Jev v3 for {len(texts)} edges", flush=True)
    E["jev3"] = ask3(texts)
    E.to_csv(DER / "jev_pair3.csv", index=False)
    print(E.jev3.describe().round(3).to_dict())
    for t in (0.5, 0.8, 0.9):
        print(f"  p>={t}: {(E.jev3 >= t).sum()}")


def cached(allc):
    """Answers already in the cache (partial run), no API calls -> data/derived/jev_pair3.csv"""
    E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=["id_a", "id_b", "decision"])
    E = E[E.decision.str.startswith("manual_review")]
    nat, nat_m, loc = stats(allc)
    def look(a, b):
        r = J.con.execute("SELECT p FROM jev WHERE kind=? AND a=? AND b=?", (QKIND, a, b)).fetchone()
        return r[0] if r else None
    E["jev3"] = [look(*context(allc.loc[a], allc.loc[b], nat, nat_m, loc)) for a, b in zip(E.id_a, E.id_b)]
    E.to_csv(DER / "jev_pair3.csv", index=False)
    print("answered", E.jev3.notna().sum(), "of", len(E), {t: int((E.jev3 >= t).sum()) for t in (0.8, 0.9)})


if __name__ == "__main__":
    allc = load_all()
    if sys.argv[1] == "cached":
        cached(allc)
    elif sys.argv[1] == "eval":
        ev(allc, int(sys.argv[2]) if len(sys.argv) > 2 else 150)
    else:
        run(allc)
