"""Pilot: can Jev (TypeSafe decision model) tell same occupation field / same local list better than string rules?

Fields: occupation strings / list names, P(jev says same) on seed matches (rare names, auto-linked) vs same-council
strangers -> likelihood ratio. Pair referee: full public candidacy profile (names allowed by Jan 2026-10-08), ages hidden,
positives = seed matches, negatives = same-council namesakes whose ages prove different people (father/son).
Needs OPENROUTER_API_KEY in env. Cache + spend cap in data/derived/jev.db.
Run: python3 src/jev_fields.py [n_per_group]
"""
import json, os, pathlib, sqlite3, sys, threading, time, urllib.error, urllib.request
import concurrent.futures as cf
import numpy as np
import pandas as pd

DER = pathlib.Path(__file__).resolve().parent.parent / "data/derived"
MODEL, API, CAP_USD = "typesafe/jev-1.13", "https://openrouter.ai/api/alpha/decisions", 5.0
QUESTIONS = {
    "occ": ("Two occupation descriptions in Czech, each written by an election candidate, years apart.",
            "Could both describe the same person's line of work: the same occupation or the same professional field "
            "(for example advokát / právník, učitelka / pedagog, OSVČ truhlář / truhlář), allowing gender forms, abbreviations, "
            "a promotion or retirement? Answer false when the fields clearly differ.",
            {"true": "same occupation or same professional field", "false": "different fields of work"}),
    "list": ("Two names of local candidate lists in the same Czech municipality, from elections years apart.",
             "Is list B plausibly the same group or party as list A (same name with another year, abbreviation, small rename, "
             "same party or movement)? Answer false for unrelated groups or different parties.",
             {"true": "same group or party continuing", "false": "different group"}),
    "pair": ("Two candidacies in Czech municipal elections, different years, same first name and surname. Ages are hidden.",
             "Are A and B the same person, or two different people with the same name (for example father and son, or relatives "
             "in one village)? Use titles, occupation, candidate list and anything else in the profiles.",
             {"true": "the same person", "false": "two different people with the same name"}),
}
# Cache key includes the question kind; bump the version in a kind name whenever its instructions or criteria change,
# otherwise old answers to a different question are silently reused (e.g. "pair@v2").
lock = threading.Lock()
con = sqlite3.connect(DER / "jev.db", check_same_thread=False)
con.execute("CREATE TABLE IF NOT EXISTS jev (kind TEXT, a TEXT, b TEXT, p REAL, cost REAL, model TEXT, PRIMARY KEY (kind, a, b))")


def ask(kind, a, b):
    with lock:  # one sqlite connection across threads only under a lock (segfault otherwise, knowdb 2026-09-28)
        if (h := con.execute("SELECT p FROM jev WHERE kind=? AND a=? AND b=?", (kind, a, b)).fetchone()):
            return h[0]
        if con.execute("SELECT COALESCE(SUM(cost), 0) FROM jev").fetchone()[0] >= CAP_USD:
            raise SystemExit(f"Jev spend cap {CAP_USD} USD")
    head, instr, crit = QUESTIONS[kind.split("@")[0]]
    body = json.dumps({"model": MODEL, "state": {"text": f"{head}\nA: {a}\nB: {b}"},
                       "questions": {"same": {"type": "noul", "instructions": instr, "criteria": crit}}}).encode()
    req = urllib.request.Request(API, data=body, headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                                          "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            break
        except (urllib.error.URLError, OSError):
            if attempt == 2:
                return None
            time.sleep(10 * (attempt + 1))
    p = d["answers"]["same"]["noul"]
    with lock:
        con.execute("INSERT OR IGNORE INTO jev VALUES (?, ?, ?, ?, ?, ?)", (kind, a, b, p, d.get("usage", {}).get("cost") or 0, d.get("model")))
        con.commit()
    return p


def main(n):
    if (DER / "cluster_edges.csv.gz").exists():
        E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=["id_a", "id_b", "E_a", "decision", "geo", "occ"])
        C = pd.read_csv(DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False).set_index("id")
    else:  # full run not finished yet: 2018 -> 2022 prototype output
        import linkage
        E = pd.read_csv(DER / "match_2018_2022_pairs.csv.gz", usecols=["id_a", "id_b", "E", "decision", "geo", "occ"]).rename(columns={"E": "E_a"})
        C = pd.concat([linkage.load(y) for y in (2018, 2022)]).astype({"year": str})
        C = C.assign(person=C.key)[["id", "person", "year", "JMENO", "PRIJMENI", "TITULPRED", "TITULZA", "VEK", "POVOLANI",
                                    "BYDLISTEN", "NAZEVCELK", "PSTRANA", "MANDAT", "KODZASTUP"]].set_index("id")
    rng = np.random.default_rng(0)

    seed = E[(E.decision == "auto_match") & (E.E_a < 0.02) & (E.geo == "zast")]
    seed = seed.assign(occ_a=seed.id_a.map(C.POVOLANI), occ_b=seed.id_b.map(C.POVOLANI),
                       list_a=seed.id_a.map(C.NAZEVCELK), list_b=seed.id_b.map(C.NAZEVCELK))
    # strangers: random pairs from different elections in the same council, different people
    Cr = C.reset_index()
    by = Cr.groupby("KODZASTUP").indices
    zs = Cr.KODZASTUP.sample(20 * n, random_state=0).values
    rows = []
    for z in zs:
        i, j = rng.choice(by[z], 2)
        a, b = Cr.iloc[i], Cr.iloc[j]
        if a.year != b.year and a.person != b.person:
            a, b = (a, b) if a.year < b.year else (b, a)
            rows.append({"occ_a": a.POVOLANI, "occ_b": b.POVOLANI, "list_a": a.NAZEVCELK, "list_b": b.NAZEVCELK})
    strangers = pd.DataFrame(rows)

    norm = lambda s: s.str.lower().str.strip()
    out = {}
    for kind in ("occ", "list"):
        groups = {}
        for name, df in (("seed", seed), ("strangers", strangers)):
            d = df[(df[f"{kind}_a"] != "") & (df[f"{kind}_b"] != "") & (norm(df[f"{kind}_a"]) != norm(df[f"{kind}_b"]))]
            groups[name] = d.sample(min(n, len(d)), random_state=1)[[f"{kind}_a", f"{kind}_b"]].values.tolist()
        for name, pairs in groups.items():
            with cf.ThreadPoolExecutor(8) as ex:
                ps = [p for p in ex.map(lambda ab: ask(kind, *ab), pairs) if p is not None]
            out[(kind, name)] = np.array(ps)
        s, u = out[(kind, "seed")], out[(kind, "strangers")]
        print(f"\n{kind}: string differs; seed n={len(s)}, strangers n={len(u)}")
        for t in (0.5, 0.8):
            ms, us = (s >= t).mean(), (u >= t).mean()
            print(f"  p>={t}: seed {ms:.2f}  strangers {us:.2f}  LR yes {ms / max(us, 1e-3):.1f}  LR no {(1 - ms) / max(1 - us, 1e-3):.2f}")
    # pair referee
    prof = lambda r: (f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip() + f"; election {r.year}; residence: {r.BYDLISTEN}; "
                      f"occupation: {r.POVOLANI}; list: {r.NAZEVCELK}")  # election result is not identity evidence
    ps_ = seed.sample(min(n, len(seed)), random_state=2)
    pos_pairs = [(prof(C.loc[a]), prof(C.loc[b])) for a, b in zip(ps_.id_a, ps_.id_b)]
    same_name = Cr.merge(Cr, on=["KODZASTUP", "JMENO", "PRIJMENI"], suffixes=("_a", "_b"))
    same_name = same_name[same_name.year_a.astype(int) < same_name.year_b.astype(int)]
    gap = same_name.year_b.astype(int) - same_name.year_a.astype(int)
    neg = same_name[((same_name.VEK_b.astype(int) - same_name.VEK_a.astype(int)) - gap).abs() >= 5].sample(n, random_state=3)
    neg_pairs = [(prof(C.loc[a]), prof(C.loc[b])) for a, b in zip(neg.id_a, neg.id_b)]
    res = {}
    for name, pairs in (("same_person", pos_pairs), ("father_son_etc", neg_pairs)):
        with cf.ThreadPoolExecutor(8) as ex:
            res[name] = np.array([p for p in ex.map(lambda ab: ask("pair", *ab), pairs) if p is not None])
    s, u = res["same_person"], res["father_son_etc"]
    print(f"\npair referee (ages hidden): same n={len(s)}, different n={len(u)}")
    for t_ in (0.5, 0.8, 0.95):
        print(f"  p>={t_}: same {(s >= t_).mean():.2f}  different {(u >= t_).mean():.2f}")

    spent = con.execute("SELECT COUNT(*), SUM(cost) FROM jev").fetchone()
    print(f"\njev calls cached {spent[0]}, spent {spent[1] or 0:.4f} USD")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
