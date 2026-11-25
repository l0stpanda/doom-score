"""Download each franchise's current logo (map/data_src/team_logos.csv logo_url) for the Doom Map (M53).

Saves dashboard/assets/logos/<league>_<franchise_id>.svg, the same git-ignored cache the older scatter page uses
(logos are trademarks: fine for a class prototype, not redistributed in the repo). Existing files are not downloaded
again. Only SVG responses are kept; anything else falls back to a monogram on the map. Failures are listed.
Run by `map/build_map.py --fetch-logos` (and by map/add_scores.py).
"""
import os, sys, time
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)
OUT = os.path.join(ROOT, "dashboard", "assets", "logos")


def main(leagues=None):
    os.makedirs(OUT, exist_ok=True)
    T = pd.read_csv(os.path.join(MAP, "data_src", "team_logos.csv"))
    if leagues:
        T = T[T.league.isin(leagues)]
    s = requests.Session()
    s.headers["User-Agent"] = "doom-map-build/0.1"
    got, fails = 0, []
    for r in T.itertuples(index=False):
        path = os.path.join(OUT, f"{r.league}_{r.franchise_id}.svg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        try:
            resp = s.get(r.logo_url, timeout=30)
            ok = resp.status_code == 200 and b"<svg" in resp.content[:4000].lower()
        except requests.RequestException:
            ok, resp = False, None
        if ok:
            with open(path, "wb") as f:
                f.write(resp.content)
            got += 1
        else:
            fails.append(f"{r.league} {r.franchise_id}: {getattr(resp, 'status_code', 'error')} {r.logo_url}")
        time.sleep(0.2)
    have = sum(os.path.exists(os.path.join(OUT, f"{r.league}_{r.franchise_id}.svg")) for r in T.itertuples(index=False))
    print(f"logos: {have} of {len(T)} cached ({got} downloaded now), {len(fails)} failed")
    for f in fails:
        print("  failed:", f)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
