"""05 - Build the two analysis-ready datasets (one per league) for Doom Score work.

WHAT IT BUILDS
    data/final/wnba_team_doom_dataset.csv
    data/final/pwhl_team_doom_dataset.csv
    data/final/feature_params.json   (every threshold used below)

    Grain: one row per franchise per season (row_type = 'season', core seasons
    only: WNBA 2021-2026, PWHL 2023-24..2025-26) PLUS one row per active
    franchise for the upcoming season (row_type = 'current': WNBA 2027,
    PWHL 2026-27). Key: team_id, season.

    The two files share the same column names and order; a column exists in
    only one league when the concept does not apply to the other (listed in
    data/final/README.md).

COLUMN ROLES (prefix)
    perf_   performance. Includes perf_win_pct, the planned Y-axis. These are
            NOT candidate Doom Score inputs (the brief keeps current win % out
            of the score); they are kept for plotting and for outcome analysis.
    out_    the franchise's NEXT-season results (outcome labels for testing
            which features predict future performance). Null for the latest season.
    age_ exp_ conc_ qual_ cont_ avail_ draft_ fin_ ctx_
            candidate structural features. No weights, scaling or score.

HOW 'current' ROWS ARE COMPUTED
    Roster = dated current-roster snapshot (processed/current_roster_snapshot.csv).
    Each rostered player is evaluated on their latest completed season
    (WNBA 2026, PWHL 2025-26) summed across all teams they played for; ages are
    at the snapshot date. So the same roster functions run on
      season rows:  season-t roster  x season-t stats
      current rows: current roster   x latest-season stats (wherever played)
    This gives expansion teams (PWHL Detroit, Hamilton, San Jose, Vegas) the same
    features as everyone else. perf_* on current rows = latest completed season
    (null for expansion teams); feature_basis records which basis applies.

DEFINITIONS (players = roster members with playing time unless stated)
    playtime    WNBA minutes; PWHL time on ice (skaters + goalies)
    production  WNBA Basketball-Reference Win Shares; PWHL points (goals + assists)
    age_*       mean / median age; playtime-weighted mean age; mean age of the
                top-N players by playtime and by production (N = 5 WNBA, 8 PWHL);
                share of players / of playtime under 25 and at 30+
    age_n_young_meaningful  players under 25 meeting the meaningful-playtime rule
    exp_*       mean and playtime-weighted experience (league definitions, see 02)
    conc_*      top-1 / top-3 / top-N share of team production (negative Win Shares
                floored at 0 so shares stay in [0,1]); top-3 share of
                playtime; Herfindahl index of playtime shares; PWHL goalie top-1 TOI share
    qual_*      production per playtime (WNBA WS per 40 min; PWHL skater points per
                60 TOI); players above the league-season median rate (qualified pool)
    cont_*      share of this roster's playtime earned for THIS franchise in the prior
                season (season rows: t-1 for this team; current rows: latest season);
                share of the franchise's prior-season playtime still on the roster;
                players new to the franchise
    avail_*     1 - mean(GP)/team GP for the top-N single-team players by playtime (season rows only)
    draft_*     the entry draft held before the season: picks made (season rows,
                and PWHL current = 2026 draft) or picks held (WNBA current = 2027
                draft); round-1 picks; best pick; picks acquired by trade; own picks
                traded away; share of playtime from the franchise's own draftees
    fin_*       payroll aggregates where player salaries exist: WNBA 2021-2023 (Spotrac
                earnings via Mendeley Data; share of cap = payroll / hard cap), PWHL 2025-26
                (PWHLPA base salaries; avg salary vs the CBA team-average requirement).
                fin_payroll_top_n_share uses N = 5 (WNBA) / 8 (PWHL). PWHL current rows
                also carry known contract counts. WNBA 2024+ and current rows: no source.
    ctx_*       seasons of franchise history, expansion / relocation flags, league size

KNOWN LIMITATIONS
    Inherited from 01-04 (see docs/source_coverage_matrix.md). In particular the
    WNBA current roster comes from Wikipedia templates that, before 2027 free
    agency, still largely show end-of-2026 rosters (ctx_roster_snapshot_quality).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: F401

import numpy as np
import pandas as pd

from config import settings
from lib.common import base_argparser, setup_logging, teams_table
from lib.store import write_csv

log = setup_logging("05_build_final_datasets")

PARAMS = {
    "age_young_lt": 25,
    "age_old_ge": 30,
    "top_n": {"WNBA": 5, "PWHL": 8},
    "production_metric": {"WNBA": "ws (Basketball-Reference Win Shares)", "PWHL": "points (goals + assists)"},
    "meaningful_playtime": {"WNBA": {"min_games": 10, "min_playtime_per_game": 15.0},
                            "PWHL": {"min_games": 10, "min_playtime_per_game": 12.0, "goalies_qualify_on_games": True}},
    "qualified_pool": {"WNBA": {"min_minutes": 200}, "PWHL": {"min_games": 10, "skaters_only": True}},
    "current_row_stats_season": {"WNBA": str(settings.WNBA_LATEST_COMPLETED_SEASON), "PWHL": settings.PWHL_LATEST_COMPLETED_SEASON},
}
UPCOMING = {"WNBA": str(settings.WNBA_LATEST_COMPLETED_SEASON + 1), "PWHL": settings.PWHL_UPCOMING_SEASON["season"]}
LATEST = PARAMS["current_row_stats_season"]


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"season": str}, low_memory=False) if path.exists() else pd.DataFrame()


def season_order(lg: str, s: str) -> int:
    return int(str(s)[:4])


# ---------------------------------------------------------------------------
# Player standardisation
# ---------------------------------------------------------------------------
def std_players(ps: pd.DataFrame) -> pd.DataFrame:
    p = ps[ps.games_played.fillna(0) > 0].copy()
    w = p.league == "WNBA"
    p["playtime"] = np.where(w, p.minutes, p.time_on_ice_total_min)
    p["production"] = np.where(w, p.ws, p.points)
    p["is_goalie"] = p.is_goalie.astype(str) == "True"
    p["age"] = p.age_at_reference
    p["exp"] = p.experience_years
    return p[["league", "season", "team_id", "player_id", "player_name", "age", "exp", "games_played", "playtime",
              "production", "is_goalie", "n_teams_in_season"]]


def wmean(x: pd.Series, w: pd.Series) -> float:
    m = x.notna() & w.notna() & (w > 0)
    return float((x[m] * w[m]).sum() / w[m].sum()) if m.any() else np.nan


def share(part, total):
    return float(part / total) if total and total > 0 and pd.notna(total) else np.nan


def league_medians(sp: pd.DataFrame) -> dict:
    """Median production-per-playtime among qualified players, per league-season."""
    out = {}
    for (lg, s), d in sp.groupby(["league", "season"]):
        out[(lg, s)] = qualified_rates(d, lg).median()
    return out


def qualified_rates(d: pd.DataFrame, lg: str) -> pd.Series:
    if lg == "WNBA":
        q = d[d.playtime >= PARAMS["qualified_pool"]["WNBA"]["min_minutes"]]
        return 40 * q.production / q.playtime
    q = d[(d.games_played >= PARAMS["qualified_pool"]["PWHL"]["min_games"]) & ~d.is_goalie & (d.playtime > 0)]
    return 60 * q.production / q.playtime


def roster_features(r: pd.DataFrame, lg: str, team_id: str, median_rate: float, own_draftees: set) -> dict:
    """r: one roster; columns age, exp, games_played, playtime, production, is_goalie, player_id.
    Players without playtime (e.g. rookies on a current roster) count toward roster
    size and unweighted age only."""
    n = PARAMS["top_n"][lg]
    has_pt = r.playtime.fillna(0) > 0
    a = r[has_pt]
    pt, prod = a.playtime, a.production
    tot_pt, tot_prod = pt.sum(), prod.sum()
    young, old = PARAMS["age_young_lt"], PARAMS["age_old_ge"]
    mp = PARAMS["meaningful_playtime"][lg]
    ppg = pt / a.games_played.replace(0, np.nan)
    meaningful = (a.games_played >= mp["min_games"]) & ((ppg >= mp["min_playtime_per_game"]) | (a.is_goalie if lg == "PWHL" else False))
    top_pt = a.loc[pt.sort_values(ascending=False).index[:n]]
    top_prod = a.loc[prod.sort_values(ascending=False).index[:n]]
    # Win Shares can be negative; concentration shares use positive production only
    prod_pos = prod.clip(lower=0)
    prod_sorted = prod_pos.sort_values(ascending=False)
    tot_prod_pos = prod_pos.sum()
    rates = qualified_rates(a, lg)
    f = {
        "roster_n": len(r),
        "roster_n_with_playtime": int(has_pt.sum()),
        "age_mean": r.age.mean(),
        "age_median": r.age.median(),
        "age_playtime_weighted": wmean(a.age, pt),
        "age_top_n_by_playtime": top_pt.age.mean(),
        "age_top_n_by_production": top_prod.age.mean(),
        "age_pct_players_under_25": (r.age < young).mean() if r.age.notna().any() else np.nan,
        "age_pct_players_30_plus": (r.age >= old).mean() if r.age.notna().any() else np.nan,
        "age_share_playtime_under_25": share(pt[a.age < young].sum(), tot_pt),
        "age_share_playtime_30_plus": share(pt[a.age >= old].sum(), tot_pt),
        "age_n_young_meaningful": int((meaningful & (a.age < young)).sum()),
        "age_data_coverage": r.age.notna().mean() if len(r) else np.nan,
        "exp_mean": r.exp.mean(),
        "exp_playtime_weighted": wmean(a.exp, pt),
        "conc_top1_share_production": share(prod_sorted.head(1).sum(), tot_prod_pos),
        "conc_top3_share_production": share(prod_sorted.head(3).sum(), tot_prod_pos),
        "conc_top_n_share_production": share(prod_sorted.head(n).sum(), tot_prod_pos),
        "conc_top3_share_playtime": share(pt.sort_values(ascending=False).head(3).sum(), tot_pt),
        "conc_playtime_hhi": float(((pt / tot_pt) ** 2).sum()) if tot_pt else np.nan,
        "conc_n_meaningful_playtime": int(meaningful.sum()),
        "qual_production_per_playtime": (40 * tot_prod / tot_pt if lg == "WNBA"
                                         else share(60 * a[~a.is_goalie].production.sum(), a[~a.is_goalie].playtime.sum())),
        "qual_n_above_league_median_rate": int((rates > median_rate).sum()) if pd.notna(median_rate) else np.nan,
        "draft_own_draftee_playtime_share": share(pt[a.player_id.isin(own_draftees)].sum(), tot_pt),
    }
    if lg == "PWHL":
        g = a[a.is_goalie].playtime
        f["conc_goalie_top1_share_playtime"] = share(g.max(), g.sum()) if len(g) else np.nan
    return f


# ---------------------------------------------------------------------------
# Draft helpers
# ---------------------------------------------------------------------------
def own_draftees_map(dh: pd.DataFrame) -> dict:
    e = dh[(dh.draft_type == "entry") & dh.player_id.notna()]
    out: dict = {}
    for r in e.itertuples():
        out.setdefault((r.league, r.selecting_team_id), set()).add(r.player_id)
    return out


def draft_made(dh: pd.DataFrame, lg: str, year: int, team: str) -> dict:
    d = dh[(dh.league == lg) & (dh.draft_year == year) & (dh.draft_type == "entry")]
    if d.empty:
        return {}
    mine = d[d.selecting_team_id == team]
    return {"draft_year_used": year, "draft_pick_status": "picks_made",
            "draft_n_picks": len(mine), "draft_n_round1_picks": int((mine["round"] == 1).sum()),
            "draft_best_pick": mine.pick_overall.min() if len(mine) else np.nan,
            "draft_n_picks_acquired_by_trade": int((mine.pick_traded_before_draft.astype(str) == "True").sum()),
            "draft_n_own_picks_traded_away": int(((d.original_owner_team_id == team) & (d.selecting_team_id != team)).sum())}


def draft_held(inv: pd.DataFrame, lg: str, team: str) -> dict:
    iv = inv[inv.league == lg] if not inv.empty else inv
    if iv is None or iv.empty:
        return {}
    held = iv[iv.current_rights_holder_team_id == team]
    return {"draft_year_used": int(iv.draft_year.min()), "draft_pick_status": "picks_held_future",
            "draft_n_picks": len(held), "draft_n_round1_picks": int((held["round"] == 1).sum()),
            "draft_best_pick": held.pick_overall.min() if len(held) else np.nan,
            "draft_n_picks_acquired_by_trade": int((held.is_traded.astype(str) == "True").sum()),
            "draft_n_own_picks_traded_away": int(((iv.original_owner_team_id == team) & (iv.current_rights_holder_team_id != team)).sum())}


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
PERF_COLS = {"games_played": "perf_games_played", "wins": "perf_wins", "losses": "perf_losses",
             "overtime_losses": "perf_otl", "win_percentage": "perf_win_pct", "points_percentage": "perf_points_pct",
             "srs_bbref": "perf_srs", "sos_bbref": "perf_sos", "playoff_round_reached": "perf_playoff_round_reached",
             "champion": "perf_champion", "prior_season_win_pct": "perf_prior_win_pct",
             "win_pct_change_yoy": "perf_win_pct_change_yoy", "win_pct_3season_pooled": "perf_win_pct_3season_pooled"}


def perf_block(t: pd.Series, lg: str) -> dict:
    d = {v: t.get(k) for k, v in PERF_COLS.items()}
    d["perf_margin_per_game"] = t.get("point_differential_per_game") if lg == "WNBA" else t.get("goal_differential_per_game")
    d["perf_champion"] = (str(d["perf_champion"]) == "True") if pd.notna(d["perf_champion"]) else np.nan
    return d


def build_league(lg: str, ts, sp, dh, inv, fin, snap, ps_all) -> pd.DataFrame:
    teams = teams_table()
    teams = teams[teams.league == lg]
    t_all = ts[ts.league == lg].copy()
    t_all["_o"] = t_all.season.map(lambda s: season_order(lg, s))
    core = t_all[t_all.in_core_scope.astype(str) == "True"]
    seasons = sorted(t_all.season.unique(), key=lambda s: season_order(lg, s))
    nxt = {s: seasons[i + 1] for i, s in enumerate(seasons[:-1])}
    tidx = t_all.set_index(["season", "team_id"])
    meds = league_medians(sp[sp.league == lg])
    own = own_draftees_map(dh)
    spl = sp[sp.league == lg]
    rows = []

    # ---------------- season rows ----------------
    for t in core.itertuples():
        r = spl[(spl.season == t.season) & (spl.team_id == t.team_id)]
        rec = {"league": lg, "team_id": t.team_id, "team_name": t.team_name, "season": t.season,
               "season_start_year": t.season_start_year, "row_type": "season",
               "feature_basis": "season_roster_same_season_stats", "perf_basis_season": t.season}
        rec.update(perf_block(tidx.loc[(t.season, t.team_id)], lg))
        ns = nxt.get(t.season)
        if ns and (ns, t.team_id) in tidx.index:
            n = tidx.loc[(ns, t.team_id)]
            rec["out_next_win_pct"] = n.win_percentage
            rec["out_next_win_pct_change"] = n.win_percentage - t.win_percentage
            if lg == "PWHL":
                rec["out_next_points_pct"] = n.points_percentage
            rec["out_next_playoff_round_reached"] = n.playoff_round_reached
        rec.update(roster_features(r, lg, t.team_id, meds.get((lg, t.season)), own.get((lg, t.team_id), set())))
        # continuity vs the previous league-season for this franchise
        prev = [s for s in seasons if season_order(lg, s) < season_order(lg, t.season)]
        if prev:
            pr = spl[(spl.season == prev[-1]) & (spl.team_id == t.team_id)]
            if len(pr):
                rec["cont_share_playtime_from_returning"] = share(r[r.player_id.isin(set(pr.player_id))].playtime.sum(), r.playtime.sum())
                rec["cont_share_prior_playtime_retained"] = share(pr[pr.player_id.isin(set(r.player_id))].playtime.sum(), pr.playtime.sum())
                rec["cont_n_new_players"] = len(set(r.player_id) - set(pr.player_id))
        # availability of top playtime players (single-team only)
        n_top = PARAMS["top_n"][lg]
        single = r[r.n_teams_in_season.fillna(1) <= 1].sort_values("playtime", ascending=False).head(n_top)
        if len(single) and t.games_played:
            rec["avail_top_players_games_missed_share"] = 1 - single.games_played.mean() / t.games_played
        rec.update(draft_made(dh, lg, int(t.season_start_year), t.team_id))
        f = fin[(fin.league == lg) & (fin.record_type == "season") & (fin.season == t.season) & (fin.team_id == t.team_id)]
        if len(f) and pd.notna(f.payroll_reported_total.iloc[0]):
            f = f.iloc[0]
            basis = (f"{t.season} PWHLPA base salaries (as of {f.salary_as_of})" if lg == "PWHL" else
                     f"{t.season} Spotrac salary earnings via Mendeley Data (CC BY 4.0); cash earned, not cap hits")
            rec.update({"fin_basis": basis,
                        "fin_payroll_reported_total": f.payroll_reported_total,
                        "fin_payroll_top_n_share": f.top8_salary_share if lg == "PWHL" else f.top5_salary_share,
                        "fin_payroll_share_of_cap": f.pct_of_cap_committed if lg == "WNBA" else np.nan,
                        "fin_avg_salary_vs_requirement": f.avg_salary_vs_requirement if lg == "PWHL" else np.nan,
                        "fin_salary_coverage_share": f.salary_coverage_share})
        rows.append(rec)

    # ---------------- current rows ----------------
    latest = LATEST[lg]
    lat = spl[spl.season == latest]
    agg = lat.groupby("player_id").agg(playtime=("playtime", "sum"), production=("production", "sum"),
                                       games_played=("games_played", "sum"), is_goalie=("is_goalie", "max"),
                                       teams=("team_id", lambda x: set(x)))
    # per-team latest-season playtime per player (for continuity)
    lat_team_pt = lat.groupby(["player_id", "team_id"]).playtime.sum()
    hist_exp = spl.groupby("player_id").season.nunique()  # PWHL: seasons played = prior PWHL seasons for 2026-27
    last_exp = ps_all[ps_all.league == lg].sort_values("season_start_year").groupby("player_id").experience_years.last()
    last_season = ps_all[ps_all.league == lg].sort_values("season_start_year").groupby("player_id").season.last()
    s_lg = snap[snap.league == lg] if not snap.empty else pd.DataFrame()
    active = teams[teams.status_as_of_snapshot.isin(["active", "relocating", "expansion_not_yet_played"])]
    n_league = len(active)
    for tm in active.itertuples():
        ros = s_lg[s_lg.snapshot_team_id == tm.franchise_id].copy()
        rec = {"league": lg, "team_id": tm.franchise_id, "team_name": tm.current_team_name, "season": UPCOMING[lg],
               "season_start_year": int(UPCOMING[lg][:4]), "row_type": "current",
               "feature_basis": f"current_roster_snapshot_{ros.snapshot_date.iloc[0] if len(ros) else 'missing'}_x_{latest}_stats",
               "perf_basis_season": latest}
        if (latest, tm.franchise_id) in tidx.index:
            rec.update(perf_block(tidx.loc[(latest, tm.franchise_id)], lg))
        if len(ros):
            pid = ros.player_id
            ros["age"] = pd.to_numeric(ros.age_at_snapshot, errors="coerce")
            ros["playtime"] = pid.map(agg.playtime)
            ros["production"] = pid.map(agg.production)
            ros["games_played"] = pid.map(agg.games_played).fillna(0)
            ros["is_goalie"] = pid.map(agg.is_goalie).fillna(ros.position.astype(str).str.upper().eq("G")).astype(bool)
            if lg == "WNBA":
                snap_exp = pd.to_numeric(ros.experience_years, errors="coerce")
                # history-based fallback: last BBRef experience + seasons elapsed
                fb = pid.map(last_exp) + (int(latest) + 1 - pd.to_numeric(pid.map(last_season), errors="coerce"))
                ros["exp"] = snap_exp.fillna(fb)
            else:
                ros["exp"] = pid.map(hist_exp).fillna(0)  # no PWHL history = 0 prior PWHL seasons
            rec.update(roster_features(ros, lg, tm.franchise_id, meds.get((lg, latest)), own.get((lg, tm.franchise_id), set())))
            pt_here = sum(lat_team_pt.get((p, tm.franchise_id), 0) for p in pid.dropna())
            rec["cont_share_playtime_from_returning"] = share(pt_here, ros.playtime.sum())
            team_lat = lat[lat.team_id == tm.franchise_id]
            rec["cont_share_prior_playtime_retained"] = share(team_lat[team_lat.player_id.isin(set(pid.dropna()))].playtime.sum(),
                                                             team_lat.playtime.sum()) if len(team_lat) else np.nan
            rec["cont_n_new_players"] = int(sum(1 for p in pid if not (isinstance(p, str) and tm.franchise_id in agg.teams.get(p, set()))))
            rec["ctx_roster_players_without_prior_stats"] = int((ros.playtime.fillna(0) <= 0).sum())
        rec.update(draft_held(inv, lg, tm.franchise_id) if lg == "WNBA" else draft_made(dh, lg, int(UPCOMING[lg][:4]), tm.franchise_id))
        if lg == "PWHL":
            f = fin[(fin.league == lg) & (fin.record_type == "current_snapshot") & (fin.team_id == tm.franchise_id)]
            if len(f):
                f = f.iloc[0]
                exp_col = f"n_known_contracts_expiring_after_{UPCOMING[lg]}"
                rec.update({"fin_basis": "known contract terms (Wikipedia transactions since 2025; lower bounds)",
                            "fin_known_contract_share_of_roster": f.known_contract_share_of_roster,
                            "fin_n_known_contracts_expiring_after_season": f.get(exp_col),
                            "fin_n_known_multi_year_contracts": f.n_known_contracts_multi_year_beyond_upcoming})
        rec["ctx_relocating_next_season"] = tm.status_as_of_snapshot == "relocating"
        rec["ctx_roster_snapshot_quality"] = ("wikipedia_template_pre_free_agency_may_reflect_end_of_season_roster" if lg == "WNBA"
                                              else "wikipedia_preseason_roster")
        rows.append(rec)

    df = pd.DataFrame(rows)
    # ---------------- context ----------------
    first = t_all.groupby("team_id").franchise_first_season.first().dropna().astype(int).to_dict()
    for r in teams.itertuples():  # franchises with no completed season yet (PWHL 2026-27 expansion)
        if r.franchise_id not in first and r.first_season_in_data_window:
            first[r.franchise_id] = int(r.first_season_in_data_window[:4])
    df["ctx_franchise_prior_seasons"] = [int(sy) - first[t] if t in first else np.nan
                                         for t, sy in zip(df.team_id, df.season_start_year)]
    df["ctx_expansion_first_season"] = df.ctx_franchise_prior_seasons == 0
    df["ctx_n_teams_in_league"] = df.groupby("season").team_id.transform("count")
    df.loc[df.row_type == "current", "ctx_n_teams_in_league"] = n_league
    if "ctx_relocating_next_season" not in df:
        df["ctx_relocating_next_season"] = False
    df["ctx_relocating_next_season"] = df.ctx_relocating_next_season.fillna(False).astype(bool)
    df["is_latest_completed_season"] = (df.row_type == "season") & (df.season == latest)
    return df


COLUMN_ORDER = [
    "league", "team_id", "team_name", "season", "season_start_year", "row_type", "is_latest_completed_season",
    "feature_basis", "perf_basis_season",
    "perf_games_played", "perf_wins", "perf_losses", "perf_otl", "perf_win_pct", "perf_points_pct", "perf_margin_per_game",
    "perf_srs", "perf_sos", "perf_playoff_round_reached", "perf_champion", "perf_prior_win_pct", "perf_win_pct_change_yoy",
    "perf_win_pct_3season_pooled",
    "out_next_win_pct", "out_next_points_pct", "out_next_win_pct_change", "out_next_playoff_round_reached",
    "roster_n", "roster_n_with_playtime",
    "age_mean", "age_median", "age_playtime_weighted", "age_top_n_by_playtime", "age_top_n_by_production",
    "age_pct_players_under_25", "age_pct_players_30_plus", "age_share_playtime_under_25", "age_share_playtime_30_plus",
    "age_n_young_meaningful", "age_data_coverage",
    "exp_mean", "exp_playtime_weighted",
    "conc_top1_share_production", "conc_top3_share_production", "conc_top_n_share_production",
    "conc_top3_share_playtime", "conc_playtime_hhi", "conc_n_meaningful_playtime", "conc_goalie_top1_share_playtime",
    "qual_production_per_playtime", "qual_n_above_league_median_rate",
    "cont_share_playtime_from_returning", "cont_share_prior_playtime_retained", "cont_n_new_players",
    "avail_top_players_games_missed_share",
    "draft_year_used", "draft_pick_status", "draft_n_picks", "draft_n_round1_picks", "draft_best_pick",
    "draft_n_picks_acquired_by_trade", "draft_n_own_picks_traded_away", "draft_own_draftee_playtime_share",
    "fin_basis", "fin_payroll_reported_total", "fin_payroll_top_n_share", "fin_salary_coverage_share",
    "fin_payroll_share_of_cap", "fin_avg_salary_vs_requirement",
    "fin_known_contract_share_of_roster", "fin_n_known_contracts_expiring_after_season",
    "fin_n_known_multi_year_contracts",
    "ctx_franchise_prior_seasons", "ctx_expansion_first_season", "ctx_relocating_next_season",
    "ctx_n_teams_in_league", "ctx_roster_players_without_prior_stats", "ctx_roster_snapshot_quality",
]
# Concepts that do not exist (or have no source) for a league -> column omitted from that league's file.
NOT_APPLICABLE = {
    "WNBA": ["perf_otl", "perf_points_pct", "out_next_points_pct", "conc_goalie_top1_share_playtime",
             "fin_avg_salary_vs_requirement",  # PWHL CBA concept (team-average requirement)
             "fin_known_contract_share_of_roster", "fin_n_known_contracts_expiring_after_season",
             "fin_n_known_multi_year_contracts"],  # no WNBA contract-term source
    "PWHL": ["perf_srs", "perf_sos",
             "fin_payroll_share_of_cap"],  # PWHL has no hard cap
}
ROUND = {"age_": 2, "exp_": 2}


def tidy(df: pd.DataFrame, lg: str) -> pd.DataFrame:
    cols = [c for c in COLUMN_ORDER if c not in NOT_APPLICABLE[lg]]
    for c in cols:
        if c not in df:
            df[c] = np.nan
    extra = [c for c in df.columns if c not in COLUMN_ORDER]
    if extra:
        log.warning("%s: dropping unlisted columns %s", lg, extra)
    df = df[cols].copy()
    for c in cols:
        if pd.api.types.is_float_dtype(df[c]):
            if c.startswith(("age_mean", "age_median", "age_playtime", "age_top", "exp_")):
                df[c] = df[c].round(2)
            elif c in ("fin_payroll_reported_total",):
                df[c] = df[c].round(2)
            else:
                df[c] = df[c].round(4)
    count_cols = [c for c in cols if c.startswith(("perf_games", "perf_wins", "perf_losses", "perf_otl", "roster_n", "draft_n_",
                                                   "draft_year", "cont_n_", "age_n_", "conc_n_", "qual_n_", "fin_n_",
                                                   "ctx_n_", "ctx_roster_players", "ctx_franchise_prior", "perf_playoff",
                                                   "out_next_playoff", "draft_best", "season_start_year"))
                  and not c.endswith("_note")]
    for c in count_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df.sort_values(["row_type", "season", "team_id"], key=lambda s: s.map({"season": 0, "current": 1}) if s.name == "row_type" else s).reset_index(drop=True)


def main() -> None:
    base_argparser(__doc__.splitlines()[0]).parse_args()
    ts = load(settings.EXPORTS_DIR / "team_season_data.csv")
    ps = load(settings.EXPORTS_DIR / "player_season_data.csv")
    dh = load(settings.EXPORTS_DIR / "draft_history.csv")
    fin = load(settings.EXPORTS_DIR / "team_financials.csv")
    inv = load(settings.PROCESSED_DIR / "draft_pick_inventory.csv")
    snap = load(settings.PROCESSED_DIR / "current_roster_snapshot.csv")
    sp = std_players(ps)
    settings.FINAL_DIR.mkdir(parents=True, exist_ok=True)
    for lg, fname in (("WNBA", "wnba_team_doom_dataset.csv"), ("PWHL", "pwhl_team_doom_dataset.csv")):
        df = tidy(build_league(lg, ts, sp, dh, inv, fin, snap, ps), lg)
        if df.duplicated(["team_id", "season"]).any():
            raise ValueError(f"duplicate team_id/season in {fname}")
        write_csv(df, settings.FINAL_DIR / fname)
        log.info("%s: %d rows (%d season, %d current), %d columns", lg, len(df), (df.row_type == "season").sum(),
                 (df.row_type == "current").sum(), df.shape[1])
    (settings.FINAL_DIR / "feature_params.json").write_text(json.dumps(PARAMS, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
