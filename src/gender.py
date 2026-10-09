"""Gender estimate from a Czech name: 'Z' (female), 'M' (male) or None (not determined). An estimate, not identity.

1. First name in the official MV list as male/female -> that.
   Neutral or unknown names: MV birth counts 1970-2015 (jmenovac) if >= 95 % one gender.
2. Surname: -á/-ová marks a woman; a male form proves nothing (women may keep a non-ová surname since 2022).
3. Conflict (male first name + female surname form) -> None.
"""
import pathlib
import pandas as pd

JM = pathlib.Path.home() / "projekty/jmenovac/data"


def _first_names():
    off = pd.read_csv(JM / "jmena_uredni.csv", dtype=str, keep_default_na=False).set_index("jmeno").seznam
    mv = pd.read_csv(JM / "jmena_mv.csv", dtype=str)
    mv["pocet"] = mv.pocet.astype(int)
    share = mv.pivot_table(index="jmeno", columns="pohlavi", values="pocet", aggfunc="sum", fill_value=0)
    share = share.div(share.sum(axis=1), axis=0)
    out = {n: (g, "official") for n, g in off.items() if g in ("M", "Z")}
    for n, row in share.iterrows():
        if n not in out:
            top = row.idxmax()
            if row[top] >= 0.95:
                out[n] = (top, "births")  # 1970-2015 births only: older bearers may differ (Vlasta, Nikola)
    return out


FIRST = _first_names()
# Names borne by both sexes in older cohorts although 1970-2015 births are one-sided (Vlasta Burian, Nikola Šuhaj).
# ponytail: hand list, extend when the labelled sample shows another one
UNISEX = {"Vlasta", "Nikola", "Saša", "Jindra", "Andrea", "Kim", "Míša", "René", "Noel", "Mája"}


def gender(jmeno, prijmeni):
    first = (jmeno or "").split()[0] if jmeno else ""
    g, src = FIRST.get(first, (None, None))
    fem_surname = (prijmeni or "").strip().lower().endswith("á")
    if g == "M" and fem_surname:
        return None
    if first in UNISEX:
        return "Z" if fem_surname else None
    if g:
        return g
    return "Z" if fem_surname else None


if __name__ == "__main__":
    assert gender("Jana", "Nováková") == "Z" and gender("Petr", "Novák") == "M"
    assert gender("Martina", "Polakovič") == "Z"          # woman without -ová
    assert gender("Petr", "Nováková") is None             # conflict
    assert gender("Vlasta", "Burian") is None and gender("Vlasta", "Buriánová") == "Z"
    print("ok")
