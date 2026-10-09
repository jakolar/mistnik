"""Build a blind, stratified labelling sample from cluster output -> data/derived/label_sample.json.

Strata cover where errors are likely plus a plain random sample of auto links (unbiased overall precision).
The page never shows the model's decision or probability; strata stay in the JSON for evaluation only.
Run: python3 src/label_sample.py [per_stratum]
"""
import json, pathlib, sys
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
from card_mockup import party_names

DER = pathlib.Path(__file__).resolve().parent.parent / "data/derived"


def main(n=40):
    E = pd.read_csv(DER / "cluster_edges.csv.gz")
    C = pd.read_csv(DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False).set_index("id")
    auto = E.decision.isin(["auto_match", "auto_jev"])
    gap = E.year_b - E.year_a
    strata = {
        "random_auto": E[auto],
        "auto_rare_name": E[auto & (E.E_a < 0.02)],
        "auto_common_name": E[auto & (E.E_a >= 1)],
        "auto_big_city": E[auto & E.big],
        "auto_family": E[auto & E.family],
        "auto_long_gap": E[auto & (gap >= 12)],
        "auto_jev": E[E.decision == "auto_jev"],
        "auto_city_part": E[auto & (E.geo == "city")],
        "manual_review": E[E.decision.str.startswith("manual_review")],
        "conflict": E[E.decision.str.startswith("conflict")],
        "possible": E[E.decision == "possible_match"],
    }
    nc = pd.read_csv(DER / "name_change_candidates.csv")
    nc = nc[nc.id_a.isin(C.index) & nc.id_b.isin(C.index)]
    strata["name_change_jev"] = nc[nc.jev >= 0.8]
    strata["name_change_rule"] = nc[nc.jev < 0.8]
    pn = party_names()
    rows, seen = [], set()
    for name, d in strata.items():
        k = 100 if name == "random_auto" else n
        for e in d.sample(min(k, len(d)), random_state=7).itertuples():
            key = f"{e.id_a}|{e.id_b}"
            if key in seen:
                continue
            seen.add(key)
            side = lambda i: {**{f: C.at[i, f] for f in ("year", "TITULPRED", "JMENO", "PRIJMENI", "TITULZA", "VEK", "POVOLANI",
                                                        "BYDLISTEN", "NAZEVCELK", "MANDAT")},
                              "party": "bez příslušnosti" if C.at[i, "PSTRANA"] == "99" else pn.get((C.at[i, "year"], C.at[i, "PSTRANA"]), "")}
            rows.append({"key": key, "stratum": name, "a": side(e.id_a), "b": side(e.id_b)})
    import random
    random.Random(7).shuffle(rows)  # strata mixed so the labeller cannot guess the model's view
    json.dump(rows, open(DER / "label_sample.json", "w"), ensure_ascii=False)
    print(f"{len(rows)} pairs:", pd.Series([r["stratum"] for r in rows]).value_counts().to_dict())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
