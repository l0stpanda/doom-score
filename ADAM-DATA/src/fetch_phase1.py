"""Phase 1 fetch: MLB + NHL regular-season standings from official league APIs.
Caches every raw response under data/raw/<source>/ and never re-downloads."""
import json, os, sys
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

MLB_URL = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={y}&standingsTypes=regularSeason"
MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1&season={y}"
NHL_URL = "https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId={sid}%20and%20gameTypeId=2"
NHL_TEAM_URL = "https://api.nhle.com/stats/rest/en/team"
NHL_FRANCHISE_URL = "https://api.nhle.com/stats/rest/en/franchise"

MLB_SEASONS = list(range(1997, 2027))
NHL_SEASONS = [2002, 2003] + list(range(2005, 2026))  # start years; 2004-05 cancelled

BLOCK_CODES = {403, 429}


def get(source, name, url):
    """Return parsed JSON, using cache. Returns None and prints BLOCKED/ERROR on failure."""
    d = os.path.join(RAW, source)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"  ERROR {source}/{name}: {e}")
            continue
        if r.status_code in BLOCK_CODES or "cf-chl" in r.text[:2000].lower():
            print(f"  BLOCKED {source}/{name}: HTTP {r.status_code}")
            return None
        if r.status_code != 200:
            print(f"  ERROR {source}/{name}: HTTP {r.status_code}")
            continue
        data = r.json()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    return None


def probe():
    res = {}
    for src, name, url in [
        ("mlb_standings", "2001", MLB_URL.format(y=2001)),
        ("nhl_team_summary", "20222023", NHL_URL.format(sid="20222023")),
        ("nhl_meta", "team", NHL_TEAM_URL),
        ("nhl_meta", "franchise", NHL_FRANCHISE_URL),
        ("mlb_meta", "teams_2026", MLB_TEAMS_URL.format(y=2026)),
    ]:
        res[f"{src}/{name}"] = "ok" if get(src, name, url) is not None else "BLOCKED/ERROR"
        print(f"probe {src}/{name}: {res[f'{src}/{name}']}")
    return res


def main():
    res = probe()
    if any(v != "ok" for v in res.values()):
        print("Probe failed; stopping before bulk download.")
        sys.exit(1)
    for y in MLB_SEASONS:
        ok = get("mlb_standings", str(y), MLB_URL.format(y=y)) is not None
        print(f"MLB {y}: {'ok' if ok else 'FAILED'}")
    for y in NHL_SEASONS:
        sid = f"{y}{y+1}"
        ok = get("nhl_team_summary", sid, NHL_URL.format(sid=sid)) is not None
        print(f"NHL {sid}: {'ok' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
