"""Phase M1b MLB features (pre-registered in reports/m1b_preregistration.md). Decisions D82-D86, D90 (value ages from MLB Stats API, not WAR).

fetch(): MLB Stats API schedules (scores), team hitting/pitching totals, minor-league affiliates + standings.
         Cached under data/raw/<source>/ via fetch_phase1.get (never re-downloads).
build(): writes data/processed/mlb_m1b_features.csv (one row per MLB team-season, raw + _lpct) and
         reports/m1b_feature_checks.csv.
Run: PYTHONUTF8=1 python ADAM-DATA/src/m1b_features.py"""
import os, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_phase1 as f1

ROOT, RAW = f1.ROOT, f1.RAW
OUT = os.path.join(ROOT, "data", "processed", "mlb_m1b_features.csv")
CHECKS = os.path.join(ROOT, "reports", "m1b_feature_checks.csv")
SEASONS = list(range(2000, 2027))
KEY = ["league", "season_start_year", "franchise_id"]

SCHED = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={y}&gameType=R&fields=dates,games,gamePk,"
         "status,codedGameState,teams,away,home,score,team,id,officialDate,gameNumber")
TOT = "https://statsapi.mlb.com/api/v1/teams/stats?season={y}&group={g}&stats=season&sportIds=1"
MILB_TEAMS = "https://statsapi.mlb.com/api/v1/teams?sportIds=11,12,13,14&season={y}"
MILB_STAND = "https://statsapi.mlb.com/api/v1/standings?leagueId={ids}&season={y}&standingsTypes=regularSeason"


def get(source, name, url):
    cached = os.path.exists(os.path.join(RAW, source, name + ".json"))
    out = f1.get(source, name, url)
    if not cached:
        time.sleep(0.3)                                # polite throttle on live requests only
    return out


def fetch():
    for y in SEASONS:
        get("mlb_schedule", f"schedule_{y}", SCHED.format(y=y))
        for g in ("hitting", "pitching"):
            get("mlb_team_totals", f"{y}_{g}", TOT.format(y=y, g=g))
        if y == 2020:                                  # no minor-league season
            continue
        t = get("milb", f"teams_{y}", MILB_TEAMS.format(y=y))
        if t:
            ids = sorted({x["league"]["id"] for x in t.get("teams", []) if x.get("league", {}).get("id")})
            get("milb", f"standings_{y}", MILB_STAND.format(ids=",".join(map(str, ids)), y=y))


def lpct(s):
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * np.nan


def load_json(source, name):
    import json
    p = os.path.join(RAW, source, name + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def second_half():
    rows = []
    for y in SEASONS:
        sc = load_json("mlb_schedule", f"schedule_{y}")
        games = {}
        for d in sc["dates"]:
            for g in d["games"]:
                if g.get("status", {}).get("codedGameState") != "F":
                    continue
                a, h = g["teams"]["away"], g["teams"]["home"]
                if "score" not in a or "score" not in h:
                    continue
                games[g["gamePk"]] = (g["officialDate"], g.get("gameNumber", 1), a["team"]["id"], a["score"],
                                      h["team"]["id"], h["score"])     # dict: later copy of a gamePk wins
        long = []
        for pk, (dt, gn, at, asc, ht, hsc) in games.items():
            long += [(at, dt, gn, pk, asc, hsc), (ht, dt, gn, pk, hsc, asc)]
        df = pd.DataFrame(long, columns=["team_id", "date", "gn", "pk", "rs", "ra"]).sort_values(
            ["team_id", "date", "gn", "pk"])
        for tid, g in df.groupby("team_id"):
            n = len(g)
            h2 = g.iloc[n // 2:]
            rows.append({"season_start_year": y, "team_id": tid, "sched_games": n, "sched_rs": g.rs.sum(),
                         "sched_ra": g.ra.sum(), "second_half_games": len(h2),
                         "second_half_margin": (h2.rs.sum() - h2.ra.sum()) / len(h2)})
    return pd.DataFrame(rows)


def baseruns():
    def bsr(s):
        H, BB, HBP, HR = s["hits"], s["baseOnBalls"], s["hitByPitch"], s["homeRuns"]
        TB, AB = s["totalBases"], s["atBats"]
        A = H + BB + HBP - HR
        B = 1.02 * (1.4 * TB - 0.6 * H - 3 * HR + 0.1 * (BB + HBP))
        C = AB - H
        return A * B / (B + C) + HR
    rows = []
    for y in SEASONS:
        part = {}
        for g in ("hitting", "pitching"):
            js = load_json("mlb_team_totals", f"{y}_{g}")
            for sp in js["stats"][0]["splits"]:
                st = sp["stat"]
                d = part.setdefault(sp["team"]["id"], {})
                d[f"bsr_{g}"] = bsr({k: float(st[k]) for k in ("hits", "baseOnBalls", "hitByPitch", "homeRuns",
                                                               "totalBases", "atBats")})
                d[f"runs_{g}"] = float(st["runs"])
                d[f"games_{g}"] = float(st["gamesPlayed"])
        df = pd.DataFrame.from_dict(part, orient="index").rename_axis("team_id").reset_index()
        # rescale so league BsR = league runs, separately for offense and runs allowed (pre-registered)
        df["bsr_for"] = df.bsr_hitting * df.runs_hitting.sum() / df.bsr_hitting.sum()
        df["bsr_against"] = df.bsr_pitching * df.runs_pitching.sum() / df.bsr_pitching.sum()
        g = df.games_hitting
        df["baserun_margin"] = (df.bsr_for - df.bsr_against) / g
        df["actual_margin_tot"] = (df.runs_hitting - df.runs_pitching) / g
        df["sequencing_luck"] = df.actual_margin_tot - df.baserun_margin
        df["season_start_year"] = y
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


VALUE_AGE_CHECKS = []


def value_age():
    """D90: value-weighted ages from MLB Stats API player stints (batting runs above average / FIP runs above
    average); replaces the Baseball-Reference WAR version (deleted)."""
    import m1b_value_age
    res, checks = m1b_value_age.build()
    VALUE_AGE_CHECKS[:] = checks
    return res


def farm():
    rows = []
    for y in SEASONS:
        if y == 2020:
            continue
        t, s = load_json("milb", f"teams_{y}"), load_json("milb", f"standings_{y}")
        if not t or not s:
            continue
        parent = {x["id"]: x.get("parentOrgId") for x in t["teams"] if x.get("sport", {}).get("id") in (11, 12, 13, 14)}
        seen = set()
        for rec in s.get("records", []):
            for tr in rec["teamRecords"]:
                tid = tr["team"]["id"]
                if tid in seen or tid not in parent or parent[tid] is None:
                    continue
                seen.add(tid)
                rows.append({"season_start_year": y, "team_id": parent[tid], "w": tr["wins"], "l": tr["losses"]})
    d = pd.DataFrame(rows)
    g = d.groupby(["season_start_year", "team_id"]).agg(w=("w", "sum"), l=("l", "sum"), affiliates=("w", "size"))
    g["farm_strength"] = g.w / (g.w + g.l)
    return g.reset_index()[["season_start_year", "team_id", "farm_strength", "affiliates"]]


NEW = ["second_half_margin", "baserun_margin", "sequencing_luck", "value_age_hitters", "value_age_pitchers",
       "farm_strength"]


def build():
    full = pd.read_csv(os.path.join(ROOT, "data", "processed", "mlb_nhl_team_seasons.csv"), low_memory=False)
    base = full[full.league == "MLB"][KEY + ["team_id", "games", "scored_per_game", "allowed_per_game"]].copy()
    n = len(base)
    for part in (second_half(), baseruns(), value_age(), farm()):
        base = base.merge(part, on=["season_start_year", "team_id"], how="left", validate="one_to_one")
    assert len(base) == n
    for c in NEW:
        base[f"{c}_lpct"] = base.groupby("season_start_year")[c].transform(lpct)

    tot_rs = base.scored_per_game * base.games
    checks = [
        ("schedule games = standings games", float((base.sched_games == base.games).mean())),
        ("schedule runs scored = standings runs (share of rows)", float((base.sched_rs == tot_rs.round()).mean())),
        ("team-totals runs = standings runs (share of rows)", float((base.runs_hitting == tot_rs.round()).mean())),
        ("team-totals actual margin vs standings margin, max abs diff",
         float((base.actual_margin_tot - (base.scored_per_game - base.allowed_per_game)).abs().max())),
        ("BaseRuns margin vs actual margin, Pearson r", float(base.baserun_margin.corr(base.actual_margin_tot))),
        ("farm affiliates per org, min", float(base.affiliates.min())),
        ("farm affiliates per org, median", float(base.affiliates.median())),
    ] + [(f"value age: {k}", v) for k, v in VALUE_AGE_CHECKS] + [
        (f"coverage {c}", float(base[c].notna().mean())) for c in NEW]
    pd.DataFrame(checks, columns=["check", "value"]).to_csv(CHECKS, index=False)
    keep = KEY + NEW + [f"{c}_lpct" for c in NEW] + ["second_half_games", "affiliates", "pos_value_hitters",
                                                     "pos_value_pitchers"]
    base[keep].to_csv(OUT, index=False)
    print(pd.DataFrame(checks, columns=["check", "value"]).to_string())
    print(base.groupby("season_start_year")[NEW].apply(lambda x: x.notna().mean()).loc[[2000, 2010, 2020, 2026]])


if __name__ == "__main__":
    if "--build-only" not in sys.argv:
        fetch()
    build()
