"""Build the whole Místník static site into site/ (one page per 2026 council, home with search, occupations, method).

Inputs: cluster_persons / cluster_edges (cluster.py), raw ČSÚ data, MV name counts.
Run: python3 src/build_site.py   then preview: python3 -m http.server 8095 --bind 0.0.0.0 -d site
"""
import collections, html, json, pathlib, shutil, sys
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import linkage as L
from gender import gender
from card_mockup import party_names, extra_fields, reasons, list_id, list_parties, list_age_stats, profile_context, occ_norm, YEARS
import bisect

ROOT = L.ROOT
SITE = ROOT / "site"
CONTACT = "jan@klr.cz"
CONTROLLER = "Jan Antonín Kolář, kontakt jan@klr.cz"  # Jan 2026-10-09: controller is Jan personally, not the company


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def main():
    C = pd.read_csv(L.DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False)
    want = ["id_a", "id_b", "decision", "geo", "cocand", "party", "titles", "occ", "same_list", "same_res", "second", "p", "list_party"]
    have = pd.read_csv(L.DER / "cluster_edges.csv.gz", nrows=0).columns
    E = pd.read_csv(L.DER / "cluster_edges.csv.gz", usecols=[c for c in want if c in have])
    pn, extra = party_names(), extra_fields()
    og, all_ages = profile_context(C)
    age_stats = collections.defaultdict(dict)
    for (k, no), v in list_age_stats(C).items():
        age_stats[k][str(no)] = v
    council_name, council_okres = {}, {}
    for y in YEARS:
        rz = L.read(y, "kvrzcoco")
        council_name.update(rz.set_index("KODZASTUP").NAZEVZAST.to_dict())
    okres_name = L.read(2026, "cnumnuts").set_index("NUMNUTS").NAZEVNUTS.to_dict()
    rz26 = L.read(2026, "kvrzcoco").drop_duplicates("KODZASTUP").set_index("KODZASTUP")

    # histories, link reasons and open questions, indexed once
    hist = collections.defaultdict(list)
    for r in C.itertuples(index=False):
        hist[r.person].append(r)
    auto = E[E.decision.isin(["auto_match", "auto_jev", "implied"])]  # implied: linked through other elections
    why_b = {}
    for e in auto.itertuples(index=False):
        why_b.setdefault(e.id_b, (e, e.decision))
    maybe_by = collections.defaultdict(list)
    for e in E[E.decision == "manual_review"].itertuples(index=False):
        maybe_by[e.id_a].append((e, e.id_b))
        maybe_by[e.id_b].append((e, e.id_a))
    row_by_id = {r.id: r for r in C.itertuples(index=False)}

    # unresolved namesakes: a compatible same-name candidacy in the same town that we did NOT link. Such people get no
    # "first time" / newcomer claim, and elected-2022 people with such a 2026 namesake are not listed as leaving.
    person_of = dict(zip(C.id, C.person))
    LE = pd.read_csv(L.DER / "linkage_edges.csv.gz", usecols=["id_a", "id_b", "geo", "year_b"])
    LE = LE[LE.geo.isin(["zast", "city"])]
    LE = LE[[person_of.get(a) != person_of.get(b) for a, b in zip(LE.id_a, LE.id_b)]]
    ns_before = set(LE.id_b[LE.year_b == 2026])
    ns_after = set(LE.id_a[LE.year_b == 2026])
    b26 = C[C.year == "2026"].copy()
    b26["first"] = b26.JMENO.str.split().str[0]
    b26["age"] = b26.VEK.astype(int)
    b26["female"] = [gender(a, b) == "Z" for a, b in zip(b26.JMENO, b26.PRIJMENI)]
    rarity = dict(zip(b26.id, L.Namesakes()(b26, 2026)))
    elected22 = C[(C.year == "2022") & (C.MANDAT == "A")]
    running26 = collections.defaultdict(set)
    for r in b26.itertuples(index=False):
        running26[r.KODZASTUP].add(r.person)
    p26 = b26.groupby("person").KODZASTUP.first().to_dict()

    if SITE.exists():
        shutil.rmtree(SITE)  # build artefact, regenerated in full
    (SITE / "obec").mkdir(parents=True)
    tpl = (ROOT / "src/obec_template.html").read_text()
    index = []
    stats = {"cands": 0, "lists": 0, "women": 0, "men": 0, "new": 0, "long": 0, "again": 0, "inc": 0, "e22": 0}
    list_ages, nlists, stalwarts, seventh = [], [], [], []
    for kod, ballot in b26.groupby("KODZASTUP"):
        people = []
        obvod = ballot.id.str.split(":").str[2].astype(int)
        multi = obvod.nunique() > 1  # Lišov 2026: list numbers repeat per electoral district -> obvod*100 + list
        for r in ballot.assign(list_no=ballot.id.str.split(":").str[3].astype(int) + (obvod * 100 if multi else 0),
                               pos=ballot.id.str.split(":").str[4].astype(int)).sort_values(["list_no", "pos"]).itertuples(index=False):
            hrows = sorted(hist[r.person], key=lambda h: h.year)
            ids = {h.id for h in hrows}
            rows = []
            for y in sorted({h.year for h in hrows}):
                hy = [h for h in hrows if h.year == y]
                here = next((x for x in hy if x.KODZASTUP == kod), None)  # city + city part double runs: the list in this council
                h = here or sorted(hy, key=lambda h: h.MANDAT)[0]
                link = next((why_b[x.id] for x in hy if x.id in why_b and why_b[x.id][0].id_a in ids), None)
                votes, skip, vrank, vn, vshare = extra.get(h.id, ("", "", None, None, None))
                rows.append({"why": (reasons(link[0]) + (["potvrdil Jev"] if link[1] == "auto_jev" else [])) if link else [],
                             "p": round(float(link[0].p), 5) if link else None,
                             "year": y, "age": h.VEK, "town": council_name.get(h.KODZASTUP, h.BYDLISTEN), "occ": h.POVOLANI,
                             "pos": int(h.id.split(":")[4]), "votes": int(votes) if votes.isdigit() and y != "2026" else None,
                             "skip": bool(skip) and y != "2026", "member": h.PSTRANA not in ("99", ""),
                             "vrank": vrank if y != "2026" else None, "vn": vn, "vshare": vshare if y != "2026" else None,
                             "list": " a ".join(dict.fromkeys(x.NAZEVCELK for x in hy)), "lid": list_id(h.NAZEVCELK), "parties": list_parties(h.id),
                             "party": pn.get((y, h.PSTRANA), ""),
                             "elected": any(x.MANDAT == "A" for x in hy),
                             "elected_here": any(x.MANDAT == "A" and x.KODZASTUP == kod for x in hy)})
                if y == "2022":
                    rows[-1]["here"] = {"list": here.NAZEVCELK, "lid": list_id(here.NAZEVCELK), "parties": list_parties(here.id)} if here else None
            past = [x for x in rows if x["year"] != "2026"]
            maybe = []
            for e, other in maybe_by.get(r.id, [])[:3]:
                o = row_by_id.get(other)
                if o is not None and o.person != r.person:
                    maybe.append({"year": o.year, "town": council_name.get(o.KODZASTUP, o.BYDLISTEN), "list": o.NAZEVCELK,
                                  "occ": o.POVOLANI, "age": o.VEK, "why": reasons(e), "p": round(float(e.p), 3)})
            g = gender(r.JMENO, r.PRIJMENI)
            people.append({
                "id": r.id, "name": f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip(), "age": int(r.VEK),
                "occ": r.POVOLANI, "town": r.BYDLISTEN, "list": r.NAZEVCELK, "list_no": r.list_no, "pos": r.pos,
                "party": pn.get(("2026", r.PSTRANA), ""), "member": r.PSTRANA not in ("99", ""), "gender": g, "female": g == "Z",
                "history": rows, "ran": len(past), "elected": sum(x["elected"] for x in past),
                "since": past[0]["year"] if past else None, "family": r.family == "True",
                # "Možná také" (unconfirmed links) is not published: launch review 2026-10-09, accuracy over coverage
                "rare": bool(rarity.get(r.id, 99) < 0.05), "maybe": [], "namesake": r.id in ns_before,
                "incumbent": any(x["elected_here"] and x["year"] == "2022" for x in rows),
                "field": og["text"].get(occ_norm(r.POVOLANI), ""),
                "age_older": round(1 - bisect.bisect_right(all_ages, int(r.VEK)) / len(all_ages), 3)})
        here = collections.Counter(p["field"] for p in people)
        for p in people:
            p["field_n"], p["field_here"] = og["n2026"].get(p["field"], 0), here[p["field"]]
        e22 = elected22[elected22.KODZASTUP == kod]
        leaving = [{"name": f"{e.TITULPRED} {e.JMENO} {e.PRIJMENI}".strip(), "list": e.NAZEVCELK,
                    "elsewhere": council_name.get(p26[e.person]) if e.person in p26 else None}
                   for e in e22.itertuples(index=False) if e.person not in running26[kod] and e.id not in ns_after]
        meta = {"elected22": len(e22), "running": sum(p["incumbent"] for p in people), "leaving": leaving, "contact": CONTACT,
                "ages": age_stats.get(kod, {})}
        town = council_name.get(kod, kod)
        page = (tpl.replace("__TOWN__", html.escape(town)).replace("__DATA__", js(people)).replace("__META__", js(meta))
                .replace("__CONTACT__", CONTACT))
        (SITE / "obec" / f"{kod}.html").write_text(page)
        okres = okres_name.get(rz26.at[kod, "OKRES"], "") if kod in rz26.index else ""
        index.append([kod, town, okres, len(people), sum(p["ran"] > 0 for p in people)])
        for p in people:  # elected in this council in all six elections 2002-2022 and running again
            past = [h for h in p["history"] if h["year"] != "2026"]
            row = [p["name"], p["age"], town, okres, kod, p["id"], p["list"]]
            if len(past) == 6:
                seventh.append(row)
                if all(h["elected_here"] for h in past):
                    stalwarts.append(row)
        stats["cands"] += len(people)
        stats["lists"] += len({p["list_no"] for p in people})
        sizes = collections.Counter(p["list_no"] for p in people)
        nlists.append([sum(n >= 2 for n in sizes.values()), town, kod])  # one-person lists are independents, not lists
        stats["women"] += sum(p["gender"] == "Z" for p in people)
        stats["men"] += sum(p["gender"] == "M" for p in people)
        stats["new"] += sum(p["ran"] == 0 and not p["namesake"] for p in people)
        stats["long"] += sum(bool(p["since"]) and int(p["since"]) <= 2010 for p in people)
        stats["again"] += sum(p["ran"] > 0 for p in people)
        stats["inc"] += meta["running"]
        stats["e22"] += meta["elected22"]
        for no, (med, younger) in meta["ages"].items():
            n = sum(p["list_no"] == int(no) for p in people)
            if n >= 10:
                name = next(p["list"] for p in people if p["list_no"] == int(no))
                list_ages.append([med, n, name, town, kod])
    index.sort(key=lambda x: x[1])
    # people search: shards by the first two letters of the normalised surname, loaded on demand by the home page
    shards = collections.defaultdict(list)
    for r in b26.itertuples(index=False):
        hrows = hist[r.person]
        ran = len({h.year for h in hrows if h.year != "2026"})
        sn = lambda s: L.name_norm(s).translate({ord(c): None for c in "'’´`"})  # O´Bryan, D’Amico -> obryan, damico
        row = [f"{r.TITULPRED} {r.JMENO} {r.PRIJMENI} {r.TITULZA}".strip(), int(r.VEK), council_name.get(r.KODZASTUP, ""),
               r.KODZASTUP, r.id, ran, sn(f"{r.PRIJMENI} {r.JMENO}")]
        for key in {w[:2] for w in sn(r.PRIJMENI).split()} or {"_"}:  # Nováková Svobodová is found under both parts
            shards[key].append(row)
    (SITE / "hledat").mkdir()
    for k, rows in shards.items():
        (SITE / "hledat" / f"{k.replace(' ', '_')}.json").write_text(js(rows))
    list_ages.sort()
    stats["young"], stats["old"] = list_ages[:50], list_ages[-50:][::-1]
    stats["most_lists"] = sorted(nlists, reverse=True)[:50]
    stats["councils"] = len(index)
    big = ["554782", "582786", "554821", "554791", "563889", "500496", "544256", "569810", "554804", "555134"]  # ten largest cities
    ages = b26.age.clip(upper=90)
    stats["age_hist"] = {"from": int(ages.min()), "n": [int(x) for x in ages.value_counts().sort_index().reindex(range(int(ages.min()), 91), fill_value=0)],
                         "mean": round(float(b26.age.mean()), 1), "median": float(b26.age.median())}  # 90 = 90 and older
    # share of women per election, among candidates and among the elected (gender estimated from names; unknown left out)
    gu = C[["JMENO", "PRIJMENI"]].drop_duplicates()
    gu["g"] = [gender(a, b) for a, b in zip(gu.JMENO, gu.PRIJMENI)]
    gw = C[["year", "JMENO", "PRIJMENI", "MANDAT"]].merge(gu, on=["JMENO", "PRIJMENI"])
    gw = gw[gw.g.isin(["Z", "M"])]
    stats["women_years"] = [[int(y), round(float((g.g == "Z").mean()), 4),
                             round(float((g[g.MANDAT == "A"].g == "Z").mean()), 4) if (g.MANDAT == "A").any() else None]
                            for y, g in gw.groupby("year")]
    # age distribution per election (share of that year's candidates at each age, 90 = 90+), for the home curve
    ay = C.assign(age=pd.to_numeric(C.VEK, errors="coerce").clip(upper=90)).dropna(subset=["age"])
    stats["age_years"] = [{"y": int(y), "mean": round(float(g.age.mean()), 1),
                           "share": [round(float(x), 5) for x in g.age.astype(int).value_counts(normalize=True).reindex(range(18, 91), fill_value=0)]}
                          for y, g in ay.groupby("year")]
    stats["stalwarts"], stats["seventh"] = len(stalwarts), len(seventh)
    people_tpl = (ROOT / "src/stalwarts_template.html").read_text().replace("__CONTACT__", CONTACT)
    for fname, rows, title, lead in (
        ("zvoleni-od-2002.html", stalwarts, "Zvoleni ve všech volbách od roku 2002",
         "Lidé, kteří byli do zastupitelstva své obce nebo městské části zvoleni ve všech šesti komunálních volbách od roku 2002 a letos kandidují znovu."),
        ("kandiduji-posedme.html", seventh, "Kandidují posedmé",
         "Lidé, kteří kandidovali ve všech šesti komunálních volbách od roku 2002 a letos kandidují posedmé. Dřívější kandidatury mohly být i v jiné obci.")):
        (SITE / fname).write_text(people_tpl.replace("__TITLE__", title).replace("__LEAD__", lead)
                                  .replace("__DATA__", js(sorted(rows, key=lambda r: (r[3], r[2], r[0])))))
    stats["occ"] = json.load(open(ROOT / "data/derived/occ_groups.json", encoding="utf-8"))["rank"]
    stats["big"] = [[k, council_name.get(k, k)] for k in big if (SITE / "obec" / f"{k}.html").exists()]
    home = (ROOT / "src/home_template.html").read_text().replace("__INDEX__", js(index)).replace("__STATS__", js(stats))
    (SITE / "index.html").write_text(home)
    (SITE / "povolani.html").write_text((ROOT / "data/mockup/povolani.html").read_text().replace("__CONTACT__", CONTACT))
    (SITE / "metodika.html").write_text((ROOT / "src/metodika.html").read_text().replace("__CONTACT__", CONTACT)
                                         .replace("__CONTROLLER__", CONTROLLER))
    import export_open_data
    export_open_data.main(CONTACT)
    # search engines: robots.txt + sitemap of every page (indexing approved by Jan 2026-10-09)
    base = "https://mistnik.cz"
    urls = [f"{base}/", f"{base}/povolani", f"{base}/metodika", f"{base}/data"]  # zvoleni-od-2002, kandiduji-posedme: noindex, not in the sitemap + [f"{base}/obec/{r[0]}" for r in index]
    (SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    size = sum(f.stat().st_size for f in SITE.rglob("*.html"))
    print(f"{len(index)} councils, {size / 1e6:.0f} MB -> {SITE}")


if __name__ == "__main__":
    main()
