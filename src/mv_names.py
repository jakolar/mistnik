"""Extract MV ČR first-name x birth-year and surname x birth-year counts (snapshot Jan 2017).

Source zips live in ~/projekty/jmenovac/data/raw/mvcr (see PROVENANCE.md there).
Needs xlrd, run with: ~/projekty/jmenovac/.venv/bin/python src/mv_names.py
Output (long, count > 0): data/derived/mv_{jmena,prijmeni}_dnar.csv  name,year,count
"""
import csv, pathlib, zipfile
import xlrd


def cell_name(sh, r, v):
    """Excel stores the surnames PRAVDA/NEPRAVDA as booleans (Czech TRUE/FALSE); str() would give '1'/'0'."""
    if sh.cell_type(r, 0) == xlrd.XL_CELL_BOOLEAN:
        return "PRAVDA" if v else "NEPRAVDA"
    return str(v).strip()

SRC = pathlib.Path.home() / "projekty/jmenovac/data/raw/mvcr"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data/derived"


def extract(zip_name, out_name):
    zf = zipfile.ZipFile(SRC / zip_name)
    wb = xlrd.open_workbook(file_contents=zf.read(zf.infolist()[0]), on_demand=True)
    n = 0
    with open(OUT / out_name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "year", "count"])
        for i in range(wb.nsheets):
            sh = wb.sheet_by_index(i)
            years = [int(y) for y in sh.row_values(0)[1:]]
            for r in range(1, sh.nrows):
                row = sh.row_values(r)
                name = cell_name(sh, r, row[0])
                if not name or name == "SOUČET":
                    continue
                for y, c in zip(years, row[1:]):
                    if 1899 <= y <= 2017 and c:
                        w.writerow([name, y, int(c)])
                        n += 1
            wb.unload_sheet(i)
    print(out_name, n, "rows")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    extract("jmena-dnar-2017.zip", "mv_jmena_dnar.csv")
    extract("prijmeni-dnar-2017.zip", "mv_prijmeni_dnar.csv")
