"""Classify candidates' free-text occupations (POVOLANI 2002-2026) into CZ-ISCO sub-major groups (2 digits).

Step 1 rules: public functions (starosta, radní, ...) are tagged separately; they are not occupations.
Step 2 Jev (typesafe/jev-1.13), hierarchical: major group 0-9 or a non-occupation status, then the sub-major group.
Only the occupation text is sent (no names). Cache + spend cap in data/derived/jev_occ.db.
Codebook: ČSÚ CZ-ISCO 1.9 (kodcis 80146), data/raw/czisco/czisco.csv.
Run: OPENROUTER_API_KEY=... python3 src/occupations.py [top_n]   -> data/derived/occupations.csv
"""
import collections, concurrent.futures as cf, csv, glob, json, os, pathlib, re, sqlite3, sys, threading, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data/raw", ROOT / "data/derived"
MODEL, API, CAP_USD = "typesafe/jev-1.13", "https://openrouter.ai/api/alpha/decisions", 4.0
STATUS = {
    "duchodce": "retired, pensioner (důchodce, důchodkyně, penzista), including disability pension",
    "student": "student or pupil (student, studentka, žák)",
    "domacnost": "on parental leave or homemaker (na mateřské, rodičovské, v domácnosti)",
    "nezamestnany": "unemployed or job seeker",
    "podnikatel": "self-employed or entrepreneur with no field given (podnikatel, OSVČ, živnostník, jednatel s.r.o.)",
    "nejasne": "too vague to classify (zaměstnanec, pracovník, manažer without field, empty)",
}
FUNCTIONS = re.compile(r"\b(starost\w*|místostarost\w*|primátor\w*|náměst\w* primátor\w*|radní|zastupitel\w*|poslan\w*|senátor\w*|hejtman\w*)", re.I)

lock = threading.Lock()
con = sqlite3.connect(DER / "jev_occ.db", check_same_thread=False)
con.execute("CREATE TABLE IF NOT EXISTS occ (step TEXT, text TEXT, choice TEXT, conf REAL, cost REAL, model TEXT, PRIMARY KEY (step, text))")


def codebook():
    r = list(csv.DictReader(open(RAW / "czisco/czisco.csv", encoding="utf-8")))
    major = {x["chodnota"]: x["text"] for x in r if x["uroven"] == "1"}
    sub = collections.defaultdict(dict)
    for x in r:
        if x["uroven"] == "2":
            sub[x["chodnota"][0]][x["chodnota"]] = x["text"]
    return major, sub


def norm(s):
    return re.sub(r"\s+", " ", s.lower()).strip(" ,.;-")


def choose(step, text, instructions, criteria):
    with lock:  # one sqlite connection across threads only under a lock (segfault otherwise, knowdb)
        if (h := con.execute("SELECT choice, conf FROM occ WHERE step=? AND text=?", (step, text)).fetchone()):
            return h
        if con.execute("SELECT COALESCE(SUM(cost), 0) FROM occ").fetchone()[0] >= CAP_USD:
            raise SystemExit(f"Jev spend cap {CAP_USD} USD")
    body = json.dumps({"model": MODEL, "state": {"text": f"Occupation written by a Czech election candidate: {text}"},
                       "questions": {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}}}).encode()
    req = urllib.request.Request(API, data=body, headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                                          "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            break
        except (urllib.error.URLError, OSError):
            if attempt == 3:
                return None, None
            time.sleep(10 * (attempt + 1))
    a = d["answers"]["q"]
    with lock:
        con.execute("INSERT OR IGNORE INTO occ VALUES (?, ?, ?, ?, ?, ?)",
                    (step, text, a.get("choice"), a.get("confidence"), d.get("usage", {}).get("cost") or 0, d.get("model")))
        con.commit()
    return a.get("choice"), a.get("confidence")


def classify(text, major, sub):
    m_crit = {f"g{k}": v for k, v in major.items()} | STATUS
    c1, p1 = choose("major", text, "Classify the occupation into a CZ-ISCO major group (Czech classification of occupations), "
                    "or into a status if it is not an occupation. Use the person's actual field of work; a degree title alone is not a field.", m_crit)
    if not c1 or not c1.startswith("g"):
        return c1, p1, None, None
    g = c1[1:]
    if len(sub[g]) == 1:
        return c1, p1, next(iter(sub[g])), 1.0
    c2, p2 = choose(f"sub{g}", text, f"Which CZ-ISCO sub-major group within '{major[g]}' fits this occupation best?",
                    {f"s{k}": v for k, v in sub[g].items()})
    return c1, p1, (c2 or "")[1:] or None, p2


def main(top_n):
    major, sub = codebook()
    raw = collections.Counter()
    for p in glob.glob(str(RAW / "kv*/**/csv_od/kvrk.csv"), recursive=True):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            raw[norm(r["POVOLANI"])] += 1
    total = sum(raw.values())
    todo = [t for t, _ in raw.most_common(top_n) if t]
    print(f"{len(raw)} distinct occupations, classifying top {len(todo)} covering {sum(raw[t] for t in todo) / total:.1%}", flush=True)
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda t: classify(t, major, sub), todo))
    with open(DER / "occupations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["text", "count", "major", "major_conf", "submajor", "submajor_conf", "functions"])
        for t, (c1, p1, s2, p2) in zip(todo, res):
            w.writerow([t, raw[t], c1, p1, s2, p2, ";".join(sorted({m.lower() for m in FUNCTIONS.findall(t)}))])
    cats = collections.Counter()
    for t, (c1, _, s2, _) in zip(todo, res):
        cats[s2 or c1] += raw[t]
    print("top categories by candidacies:", cats.most_common(15))
    print(f"spent {con.execute('SELECT SUM(cost) FROM occ').fetchone()[0]:.4f} USD")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
