import datetime as dt, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from linkage import birth_window

D18, D22 = dt.date(2018, 10, 5), dt.date(2022, 9, 23)


def overlap(a, b):
    return (min(a[1], b[1]) - max(a[0], b[0])).days + 1


def test_birth_window():
    assert overlap(birth_window(D18, 39), birth_window(D22, 43)) > 300   # usual +4
    assert 0 < overlap(birth_window(D18, 39), birth_window(D22, 42)) <= 13  # birthday between the two election dates
    assert overlap(birth_window(D18, 39), birth_window(D22, 44)) <= 0     # +5 impossible


def test_transitivity_guard():
    import types
    import numpy as np, pandas as pd
    sys.modules.setdefault("jev_fields", types.ModuleType("jev_fields"))  # no API or cache needed
    from cluster import SafeClusters
    d = np.datetime64("1970-01-01")
    nodes = pd.DataFrame({"year": [2010, 2014, 2018], "blo": [d] * 3, "bhi": [d] * 3}, index=["2010|a", "2014|a", "2018|a"])
    cl = SafeClusters(nodes, {("2010|a", "2014|a"): 0.9999, ("2014|a", "2018|a"): 0.9999, ("2010|a", "2018|a"): 0.2})
    cl.union("2010|a", "2014|a")
    assert not cl.direct_ok("2014|a", "2018|a")  # A~B, B~C but direct A-C weak: refuse
    del cl.pmap[("2010|a", "2018|a")]
    assert not cl.direct_ok("2014|a", "2018|a")  # no direct evidence at all: refuse
    cl.pmap[("2010|a", "2018|a")] = 0.95
    assert cl.direct_ok("2014|a", "2018|a")


def test_double_surname_forms():
    from linkage import name_norm
    assert name_norm("Nováková - Svobodová") == name_norm("Nováková-Svobodová") == name_norm("Nováková Svobodová")


if __name__ == "__main__":
    test_double_surname_forms()
    test_birth_window()
    test_transitivity_guard()
    print("ok")
