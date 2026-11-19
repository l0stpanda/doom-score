"""05 - Build descriptive team-season features from the collected player, draft and financial tables.

WHAT IT DOES
    Aggregates player_season_data, draft_history, draft_pick_inventory,
    team_financials and current_roster_snapshot into team-level DESCRIPTIVE
    features. It does NOT compute a Doom Score, combine features, standardise
    them, or assign weights. Every threshold used below is a named parameter in
    PARAMS (recorded in the output) so alternative definitions can be tested.

LEAGUES / SEASONS
    WNBA 2021-2026, PWHL 2023-24..2025-26 (historical rows), plus one
    current-snapshot row per active franchise (record_type='current_snapshot').

OUTPUTS
    data/exports/team_features.csv         (key: league, season, record_type, team_id)
    data/exports/team_features_params.json (the parameter values used)

INPUTS (all produced by scripts 01-04)
    team_season_data.csv, player_season_data.csv, draft_history.csv,
    draft_pick_inventory.csv, team_financials.csv, current_roster_snapshot.csv

FEATURE DEFINITIONS (players = rows with games_played > 0 for the team-season)
    playing time  = minutes (WNBA) / time_on_ice_total_min (PWHL, skaters + goalies)
    roster_n_appeared, roster_n_listed
    age_mean / age_median        unweighted over players (age_at_reference)
    age_playtime_weighted        sum(age * playing time) / sum(playing time)
    pct_players_under_25 / over_30  share of players (age_at_reference <25 / >=30)
    playtime_share_under_25 / over_30  share of team playing time
    experience_mean, experience_playtime_weighted (league-specific experience definitions)
    n_young_meaningful           players <25 meeting the "meaningful playing time" rule (PARAMS)
    age_mean_top{N}_by_<metric>  mean age of the top N players by <metric>
                                 (WNBA N=5: minutes, win_shares; PWHL N=8: toi, points)
    top{k}_share_<metric>        share of team total <metric> produced by its top k players
    playtime_hhi                 Herfindahl index of playing-time shares (sum of squared shares)
    n_above_league_median_<metric>  players above the league-season median of a rate
                                 metric among qualified players (PARAMS); comparison population
                                 = all qualified players in the same league-season
    continuity_playtime_share    share of this season's playing time from players who also
                                 played for the team in the previous league-season
    retention_prior_playtime_share  share of last season's playing time from players who
                                 play for the team again this season
    n_new_players / n_departed_players
    draft_*                      counts from that team's entry draft held before the season
                                 (WNBA: draft year = season; PWHL: draft year = season start year)
    snapshot_* (current rows)    share of latest-season playing time retained on the current
                                 roster snapshot; future picks held from draft_pick_inventory
    payroll fields               copied from team_financials (null where not collected)

KNOWN LIMITATIONS
    * Win Shares are only available for the WNBA; PWHL "contribution" uses TOI and points.
    * Ages / experience inherit source limitations (see 02 docstring).
    * Snapshot features rely on Wikipedia current rosters (secondary, dated).
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
from lib.store import upsert_csv

SCRIPT = "05_build_team_features.py"
log = setup_logging("05_build_team_features")

PARAMS = {
    "age_young_threshold": 25,          # strictly below
    "age_old_threshold": 30,            # at or above
    "top_n": {"WNBA": 5, "PWHL": 8},
    "top_k_concentration": [1, 3],
    "meaningful_playtime": {"WNBA": {"min_games": 10, "min_minutes_per_game": 15.0},
                            "PWHL": {"min_games": 10, "min_toi_per_game": 12.0}},
    "qualified_for_league_median": {"WNBA": {"min_minutes": 200, "metric": "ws_per_40"},
                                    "PWHL": {"min_games": 10, "metric": "points_per_game", "skaters_only": True}},
}


def load(name: str) -> pd.DataFrame:
    p = settings.EXPORTS_DIR / name
    return pd.read_csv(p, dtype={"season": str}, low_memory=False) if p.exists() else pd.DataFrame()


def playtime(df: pd.DataFrame) -> pd.Series:
    return np.where(df.league == "WNBA", df.minutes, df.time_on_ice_total_min)


def wmean(x, w):
    m = x.notna() & w.notna() & (w > 0)
    return float((x[m] * w[m]).sum() / w[m].sum()) if m.any() else np.nan


def team_player_features(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["playtime"] = playtime(p)
    p["appeared"] = p.games_played.fillna(0) > 0
    # league-season medians for "above-average" counts
    med = {}
    for (lg, ssn), d in p[p.appeared].groupby(["league", "season"]):
        q = PARAMS["qualified_for_league_median"][lg]
        if lg == "WNBA":
            pool = d[d.minutes.fillna(0) >= q["min_minutes"]]
        else:
            pool = d[(d.games_played >= q["min_games"]) & (d.is_goalie.astype(str) != "True")]
        med[(lg, ssn)] = pool[q["metric"]].median()
    rows = []
    for (lg, ssn, tid), d in p.groupby(["league", "season", "team_id"]):
        a = d[d.appeared]
        pt = a.playtime
        tot_pt = pt.sum()
        rec = {"league": lg, "season": ssn, "team_id": tid, "roster_n_listed": len(d), "roster_n_appeared": len(a)}
        ages = a.age_at_reference
        rec.update({"age_mean": ages.mean(), "age_median": ages.median(), "age_playtime_weighted": wmean(ages, pt),
                    "pct_players_under_25": (ages < PARAMS["age_young_threshold"]).mean() if ages.notna().any() else np.nan,
                    "pct_players_over_30": (ages >= PARAMS["age_old_threshold"]).mean() if ages.notna().any() else np.nan,
                    "playtime_share_under_25": pt[ages < PARAMS["age_young_threshold"]].sum() / tot_pt if tot_pt else np.nan,
                    "playtime_share_over_30": pt[ages >= PARAMS["age_old_threshold"]].sum() / tot_pt if tot_pt else np.nan,
                    "age_coverage_share": ages.notna().mean() if len(a) else np.nan,
                    "experience_mean": a.experience_years.mean(),
                    "experience_playtime_weighted": wmean(a.experience_years, pt),
                    "playtime_total": tot_pt, "playtime_unit": "minutes" if lg == "WNBA" else "toi_minutes",
                    "playtime_hhi": float(((pt / tot_pt) ** 2).sum()) if tot_pt else np.nan})
        mp = PARAMS["meaningful_playtime"][lg]
        if lg == "WNBA":
            meaningful = (a.games_played >= mp["min_games"]) & (a.minutes_per_game >= mp["min_minutes_per_game"])
        else:
            meaningful = (a.games_played >= mp["min_games"]) & ((a.toi_per_game >= mp["min_toi_per_game"]) | (a.is_goalie.astype(str) == "True"))
        rec["n_meaningful_playtime"] = int(meaningful.sum())
        rec["n_young_meaningful"] = int((meaningful & (ages < PARAMS["age_young_threshold"])).sum())
        n = PARAMS["top_n"][lg]
        metrics = {"WNBA": {"minutes": "minutes", "win_shares": "ws", "points": "points"},
                   "PWHL": {"toi": "time_on_ice_total_min", "points": "points", "goals": "goals"}}[lg]
        for label, col in metrics.items():
            vals = a[col]
            tops = a.loc[vals.sort_values(ascending=False).index[:n]]
            rec[f"age_mean_top{n}_by_{label}"] = tops.age_at_reference.mean() if vals.notna().any() else np.nan
            total = vals.sum()
            for k in PARAMS["top_k_concentration"] + [n]:
                rec[f"top{k}_share_{label}"] = vals.sort_values(ascending=False).head(k).sum() / total if total and total > 0 else np.nan
            rec[f"team_total_{label}"] = total
        if lg == "WNBA":
            rec["per_minutes_weighted"] = wmean(a.per, a.minutes)
            rec["ws_per_40_minutes_weighted"] = wmean(a.ws_per_40, a.minutes)
        else:
            g = a[a.is_goalie.astype(str) == "True"]
            gt = g.time_on_ice_total_min
            rec["goalie_top1_toi_share"] = gt.max() / gt.sum() if gt.sum() else np.nan
            rec["goalie_save_pct_toi_weighted"] = wmean(g.save_pct, gt)
            sk = a[a.is_goalie.astype(str) != "True"]
            rec["skater_toi_hhi"] = float(((sk.time_on_ice_total_min / sk.time_on_ice_total_min.sum()) ** 2).sum()) if sk.time_on_ice_total_min.sum() else np.nan
        q = PARAMS["qualified_for_league_median"][lg]
        m = med.get((lg, ssn))
        if lg == "WNBA":
            pool = a[a.minutes.fillna(0) >= q["min_minutes"]]
        else:
            pool = a[(a.games_played >= q["min_games"]) & (a.is_goalie.astype(str) != "True")]
        rec[f"n_above_league_median_{q['metric']}"] = int((pool[q["metric"]] > m).sum()) if m is not None and pd.notna(m) else np.nan
        rec[f"league_median_{q['metric']}"] = m
        # availability of top players by playing time (single-team players only)
        single = a[a.n_teams_in_season.fillna(1) <= 1]
        rec["tmp_top_pt_players"] = list(single.sort_values("playtime", ascending=False).player_id.head(n))
        rows.append(rec)
    return pd.DataFrame(rows)


def continuity(p: pd.DataFrame) -> pd.DataFrame:
    p = p[p.games_played.fillna(0) > 0].copy()
    p["playtime"] = playtime(p)
    out = []
    for lg, d in p.groupby("league"):
        order = sorted(d.season.unique(), key=lambda s: int(str(s)[:4]))
        for i, ssn in enumerate(order):
            if i == 0:
                continue
            prev = order[i - 1]
            for tid, cur in d[d.season == ssn].groupby("team_id"):
                prv = d[(d.season == prev) & (d.team_id == tid)]
                if prv.empty:
                    continue
                cur_ids, prv_ids = set(cur.player_id), set(prv.player_id)
                out.append({"league": lg, "season": ssn, "team_id": tid,
                            "continuity_playtime_share": cur[cur.player_id.isin(prv_ids)].playtime.sum() / cur.playtime.sum(),
                            "retention_prior_playtime_share": prv[prv.player_id.isin(cur_ids)].playtime.sum() / prv.playtime.sum(),
                            "n_new_players": len(cur_ids - prv_ids), "n_departed_players": len(prv_ids - cur_ids)})
    return pd.DataFrame(out)


def draft_features(dh: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    if dh.empty:
        return pd.DataFrame()
    e = dh[dh.draft_type == "entry"].copy()
    out = []
    for r in ts[["league", "season", "season_start_year", "team_id"]].drop_duplicates().itertuples():
        dy = int(r.season_start_year)
        d = e[(e.league == r.league) & (e.draft_year == dy)]
        if d.empty:
            continue
        mine = d[d.selecting_team_id == r.team_id]
        out.append({"league": r.league, "season": r.season, "team_id": r.team_id, "draft_year_used": dy,
                    "draft_n_picks_made": len(mine), "draft_n_round1_picks": int((mine["round"] == 1).sum()),
                    "draft_best_pick_overall": mine.pick_overall.min() if len(mine) else np.nan,
                    "draft_n_picks_acquired_by_trade": int((mine.pick_traded_before_draft.astype(str) == "True").sum()),
                    "draft_n_own_picks_traded_away": int(((d.original_owner_team_id == r.team_id) & (d.selecting_team_id != r.team_id)).sum())})
    return pd.DataFrame(out)


def drafted_on_roster(p: pd.DataFrame, dh: pd.DataFrame) -> pd.DataFrame:
    if dh.empty or "player_id" not in dh:
        return pd.DataFrame()
    e = dh[(dh.draft_type == "entry") & dh.player_id.notna()][["league", "player_id", "selecting_team_id", "draft_year"]]
    e = e.sort_values("draft_year").drop_duplicates(["league", "player_id"])
    a = p[p.games_played.fillna(0) > 0].merge(e, on=["league", "player_id"], how="left")
    a["playtime"] = playtime(a)
    a["own_draftee"] = a.selecting_team_id == a.team_id
    g = a.groupby(["league", "season", "team_id"]).apply(
        lambda d: pd.Series({"n_own_draftees_appeared": int(d.own_draftee.sum()),
                             "own_draftee_playtime_share": d[d.own_draftee].playtime.sum() / d.playtime.sum() if d.playtime.sum() else np.nan}),
        include_groups=False)
    return g.reset_index()


def snapshot_rows(p: pd.DataFrame, snap: pd.DataFrame, inv: pd.DataFrame, fin: pd.DataFrame) -> pd.DataFrame:
    teams = teams_table()
    teams = teams[teams.status_as_of_snapshot.isin(["active", "relocating", "expansion_not_yet_played"])]
    latest = {"WNBA": str(settings.WNBA_LATEST_COMPLETED_SEASON), "PWHL": settings.PWHL_LATEST_COMPLETED_SEASON}
    rows = []
    pp = p[p.games_played.fillna(0) > 0].copy()
    pp["playtime"] = playtime(pp)
    for t in teams.itertuples():
        lg = t.league
        rec = {"league": lg, "season": "current_snapshot", "record_type": "current_snapshot", "team_id": t.franchise_id,
               "team_name": t.current_team_name, "latest_completed_season": latest[lg]}
        s = snap[(snap.league == lg) & (snap.snapshot_team_id == t.franchise_id)] if not snap.empty else pd.DataFrame()
        if len(s):
            rec["snapshot_date"] = s.snapshot_date.iloc[0]
            rec["snapshot_roster_n"] = len(s)
            ages = pd.to_numeric(s.age_at_snapshot, errors="coerce")
            if ages.isna().all() and "age_integer_source" in s:
                ages = pd.to_numeric(s.age_integer_source, errors="coerce")
                rec["snapshot_age_basis"] = "integer age shown on source page"
            else:
                rec["snapshot_age_basis"] = "decimal age at snapshot date from DOB"
            rec["snapshot_age_mean"] = ages.mean()
            rec["snapshot_age_median"] = ages.median()
            rec["snapshot_pct_under_25"] = (ages < PARAMS["age_young_threshold"]).mean() if ages.notna().any() else np.nan
            rec["snapshot_pct_over_30"] = (ages >= PARAMS["age_old_threshold"]).mean() if ages.notna().any() else np.nan
            rec["snapshot_n_matched_to_history"] = int(s.player_id.notna().sum())
            last = pp[(pp.league == lg) & (pp.season == latest[lg]) & (pp.team_id == t.franchise_id)]
            if len(last) and last.playtime.sum():
                kept = last[last.player_id.isin(set(s.player_id.dropna()))]
                rec["snapshot_latest_season_playtime_retained_share"] = kept.playtime.sum() / last.playtime.sum()
                rec["snapshot_latest_season_players_retained"] = len(kept)
                rec["snapshot_latest_season_players_total"] = len(last)
            # players on the snapshot roster who played elsewhere last season (incoming)
            prev_team = pp[(pp.league == lg) & (pp.season == latest[lg])].groupby("player_id").team_id.agg(lambda x: ";".join(sorted(set(x))))
            inc = s[s.player_id.notna() & s.player_id.map(prev_team).notna() & ~s.player_id.map(prev_team).fillna("").str.contains(t.franchise_id, regex=False)]
            rec["snapshot_n_incoming_from_other_teams"] = len(inc)
            other_pt = pp[(pp.league == lg) & (pp.season == latest[lg]) & pp.player_id.isin(set(inc.player_id))]
            rec["snapshot_incoming_latest_season_playtime"] = other_pt.playtime.sum()
        if not inv.empty and (inv.league == lg).any():
            iv = inv[(inv.league == lg)]
            held = iv[iv.current_rights_holder_team_id == t.franchise_id]
            rec["future_draft_year"] = iv.draft_year.min() if len(iv) else np.nan
            rec["future_picks_known_held"] = len(held)
            rec["future_round1_picks_known_held"] = int((held["round"] == 1).sum())
            rec["future_best_known_pick_slot"] = held.pick_overall.min() if len(held) else np.nan
            rec["future_own_picks_known_traded_away"] = int(((iv.original_owner_team_id == t.franchise_id) & (iv.current_rights_holder_team_id != t.franchise_id)).sum())
            rec["future_pick_inventory_completeness"] = ("full_draft_order_listed" if lg == "WNBA" else
                                                         "traded_picks_only_own_picks_not_assumed")
        else:
            # No inventory source for this league: unknown, not zero.
            rec["future_pick_inventory_completeness"] = "not_available_no_source"
        if lg == "WNBA" and len(s):
            rec["snapshot_caveat"] = ("WNBA offseason: Wikipedia roster templates largely still reflect end-of-season "
                                      "rosters before free agency; retention shares are not a forward-looking roster.")
        f = fin[(fin.league == lg) & (fin.record_type == "current_snapshot") & (fin.team_id == t.franchise_id)] if not fin.empty else pd.DataFrame()
        if len(f):
            for c in f.columns:
                if c.startswith("n_known_contracts") or c in ("team_average_salary_requirement", "league_min_salary", "financial_data_status"):
                    rec[f"fin_{c}"] = f[c].iloc[0]
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    base_argparser(__doc__.splitlines()[0]).parse_args()
    ts, p, dh = load("team_season_data.csv"), load("player_season_data.csv"), load("draft_history.csv")
    inv, fin, snap = load("draft_pick_inventory.csv"), load("team_financials.csv"), load("current_roster_snapshot.csv")
    core = ts[ts.in_core_scope.astype(str) == "True"][["league", "season", "season_start_year", "team_id", "team_name",
                                                       "games_played", "win_percentage", "points_percentage"]]
    feats = core.merge(team_player_features(p), on=["league", "season", "team_id"], how="left")
    # availability: games missed by top playing-time players (single-team players)
    gp_map = p.set_index(["league", "season", "team_id", "player_id"]).games_played.to_dict()
    miss = []
    for r in feats.itertuples():
        ids = r.tmp_top_pt_players if isinstance(r.tmp_top_pt_players, list) else []
        if not ids or not r.games_played:
            miss.append(np.nan); continue
        gp = [gp_map.get((r.league, r.season, r.team_id, i), np.nan) for i in ids]
        miss.append(1 - np.nanmean(gp) / r.games_played)
    feats["top_playtime_players_games_missed_share"] = miss
    feats = feats.drop(columns=["tmp_top_pt_players"])
    for extra in (continuity(p), draft_features(dh, ts), drafted_on_roster(p, dh)):
        if not extra.empty:
            feats = feats.merge(extra, on=["league", "season", "team_id"], how="left")
    if not fin.empty:
        fcols = ["league", "season", "team_id", "payroll_reported_total", "payroll_avg", "salary_coverage_share",
                 "top5_salary_share", "top8_salary_share", "pct_of_cap_committed", "cap_space", "avg_salary_vs_requirement",
                 "team_salary_cap", "team_average_salary_requirement", "financial_data_status"]
        fs = fin[fin.record_type == "season"][[c for c in fcols if c in fin]]
        feats = feats.merge(fs, on=["league", "season", "team_id"], how="left")
    feats["record_type"] = "season"
    snapdf = snapshot_rows(p, snap, inv, fin)
    out = pd.concat([feats, snapdf], ignore_index=True)
    out["feature_params_file"] = "team_features_params.json"
    first = ["league", "season", "record_type", "team_id", "team_name"]
    out = out[first + [c for c in out.columns if c not in first]]
    upsert_csv(out, settings.EXPORTS_DIR / "team_features.csv", ["league", "season", "record_type", "team_id"],
               replace_scope={"league": ["WNBA", "PWHL"]})
    (settings.EXPORTS_DIR / "team_features_params.json").write_text(json.dumps(PARAMS, indent=2), encoding="utf-8")
    log.info("done: %d feature rows (%d historical, %d snapshot)", len(out), len(feats), len(snapdf))


if __name__ == "__main__":
    main()
