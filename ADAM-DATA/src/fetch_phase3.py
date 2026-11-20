"""Phase 3 fetch: player-level stints (per team) + birthdates, and NHL team underlying metrics.
Usage: python fetch_phase3.py mlb|nhl|mp     (all responses cached under data/raw/<source>/)
- MLB: /stats?stats=season&group=hitting|pitching&season=Y&teamId=T -> stint stats for that team only
  (verified: Manny Ramirez 2010 = 232 PA LAD + 88 PA CWS; player PA sum == team PA).
- NHL: skater/goalie summary with cayenneExp franchiseId=F -> stint stats (verified: Nigel Dawes 2010-11 = 9 GP ATL
  + 4 GP MTL); birthdates from skater/goalie bios per season (paged, 100 rows/page).
- MoneyPuck team season CSV (2008+)."""
import json, os, sys, time
from urllib.parse import quote
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_phase1 as f1
from fetch_phase1 import RAW

UA = {"User-Agent": "DoomViz-UW-DATA511/0.1 (student project; contact: https://github.com/AdamRychtecky8)"}
S = requests.Session()
S.headers.update(UA)


def get(source, name, url, kind="json"):
    """Cached GET; json or text. Returns None on block/error (prints BLOCKED/ERROR; no retry loops)."""
    d = os.path.join(RAW, source)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + (".json" if kind == "json" else ".csv"))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f) if kind == "json" else f.read()
    for _ in range(2):
        try:
            r = S.get(url, timeout=60)
        except requests.RequestException as e:
            print(f"  ERROR {source}/{name}: {e}", flush=True)
            continue
        if r.status_code in (403, 429) or "cf-chl" in r.text[:2000].lower():
            print(f"  BLOCKED {source}/{name}: HTTP {r.status_code}", flush=True)
            return None
        if r.status_code != 200:
            print(f"  ERROR {source}/{name}: HTTP {r.status_code}", flush=True)
            continue
        with open(path, "w", encoding="utf-8") as f:
            if kind == "json":
                json.dump(r.json(), f)
            else:
                f.write(r.text)
        return r.json() if kind == "json" else r.text
    return None


def load(src, name):
    with open(os.path.join(RAW, src, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


MLB_STATS = ("https://statsapi.mlb.com/api/v1/stats?stats=season&group={g}&season={y}&playerPool=ALL&sportId=1"
             "&limit=1000&teamId={t}")
MLB_PEOPLE = "https://statsapi.mlb.com/api/v1/people?personIds={ids}"


def mlb():
    tids = [t["id"] for t in load("mlb_meta", "teams_2026")["teams"]]
    for y in range(2000, 2027):
        n = 0
        for t in tids:
            for g in ("hitting", "pitching"):
                n += get("mlb_player_stats", f"{y}_{t}_{g}", MLB_STATS.format(g=g, y=y, t=t)) is not None
        print(f"MLB stints {y}: {n}/{len(tids) * 2}", flush=True)
    ids = set()
    for fn in os.listdir(os.path.join(RAW, "mlb_player_stats")):
        for s in load("mlb_player_stats", fn[:-5])["stats"][0]["splits"]:
            ids.add(s["player"]["id"])
    ids = sorted(ids)
    for i in range(0, len(ids), 100):
        get("mlb_people", f"batch_{i // 100:04d}", MLB_PEOPLE.format(ids=",".join(map(str, ids[i:i + 100]))))
    print(f"MLB people: {len(ids)} ids in {len(ids) // 100 + 1} batches", flush=True)


MLB_TEAM_TOT = "https://statsapi.mlb.com/api/v1/teams/stats?season={y}&group={g}&stats=season&sportIds=1"
MLB_ROSTER = "https://statsapi.mlb.com/api/v1/teams/{t}/roster?season={y}&rosterType=fullSeason"
MLB_YBY = ("https://statsapi.mlb.com/api/v1/people?personIds={ids}"
           "&hydrate=stats(group=[hitting,pitching],type=[yearByYear])")


def mlb_repair():
    """For recent seasons the teamId query omits players traded AWAY (e.g. 2025 Twins: Correa, Castro, Duran).
    Find team-seasons whose player PA/BF don't sum to the official team totals, take their fullSeason rosters,
    and fetch the missing players' yearByYear splits (per team) in batches of 100 (D46)."""
    bad = []
    for y in range(2000, 2027):
        for g, key in (("hitting", "plateAppearances"), ("pitching", "battersFaced")):
            tot = get("mlb_team_totals", f"{y}_{g}", MLB_TEAM_TOT.format(y=y, g=g))
            for s in tot["stats"][0]["splits"]:
                t = s["team"]["id"]
                sp = load("mlb_player_stats", f"{y}_{t}_{g}")["stats"][0]["splits"]
                if sum(x["stat"].get(key, 0) for x in sp) != s["stat"][key]:
                    bad.append((y, t))
    bad = sorted(set(bad))
    print(f"MLB team-seasons not summing to official totals: {len(bad)}", flush=True)
    missing = set()
    for y, t in bad:
        ro = get("mlb_rosters", f"{y}_{t}", MLB_ROSTER.format(t=t, y=y))
        have = set()
        for g in ("hitting", "pitching"):
            have |= {x["player"]["id"] for x in load("mlb_player_stats", f"{y}_{t}_{g}")["stats"][0]["splits"]}
        missing |= {r["person"]["id"] for r in ro.get("roster", []) if r["person"]["id"] not in have}
    missing = sorted(missing)
    for i in range(0, len(missing), 100):
        get("mlb_yby", f"batch_{i // 100:04d}", MLB_YBY.format(ids=",".join(map(str, missing[i:i + 100]))))
    with open(os.path.join(RAW, "mlb_yby", "_bad_team_seasons.json"), "w") as f:
        json.dump(bad, f)
    print(f"MLB repair: {len(missing)} missing players fetched in {len(missing) // 100 + 1} batches", flush=True)


NHL_REP = ("https://api.nhle.com/stats/rest/en/{who}/{rep}?isAggregate=false&isGame=false&limit=100&start={s}"
           "&cayenneExp={q}")


def nhl():
    for y in range(2005, 2026):
        sid = f"{y}{y + 1}"
        fr_ids = sorted({t["franchiseId"] for t in
                         [x for x in load("nhl_meta", "team")["data"]]
                         if t["id"] in {r["teamId"] for r in load("nhl_team_summary", sid)["data"]}})
        n = 0
        for fr in fr_ids:
            q = quote(f"seasonId={sid} and gameTypeId=2 and franchiseId={fr}")
            for who in ("skater", "goalie"):
                r = get("nhl_player_stats", f"{sid}_{fr}_{who}", NHL_REP.format(who=who, rep="summary", s=0, q=q))
                n += r is not None
                if r and r.get("total", 0) > 100:
                    print(f"  WARNING {sid} fr{fr} {who}: {r['total']} rows > 100 (paging needed)", flush=True)
        for who in ("skater", "goalie"):  # birthdates: season-wide bios, paged
            q = quote(f"seasonId={sid} and gameTypeId=2")
            first = get("nhl_bios", f"{sid}_{who}_0", NHL_REP.format(who=who, rep="bios", s=0, q=q))
            total = (first or {}).get("total", 0)
            for s in range(100, total, 100):
                get("nhl_bios", f"{sid}_{who}_{s}", NHL_REP.format(who=who, rep="bios", s=s, q=q))
        print(f"NHL stints {sid}: {n}/{len(fr_ids) * 2}", flush=True)


NHL_LANDING = "https://api-web.nhle.com/v1/player/{pid}/landing"


def nhl_births():
    """Birthdates for players absent from the season bios reports (27 players) via the player landing page (D47)."""
    known = set()
    for fn in os.listdir(os.path.join(RAW, "nhl_bios")):
        known |= {r["playerId"] for r in load("nhl_bios", fn[:-5])["data"] if r.get("birthDate")}
    need = set()
    for fn in os.listdir(os.path.join(RAW, "nhl_player_stats")):
        need |= {r["playerId"] for r in load("nhl_player_stats", fn[:-5])["data"]}
    missing = sorted(need - known)
    ok = sum(get("nhl_player_landing", str(p), NHL_LANDING.format(pid=p)) is not None for p in missing)
    print(f"NHL birthdates: {len(missing)} missing from bios, fetched {ok}", flush=True)


MP = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{y}/regular/teams.csv"


def mp():
    for y in range(2008, 2026):
        ok = get("moneypuck", f"teams_{y}", MP.format(y=y), kind="csv") is not None
        print(f"MoneyPuck {y}: {'ok' if ok else 'FAILED'}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    {"mlb": mlb, "nhl": nhl, "mp": mp, "mlb_repair": mlb_repair, "nhl_births": nhl_births}[sys.argv[1]]()
