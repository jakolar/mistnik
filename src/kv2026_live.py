"""Archive live KV2026 result XMLs from volby.gov.cz during the count.

The live feed is deleted after the election, so we keep:
  - vysledky.xml (national totals) whenever it changes
  - every incremental batch of okrsky/ and obce_d/ (append-only, numbered)
  - snapshots of all district XMLs (okresy/) every 15 min, only files that changed
Usage: nohup caffeinate -i python3 src/kv2026_live.py &
"""
import csv, datetime as dt, glob, hashlib, pathlib, re, time, urllib.error, urllib.request

BASE = "https://volby.gov.cz/appdata/kv2026/20261009/odata"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data/live/kv2026"
STOP = dt.datetime(2026, 10, 11, 18, 0)
OKRES_EVERY = 15 * 60

NUTS = sorted({r["NUTS"] for r in csv.DictReader(open(glob.glob(str(ROOT / "data/raw/kv2026/*cisel*/csv_od/cnumnuts.csv"))[0], encoding="utf-8")) if len(r["NUTS"]) == 6})
GEN = re.compile(rb'DATUM_CAS_GENEROVANI="[^"]*"')


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(OUT / "live.log", "a") as f:
        f.write(line + "\n")


def get(path):
    """Return body, or None on 404 / not-yet-available batch (CHYBA KOD_CHYBY=10)."""
    try:
        with urllib.request.urlopen(f"{BASE}/{path}", timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if b"<CHYBA" in body:
        return None
    return body


def digest(body):
    return hashlib.sha256(GEN.sub(b"", body)).hexdigest()


def save(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def next_batch(sub):
    done = sorted((OUT / sub).glob("*.xml"))
    return int(done[-1].stem.rsplit("_", 1)[1]) + 1 if done else 1


def pull_batches(sub, prefix):
    n = next_batch(sub)
    while (body := get(f"{sub}/{prefix}_{n:05d}.xml")) is not None:
        save(OUT / sub / f"{prefix}_{n:05d}.xml", body)
        log(f"{sub} batch {n} ({len(body)} B)")
        n += 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"start, {len(NUTS)} okresu, stop {STOP}")
    last_cr, last_okres_at, okres_hash = None, 0.0, {}
    while dt.datetime.now() < STOP:
        try:
            body = get("vysledky.xml")
            if body and digest(body) != last_cr:
                last_cr = digest(body)
                save(OUT / "vysledky" / f"{dt.datetime.now():%Y%m%dT%H%M%S}.xml", body)
                log("vysledky.xml changed")
            pull_batches("okrsky", "vysledky_okrsky")
            pull_batches("obce_d", "vysledky_obce")
            counting = any((OUT / "okrsky").glob("*.xml"))
            if counting and time.time() - last_okres_at > OKRES_EVERY:
                ts, changed = f"{dt.datetime.now():%Y%m%dT%H%M%S}", 0
                for nuts in NUTS:
                    b = get(f"okresy/vysledky_obce_okres_{nuts}.xml")
                    if b and digest(b) != okres_hash.get(nuts):
                        okres_hash[nuts] = digest(b)
                        save(OUT / "okresy" / ts / f"{nuts}.xml", b)
                        changed += 1
                last_okres_at = time.time()
                log(f"okresy snapshot {ts}: {changed} changed")
        except Exception as e:  # ponytail: network blips just retry next tick
            log(f"error {type(e).__name__}: {e}")
        time.sleep(60)
    log("stop")


if __name__ == "__main__":
    main()
