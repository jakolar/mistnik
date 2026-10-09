"""Second opinion on occupation groups: Gemini reviews our assignment of the top occupation texts.

Sends only occupation texts and our group (no names, approved by Jan 2026-10-09). Batches of 50, JSON output.
Output: data/derived/occ_gemini.csv (text, count, ours, gemini, agree) and a weighted disagreement rate.
Run: OPENROUTER_API_KEY=... python3 src/occ_gemini_check.py
"""
import concurrent.futures as cf, json, os, pathlib, re, sys, time, urllib.error, urllib.request
import pandas as pd

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import occ_cards as O

DER = pathlib.Path(__file__).resolve().parent.parent / "data/derived"
MODEL = "google/gemini-3.8-flash"  # via OpenRouter (direct Google keys were invalid or capped on 2026-10-09)
URL = "https://openrouter.ai/api/v1/chat/completions"
LABELS = list(O.GROUPS) + [v for k, v in O.STATUS_CS.items() if k]


def our_group(texts, occ):
    D = pd.DataFrame({"text": texts})
    D["cat"] = D.text.map(occ.submajor.where(occ.submajor != "", occ.major)).fillna("")
    skip = D.text.str.contains(r"dobrovoln|výslužb|bývalý|důchod", regex=True)
    for pat, cat in O.OVERRIDES:
        D.loc[D.text.str.contains(pat, regex=True) & ~skip, "cat"] = cat
    D["grp"] = D.cat.map(lambda c: O.GROUP_OF.get(c, c))
    animals = D.text.str.contains(O.NOT_HUMAN_CARE, regex=True)
    for pat, grp in O.GROUP_OVERRIDES:
        D.loc[D.text.str.contains(pat, regex=True) & ~skip & ~animals, "grp"] = grp
    return D.grp.map(lambda g: O.STATUS_CS.get(g, g)).tolist()


def ask(batch):
    prompt = ("Below are occupations written by Czech municipal-election candidates, each with the group we assigned. "
              "Groups (use exactly these names):\n" + "\n".join(f"- {l}" for l in LABELS) +
              "\n\nFor each item say whether our group is right. If not, give the best group from the list. "
              "A public office (starosta, poslanec) belongs to 'Politici a veřejné funkce'; a retired person whose text names a "
              "former job is 'Důchodci'; a volunteer role (dobrovolný hasič) is not an occupation. "
              "Return JSON: {\"items\": [{\"i\": int, \"ok\": bool, \"group\": string}]}.\n\n" +
              "\n".join(f"{i}. {t} -> {g}" for i, t, g in batch))
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                       "response_format": {"type": "json_object"}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json",
                                                          "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            return json.loads(d["choices"][0]["message"]["content"])["items"], d.get("usage", {})
        except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as e:
            if attempt == 3:
                print("batch failed:", e, flush=True)
                return [], {}
            time.sleep(15 * (attempt + 1))


def main(top_n=5000):
    occ = pd.read_csv(DER / "occupations.csv", dtype=str, keep_default_na=False).set_index("text")
    occ = occ[occ.index != ""]
    texts = list(occ.index[:top_n])
    ours = our_group(texts, occ)
    items = list(zip(range(len(texts)), texts, ours))
    batches = [items[i:i + 50] for i in range(0, len(items), 50)]
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(ask, batches))
    verdict, tok = {}, [0, 0]
    for answers, usage in res:
        tok[0] += usage.get("prompt_tokens", 0)
        tok[1] += usage.get("cost", 0) or 0
        for a in answers:
            if isinstance(a, dict) and "i" in a:
                verdict[a["i"]] = a
    out = pd.DataFrame({"text": texts, "count": occ["count"].astype(int).values[:len(texts)], "ours": ours})
    out["gemini"] = [verdict.get(i, {}).get("group", "") for i in range(len(texts))]
    out["agree"] = [bool(verdict.get(i, {}).get("ok")) or verdict.get(i, {}).get("group") == g for i, g in enumerate(ours)]
    out["answered"] = [i in verdict for i in range(len(texts))]
    out.to_csv(DER / "occ_gemini.csv", index=False)
    a = out[out.answered]
    print(f"answered {len(a)}/{len(out)}; disagree {(~a.agree).sum()} texts, "
          f"{(a['count'] * ~a.agree).sum() / a['count'].sum():.1%} of candidacies; tokens in {tok[0]}, cost {tok[1]:.3f} USD")
    print(a[~a.agree].sort_values("count", ascending=False).head(25)[["text", "count", "ours", "gemini"]].to_string(index=False))


if __name__ == "__main__":
    main()
