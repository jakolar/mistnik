"""Prototype v2: link 2018 -> 2022 municipal-election candidacies (see docs/parovani-kandidatu-v2.md).

Model, per pair (A from 2018, B from 2022, same first name + surname, compatible birth window):
  odds(B is A) = r * prod m_f(level) / ( E * c * prod u_f(level) )
    r   P(a 2018 candidate runs again in 2022), measured on the seed
    E   expected namesakes (same first name, surname, birth year) living in CZ, from MV ČR 2017 counts
    c   share of population that is a 2022 candidate
    u   distribution of the field level for a random 2022 candidacy (geo: per-pair from candidacy counts)
    m   distribution of the field level among seed matches (names with E < SEED_E)
  E is inflated by local surname concentration (other same-surname candidates in the city), co-candidate
  overlap is compared only inside the same city with u measured on random same-council pairs.
  Pairs are aggregated to person-events (name, city, age): one person may run for city and city part at once.
  Final p is normalised against all competing namesakes on both sides (negative evidence).
Run: python3 src/match_v2.py
"""
import csv, datetime as dt, glob, gzip, pathlib, re, unicodedata
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data/raw", ROOT / "data/derived"
JMENOVAC = pathlib.Path.home() / "projekty/jmenovac/data/jmena_mv_rocniky.csv"
DATES = {2018: "20181005", 2022: "20220923"}
SEED_E = 0.02
GEO_LEVELS = ["zast", "city", "orp", "okres", "kraj", "other"]


def strip(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).lower().strip()


def od(year, name):
    return glob.glob(str(RAW / f"kv{year}/**/csv_od/{name}.csv"), recursive=True)[0]


def birth_window(date, age):
    """Birth date interval (lo, hi], inclusive, for someone `age` years old on the 2nd election day."""
    d = date + dt.timedelta(days=1)
    hi = d.replace(year=d.year - age)
    lo = d.replace(year=d.year - age - 1) + dt.timedelta(days=1)
    return lo, hi


TITLE_RE = re.compile(r"[a-z]+")


def titles(pre, post):
    return frozenset(TITLE_RE.findall(strip(f"{pre} {post}").replace("ph.d", "phd")))


def occ_stems(s):
    # ponytail: 5-char prefix stem merges advokát/advokátka; no real stemmer, upgrade if occupation weight matters
    return frozenset(t[:5] for t in re.findall(r"[a-z]{3,}", strip(s)))


def load(year):
    date = DATES[year]
    k = pd.read_csv(od(year, "kvrk"), dtype=str, keep_default_na=False)
    k = k[(k.DATUMVOLEB == date) & (k.VEK != "") & (k.PLATNOST == "A")]
    ros = pd.read_csv(od(year, "kvros"), dtype=str, keep_default_na=False)
    ros = ros[ros.DATUMVOLEB == date][["KODZASTUP", "COBVODU", "POR_STR_HL", "VSTRANA", "NAZEVCELK"]]
    coco = pd.read_csv(od(year, "kvcoco"), dtype=str, keep_default_na=False)
    coco = coco[coco.DATUMVOLEB == date].drop_duplicates("KODZASTUP")[["KODZASTUP", "NADRZASTUP", "TYPZASTUP", "KRAJ"]]
    rz = pd.read_csv(od(year, "kvrzcoco"), dtype=str, keep_default_na=False)
    rz = rz[rz.DATUMVOLEB == date].drop_duplicates("KODZASTUP")[["KODZASTUP", "ORP"]]
    k = k.merge(ros, on=["KODZASTUP", "COBVODU", "POR_STR_HL"], how="left").merge(coco, on="KODZASTUP", how="left").merge(rz, on="KODZASTUP", how="left")
    k["id"] = f"{year}:" + k.KODZASTUP + ":" + k.COBVODU + ":" + k.POR_STR_HL + ":" + k.PORCISLO
    k["first"] = k.JMENO.str.split().str[0].fillna("")
    k["key"] = k["first"].map(strip) + "|" + k.PRIJMENI.map(strip)
    k["age"] = k.VEK.astype(int)
    d = dt.datetime.strptime(date, "%Y%m%d").date()
    w = [birth_window(d, a) for a in k.age]
    k["blo"], k["bhi"] = [x[0] for x in w], [x[1] for x in w]
    k["city"] = k.NADRZASTUP.where(k.NADRZASTUP != "", k.KODZASTUP)
    k["listkey"] = k.KODZASTUP + "|" + k.COBVODU + "|" + k.POR_STR_HL
    mates = k.groupby("listkey").key.agg(frozenset)
    k["cocand"] = [mates[l] - {own} for l, own in zip(k.listkey, k.key)]
    k["surname"] = k.PRIJMENI.map(strip)
    k["titles"] = [titles(a, b) for a, b in zip(k.TITULPRED, k.TITULZA)]
    k["occ"] = k.POVOLANI.map(occ_stems)
    k["female"] = k.PRIJMENI.str.lower().str.endswith("á")
    return k.reset_index(drop=True)


def namesakes(df, year, date):
    """Expected living namesakes in CZ (MV 2017) for each row's name and birth year, independence of first name and surname."""
    fn, sn = {}, {}
    for path, dct in ((DER / "mv_jmena_dnar.csv", fn), (DER / "mv_prijmeni_dnar.csv", sn)):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            dct[(r["name"], int(r["year"]))] = int(r["count"])
    pop = {int(r["rok"]): (int(r["M"]), int(r["Z"])) for r in csv.DictReader(open(JMENOVAC))}
    d = dt.datetime.strptime(date, "%Y%m%d").date()
    w_late = (dt.date(d.year, 12, 31) - d).days / 365  # share born after election day -> earlier birth year
    out = []
    for f, s, a, fem in zip(df["first"].str.upper(), df.PRIJMENI.str.upper(), df.age, df.female):
        e = 0.0
        for y, wt in ((year - a - 1, w_late), (year - a, 1 - w_late)):
            n = pop.get(max(y, 1920), pop[1920])[1 if fem else 0]
            e += wt * (fn.get((f, y), 0) + 0.5) * (sn.get((s, y), 0) + 0.5) / max(n, 1)
        out.append(e)
    return np.array(out)


def levels(P):
    """Comparison levels for a frame of pairs with _a/_b columns (vectorised)."""
    sa = lambda c: P[f"{c}_a"].values
    sb = lambda c: P[f"{c}_b"].values
    eq = lambda c: sa(c) == sb(c)
    geo = np.select([eq("KODZASTUP"), eq("city"), eq("ORP"), eq("OKRES"), eq("KRAJ")], GEO_LEVELS[:-1], "other")
    shared = np.array([len(a & b) for a, b in zip(sa("cocand"), sb("cocand"))])
    coc = np.where(~eq("city"), "na", np.select([shared >= 2, shared == 1], ["2+", "1"], "0"))
    party = np.select([eq("PSTRANA") & (sa("PSTRANA") == "99"), eq("PSTRANA")], ["both_bezpp", "same"], "diff")
    tl = ["none" if not a and not b else "same" if a == b else "gained" if a < b else "other"
          for a, b in zip(sa("titles"), sb("titles"))]
    oc = []
    for a, b in zip(sa("occ"), sb("occ")):
        if not a or not b:
            oc.append("missing")
        else:
            j = len(a & b) / len(a | b)
            oc.append("same" if j == 1 else "similar" if j >= 0.5 else "diff")
    return {"geo": geo, "cocand": coc, "party": party, "titles": np.array(tl), "occ": np.array(oc)}


FIELDS = ["cocand", "party", "titles", "occ"]


def geo_u(P, B):
    """Share of 2022 candidacies in each geo ring around A (rings nested, inner ring subtracted)."""
    total = len(B)
    prev = np.zeros(len(P))
    u = {}
    for lvl, col in zip(GEO_LEVELS, ["KODZASTUP", "city", "ORP", "OKRES", "KRAJ", None]):
        n = P[f"{col}_a"].map(B[col].value_counts()).fillna(0).values if col else np.full(len(P), total)
        u[lvl] = np.maximum(n - prev, 1) / total
        prev = np.maximum(n, prev)
    return u


def main():
    A, B = load(2018), load(2022)
    A["E"] = namesakes(A, 2018, DATES[2018])
    print(f"2018 {len(A)}  2022 {len(B)}")

    P = A.reset_index().merge(B.reset_index(), on="key", suffixes=("_a", "_b"))
    lo = np.maximum(P.blo_a.values.astype("datetime64[D]"), P.blo_b.values.astype("datetime64[D]"))
    hi = np.minimum(P.bhi_a.values.astype("datetime64[D]"), P.bhi_b.values.astype("datetime64[D]"))
    P["overlap"] = (hi - lo).astype(int) + 1
    P["dage"] = P.age_b - P.age_a
    print(f"blocked pairs {len(P)}, birth-compatible {(P.overlap > 0).sum()}, off by <=1y {((P.overlap <= 0) & (P.overlap > -366)).sum()}")

    for f, v in levels(P).items():
        P[f] = v

    # u: random A x random B pairs (almost surely different people); cocand conditional on the same council
    rng = np.random.default_rng(0)
    R = pd.concat([A.iloc[rng.integers(0, len(A), 200_000)].reset_index(drop=True).add_suffix("_a"),
                   B.iloc[rng.integers(0, len(B), 200_000)].reset_index(drop=True).add_suffix("_b")], axis=1)
    u = {f: pd.Series(v).value_counts(normalize=True).to_dict() for f, v in levels(R).items() if f in FIELDS}
    by_zast = A.groupby("KODZASTUP").indices
    bs = B[B.KODZASTUP.isin(by_zast)].sample(200_000, replace=True, random_state=0)
    ai = [by_zast[z][rng.integers(len(by_zast[z]))] for z in bs.KODZASTUP]
    same = pd.concat([A.iloc[ai].reset_index(drop=True).add_suffix("_a"), bs.reset_index(drop=True).add_suffix("_b")], axis=1)
    same = same[same.key_a != same.key_b]
    # same-council strangers share party / occupation / co-candidates more often than national strangers
    u_local = {f: pd.Series(v).value_counts(normalize=True).to_dict() for f, v in levels(same).items() if f in FIELDS}
    u["cocand"] = {"na": 1.0}

    # local surname concentration: other same-surname candidates (distinct first names) in A's city, both elections
    both = pd.concat([A[["city", "surname", "first"]], B[["city", "surname", "first"]]])
    fam = both.drop_duplicates().groupby(["city", "surname"]).size()
    city_people = both.drop_duplicates().groupby("city").size()
    nat = both.drop_duplicates(["surname", "first"]).surname.value_counts() / len(both.drop_duplicates(["surname", "first"]))
    others = np.array([fam.get((c, s), 1) - 1 for c, s in zip(A.city, A.surname)])
    expected = A.city.map(city_people).values * A.surname.map(nat).values
    A["k_local"] = np.clip((others + 1) / (expected + 1), 1, 50)
    A["E_eff"] = A.E * A.k_local
    P["k_local"] = P.index_a.map(A.k_local)
    P["E_eff"] = np.where(P.geo.isin(["zast", "city"]), P.E * P.k_local, P.E)

    # seed: rare names, compatible birth -> m and r
    P["ok"] = ok = P.overlap > 0
    seed = P[ok & (P.E < SEED_E)].sort_values("geo", key=lambda s: s.map(GEO_LEVELS.index)).drop_duplicates("index_a")
    n_seed_a = (A.E < SEED_E).sum()
    r = len(seed) / n_seed_a
    m = {f: seed[f].value_counts(normalize=True).to_dict() for f in ["geo", *FIELDS]}
    m["cocand"] = seed[seed.geo.isin(["zast", "city"])].cocand.value_counts(normalize=True).to_dict()
    m["cocand"]["na"] = 1.0
    c = len(B) / 8_300_000  # ponytail: ~8.3 M voters as population; age-specific rate if calibration needs it
    print(f"seed {len(seed)} of {n_seed_a} rare-name 2018 candidates -> r={r:.3f}, c={c:.4f}")

    gu = geo_u(P, B)
    eps = 1e-4
    P["w_prior"] = np.log2(r) - np.log2(P.E_eff * c)
    P["w_geo"] = np.log2([m["geo"].get(g, eps) for g in P.geo]) - np.log2(np.choose([GEO_LEVELS.index(g) for g in P.geo], [gu[l] for l in GEO_LEVELS]))
    total = P.w_prior + P.w_geo
    local = P.geo.isin(["zast", "city"]).values
    for f in FIELDS:
        P[f"w_{f}"] = [np.log2(m[f].get(x, eps) / (u_local if loc else u)[f].get(x, eps)) for x, loc in zip(P[f], local)]
        total += P[f"w_{f}"]
    P["weight"] = total

    # person-events: same name + city + age in one election = one person (city + city-part double candidacy)
    # ponytail: two different same-name same-age people in one city would merge; rare, review sample will show it
    P["ga"] = P.key + "|" + P.city_a + "|" + P.age_a.astype(str)
    P["gb"] = P.key + "|" + P.city_b + "|" + P.age_b.astype(str)
    G = P[P.ok].groupby(["ga", "gb"]).agg(weight=("weight", "max"), geo=("geo", "first"), E=("E", "first")).reset_index()
    G["odds"] = 2.0 ** G.weight.clip(-60, 60)
    sa_, sb_ = G.groupby("ga").odds.transform("sum"), G.groupby("gb").odds.transform("sum")
    G["p"] = G.odds / (1 + sa_ + sb_ - G.odds)  # competing namesakes on both sides count against
    G = G.sort_values("p", ascending=False)
    used_a, used_b, linked = set(), set(), []
    for a, b in zip(G.ga, G.gb):
        hit = a not in used_a and b not in used_b
        if hit:
            used_a.add(a), used_b.add(b)
        linked.append(hit)
    G["linked"] = linked
    strong = G.geo.isin(["zast", "city"])
    G["decision"] = np.select([G.linked & (G.p >= 0.999) & strong, G.linked & (G.p >= 0.9), G.p >= 0.5],
                              ["auto_match", "manual_review", "possible_match"], "no_match")

    P = P.merge(G[["ga", "gb", "p", "linked", "decision"]], on=["ga", "gb"], how="left")
    P["decision"] = P.decision.fillna("reject_birth")
    P.loc[~P.ok & (P.overlap > -366) & (P.weight - P.w_prior > 10), "decision"] = "review_age_conflict"
    P["linked"] = P.linked.fillna(False).astype(bool)

    cols = ["id_a", "id_b", "key", "age_a", "age_b", "dage", "overlap", "E", "k_local", "E_eff", "geo", "cocand", "party",
            "titles", "occ", "w_prior", "w_geo", "w_cocand", "w_party", "w_titles", "w_occ", "weight", "p", "linked", "decision"]
    DER.mkdir(exist_ok=True)
    P[cols].to_csv(DER / "match_2018_2022_pairs.csv.gz", index=False, compression="gzip")

    print("\nm / u_national / u_same_council")
    for f in ["geo", *FIELDS]:
        print(f"  {f}: " + ", ".join(f"{k}: m={v:.3f}" + (f" u={u[f].get(k, 0):.3f} uloc={u_local[f].get(k, 0):.3f}" if f != "geo" else "")
                                     for k, v in sorted(m[f].items(), key=lambda t: -t[1])))
    print("\nperson-event decisions")
    print(G.decision.value_counts().to_string())
    a = G[G.decision == "auto_match"]
    print(f"expected false links in auto (sum 1-p): {(1 - a.p).sum():.1f}; auto by geo {a.geo.value_counts().to_dict()}")
    print(f"review queue {(G.decision == 'manual_review').sum()}, age conflicts {P[P.decision == 'review_age_conflict'].ga.nunique()}")
    print(f"2018 person-events {A.assign(g=A.key + '|' + A.city + '|' + A.age.astype(str)).g.nunique()}, linked {G.linked.sum()}")

    # stratified labelling sample (pair level, one pair per person-event pair)
    Q = P.drop_duplicates(["ga", "gb"])
    strata = {
        "auto_rare": Q[(Q.decision == "auto_match") & (Q.E < SEED_E)],
        "auto_common": Q[(Q.decision == "auto_match") & (Q.E >= 1)],
        "auto_low_margin": Q[(Q.decision == "auto_match") & (Q.p < 0.9999)],
        "review": Q[Q.decision == "manual_review"],
        "possible": Q[Q.decision == "possible_match"],
        "movers_linked": Q[Q.linked & ~Q.geo.isin(["zast", "city"])],
        "age_conflict": Q[Q.decision == "review_age_conflict"],
        "father_son": Q[(Q.geo == "zast") & Q.dage.between(-40, -15)],
    }
    sample = pd.concat([s.sample(min(len(s), 40), random_state=1).assign(stratum=k) for k, s in strata.items()])
    view = sample.merge(A.add_suffix("_A")[["id_A", "JMENO_A", "PRIJMENI_A", "TITULPRED_A", "POVOLANI_A", "BYDLISTEN_A", "NAZEVCELK_A"]], left_on="id_a", right_on="id_A")
    view = view.merge(B.add_suffix("_B")[["id_B", "TITULPRED_B", "POVOLANI_B", "BYDLISTEN_B", "NAZEVCELK_B"]], left_on="id_b", right_on="id_B")
    view["label"] = ""
    view[["stratum", "label", "p", "decision", "JMENO_A", "PRIJMENI_A", "age_a", "age_b", "TITULPRED_A", "TITULPRED_B",
          "BYDLISTEN_A", "BYDLISTEN_B", "POVOLANI_A", "POVOLANI_B", "NAZEVCELK_A", "NAZEVCELK_B", "E_eff", "geo", "cocand", "id_a", "id_b"]
         ].to_csv(DER / "labeling_sample_2018_2022.csv", index=False)
    print({k: len(s) for k, s in strata.items()})


if __name__ == "__main__":
    main()
