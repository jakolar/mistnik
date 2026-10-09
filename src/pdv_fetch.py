"""Fetch programydovoleb.cz per-town candidate histories (their own person linkage, CC BY 4.0) for a stratified sample.

One request per council, 2 s apart; budget agreed with Jan: max 200 requests in total.
Run: python3 src/pdv_fetch.py [n]   -> data/raw/pdv/<KODZASTUP>.json
"""
import json, pathlib, sys, time, urllib.request
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import linkage as L

OUT = L.ROOT / "data/raw/pdv"
STRATA = [(0, 1000, 0.40), (1000, 20000, 0.33), (20000, 100000, 0.20), (100000, 10**8, 0.07)]


def main(n=150):
    rz = L.read(2026, "kvrzcoco").drop_duplicates("KODZASTUP")
    rz["pop"] = pd.to_numeric(rz.POCOBYV, errors="coerce")
    picks = []
    for lo, hi, share in STRATA:
        d = rz[(rz["pop"] >= lo) & (rz["pop"] < hi)]
        picks += list(d.sample(min(len(d), round(n * share)), random_state=11).KODZASTUP)
    OUT.mkdir(parents=True, exist_ok=True)
    budget = int((OUT / "budget").read_text()) if (OUT / "budget").exists() else 0  # requests already spent
    fails = 0
    for i, kod in enumerate(picks):
        f = OUT / f"{kod}.json"
        if f.exists():
            continue
        req = urllib.request.Request(f"https://programydovoleb.cz/api.php?action=/town/history-candidates/{kod}",
                                     headers={"User-Agent": "Mozilla/5.0 mistnik-research"})
        if budget >= 200:
            print("request budget 200 reached", flush=True)
            break
        budget += 1
        (OUT / "budget").write_text(str(budget))
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                f.write_bytes(r.read())
            fails = 0
        except Exception as e:
            fails += 1
            print(kod, "error", e, flush=True)
            if fails >= 3:
                print("3 errors in a row, stopping", flush=True)
                break
        print(f"{i + 1}/{len(picks)} {kod} (requests spent {budget})", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
