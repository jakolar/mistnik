"""Open data for checking the person linkage (Jan 2026-10-09: links without names, uncertain links in a separate file).

No names, ages or MV-derived numbers: candidacies are referenced by their ČSÚ key, anyone can join names from volby.gov.cz.
Writes site/data/*.csv.gz + site/data.html.  Run after cluster.py and occ_cards.py (build_site.py calls it).
"""
import pathlib, shutil
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER, SITE = ROOT / "data/derived", ROOT / "site"
PUBLISHED = ["auto_match", "auto_jev", "implied"]
UNCERTAIN = ["manual_review", "manual_review_namesake", "possible_match"]
COLS = ["id_a", "id_b", "decision", "p", "geo", "cocand", "party", "titles", "occ", "list_party", "same_list", "same_res", "second", "jev_pair"]


def main(contact="opravy@mistnik.cz"):
    out = SITE / "data"
    out.mkdir(parents=True, exist_ok=True)
    C = pd.read_csv(DER / "cluster_persons.csv.gz", dtype=str, keep_default_na=False, usecols=["id", "person"])
    # opaque person number instead of the internal key (which contains the name)
    keys = pd.Series(C.person.unique()).sample(frac=1, random_state=2026).values  # random order: number says nothing about the name
    C["osoba"] = C.person.map({k: i + 1 for i, k in enumerate(keys)})
    C[["id", "osoba"]].rename(columns={"id": "kandidatura"}).sort_values("kandidatura").to_csv(out / "osoby.csv.gz", index=False)
    E = pd.read_csv(DER / "cluster_edges.csv.gz", usecols=COLS)
    E["p"] = pd.to_numeric(E.p, errors="coerce").round(5)
    E[E.decision.isin(PUBLISHED)].to_csv(out / "spojeni.csv.gz", index=False)
    U = E[E.decision.isin(UNCERTAIN)]
    if (DER / "jev_pair3.csv").exists():
        U = U.merge(pd.read_csv(DER / "jev_pair3.csv", usecols=["id_a", "id_b", "jev3"]), on=["id_a", "id_b"], how="left")
    U.to_csv(out / "nejista_spojeni.csv.gz", index=False)
    shutil.copy(DER / "occ_rank.csv", out / "povolani_zvolitelnost.csv")
    sizes = {f.name: f"{f.stat().st_size / 1e6:.1f} MB" for f in out.iterdir()}
    page = (ROOT / "src/data.html").read_text()
    for k, v in sizes.items():
        page = page.replace(f"__{k}__", v)
    page = page.replace("__N_OSOBY__", f"{C.osoba.max():,}".replace(",", " ")).replace("__N_SPOJENI__", f"{E.decision.isin(PUBLISHED).sum():,}".replace(",", " ")) \
               .replace("__N_NEJISTA__", f"{len(U):,}".replace(",", " "))
    (SITE / "data.html").write_text(page.replace("__CONTACT__", contact))
    print(sizes)


if __name__ == "__main__":
    main()
