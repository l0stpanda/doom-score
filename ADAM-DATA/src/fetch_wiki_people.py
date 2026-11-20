"""Fetch individual Wikipedia articles (GMs on team pages that list names without years).
Same rules as fetch_wiki_batch.py: MediaWiki Action API, <=50 titles/request, >=3 s apart, descriptive UA,
stop using Wikipedia on any 429/403. Cached under data/raw/wikipedia_people/<title>.json."""
import json, os, re, sys, time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_wiki_batch import UA, API
import parse_front_office as pf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "raw", "wikipedia_people")
TEAM_PAGES = {"atlanta-braves": "Atlanta Braves", "baltimore-orioles": "Baltimore Orioles",
              "cincinnati-reds": "Cincinnati Reds"}


def gm_titles():
    """franchise_id -> article titles listed (in page order) under the team page's GM section."""
    out = {}
    for fid, team in TEAM_PAGES.items():
        t = pf.wikitext(f"List of {team} owners and executives")
        for h, b in pf.sections(t):
            if re.search("general manager", h, re.I):
                out.setdefault(fid, []).extend(
                    m.group(1) for m in re.finditer(r"^\*\s*\[\[([^|\]]+)(?:\|[^\]]*)?\]\]", b, flags=re.M))
    return out


def path(title):
    return os.path.join(D, re.sub(r'[\\/:*?"<>|]', "_", title) + ".json")


def main():
    os.makedirs(D, exist_ok=True)
    titles = sorted({t for ts in gm_titles().values() for t in ts})
    missing = [t for t in titles if not os.path.exists(path(t))]
    print(f"articles: {len(titles)}, to fetch: {len(missing)}", flush=True)
    s = requests.Session()
    for i in range(0, len(missing), 50):
        if i:
            time.sleep(3)
        batch = missing[i:i + 50]
        r = s.get(API, headers={"User-Agent": UA}, timeout=60, params=dict(
            action="query", prop="revisions", rvprop="content", rvslots="main", redirects=1,
            format="json", formatversion=2, titles="|".join(batch)))
        if r.status_code in (403, 429):
            print(f"BLOCKED HTTP {r.status_code} Retry-After={r.headers.get('Retry-After')} -> stop", flush=True)
            return
        r.raise_for_status()
        q = r.json()["query"]
        norm = {x["from"]: x["to"] for x in q.get("normalized", [])}
        red = {x["from"]: x["to"] for x in q.get("redirects", [])}
        pages = {p["title"]: p for p in q["pages"]}
        n = 0
        for t in batch:
            tt = red.get(norm.get(t, t), norm.get(t, t))
            p = pages.get(tt)
            if p and "revisions" in p:
                with open(path(t), "w", encoding="utf-8") as f:
                    json.dump({"title": tt, "wikitext": p["revisions"][0]["slots"]["main"]["content"]}, f)
                n += 1
            else:
                print(f"  not found: {t}")
        print(f"batch {i // 50 + 1}: HTTP {r.status_code}, cached {n}/{len(batch)}", flush=True)


if __name__ == "__main__":
    main()
