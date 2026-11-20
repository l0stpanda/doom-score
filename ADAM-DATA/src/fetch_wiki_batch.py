"""One compliant retry of the Wikipedia pages missing after the HTTP 429 in fetch_phase2.py.
Waits >= 5 min, then uses the MediaWiki Action API with up to 50 titles per request, >= 2 s apart.
On any 429 it stops for good (no further Wikipedia requests). Cached in the same format as fetch_phase2."""
import json, os, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_phase2 import wiki_pages
from fetch_phase1 import RAW

UA = "DoomViz-UW-DATA511/0.1 (student project; contact: https://github.com/AdamRychtecky8)"
API = "https://en.wikipedia.org/w/api.php"
D = os.path.join(RAW, "wikipedia")
STATUS = os.path.join(D, "_batch_retry_status.json")


def path(page):
    return os.path.join(D, page.replace("/", "_") + ".json")


def main(wait=300):
    missing = [p for p in wiki_pages() if not os.path.exists(path(p))]
    print(f"missing pages: {len(missing)}; waiting {wait}s before the single retry", flush=True)
    time.sleep(wait)
    status = {"requests": 0, "fetched": 0, "result": "ok", "retry_after": None}
    for i in range(0, len(missing), 50):
        batch = missing[i:i + 50]
        if i:
            time.sleep(3)
        # own Session: fetch_phase2 monkeypatches the module-level requests.get on import
        r = requests.Session().get(API, headers={"User-Agent": UA}, timeout=60, params=dict(
            action="query", prop="revisions", rvprop="content", rvslots="main", redirects=1,
            format="json", formatversion=2, titles="|".join(batch)))
        status["requests"] += 1
        if r.status_code == 429 or r.status_code == 403:
            status.update(result=f"BLOCKED HTTP {r.status_code}", retry_after=r.headers.get("Retry-After"))
            print(f"BLOCKED: HTTP {r.status_code}, Retry-After={status['retry_after']} -> stop using Wikipedia", flush=True)
            break
        r.raise_for_status()
        q = r.json()["query"]
        norm = {x["from"]: x["to"] for x in q.get("normalized", [])}
        red = {x["from"]: x["to"] for x in q.get("redirects", [])}
        pages = {p["title"]: p for p in q["pages"]}
        for t in batch:
            tt = norm.get(t, t)
            tt = red.get(tt, tt)
            p = pages.get(tt)
            if not p or p.get("missing") or "revisions" not in p:
                print(f"  not found: {t}", flush=True)
                continue
            wt = p["revisions"][0]["slots"]["main"]["content"]
            with open(path(t), "w", encoding="utf-8") as f:
                json.dump({"parse": {"title": tt, "wikitext": wt, "via": "action=query batch retry"}}, f)
            status["fetched"] += 1
        print(f"batch {i // 50 + 1}: HTTP {r.status_code}, cached so far {status['fetched']}", flush=True)
    with open(STATUS, "w") as f:
        json.dump(status, f)
    print("status:", status, flush=True)


if __name__ == "__main__":
    main()
