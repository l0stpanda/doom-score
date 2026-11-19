"""Phase 1 build: core MLB+NHL team-season table with labels, cheap features, validation."""
import json, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
REP = os.path.join(ROOT, "reports")
os.makedirs(OUT, exist_ok=True); os.makedirs(REP, exist_ok=True)

MLB_URL = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={y}&standingsTypes=regularSeason"
NHL_URL = "https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId={sid} and gameTypeId=2"

CORE = ["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ties", "games",
        "win_pct", "point_diff_per_game", "win_pct_percentile", "win_pct_trailing_3_seasons",
        "observed_doom_next_3_seasons", "draft_picks_used", "cap_space_pct",
        "personnel_lead_tenure_years", "personnel_lead_changed_past_year", "standings_source", "draft_source"]


def load(src, name):
    with open(os.path.join(RAW, src, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def slug(name):
    return name.lower().replace(".", "").replace("é", "e").replace(" ", "-")


# ---------------- MLB ----------------
mlb_teams = {t["id"]: t["name"] for t in load("mlb_meta", "teams_2026")["teams"]}
rows = []
for y in range(1997, 2027):
    for rec in load("mlb_standings", str(y))["records"]:
        for tr in rec["teamRecords"]:
            rows.append(dict(league="MLB", season_start_year=y, team_id=tr["team"]["id"],
                             team_name_then=tr["team"]["name"],
                             wins=tr["wins"], losses=tr["losses"],
                             ties=tr["leagueRecord"].get("ties", 0) or 0,
                             games=tr["gamesPlayed"], scored=tr["runsScored"], allowed=tr["runsAllowed"],
                             standings_source=MLB_URL.format(y=y)))
mlb = pd.DataFrame(rows)
ids_by_year = mlb.groupby("season_start_year")["team_id"].apply(frozenset)
mlb_ids_stable = all(ids_by_year[y] == frozenset(mlb_teams) for y in range(1998, 2027)) and ids_by_year[1997] <= frozenset(mlb_teams)
print(f"MLB team IDs identical every season 1998-2026 (1997: 28-team subset) and match 2026 teams: {mlb_ids_stable}")
mlb["team"] = mlb["team_id"].map(mlb_teams)
mlb["franchise_id"] = mlb["team"].map(slug)
mlb["win_pct"] = (mlb.wins + 0.5 * mlb.ties) / mlb.games
mlb["win_pct_raw"] = mlb.wins / mlb.games
mlb["ot_losses"] = np.nan
print(f"MLB rows loaded: {len(mlb)}")

# ---------------- NHL ----------------
nteam = {t["id"]: t for t in load("nhl_meta", "team")["data"]}
nfr = {f["id"]: f["fullName"] for f in load("nhl_meta", "franchise")["data"]}
FRANCHISE_OVERRIDE = {28: 40}  # Phoenix/Arizona Coyotes franchise -> Utah Mammoth franchise (manual, needs review)
rows = []
for y in [2002, 2003] + list(range(2005, 2026)):
    sid = f"{y}{y+1}"
    for t in load("nhl_team_summary", sid)["data"]:
        fid = nteam[t["teamId"]]["franchiseId"]
        fid = FRANCHISE_OVERRIDE.get(fid, fid)
        rows.append(dict(league="NHL", season_start_year=y, team_id=t["teamId"], team_name_then=t["teamFullName"],
                         nhl_franchise=fid, team=nfr[fid], wins=t["wins"], losses=t["losses"],
                         ot_losses=t["otLosses"] or 0, real_ties=t["ties"] or 0,
                         games=t["gamesPlayed"], scored=t["goalsFor"], allowed=t["goalsAgainst"],
                         point_pct_api=t["pointPct"], standings_source=NHL_URL.format(sid=sid)))
nhl = pd.DataFrame(rows)
nhl["ties"] = nhl.ot_losses + nhl.real_ties  # so win_pct == NHL points %
nhl["franchise_id"] = nhl["team"].map(slug)
nhl["win_pct"] = (nhl.wins + 0.5 * nhl.ties) / nhl.games
nhl["win_pct_raw"] = nhl.wins / nhl.games
print(f"NHL rows loaded: {len(nhl)}; max |win_pct - API pointPct| = {(nhl.win_pct - nhl.point_pct_api).abs().max():.5f}")

df = pd.concat([mlb, nhl], ignore_index=True)

# ---------------- features ----------------
df = df.sort_values(["league", "franchise_id", "season_start_year"]).reset_index(drop=True)
df["point_diff_per_game"] = (df.scored - df.allowed) / df.games
df["scored_per_game"] = df.scored / df.games
df["allowed_per_game"] = df.allowed / df.games
exp = np.where(df.league == "MLB", 1.83, 2.0)
df["pythag_win_pct"] = df.scored ** exp / (df.scored ** exp + df.allowed ** exp)
df["luck"] = df.win_pct - df.pythag_win_pct


def pct_rank(s):
    return (s.rank(method="average", ascending=True) - 1) / (len(s) - 1) * 100


df["win_pct_percentile"] = df.groupby(["league", "season_start_year"])["win_pct"].transform(pct_rank)

# trailing features use the franchise's previous *played* seasons (NHL skips cancelled 2004-05)
g = df.groupby(["league", "franchise_id"])
df["win_pct_trailing_3_seasons"] = g["win_pct"].transform(lambda s: s.rolling(3, min_periods=1).mean())
df["win_pct_change_1yr"] = g["win_pct"].diff()


def slope3(s):
    def f(w):
        return np.polyfit(np.arange(len(w)), w, 1)[0] if len(w) >= 2 else np.nan
    return s.rolling(3, min_periods=2).apply(f, raw=True)


df["win_pct_slope_3yr"] = g["win_pct"].transform(slope3)
df["seasons_of_history"] = g.cumcount() + 1

short = {("MLB", 2020), ("NHL", 2012), ("NHL", 2019), ("NHL", 2020)}
df["short_season"] = [(l, y) in short for l, y in zip(df.league, df.season_start_year)]
df["expansion_first_3_seasons"] = (((df.franchise_id == "vegas-golden-knights") & df.season_start_year.between(2017, 2019)) |
                                   ((df.franchise_id == "seattle-kraken") & df.season_start_year.between(2021, 2023)))

# ---------------- labels (next three played seasons of the franchise) ----------------
for k in (1, 2, 3):
    df[f"y_pct_t{k}"] = g["win_pct_percentile"].shift(-k)
df["y_doom_3yr"] = 100 - df[["y_pct_t1", "y_pct_t2", "y_pct_t3"]].mean(axis=1, skipna=False)
df["y_doomed_bottom25"] = (df.y_doom_3yr >= 75).astype("boolean")
df.loc[df.y_doom_3yr.isna(), "y_doomed_bottom25"] = pd.NA
df["observed_doom_next_3_seasons"] = df.y_doom_3yr

for c in ["draft_picks_used", "cap_space_pct", "personnel_lead_tenure_years", "personnel_lead_changed_past_year", "draft_source"]:
    df[c] = np.nan

# keep only modelling seasons (history-only seasons were used for trailing features)
first = {"MLB": 2000, "NHL": 2005}
out = df[df.season_start_year >= df.league.map(first)].copy()

extra = ["ot_losses", "win_pct_raw", "scored_per_game", "allowed_per_game", "pythag_win_pct", "luck",
         "win_pct_change_1yr", "win_pct_slope_3yr", "seasons_of_history", "short_season", "expansion_first_3_seasons",
         "team_name_then", "team_id"]
labels = ["y_pct_t1", "y_pct_t2", "y_pct_t3", "y_doom_3yr", "y_doomed_bottom25"]
out = out[CORE + extra + labels].sort_values(["league", "season_start_year", "franchise_id"]).reset_index(drop=True)
out.to_csv(os.path.join(OUT, "mlb_nhl_core.csv"), index=False)
print(f"wrote data/processed/mlb_nhl_core.csv ({len(out)} rows)")

# ---------------- validation ----------------
checks = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


check("one row per league-season-franchise", not out.duplicated(["league", "season_start_year", "franchise_id"]).any())
cnt = out.groupby(["league", "season_start_year"]).size()
exp_cnt = {(l, y): 30 if l == "MLB" else (30 if y < 2017 else 31 if y < 2021 else 32) for l, y in cnt.index}
bad = [f"{k}:{v}" for k, v in cnt.items() if v != exp_cnt[k]]
check("team counts (MLB 30; NHL 30/31/32)", not bad, ", ".join(bad))
m = out[out.league == "MLB"]
ndiff = int((m.wins + m.losses != m.games).sum())
check("MLB W+L = G", ndiff == 0,
      f"({ndiff} rows differ; W+L+T = G for all rows: {(m.wins + m.losses + m.ties == m.games).all()})")
check("MLB W+L+T = G", (m.wins + m.losses + m.ties == m.games).all())
n = out[out.league == "NHL"]
check("NHL W+L+OTL = GP", (n.wins + n.losses + n.ot_losses == n.games).all())
lg = df.groupby(["league", "season_start_year"]).apply(lambda x: (x.scored - x.allowed).sum(), include_groups=False)
check("league-wide run/goal differential = 0 each season", (lg.abs() <= 2).all(), f"(max |sum| = {lg.abs().max()})")
rng = out.groupby(["league", "season_start_year"])["win_pct_percentile"].agg(["min", "max"])
check("percentiles span 0-100 in every league-season", ((rng["min"] == 0) & (rng["max"] == 100)).all(),
      f"(lowest max {rng['max'].min():.1f}, highest min {rng['min'].max():.1f})")
def ends_ok(x):
    w = x.win_pct; n = len(x)
    return (np.isclose(x.win_pct_percentile.min(), ((w == w.min()).sum() - 1) / 2 / (n - 1) * 100) and
            np.isclose(x.win_pct_percentile.max(), 100 - ((w == w.max()).sum() - 1) / 2 / (n - 1) * 100))
ends = out.groupby(["league", "season_start_year"]).apply(ends_ok, include_groups=False)
check("percentile endpoints = 0/100 except where top/bottom win_pct is tied (average rank)", ends.all(),
      f"({int((rng['max'] < 100).sum() + (rng['min'] > 0).sum())} league-season endpoints affected by ties)")
sea = out[(out.franchise_id == "seattle-mariners") & (out.season_start_year == 2001)].iloc[0]
check("spot: 2001 Mariners 116-46", (sea.wins, sea.losses) == (116, 46), f"({sea.wins}-{sea.losses})")
bos = out[(out.franchise_id == "boston-bruins") & (out.season_start_year == 2022)].iloc[0]
check("spot: 2022-23 Bruins 65-12-5", (bos.wins, bos.losses, bos.ot_losses) == (65, 12, 5),
      f"({bos.wins}-{bos.losses}-{int(bos.ot_losses)})")
last = out.groupby("league").season_start_year.transform("max")
in_last3 = out.season_start_year > last - 3
check("y_doom_3yr NaN exactly in each league's last 3 seasons",
      (out.y_doom_3yr.isna() == in_last3).all(), f"(NaN rows: {int(out.y_doom_3yr.isna().sum())})")
pd.DataFrame(checks, columns=["check", "pass", "detail"]).to_csv(os.path.join(REP, "phase1_checks.csv"), index=False)

# ---------------- plot + summary ----------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(7, 5))
for lg_name, col in [("MLB", "#1f77b4"), ("NHL", "#d62728")]:
    s = out[(out.league == lg_name) & out.y_doom_3yr.notna()]
    ax.scatter(s.win_pct_percentile, s.y_doom_3yr, s=10, alpha=0.5, c=col, label=f"{lg_name} (n={len(s)})")
ax.set_xlabel("win_pct_percentile (season t)")
ax.set_ylabel("y_doom_3yr (seasons t+1..t+3)")
ax.axhline(75, ls="--", c="grey", lw=0.8)
ax.legend()
ax.set_title("Season-t standing vs. next-3-season doom")
fig.tight_layout()
fig.savefig(os.path.join(REP, "phase1.png"), dpi=120)

lab = out[out.y_doom_3yr.notna()]
print("\ncorr(win_pct_percentile, y_doom_3yr):",
      lab.groupby("league").apply(lambda x: round(x.win_pct_percentile.corr(x.y_doom_3yr), 3), include_groups=False).to_dict())
print("bottom25 rate:", lab.groupby("league").y_doomed_bottom25.mean().round(3).to_dict())
cols = ["league", "season_start_year", "team", "wins", "losses", "win_pct_percentile", "y_doom_3yr"]
print("\nMOST DOOMED\n", lab.nlargest(5, "y_doom_3yr")[cols].to_string(index=False))
print("\nLEAST DOOMED\n", lab.nsmallest(5, "y_doom_3yr")[cols].to_string(index=False))
print("\nrows by league:", out.league.value_counts().to_dict(), "| labelled:", lab.league.value_counts().to_dict())
mt = m[m.ties > 0]
print("MLB tie rows:", len(mt), mt[["season_start_year", "team", "ties"]].values.tolist())
print("NHL franchise ids:", sorted(n.franchise_id.unique()))
print("MLB franchise ids:", sorted(m.franchise_id.unique()))
