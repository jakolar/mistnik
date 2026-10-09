"""Local labelling app: serves the blind sample and appends every decision to data/derived/labels.csv.

Run: python3 src/label_server.py [port]   then open http://jans-mac-mini.local:<port>/  (LAN only, real names)
"""
import csv, datetime as dt, http.server, json, pathlib, sys, threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER = ROOT / "data/derived"
LABELS = DER / "labels.csv"
lock = threading.Lock()


def load_labels():
    if not LABELS.exists():
        return {}
    out = {}
    for r in csv.DictReader(open(LABELS, encoding="utf-8")):
        out[r["key"]] = {"label": r["label"], "note": r["note"]}  # last decision wins
    return out


class H(http.server.BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.send(200, (ROOT / "src/label.html").read_bytes(), "text/html")
        if self.path == "/sample":
            sample = json.load(open(DER / "label_sample.json", encoding="utf-8"))
            for r in sample:
                r.pop("stratum", None)  # blind: the labeller never sees the model's grouping
            return self.send(200, json.dumps(sample, ensure_ascii=False))
        if self.path == "/labels":
            return self.send(200, json.dumps(load_labels(), ensure_ascii=False))
        self.send(404, "{}")

    def do_POST(self):
        if self.path != "/label":
            return self.send(404, "{}")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send(415, '{"error": "json only"}')  # a plain form from another page cannot write labels
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            assert isinstance(d.get("key"), str) and d["key"] in SAMPLE_KEYS
            assert d.get("label") in ("same", "different", "unsure") and isinstance(d.get("note", ""), str)
        except Exception:
            return self.send(400, '{"error": "bad request"}')
        with lock:
            new = not LABELS.exists()
            with open(LABELS, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["time", "key", "label", "note"])
                w.writerow([dt.datetime.now().isoformat(timespec="seconds"), d["key"], d["label"], (d.get("note") or "")[:500]])
        self.send(200, '{"ok": true}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    SAMPLE_KEYS = {r["key"] for r in json.load(open(DER / "label_sample.json", encoding="utf-8"))}
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8094
    print(f"http://jans-mac-mini.local:{port}/")
    http.server.ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
