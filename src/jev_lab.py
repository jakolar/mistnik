"""Jev prompt lab: which question design separates same-person pairs from namesakes on *hard* cases?

Labelled backtest (ages hidden everywhere, so age cannot decide):
  pos_hard  uncertain edges (manual_review) that iROZHLAS independently links (sampled councils, 2002-2022)
  pos_easy  published links in big cities / families
  neg       same name, same council, birth windows 5+ years apart -> provably different people
Variants (all cached in jev.db by kind):
  v3     the production text prompt (composite question, numbers in text)
  json   same facts as a JSON state with named fields, rarity as words, one composite noul
  multi  JSON state, several one-judgment nouls (career, list continuity, co-candidates, residence, same person)
  choice JSON state, one choice: same person / relative / unrelated namesake / cannot tell
Run: OPENROUTER_API_KEY=... python3 src/jev_lab.py [n_per_group]
"""
import json, sys, pathlib
import concurrent.futures as cf
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import jev_fields as J
import jev_pair3 as P3

DER = J.DER
IROZ = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None


def rarity(n):
    return "very rare" if n <= 2 else "rare" if n <= 6 else "fairly common" if n <= 30 else "very common"


def state(a, b, nat, loc):
    side = lambda r: {"name": f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip(), "election_year": int(r.year),
                      "residence": r.BYDLISTEN, "occupation": r.POVOLANI or "not given", "list": r.NAZEVCELK,
                      "party_member": "" if r.party_name in ("bezpp", "") else r.party_name}
    shared = sorted(a.cocand & b.cocand)
    return {"candidacy_A": side(a), "candidacy_B": side(b), "years_apart": abs(int(b.year) - int(a.year)),
            "shared_co_candidates": [s.replace("|", " ").title() for s in shared[:8]] or "none",
            "name_frequency_among_candidates": rarity(J_nat(nat, a.key)),
            "same_name_candidacies_in_this_municipality": rarity(loc.get((a.key, a.city), 0))}


J_nat = lambda nat, k: nat.get(k, 0)

Q_SAME = {"type": "noul",
          "instructions": "Are `candidacy_A` and `candidacy_B` the same person running in two municipal elections? Ages are hidden but compatible. "
                          "Relatives (parent and child) in one municipality often share the exact name.",
          "criteria": {"true": "the same person", "false": "two different people with the same name"}}
MULTI = {
    "same": Q_SAME,
    "career": {"type": "noul", "instructions": "Could the `occupation` of `candidacy_A` and the `occupation` of `candidacy_B` belong to one person's working life "
               "over `years_apart` years (same job, same field, promotion, retirement, student who started working)?",
               "criteria": {"true": "plausibly one career", "false": "unrelated lines of work, or one is clearly a different generation"}},
    "list": {"type": "noul", "instructions": "Is the `list` of `candidacy_B` the same local group or party as the `list` of `candidacy_A`, possibly renamed?",
             "criteria": {"true": "same group or party", "false": "a different group"}},
    "residence": {"type": "noul", "instructions": "Do `candidacy_A` and `candidacy_B` give the same `residence` (same village or same part of the town)?",
                  "criteria": {"true": "same place", "false": "different places"}},
    "cocand": {"type": "noul", "instructions": "Does `shared_co_candidates` list at least one person?",
               "criteria": {"true": "at least one shared co-candidate", "false": "none"}},
}
Q_CHOICE = {"type": "choice",
            "instructions": "Who are `candidacy_A` and `candidacy_B`? Ages are hidden but compatible.",
            "criteria": {"same": "the same person in both elections", "relative": "two relatives with the same name, e.g. parent and child",
                         "namesake": "two unrelated people who share a name", "other": "cannot tell from the information given"}}


R2 = {
    "generation": {"type": "noul", "instructions": "Do `candidacy_A` and `candidacy_B` look like people of different generations, for example a parent "
                   "and a grown-up child (one a student or young worker, the other senior, retired or in a long career; different titles levels)?",
                   "criteria": {"true": "different generations", "false": "nothing suggests different generations"}},
    "evidence": {"type": "score", "instructions": "How strong is the evidence that `candidacy_A` and `candidacy_B` are the same person? Ages are hidden but compatible.",
                 "criteria": ["contradicting evidence: looks like two different people",
                              "no evidence either way beyond the shared name",
                              "weak evidence: one loose match (same place or similar field)",
                              "good evidence: a specific match such as the same list or a plausible career",
                              "strong evidence: several specific matches, e.g. shared co-candidates and the same list and career"]},
    "skeptic": {"type": "noul", "instructions": "Is there specific evidence that `candidacy_A` and `candidacy_B` are the same person: a shared co-candidate, "
                "the same or renamed list, or an occupation that continues one career? A shared name and place alone is not enough.",
                "criteria": {"true": "at least one specific piece of evidence for the same person", "false": "only the name and place match, or the details contradict"}},
}


def ask_raw(kind, st, questions):
    """One request, several questions; cached per (kind, state) in jev.db as JSON of answers."""
    key = json.dumps(st, ensure_ascii=False, sort_keys=True)
    with J.lock:
        h = J.con.execute("SELECT p FROM jev WHERE kind=? AND a=? AND b=''", (kind, key)).fetchone()
    if h:
        return json.loads(h[0]) if isinstance(h[0], str) else h[0]
    with J.lock:
        if J.con.execute("SELECT COALESCE(SUM(cost), 0) FROM jev").fetchone()[0] >= J.CAP_USD:
            raise SystemExit(f"Jev spend cap {J.CAP_USD} USD")
    import urllib.request, os
    body = json.dumps({"model": J.MODEL, "state": st, "questions": questions}).encode()
    req = urllib.request.Request(J.API, data=body, headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json"})
    for t in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=30)); break
        except Exception:
            if t == 2: return None
            import time; time.sleep(5 * (t + 1))
    ans = {k: (v.get("noul") if v["type"] == "noul" else v.get("score") if v["type"] == "score" else v.get("probabilities")) for k, v in d["answers"].items()}
    with J.lock:
        J.con.execute("INSERT OR IGNORE INTO jev VALUES (?, ?, '', ?, ?, ?)", (kind, key, json.dumps(ans), d.get("usage", {}).get("cost") or 0, d.get("model")))
        J.con.commit()
    return ans


def sample(allc, n):
    E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=["id_a", "id_b", "decision", "geo", "big", "family"])
    rng = np.random.default_rng(3)
    pos_hard = pd.read_csv(DER / "lab_pos_hard.csv").sample(frac=1, random_state=1).head(n)[["id_a", "id_b"]].values.tolist()
    easy = E[(E.decision == "implied") & E.geo.isin(["zast", "city"]) & (E.big.astype(str).eq("True") | E.family.astype(str).eq("True"))]
    pos_easy = easy.sample(n, random_state=1)[["id_a", "id_b"]].values.tolist()
    s = allc[allc.duplicated(["city", "key"], keep=False)][["id", "city", "key", "year", "blo"]]
    m = s.merge(s, on=["city", "key"], suffixes=("_a", "_b"))
    m = m[(m.year_a < m.year_b) & ((m.blo_a - m.blo_b).abs().dt.days > 5 * 365)]
    neg = m.sample(n, random_state=2)[["id_a", "id_b"]].values.tolist()
    # unrelated namesakes: same name, different council in the same district, birth years 5+ apart (the big-city / cross-town case)
    s2 = allc[["id", "city", "key", "year", "blo", "OKRES"]]
    s2 = s2[s2.key.isin(s2.key.sample(200000, random_state=4))]
    m2 = s2.merge(s2, on=["key", "OKRES"], suffixes=("_a", "_b"))
    m2 = m2[(m2.city_a != m2.city_b) & (m2.year_a < m2.year_b) & ((m2.blo_a - m2.blo_b).abs().dt.days > 5 * 365)]
    neg_far = m2.sample(n, random_state=5)[["id_a", "id_b"]].values.tolist()
    return {"pos_hard": pos_hard, "pos_easy": pos_easy, "neg": neg, "neg_far": neg_far}


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    return float(((pos[:, None] > neg[None, :]).mean() + .5 * (pos[:, None] == neg[None, :]).mean()))


def main(n):
    allc = P3.load_all()
    nat, nat_m, loc = P3.stats(allc)
    groups = sample(allc, n)
    res = {}
    for g, pairs in groups.items():
        A = [(allc.loc[a], allc.loc[b]) for a, b in pairs]
        with cf.ThreadPoolExecutor(8) as ex:
            v3 = list(ex.map(lambda ab: J.ask(P3.QKIND, *P3.context(ab[0], ab[1], nat, nat_m, loc)), A))
            js = list(ex.map(lambda ab: ask_raw("lab_json@v1", state(ab[0], ab[1], nat, loc), {"same": Q_SAME}), A))
            mu = list(ex.map(lambda ab: ask_raw("lab_multi@v1", state(ab[0], ab[1], nat, loc), MULTI), A))
            ch = list(ex.map(lambda ab: ask_raw("lab_choice@v1", state(ab[0], ab[1], nat, loc), {"who": Q_CHOICE}), A))
            r2 = list(ex.map(lambda ab: ask_raw("lab_r2@v1", state(ab[0], ab[1], nat, loc), R2), A))
        res[g] = pd.DataFrame({"v3": v3, "json": [x and x["same"] for x in js],
                               **{f"m_{k}": [x and x[k] for x in mu] for k in MULTI},
                               "choice_same": [x and x["who"].get("same") for x in ch],
                               "choice_rel": [x and x["who"].get("relative") for x in ch],
                               "r2_not_generation": [x and (1 - x["generation"]) for x in r2],
                               "r2_evidence": [x and x["evidence"] for x in r2], "r2_skeptic": [x and x["skeptic"] for x in r2]})
    out = []
    for col in res["neg"].columns:
        p_h, p_e, ng, nf = (res[g][col].dropna() for g in ("pos_hard", "pos_easy", "neg", "neg_far"))
        thr = float(np.quantile(ng, .99)) if len(ng) else 1
        thr_f = float(np.quantile(nf, .99)) if len(nf) else 1
        out.append([col, round(auc(p_h, ng), 3), round(auc(p_h, nf), 3), f"{(p_h > thr_f).mean():.0%}", round(auc(p_e, ng), 3), round(p_h.median(), 2), round(ng.median(), 2),
                    f"{(p_h > thr).mean():.0%}", round(thr, 2), f"{(p_h >= .9).mean():.0%}", f"{(ng >= .9).mean():.0%}"])
    print(pd.DataFrame(out, columns=["signal", "AUC hard", "AUC hard vs far", "TPR@1% far", "AUC easy", "med pos_hard", "med neg", "TPR hard @FPR1%", "thr", "pos_hard>=.9", "neg>=.9"]).to_string(index=False))
    # threshold sweep: share of hard positives accepted vs share of father/son namesakes accepted
    for col in ("json", "m_career", "r2_not_generation", "choice_same"):
        ph, ng = res["pos_hard"][col].dropna(), res["neg"][col].dropna()
        print(col, " ".join(f"{t}:{(ph >= t).mean():.0%}/{(ng >= t).mean():.0%}" for t in (0.5, 0.6, 0.7, 0.8, 0.9)))
    # code-side combination of the multi answers (pattern F): logistic regression, 2-fold
    from itertools import chain
    X = pd.concat([res["pos_hard"].assign(y=1), res["neg"].assign(y=0)]).dropna()
    feats = [c for c in X.columns if c.startswith("m_") or c.startswith("r2_")]
    try:
        from sklearn.linear_model import LogisticRegression
        idx = np.arange(len(X)); np.random.default_rng(0).shuffle(idx); h = len(idx) // 2; pr = np.zeros(len(X))
        for tr, te in ((idx[:h], idx[h:]), (idx[h:], idx[:h])):
            pr[te] = LogisticRegression().fit(X.iloc[tr][feats], X.iloc[tr].y).predict_proba(X.iloc[te][feats])[:, 1]
        print("multi combined (2-fold LR) AUC hard:", round(auc(pr[X.y.values == 1], pr[X.y.values == 0]), 3))
    except ImportError:
        print("sklearn missing: skip combination")
    spent = J.con.execute("SELECT kind, COUNT(*), ROUND(SUM(cost), 4) FROM jev WHERE kind LIKE 'lab_%' OR kind LIKE 'pair3%' GROUP BY kind").fetchall()
    print(spent)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)


def round4(n=150):
    """Realistic negatives: in production every uncertain pair has compatible ages, so the risk is not father/son but two
    different people with the same name AND birth year. Guaranteed different: same election, same district, same name,
    birth windows overlapping, two candidacies (one person runs in one council per election, city+part aside -> excluded).
    Years are hidden for every group, so the shared election year gives nothing away."""
    allc = P3.load_all()
    nat, nat_m, loc = P3.stats(allc)
    s = allc[allc.TYPZASTUP == "1"][["id", "city", "key", "year", "blo", "bhi", "OKRES", "KODZASTUP", "NADRZASTUP"]]  # parts lack NADRZASTUP in some years
    s = s[s.key.duplicated(keep=False)]
    m = s.merge(s, on=["key", "year", "OKRES"], suffixes=("_a", "_b"))
    m = m[(m.id_a < m.id_b) & (m.city_a != m.city_b) & (m.blo_a <= m.bhi_b) & (m.blo_b <= m.bhi_a)]
    # a city and its parts are one place: the same person may run in both (first try leaked those as "negatives")
    top = lambda kod, nadr: nadr.where(nadr != "", kod)
    m = m[(top(m.KODZASTUP_a, m.NADRZASTUP_a) != top(m.KODZASTUP_b, m.NADRZASTUP_b))
          & (m.KODZASTUP_a != m.NADRZASTUP_b) & (m.KODZASTUP_b != m.NADRZASTUP_a)]
    neg = m.sample(min(n, len(m)), random_state=6)[["id_a", "id_b"]].values.tolist()
    # hardest realistic case: same council, same election, same name, compatible age -> two different people (big cities)
    t = s.merge(s, on=["key", "year", "KODZASTUP"], suffixes=("_a", "_b"))
    t = t[(t.id_a < t.id_b) & (t.blo_a <= t.bhi_b) & (t.blo_b <= t.bhi_a)]
    neg_town = t.sample(min(n, len(t)), random_state=7)[["id_a", "id_b"]].values.tolist()
    print("same-town same-age namesake pairs available:", len(t))
    pos = pd.read_csv(DER / "lab_pos_hard.csv").sample(frac=1, random_state=1).head(n)[["id_a", "id_b"]].values.tolist()
    def st(a, b):
        x = state(a, b, nat, loc)
        for k in ("candidacy_A", "candidacy_B"): x[k].pop("election_year")
        x.pop("years_apart")
        return x
    Q = {"same": {**Q_SAME, "instructions": Q_SAME["instructions"].replace("running in two municipal elections", "running in municipal elections")},
         "career": {**MULTI["career"], "instructions": "Could the `occupation` of `candidacy_A` and the `occupation` of `candidacy_B` belong to one person's working life "
                    "(same job, same field, promotion, retirement, student who started working)?"},
         "who": Q_CHOICE}
    out = {}
    for g, pairs in (("pos_hard", pos), ("neg_same_age", neg), ("neg_same_town", neg_town)):
        with cf.ThreadPoolExecutor(8) as ex:
            r = list(ex.map(lambda ab: ask_raw("lab_r4@v3", st(allc.loc[ab[0]], allc.loc[ab[1]]), Q), pairs))
        out[g] = pd.DataFrame({"same": [x and x["same"] for x in r], "career": [x and x["career"] for x in r],
                               "choice_same": [x and x["who"].get("same") for x in r]})
    print("negatives available:", len(m))
    for col in ("same", "career", "choice_same"):
        for neg_g in ("neg_same_age", "neg_same_town"):
            ph, ng = out["pos_hard"][col].dropna(), out[neg_g][col].dropna()
            print(neg_g, col, "AUC", round(auc(ph, ng), 3), " ".join(f"{t}:{(ph >= t).mean():.0%}/{(ng >= t).mean():.0%}" for t in (0.5, 0.6, 0.7, 0.8, 0.9)))
