"""Decide and cluster scored edges (data/derived/linkage_edges.csv.gz from linkage.py) into persons.

Rules (precision first):
  auto_match      p >= 0.999, same council or city/city-part; in big cities (>= BIG_POP) and where a namesake of another
                  age runs in the same council (family) also a second signal: same titles, same residence (city part),
                  same/similar occupation, same party or list in the next term, a shared co-candidate, or Jev saying
                  same occupation field / same list (p >= 0.8)
  auto_jev        0.99 <= p < 0.999 (or missing second signal) and Jev pair referee >= 0.8 and a second signal
  manual_review   0.9 <= p, not auto; Jev pair referee < 0.5 demotes to possible_match
  merges keep at most one person-event per election and a non-empty intersection of all birth windows.
Run: OPENROUTER_API_KEY=... python3 src/cluster.py
"""
import concurrent.futures as cf, re, sys
import numpy as np
import pandas as pd

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
import linkage as L
import jev_fields as J

BIG_POP = 50_000
P_DIRECT = 0.5  # every cross pair of two merged clusters needs direct evidence at least this good
JEV_YES, JEV_NO = 0.8, 0.5
DER = L.DER


def norm_list(s):
    return re.sub(r"[\d\W_]+", " ", L.strip(s)).strip()


def surname_district(E, allc):
    """Raise expected namesakes by the surname's concentration in A's district (MV 2017), renormalise p.

    k_okres = (bearers in district / bearers in CZ) / (district population / CZ population). Only raises E (precision first);
    the earlier candidate-based local factor stays when it is higher.
    """
    mv = pd.read_csv(DER / "mv_prijmeni_okres.csv", keep_default_na=False).groupby(["surname", "nuts"])["count"].sum()
    pop = mv.loc["SOUČET"]
    nat = mv.groupby(level=0).sum()
    nuts = pd.read_csv(glob_one("kv2026", "cnumnuts"), dtype=str).set_index("NUMNUTS").NUTS.replace({"CZ010": "CZ0100"})
    a = allc.set_index("id").loc[E.id_a]
    s, n = a.PRIJMENI.str.upper().values, a.OKRES.map(nuts).values
    share = (pop / pop.sum()).to_dict()
    # prior pseudo-count spread by district population, so a surname missing in MV gets k ~ 1, not 1/share
    k_okres = np.array([(mv.get((x, y), 0) + 0.5 * share[y]) / (nat.get(x, 0) + 0.5) / share[y] if y in share else 1.0
                        for x, y in zip(s, n)])
    missing = pd.Series(n)[~pd.Series(n).isin(pop.index)].unique()
    if len(missing):
        print(f"WARNING districts without MV surname data (no adjustment there): {missing}", flush=True)
    local = E.geo.isin(L.LOCAL).values
    k_old = np.where(local, E.E_eff / E.E_a, 1.0)
    k_new = np.where(local, np.clip(np.maximum(k_old, k_okres), 1, 50), 1.0)
    E["k_okres"] = k_okres
    E["weight"] = E.weight - np.log2(k_new / k_old)
    E["w_prior"] = E.w_prior - np.log2(k_new / k_old)
    odds = 2.0 ** E.weight.clip(-60, 60)
    grp = [E.year_a, E.year_b]
    E["p_before_okres"] = E.p
    E["p"] = odds / (1 + odds.groupby(grp + [E.pe_a]).transform("sum") + odds.groupby(grp + [E.pe_b]).transform("sum") - odds)
    print(f"surname district factor: raised E on {(k_new > k_old).sum()} local edges; "
          f"p>=0.999 before {(E.p_before_okres >= 0.999).sum()}, after {(E.p >= 0.999).sum()}", flush=True)
    return E


def post_fix(E, allc):
    """Correct edges scored by an older linkage.py: reused party codes, person-events merging two namesakes."""
    C = allc.set_index("id")
    if "party_name" not in E:
        pa, pb = C.loc[E.id_a].party_name.values, C.loc[E.id_b].party_name.values
        bad = (E.party == "same").values & (pa != pb)
        E.loc[bad, "weight"] -= E.loc[bad, "w_party"]
        E.loc[bad, ["party", "w_party"]] = ["diff_name", 0.0]
        print(f"party code reused for another party: neutralised {bad.sum()} edges", flush=True)
    split = set(allc.pe[allc.pe.str.count(r"\|") > 4].str.rsplit("|", n=1).str[0])  # year|first|surname|city|age|id
    E["namesake_pe"] = E.pe_a.isin(split) | E.pe_b.isin(split)
    print(f"edges touching a person-event that merged two namesakes: {E.namesake_pe.sum()}", flush=True)
    return E


def glob_one(year_dir, name):
    return __import__("glob").glob(str(L.RAW / f"{year_dir}/**/csv_od/{name}.csv"), recursive=True)[0]


class SafeClusters(L.Clusters):
    """Clusters that merge only when every member of one is directly compatible with every member of the other.

    A~B and B~C must not imply A=C: the direct A-C edge (all same-name, birth-compatible pairs across elections are
    scored) has to exist and reach P_DIRECT, otherwise the merge is refused as a transitive conflict.
    """

    def __init__(self, nodes, pmap):
        super().__init__(nodes)
        self.members = {n: [n] for n in nodes.index}
        self.pmap = pmap

    def direct_ok(self, a, b):
        for x in self.members[self.find(a)]:
            for y in self.members[self.find(b)]:
                k = (x, y) if x < y else (y, x)  # person-event ids start with the election year
                if self.pmap.get(k, 0.0) < P_DIRECT:
                    return False
        return True

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        super().union(a, b)
        self.members[ra] += self.members.pop(rb)


def jev_many(kind, pairs):
    with cf.ThreadPoolExecutor(8) as ex:
        return list(ex.map(lambda ab: J.ask(kind, *ab), pairs))


def main():
    allc = pd.concat([L.load(y) for y in L.DATES], ignore_index=True)
    E = pd.read_csv(DER / "linkage_edges.csv.gz")
    E = post_fix(E, allc)
    E = surname_district(E, allc)
    pmap = dict(zip(zip(E.pe_a, E.pe_b), E.p))  # all direct edges, for the transitivity check
    E = E[E.p >= 0.5].copy()  # below that nothing can become a link

    # big city: population of the whole city (city parts point to it)
    pop = allc.drop_duplicates("KODZASTUP").set_index("KODZASTUP").POCOBYV.replace("", "0").astype(int)
    allc["big"] = allc.city.map(pop).fillna(0) >= BIG_POP
    # family: same name in the same council with a non-overlapping birth window, in any election
    allc["family"] = False
    for _, g in allc[allc.duplicated(["KODZASTUP", "key"], keep=False)].groupby(["KODZASTUP", "key"]):
        lo, hi = g.blo.values, g.bhi.values
        clash = (np.maximum.outer(lo, lo) > np.minimum.outer(hi, hi)).any(axis=1)
        allc.loc[g.index[clash], "family"] = True
    main_town = allc.groupby("city").BYDLISTEN.agg(lambda s: s.mode().iat[0])

    C = allc.set_index("id")
    a, b = C.loc[E.id_a], C.loc[E.id_b]
    E["big"] = a.big.values | b.big.values
    E["family"] = a.family.values | b.family.values
    E["same_list"] = [norm_list(x) == norm_list(y) and x != "" for x, y in zip(a.NAZEVCELK, b.NAZEVCELK)]
    ra_, rb_ = a.BYDLISTEN.map(L.name_norm).values, b.BYDLISTEN.map(L.name_norm).values  # "Brandýs n. L." ⊂ "Brandýs n. L.-Stará Boleslav"
    E["same_res"] = (np.array([x != "" and y != "" and (x.startswith(y) or y.startswith(x)) for x, y in zip(ra_, rb_)])
                     & (a.BYDLISTEN.values != a.city.map(main_town).values))
    cheap = ((E.titles == "same") | E.occ.isin(["same", "similar", "same_field"]) | (E.party == "same") | E.cocand.isin(["1", "2+"])
             | (E.list_party == "shared")
             | E.same_list | E.same_res)
    E["second"] = np.where(cheap, "rules", "")

    local = E.geo.isin(L.LOCAL)
    need = local & (E.p >= 0.99) & (E.big | E.family) & ~cheap
    if need.any():
        n = need.sum()
        print(f"Jev field checks for {n} edges without a cheap second signal", flush=True)
        oa, ob = a.POVOLANI.values[need.values], b.POVOLANI.values[need.values]
        la, lb = a.NAZEVCELK.values[need.values], b.NAZEVCELK.values[need.values]
        po = jev_many("occ", [(x, y) for x, y in zip(oa, ob)])
        pl = jev_many("list", [(x, y) for x, y in zip(la, lb)])
        hit = [(x or 0) >= JEV_YES or (y or 0) >= JEV_YES for x, y in zip(po, pl)]
        E.loc[need, "second"] = np.where(hit, "jev_field", "")

    prof = lambda r: (f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip() + f"; election {r.year}; residence: {r.BYDLISTEN}; "
                      f"occupation: {r.POVOLANI}; list: {r.NAZEVCELK}; elected: {'yes' if r.MANDAT == 'A' else 'no'}")
    # ponytail: 'elected' kept only to reuse the cached Jev answers for the 2026-10-09 launch; drop it with pair@v2 later
    gate_ok = ~(E.big | E.family) | (E.second != "")
    auto = local & (E.p >= 0.999) & gate_ok & ~E.namesake_pe
    uncertain = (E.p >= 0.9) & ~auto
    print(f"Jev pair referee for {uncertain.sum()} uncertain edges", flush=True)
    ra, rb = a[uncertain.values], b[uncertain.values]
    E.loc[uncertain, "jev_pair"] = jev_many("pair", [(prof(x), prof(y)) for x, y in zip(ra.itertuples(), rb.itertuples())])

    # Jev "no" no longer demotes: the pair referee sees the same evidence as the model (not independent) and its
    # production scores cluster around 0.4-0.75; it only orders the manual queue (Jev review 2026-10-09).
    E["proposal"] = np.select(
        [auto,
         uncertain & local & (E.p >= 0.99) & (E.second != "") & (E.jev_pair >= JEV_YES),
         uncertain],
        ["auto_match", "auto_jev", "manual_review"], "possible_match")

    # cluster: auto first by p, then auto_jev
    nodes = allc.drop_duplicates("pe").set_index("pe")[["year", "blo", "bhi"]]
    cl = SafeClusters(nodes, pmap)
    E["rank"] = E.proposal.map({"auto_match": 0, "auto_jev": 1}).fillna(2)
    E = E.sort_values(["rank", "p"], ascending=[True, False])
    out = []
    for pa, pb, prop, ns in zip(E.pe_a, E.pe_b, E.proposal, E.namesake_pe):
        if ns:  # old person-event that merged two namesakes: never clustered automatically
            out.append("manual_review_namesake" if prop != "possible_match" else "possible_match")
            continue
        why = cl.why_not(pa, pb)
        if why == "same":
            out.append("implied")
        elif prop in ("auto_match", "auto_jev"):
            if why:
                out.append(f"conflict_{why}")
            elif not cl.direct_ok(pa, pb):
                out.append("conflict_transitive")
            else:
                cl.union(pa, pb)
                out.append(prop)
        else:
            out.append(prop if not why else f"conflict_{why}" if prop == "manual_review" else "no_match")
    E["decision"] = out
    root = {n: cl.find(n) for n in nodes.index}
    E.loc[E.decision.isin(["manual_review", "possible_match"]) & (E.pe_a.map(root) == E.pe_b.map(root)) & ~E.namesake_pe, "decision"] = "implied"
    allc["person"] = allc.pe.map(root)

    E.drop(columns="rank").to_csv(DER / "cluster_edges.csv.gz", index=False, compression="gzip")
    allc[["id", "person", "year", "JMENO", "PRIJMENI", "TITULPRED", "TITULZA", "VEK", "POVOLANI", "BYDLISTEN", "NAZEVCELK",
          "PSTRANA", "MANDAT", "KODZASTUP", "city", "big", "family"]].to_csv(DER / "cluster_persons.csv.gz", index=False, compression="gzip")

    sizes = allc.groupby("person").year.nunique()
    print("decisions:", E.decision.value_counts().to_dict())
    print("gate: big/family edges with p>=0.999 local:", int((local & (E.p >= 0.999) & (E.big | E.family)).sum()),
          " second signal by:", E[local & (E.p >= 0.999) & (E.big | E.family)].second.replace("", "none").value_counts().to_dict())
    print("jev pair on uncertain:", E.jev_pair.describe().round(3).to_dict() if "jev_pair" in E else {})
    print(f"candidacies {len(allc)}, persons {allc.person.nunique()}; by number of elections {sizes.value_counts().sort_index().to_dict()}")
    print(f"jev spend total {J.con.execute('SELECT SUM(cost) FROM jev').fetchone()[0]:.4f} USD")


if __name__ == "__main__":
    main()
