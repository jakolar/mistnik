"""Re-apply src/obec_template.html to already built site/obec pages (template-only changes, no data rebuild)."""
import pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from build_site import CONTACT, obec_desc
import html, json
tpl = (ROOT / "src/obec_template.html").read_text()
files = [ROOT / "site/obec" / f"{k}.html" for k in sys.argv[1:]] or sorted((ROOT / "site/obec").glob("*.html"))
for f in files:
    s = f.read_text()
    town = re.search(r"<h1>(.*?)</h1>", s).group(1)
    data = re.search(r"^const people = (.*);$", s, re.M).group(1)
    meta = re.search(r"^const meta = (.*);$", s, re.M).group(1)
    desc = html.escape(obec_desc(html.unescape(town), json.loads(data.replace("<\\/", "</"))), quote=True)
    f.write_text(tpl.replace("__DESC__", desc).replace("__KOD__", f.stem).replace("__TOWN__", town).replace("__CONTACT__", CONTACT).replace("__DATA__", data, 1).replace("__META__", meta, 1))
print(len(files))
