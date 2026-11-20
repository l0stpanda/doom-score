"""Download each franchise's current logo (team_meta.csv logo_url) to dashboard/assets/logos/<league>_<franchise>.svg.
The folder is git-ignored: team logos are trademarks, fine for a class prototype but not redistributed in the
repo. Cached: existing files are not re-downloaded. Failures are listed in dashboard/assets/logos/_failures.csv.
Run: PYTHONUTF8=1 python ADAM-DATA/src/viz/fetch_logos.py"""
import os, time
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
META = os.path.join(ROOT, "dashboard", "data", "team_meta.csv")
OUT = os.path.join(ROOT, "dashboard", "assets", "logos")


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = pd.read_csv(META)
    fails = []
    s = requests.Session()
    s.headers["User-Agent"] = "doom-score-class-prototype/0.1"
    for _, r in meta.iterrows():
        path = os.path.join(OUT, f"{r.league}_{r.franchise_id}.svg")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        try:
            resp = s.get(r.logo_url, timeout=30)
            ok = resp.status_code == 200 and b"<svg" in resp.content[:2000].lower()
        except requests.RequestException as e:
            ok, resp = False, None
        if ok:
            open(path, "wb").write(resp.content)
        else:
            fails.append({"league": r.league, "franchise_id": r.franchise_id, "url": r.logo_url,
                          "status": getattr(resp, "status_code", "error")})
        time.sleep(0.2)
    pd.DataFrame(fails, columns=["league", "franchise_id", "url", "status"]).to_csv(
        os.path.join(OUT, "_failures.csv"), index=False)
    n = len([f for f in os.listdir(OUT) if f.endswith(".svg")])
    print(f"logos: {n} files, {len(fails)} failures")


if __name__ == "__main__":
    main()
