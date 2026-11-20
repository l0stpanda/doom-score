"""Phase 3 build: roster age and composition (team-season level) + NHL underlying metrics (MoneyPuck).
Input: data/processed/mlb_nhl_core_phase2.csv -> output: data/processed/mlb_nhl_core_phase3.csv.
All features use season-t player stints only (traded players are split by team via the teamId/franchiseId
queries in fetch_phase3.py)."""
import glob, json, os, sys
from datetime import date
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_api_features as api

ROOT = api.ROOT
RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed")
REP = os.path.join(ROOT, "reports")
KEY = ["league", "season_start_year", "franchise_id"]


def load(src, name):
    with open(os.path.join(RAW, src, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def wavg(x, w):
    return np.average(x, weights=w) if len(x) and w.sum() > 0 else np.nan


def age_on(birth, on):
    if not isinstance(birth, str) or len(birth) < 10:
        return np.nan
    b = date.fromisoformat(birth[:10])
    return (on - b).days / 365.25


# ---------------- MLB ----------------
def mlb_stints():
    fmap = api.mlb_franchise_map()
    births = {}
    for f in glob.glob(os.path.join(RAW, "mlb_people", "*.json")):
        for p in json.load(open(f, encoding="utf-8"))["people"]:
            births[p["id"]] = p.get("birthDate")
    rows = []
    for f in glob.glob(os.path.join(RAW, "mlb_player_stats", "*.json")):
        y, t, g = os.path.basename(f)[:-5].split("_")
        for s in json.load(open(f, encoding="utf-8"))["stats"][0]["splits"]:
            if s.get("team", {}).get("id") not in (None, int(t)):
                continue  # defensive: keep only this team's stint
            st = s["stat"]
            rows.append(dict(season_start_year=int(y), team_id=int(t), player_id=s["player"]["id"],
                             player=s["player"]["fullName"], group=g,
                             pa=st.get("plateAppearances", 0) if g == "hitting" else 0,
                             bf=st.get("battersFaced", 0) if g == "pitching" else 0))
    # D46: add players the teamId query omitted (traded away), from their yearByYear per-team splits,
    # only for team-seasons that did not sum to the official team totals
    bad_path = os.path.join(RAW, "mlb_yby", "_bad_team_seasons.json")
    bad = {tuple(x) for x in json.load(open(bad_path))} if os.path.exists(bad_path) else set()
    have = {(r["season_start_year"], r["team_id"], r["player_id"], r["group"]) for r in rows}
    added = 0
    for f in glob.glob(os.path.join(RAW, "mlb_yby", "batch_*.json")):
        for p in json.load(open(f, encoding="utf-8"))["people"]:
            births[p["id"]] = p.get("birthDate")
            for grp in p.get("stats", []):
                g = grp["group"]["displayName"]
                for s in grp["splits"]:
                    t = s.get("team", {}).get("id")
                    y = int(s["season"])
                    if t is None or (y, t) not in bad or (y, t, p["id"], g) in have or s.get("sport", {}).get("id", 1) != 1:
                        continue
                    stt = s["stat"]
                    rows.append(dict(season_start_year=y, team_id=t, player_id=p["id"], player=p["fullName"], group=g,
                                     pa=stt.get("plateAppearances", 0) if g == "hitting" else 0,
                                     bf=stt.get("battersFaced", 0) if g == "pitching" else 0))
                    have.add((y, t, p["id"], g))
                    added += 1
    print(f"MLB stints added from yearByYear for {len(bad)} team-seasons: {added}")
    st = pd.DataFrame(rows)
    st["franchise_id"] = st.team_id.map(fmap)
    st["birth"] = st.player_id.map(births)
    st["age"] = [age_on(b, date(y, 6, 30)) for b, y in zip(st.birth, st.season_start_year)]  # D45: June 30 of t
    return st


def mlb_features(st):
    # one row per player-team-season: production = PA + BF (two-way players summed)
    p = st.groupby(["season_start_year", "franchise_id", "player_id"]).agg(
        pa=("pa", "sum"), bf=("bf", "sum"), age=("age", "first")).reset_index()
    p["w"] = p.pa + p.bf
    out = []
    for (y, fid), g in p.groupby(["season_start_year", "franchise_id"]):
        g = g[g.w > 0]
        known = g[g.age.notna()]
        tot = g.w.sum()
        out.append(dict(league="MLB", season_start_year=y, franchise_id=fid,
                        age_weighted=wavg(known.age, known.w),
                        age_weighted_hitters=wavg(known.age, known.pa),
                        age_weighted_pitchers=wavg(known.age, known.bf),
                        share_production_age32plus=known[known.age >= 32].w.sum() / known.w.sum() if known.w.sum() else np.nan,
                        top3_concentration=g.w.nlargest(3).sum() / tot,
                        roster_players_used=len(g), age_weight_coverage=known.w.sum() / tot,
                        team_pa=g.pa.sum(), team_bf=g.bf.sum()))
    return pd.DataFrame(out)


# ---------------- NHL ----------------
def nhl_slug_by_franchise():
    fr = {f["id"]: f["fullName"] for f in load("nhl_meta", "franchise")["data"]}
    out = {k: api.slug(v) for k, v in fr.items()}
    out[28] = out[40]  # Coyotes -> Utah (D06)
    return out


def nhl_stints():
    fslug = nhl_slug_by_franchise()
    births = {}
    for f in glob.glob(os.path.join(RAW, "nhl_bios", "*.json")):
        for r in json.load(open(f, encoding="utf-8"))["data"]:
            births[r["playerId"]] = r.get("birthDate")
    for f in glob.glob(os.path.join(RAW, "nhl_player_landing", "*.json")):  # D47: players missing from bios
        p = json.load(open(f, encoding="utf-8"))
        births.setdefault(p["playerId"], p.get("birthDate"))
        if not births[p["playerId"]]:
            births[p["playerId"]] = p.get("birthDate")
    rows = []
    for f in glob.glob(os.path.join(RAW, "nhl_player_stats", "*.json")):
        sid, fr, who = os.path.basename(f)[:-5].split("_")
        for r in json.load(open(f, encoding="utf-8"))["data"]:
            gp = r.get("gamesPlayed") or 0
            toi = (r.get("timeOnIcePerGame") or 0) * gp if who == "skater" else (r.get("timeOnIce") or 0)
            rows.append(dict(season_start_year=int(sid[:4]), franchise_id=fslug[int(fr)], player_id=r["playerId"],
                             who=who, gp=gp, toi=toi, points=r.get("points") or 0))
    st = pd.DataFrame(rows)
    st["birth"] = st.player_id.map(births)
    st["age"] = [age_on(b, date(y + 1, 2, 1)) for b, y in zip(st.birth, st.season_start_year)]  # D45: Feb 1 of t+1
    return st


def nhl_features(st):
    out = []
    for (y, fid), g in st.groupby(["season_start_year", "franchise_id"]):
        g = g[g.toi > 0]
        known = g[g.age.notna()]
        sk = g[g.who == "skater"]
        skk = sk[sk.age.notna()]
        out.append(dict(league="NHL", season_start_year=y, franchise_id=fid,
                        age_weighted=wavg(known.age, known.toi),
                        share_production_age32plus=known[known.age >= 32].toi.sum() / known.toi.sum() if known.toi.sum() else np.nan,
                        share_points_age32plus=(skk[skk.age >= 32].points.sum() / skk.points.sum()
                                                if skk.points.sum() else np.nan),
                        top3_concentration=sk.points.nlargest(3).sum() / sk.points.sum() if sk.points.sum() else np.nan,
                        roster_players_used=g.player_id.nunique(), age_weight_coverage=known.toi.sum() / g.toi.sum(),
                        skater_gp_sum=sk.gp.sum(), goalie_gp_sum=g[g.who == "goalie"].gp.sum()))
    return pd.DataFrame(out)


# ---------------- MoneyPuck ----------------
MP_FIX = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL"}


def moneypuck():
    tri = {}
    fslug = nhl_slug_by_franchise()
    for t in load("nhl_meta", "team")["data"]:
        if t["franchiseId"] in fslug:
            tri.setdefault(t["triCode"], fslug[t["franchiseId"]])
    tri["ARI"], tri["PHX"], tri["UTA"], tri["ATL"] = (fslug[40], fslug[40], fslug[40], fslug[35])
    rows = []
    for f in sorted(glob.glob(os.path.join(RAW, "moneypuck", "teams_*.csv"))):
        d = pd.read_csv(f)
        y = int(os.path.basename(f)[6:10])
        for code, g in d.groupby("team"):
            a = g[g.situation == "all"].iloc[0]
            e = g[g.situation == "5on5"].iloc[0]
            rows.append(dict(league="NHL", season_start_year=y, franchise_id=tri[MP_FIX.get(code, code)],
                             xgoals_pct=a.xGoalsPercentage, corsi_pct=a.corsiPercentage,
                             pdo_5v5=e.goalsFor / e.shotsOnGoalFor + 1 - e.goalsAgainst / e.shotsOnGoalAgainst,
                             underlying_source="https://moneypuck.com/moneypuck/playerData/seasonSummary/"
                                               f"{y}/regular/teams.csv"))
    return pd.DataFrame(rows)


def main():
    core = pd.read_csv(os.path.join(PROC, "mlb_nhl_core_phase2.csv"))
    ms = mlb_stints()
    print(f"MLB stints: {len(ms)} rows, {ms.player_id.nunique()} players, birthdate missing "
          f"{ms.birth.isna().mean():.2%}")
    mf = mlb_features(ms)
    ns = nhl_stints()
    print(f"NHL stints: {len(ns)} rows, {ns.player_id.nunique()} players, birthdate missing "
          f"{ns.birth.isna().mean():.2%}")
    nf = nhl_features(ns)
    mp = moneypuck()
    print(f"MoneyPuck: {len(mp)} team-seasons {mp.season_start_year.min()}-{mp.season_start_year.max()}")
    feat = pd.concat([mf, nf], ignore_index=True)
    df = core.merge(feat, on=KEY, how="left").merge(mp, on=KEY, how="left")
    labels = [c for c in df.columns if c.startswith("y_")]
    df = df[[c for c in df.columns if c not in labels] + labels]
    df.to_csv(os.path.join(PROC, "mlb_nhl_core_phase3.csv"), index=False)
    print(f"wrote mlb_nhl_core_phase3.csv: {df.shape}")

    # coverage
    cols = ["age_weighted", "share_production_age32plus", "top3_concentration", "age_weighted_hitters",
            "age_weighted_pitchers", "share_points_age32plus", "xgoals_pct", "corsi_pct", "pdo_5v5"]
    cov = []
    for lg in ("MLB", "NHL"):
        sub = df[df.league == lg]
        for c in cols:
            nn = sub[sub[c].notna()]
            cov.append(dict(league=lg, column=c, pct_non_missing=round(100 * len(nn) / len(sub), 1),
                            first=nn.season_start_year.min() if len(nn) else None,
                            last=nn.season_start_year.max() if len(nn) else None))
    cov = pd.DataFrame(cov)
    cov.to_csv(os.path.join(REP, "phase3_coverage.csv"), index=False)
    print(cov.to_string(index=False))

    # checks
    m, n = df[df.league == "MLB"], df[df.league == "NHL"]
    ram = ms[(ms.player.str.contains("Manny Ram")) & (ms.season_start_year == 2010)].groupby("franchise_id").pa.sum()
    ratio = n.skater_gp_sum / n.games
    fmap = api.mlb_franchise_map()
    official_bad = []
    for g, key, col in (("hitting", "plateAppearances", "team_pa"), ("pitching", "battersFaced", "team_bf")):
        for y in range(2000, 2027):
            for s in load("mlb_team_totals", f"{y}_{g}")["stats"][0]["splits"]:
                mine = m[(m.season_start_year == y) & (m.franchise_id == fmap[s["team"]["id"]])][col]
                if not len(mine) or mine.iloc[0] != s["stat"][key]:
                    official_bad.append((y, fmap[s["team"]["id"]], g, mine.iloc[0] if len(mine) else None, s["stat"][key]))
    official_ok = not official_bad
    checks = [
        ("every team-season has Phase 3 roster features", df.age_weighted.notna().all(),
         f"missing {int(df.age_weighted.isna().sum())}"),
        ("birthdate coverage of playing time >= 99.5%", df.age_weight_coverage.min() >= 0.995,
         f"min {df.age_weight_coverage.min():.4f}"),
        ("traded player split by stint (Manny Ramirez 2010: LAD 232 + CWS 88 PA)",
         ram.get("los-angeles-dodgers") == 232 and ram.get("chicago-white-sox") == 88, str(ram.to_dict())),
        ("MLB player PA and BF sum exactly to official team totals (all team-seasons)", official_ok,
         f"mismatches: {official_bad[:5]}"),
        ("NHL skater games per team game in 17.5..18.5 (18 dressed)", ratio.between(17.5, 18.5).all(),
         f"{ratio.min():.2f}-{ratio.max():.2f}"),
        ("NHL goalie GP >= team games", (n.goalie_gp_sum >= n.games).all(), ""),
        ("age_weighted league means plausible (MLB 27-31, NHL 26-30)",
         m.age_weighted.mean() > 27 and m.age_weighted.mean() < 31 and 26 < n.age_weighted.mean() < 30,
         f"MLB {m.age_weighted.mean():.2f}, NHL {n.age_weighted.mean():.2f}"),
        ("shares within [0,1]", df[["share_production_age32plus", "top3_concentration"]].stack().between(0, 1).all(), ""),
        ("MoneyPuck: every NHL team 2008+ matched", n[n.season_start_year >= 2008].corsi_pct.notna().all(),
         f"missing {int(n[n.season_start_year >= 2008].corsi_pct.isna().sum())}"),
        ("Corsi/xG league mean ~0.5, PDO ~1.0", abs(n.corsi_pct.mean() - 0.5) < 0.01 and
         abs(n.xgoals_pct.mean() - 0.5) < 0.01 and abs(n.pdo_5v5.mean() - 1) < 0.01,
         f"corsi {n.corsi_pct.mean():.3f}, xg {n.xgoals_pct.mean():.3f}, pdo {n.pdo_5v5.mean():.3f}"),
        ("one row per key", not df.duplicated(KEY).any(), ""),
    ]
    for c, ok, det in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {c} {det}")
    pd.DataFrame(checks, columns=["check", "pass", "detail"]).to_csv(os.path.join(REP, "phase3_checks.csv"), index=False)

    lab = df[df.y_doom_3yr.notna()]
    sp = {lg: {c: round(g[c].rank().corr(g.y_doom_3yr.rank()), 3) for c in  # Spearman = Pearson on ranks
               ["age_weighted", "share_production_age32plus", "top3_concentration", "corsi_pct", "xgoals_pct",
                "pdo_5v5"] if g[c].notna().sum() > 30} for lg, g in lab.groupby("league")}
    print("Spearman vs y_doom_3yr (review only):", sp)
    return df


if __name__ == "__main__":
    main()
