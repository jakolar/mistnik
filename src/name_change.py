"""Measure: how many women can be linked across a surname change, and how often the same pattern is pure coincidence.

Pattern (consecutive elections A -> B, same council): same first name, compatible birth window, different surname,
the A surname does not run again in B (same first name, compatible age) and the B surname did not run in A.
Control: the same pattern for men, who almost never change surname, estimates coincidences of two different people.
Run: python3 src/name_change.py
"""
import collections, pathlib, sys
import numpy as np
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import linkage as L
from gender import gender
import jev_fields as J
import concurrent.futures as cf

COLS = ["KODZASTUP", "COBVODU", "POR_STR_HL", "PORCISLO", "JMENO", "PRIJMENI", "VEK", "POVOLANI", "TITULPRED", "TITULZA", "PLATNOST"]


def light(year):
    k = L.read(year, "kvrk")[COLS]
    k = k[(k.VEK != "") & (k.PLATNOST == "A")].copy()
    k["id"] = f"{year}:" + k.KODZASTUP + ":" + k.COBVODU + ":" + k.POR_STR_HL + ":" + k.PORCISLO
    k["first"] = k.JMENO.str.split().str[0].map(L.name_norm)
    k["sur"] = k.PRIJMENI.map(L.name_norm)
    k["g"] = [gender(a, b) for a, b in zip(k.JMENO, k.PRIJMENI)]
    w = [L.birth_window(L.edate(year), int(a)) for a in k.VEK]
    k["blo"] = np.array([x[0] for x in w], dtype="datetime64[D]")
    k["bhi"] = np.array([x[1] for x in w], dtype="datetime64[D]")
    lst = k.KODZASTUP + "|" + k.COBVODU + "|" + k.POR_STR_HL
    mates = k.groupby(lst).apply(lambda d: frozenset(d["first"] + "|" + d["sur"]))
    k["mates"] = [mates[l] for l in lst]
    k["list"] = k.KODZASTUP + "|" + lst.map(lambda x: x)  # list identity within the council
    k["occ"] = k.POVOLANI.map(L.occ_stems)
    k["tit"] = [L.titles(a, b) for a, b in zip(k.TITULPRED, k.TITULZA)]
    return k.reset_index(drop=True)


def pairs(A, B):
    P = A.merge(B, on=["KODZASTUP", "first"], suffixes=("_a", "_b"))
    P = P[(P.sur_a != P.sur_b) & (P.g_a == P.g_b) & P.g_a.notna()]
    P = P[np.minimum(P.bhi_a, P.bhi_b) >= np.maximum(P.blo_a, P.blo_b)]
    # old name must not run again, new name must not have run before (same council, compatible age)
    keyB = set(zip(B.KODZASTUP, B["first"], B.sur, B.VEK.astype(int)))
    keyA = set(zip(A.KODZASTUP, A["first"], A.sur, A.VEK.astype(int)))
    gap = 4
    reran = [any((z, f, s, int(v) + d) in keyB for d in (gap - 1, gap, gap + 1)) for z, f, s, v in zip(P.KODZASTUP, P["first"], P.sur_a, P.VEK_a)]
    before = [any((z, f, s, int(v) - d) in keyA for d in (gap - 1, gap, gap + 1)) for z, f, s, v in zip(P.KODZASTUP, P["first"], P.sur_b, P.VEK_b)]
    P = P[~np.array(reran) & ~np.array(before)].copy()
    P["shared"] = [len({m.split("|", 1)[0] + "|" + m.split("|", 1)[1] for m in a} & b) for a, b in zip(P.mates_a, P.mates_b)]
    P["occ_same"] = [bool(a) and a == b for a, b in zip(P.occ_a, P.occ_b)]
    P["tit_same"] = [bool(a) and a == b for a, b in zip(P.tit_a, P.tit_b)]
    na = P.groupby(["KODZASTUP", "first", "sur_a", "VEK_a"]).sur_b.transform("size")
    nb = P.groupby(["KODZASTUP", "first", "sur_b", "VEK_b"]).sur_a.transform("size")
    P["n_b_per_a"] = np.maximum(na, nb)  # unique only if one-to-one in both directions
    ta, tb = P.sur_a.str.split().map(set), P.sur_b.str.split().map(set)
    P["subset"] = [bool(a) and bool(b) and (a < b or b < a) for a, b in zip(ta, tb)]  # Dvořáková -> Černá Dvořáková
    return P


def prof(r, s):
    return (f"{r['TITULPRED_' + s]} {r['JMENO_' + s]} {r['PRIJMENI_' + s]} {r['TITULZA_' + s]}".strip()
            + f"; election {r['year_' + s]}; occupation: {r['POVOLANI_' + s]}; co-candidates on the list: {r['mates_txt_' + s]}")


def referee(C):
    """Jev on candidate pairs: same woman under two surnames? Men run as a control (any 'same' there is an error)."""
    instr = ("Two candidacies in one Czech municipality in consecutive elections. Same first name and compatible age, different "
             "surname. Is B the same person as A after a surname change (marriage or divorce), or a different person with the "
             "same first name? Use co-candidates, occupation and titles.")
    crit = {"true": "the same person after a surname change", "false": "two different people"}
    J.QUESTIONS["namechange"] = ("Two candidacies, possibly the same person under two surnames.", instr, crit)
    with cf.ThreadPoolExecutor(8) as ex:
        return list(ex.map(lambda r: J.ask("namechange", prof(r, "a"), prof(r, "b")), C.to_dict("records")))


def main():
    years = list(L.DATES)
    cands = []
    tot = collections.defaultdict(collections.Counter)
    base = collections.Counter()
    for ya, yb in zip(years, years[1:]):
        A, B = light(ya), light(yb)
        base["Z"] += (A.g == "Z").sum()
        base["M"] += (A.g == "M").sum()
        P = pairs(A, B)
        P["year_a"], P["year_b"] = ya, yb
        rule = (((P.shared >= 2) & (P.occ_same | P.tit_same)) | P.subset) & (P.n_b_per_a == 1)
        cands.append(P[rule])
        for g, d in P.groupby("g_a"):
            c = tot[g]
            c["pairs"] += len(d)
            c["unique_a"] += (d.n_b_per_a == 1).sum()
            c["shared2"] += (d.shared >= 2).sum()
            c["shared2_unique"] += ((d.shared >= 2) & (d.n_b_per_a == 1)).sum()
            c["shared2_occ_or_tit"] += ((d.shared >= 2) & (d.occ_same | d.tit_same)).sum()
            c["subset_surname"] += (d.subset & (d.n_b_per_a == 1)).sum()
            c["subset_and_shared1"] += (d.subset & (d.n_b_per_a == 1) & (d.shared >= 1)).sum()
        print(f"{ya}->{yb}: women {int((P.g_a == 'Z').sum())}, men {int((P.g_a == 'M').sum())}", flush=True)
    print("\nper 10 000 candidates of that gender in the earlier election:")
    for k in ["pairs", "unique_a", "shared2", "shared2_unique", "shared2_occ_or_tit", "subset_surname", "subset_and_shared1"]:
        z, m = tot["Z"][k], tot["M"][k]
        rz, rm = 1e4 * z / base["Z"], 1e4 * m / base["M"]
        est = max(0.0, 1 - rm / rz) if rz else 0
        print(f"  {k:20} women {z:6d} ({rz:6.1f})  men {m:6d} ({rm:6.1f})  -> share of women's matches beyond coincidence ~ {est:.0%}")

    C = pd.concat(cands, ignore_index=True)
    for s in ("a", "b"):
        C["mates_txt_" + s] = [", ".join(sorted(x.replace("|", " ") for x in m)[:12]) for m in C["mates_" + s]]
    W, M = C[C.g_a == "Z"], C[C.g_a == "M"].sample(min(500, (C.g_a == "M").sum()), random_state=3)
    W = W.assign(jev=referee(W))
    M = M.assign(jev=referee(M))
    n_w, n_m = len(C[C.g_a == "Z"]), (C.g_a == "M").sum()
    rate_m = n_m / base["M"]
    print(f"\nrule (2+ shared co-candidates, same occupation or titles, unique): women {n_w}, men {n_m}")
    for t_ in (0.5, 0.8, 0.9):
        yw, ym = (W.jev >= t_).mean(), (M.jev >= t_).mean()
        fp_w = rate_m * base["Z"] * ym  # expected coincidences among women that Jev would still accept
        acc_w = yw * n_w
        print(f"  Jev >= {t_}: accepts women {yw:.0%} ({acc_w:.0f}), men {ym:.0%}  -> est. precision on women {max(0, 1 - fp_w / max(acc_w, 1)):.1%}")
    keep = ["id_a", "id_b", "subset", "year_a", "year_b", "KODZASTUP", "JMENO_a", "PRIJMENI_a", "VEK_a", "PRIJMENI_b", "VEK_b", "POVOLANI_a", "POVOLANI_b",
            "shared", "occ_same", "tit_same", "jev"]
    W[keep].to_csv(L.DER / "name_change_candidates.csv", index=False)
    print(f"jev spend total {J.con.execute('SELECT SUM(cost) FROM jev').fetchone()[0]:.3f} USD")


if __name__ == "__main__":
    main()
