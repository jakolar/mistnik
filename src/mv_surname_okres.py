"""Extract MV ČR surname x district counts (Jan 2017) -> data/derived/mv_prijmeni_okres.csv  surname,nuts,count

The MV file is named "příjmení × obec" but its columns are ORP offices, Praha districts and region totals;
ORP offices and Praha districts are summed into districts (okres, Praha = CZ0100), region totals are skipped.
Local model input only: never display or publish the values (knowdb mvcr-cetnosti-jmen-a-prijmeni).
Run: ~/projekty/jmenovac/.venv/bin/python src/mv_surname_okres.py
"""
import collections, csv, pathlib, zipfile
import xlrd


def cell_name(sh, r, v):
    """Excel stores the surnames PRAVDA/NEPRAVDA as booleans (Czech TRUE/FALSE); str() would give '1'/'0'."""
    if sh.cell_type(r, 0) == xlrd.XL_CELL_BOOLEAN:
        return "PRAVDA" if v else "NEPRAVDA"
    return str(v).strip()

SRC = pathlib.Path.home() / "projekty/jmenovac/data/raw/mvcr"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data/derived/mv_prijmeni_okres.csv"

cis = xlrd.open_workbook(SRC / "stare-2011-ciselniky.xls")
ok, ur = cis.sheet_by_name("okresy"), cis.sheet_by_name("urady")
district = {}
for r in range(1, ok.nrows):
    code, _, n = ok.row_values(r)[:3]
    if n and n != "CZZZZZ":
        district[int(code)] = "CZ0100" if n.startswith("CZ01") else n
# Columns mix three levels: ORP offices (type N), Praha districts (P) and region totals (K, plus F/R).
# Only N and P partition the population; K would count everyone twice.
nuts = {}
for r in range(1, ur.nrows):
    code, _, _, typ, okres = ur.row_values(r)[:5]
    if typ in ("N", "P") and okres:
        nuts[int(code)] = "CZ0100" if typ == "P" else district.get(int(okres))
zf = zipfile.ZipFile(SRC / "prijmeni-obec-2017.zip")
wb = xlrd.open_workbook(file_contents=zf.read(zf.infolist()[0]), on_demand=True)
rows = 0
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["surname", "nuts", "count"])
    for i in range(wb.nsheets):
        sh = wb.sheet_by_index(i)
        cols = [nuts.get(int(c)) for c in sh.row_values(0)[1:]]
        for r in range(1, sh.nrows):
            row = sh.row_values(r)
            name = cell_name(sh, r, row[0])
            if not name:
                continue
            agg = collections.Counter()
            for n, c in zip(cols, row[1:]):
                if n and c:
                    agg[n] += int(c)
            for n, c in agg.items():
                w.writerow([name, n, c])  # SOUČET row kept: it gives district population
                rows += 1
        wb.unload_sheet(i)
unmapped = [int(c) for c in wb.sheet_by_index(0).row_values(0)[1:] if not nuts.get(int(c))]
pop = collections.Counter()
for r in csv.DictReader(open(OUT, encoding="utf-8")):
    if r["surname"] == "SOUČET":
        pop[r["nuts"]] += int(r["count"])
print(OUT, rows, "rows;", len(pop), "districts;", sum(pop.values()), "people; unmapped columns:", unmapped)
assert len(pop) == 77 and 10_000_000 < sum(pop.values()) < 11_000_000, "district coverage incomplete"
