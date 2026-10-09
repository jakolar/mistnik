"""Compare our person linkage with programydovoleb.cz (PDV) town histories, pair by pair.

Within each sampled council: every pair of candidacies from different regular elections is 'same person' or not,
once by PDV (their person groups) and once by us (cluster_persons). Disagreements go to a CSV for adjudication.
PDV is an independent linkage, not ground truth: both can be wrong.
Run: python3 src/pdv_compare.py
"""
import collections, itertools, json, pathlib, sys
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import linkage as L

PDV = L.ROOT / "data/raw/pdv"


def main():
    ours = pd.read_csv(L.DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False).set_index("id")
    person = ours.person.to_dict()
    cnt, rows, towns = collections.Counter(), [], 0
    for f in sorted(PDV.glob("*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("code") != 200:
            continue
        year = {v["id"]: int(v["datum"][:4]) for v in d["cis"]["volby"] if v.get("typ") == "KV" and v.get("radne") == 1
                and v.get("datum", "")[:4].isdigit() and int(v["datum"][:4]) in L.DATES and v["datum"].replace("-", "") == L.DATES[int(v["datum"][:4])]}
        cand = {c["id"]: c for c in d["kandidati"]}
        pid = {}
        for i, group in enumerate(d["list"]):
            for x in group:
                c = cand.get(x["id"])
                if c and c["volby"] in year:
                    our_id = f"{year[c['volby']]}:{c['KODZASTUP']}:{c['COBVODU']}:{c['POR_STR_HL']}:{c['PORCISLO']}"
                    if our_id in person:
                        pid[our_id] = i
                    else:
                        cnt["pdv_not_in_ours"] += 1
        towns += 1
        for a, b in itertools.combinations(sorted(pid), 2):
            if a[:4] == b[:4]:
                continue
            p, o = pid[a] == pid[b], person[a] == person[b]
            cnt[("both" if p and o else "pdv_only" if p else "ours_only" if o else "neither")] += 1
            if p != o:
                ra, rb = ours.loc[a], ours.loc[b]
                rows.append({"who": "pdv_only" if p else "ours_only", "id_a": a, "id_b": b,
                             "a": f"{ra.JMENO} {ra.PRIJMENI}, {ra.VEK}, {ra.POVOLANI}, {ra.NAZEVCELK}",
                             "b": f"{rb.JMENO} {rb.PRIJMENI}, {rb.VEK}, {rb.POVOLANI}, {rb.NAZEVCELK}"})
    both, po, oo = cnt["both"], cnt["pdv_only"], cnt["ours_only"]
    print(f"towns {towns}; linked pairs: both {both}, only PDV {po}, only ours {oo}; PDV candidacies not in our data {cnt['pdv_not_in_ours']}")
    print(f"agreement on our links: {both / max(both + oo, 1):.2%}; share of PDV links we also make: {both / max(both + po, 1):.2%}")
    pd.DataFrame(rows).to_csv(L.DER / "pdv_disagreements.csv", index=False)
    print(f"{len(rows)} disagreements -> {L.DER / 'pdv_disagreements.csv'}")


if __name__ == "__main__":
    main()
