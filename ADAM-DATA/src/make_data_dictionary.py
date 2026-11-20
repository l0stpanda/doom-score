"""Write DATA_DICTIONARY.md: definition, source, as-of timing, coverage (computed), leakage note for every column."""
import os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
df = pd.read_csv(os.path.join(ROOT, "data", "processed", "mlb_nhl_team_seasons.csv"))

MLBAPI, NHLAPI = "MLB Stats API (statsapi.mlb.com)", "NHL stats REST (api.nhle.com)"
WIKI = "Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs)"
END_T = "end of season t"
PM = "prediction moment (MLB Nov 15 t; NHL Jun 15 t+1)"
OK = "Season t or earlier only."

# column: (definition, source, as-of, leakage note)
D = {
 "league": ("MLB or NHL.", "-", "-", "Identifier."),
 "season_start_year": ("Calendar year season t starts (NHL 2017 = 2017-18).", "-", "-", "Identifier."),
 "franchise_id": ("Lowercase-hyphenated current franchise name, constant through relocations/renames.", "Derived", "-", "Identifier."),
 "team": ("Franchise's current name (same for all years).", "MLB/NHL APIs", "-", "Identifier."),
 "wins": ("Regular-season wins.", MLBAPI + " / " + NHLAPI, END_T, OK),
 "losses": ("Regular-season losses (NHL: regulation losses).", MLBAPI + " / " + NHLAPI, END_T, OK),
 "ties": ("MLB: tie games. NHL: OT/SO losses (+ real ties 2002-04) so that win_pct = NHL points %.", MLBAPI + " / " + NHLAPI, END_T, OK),
 "games": ("Games played (MLB W+L+T; NHL W+L+OTL).", MLBAPI + " / " + NHLAPI, END_T, OK),
 "win_pct": ("(wins + 0.5*ties) / games.", "Derived", END_T, OK),
 "point_diff_per_game": ("(runs/goals for - against) / games.", "Derived", END_T, OK),
 "win_pct_percentile": ("Within league-season: (average ascending rank - 1)/(n - 1)*100; worst 0, best 100.", "Derived", END_T, OK),
 "win_pct_trailing_3_seasons": ("Mean win_pct of the franchise's last 3 played seasons incl. t (min 1).", "Derived", END_T, OK),
 "observed_doom_next_3_seasons": ("= y_doom_3yr (teammate schema name). **LABEL, not a feature.**", "Derived", "seasons t+1..t+3", "Label - never use as a feature."),
 "draft_picks_used": ("Picks made by the team in the year-t draft (MLB Jun/Jul t; NHL Jun t, before season t).", "MLB Stats API draft / NHL api-web draft", "draft of year t", "MLB July draft is before Nov; NHL uses the June t draft only (June t+1 is after the moment)."),
 "cap_space_pct": ("NHL: (cap ceiling - team cap hit)/ceiling. **Empty: no historical team cap hits available** (Spotrac 403, PuckPedia anti-bot, CapWages current-season only) -> data/manual/payroll_template.csv. MLB: not defined (no cap); see payroll_pct_of_cbt.", "-", "season t", OK),
 "personnel_lead_tenure_years": ("Years the current GM has been the team's GM at the prediction moment (GM only, both leagues).", WIKI, PM, "Measured at the moment, never total tenure. Year-only dates are placed after that year's season (MLB except Giants/Rays)."),
 "personnel_lead_changed_past_year": ("1 if the GM at the moment differs from the GM 365 days earlier (VACANT counts as a state). **MLB 2026 is systematically 0**: every 2026 MLB change in the sources is year-only and is placed on Dec 31, after the Nov 15 moment.", WIKI, PM, OK),
 "standings_source": ("API URL for the standings row.", "-", "-", "Audit."),
 "draft_source": ("API URL for the draft data.", "-", "-", "Audit."),
 "ot_losses": ("NHL overtime/shootout losses.", NHLAPI, END_T, OK),
 "win_pct_raw": ("wins / games (NHL without OTL credit).", "Derived", END_T, OK),
 "scored_per_game": ("Runs/goals scored per game.", "Standings APIs", END_T, OK),
 "allowed_per_game": ("Runs/goals allowed per game.", "Standings APIs", END_T, OK),
 "pythag_win_pct": ("RS^k/(RS^k+RA^k); k = 1.83 MLB, 2.0 NHL.", "Derived", END_T, OK),
 "luck": ("win_pct - pythag_win_pct.", "Derived", END_T, OK),
 "win_pct_change_1yr": ("win_pct(t) - win_pct(previous played season).", "Derived", END_T, OK),
 "win_pct_slope_3yr": ("OLS slope of win_pct over the last 3 played seasons (needs >= 2).", "Derived", END_T, OK),
 "seasons_of_history": ("Number of franchise seasons available up to t (from 1997 MLB / 2002 NHL).", "Derived", END_T, OK),
 "short_season": ("MLB 2020; NHL 2012, 2019, 2020.", "Derived", "-", OK),
 "expansion_first_3_seasons": ("Vegas 2017-19, Seattle 2021-23.", "Derived", "-", OK),
 "draft_picks_rd1_2": ("Picks listed up to and incl. round 2 (MLB incl. supplemental 1st, Competitive Balance Round A, PPI; NHL rounds 1-2).", "Draft APIs", "draft of year t", OK),
 "draft_first_pick_number": ("Team's earliest overall pick in the year-t draft.", "Draft APIs", "draft of year t", OK),
 "draft_rounds_in_year": ("Distinct round labels in that year's draft (MLB 2020 had 5 rounds).", "Draft APIs", "draft of year t", OK),
 "draft_picks_used_pctile": ("Within league-season percentile of draft_picks_used (comparable across MLB round-count changes).", "Derived", "draft of year t", OK),
 "coach_name": ("Manager/head coach at the end of the regular season t.", "MLB Stats API coaches / " + WIKI, "last regular-season game of t", "Changes after the last regular-season game are not captured."),
 "coach_tenure_years": ("Consecutive seasons as season-end coach incl. t; a first season taken over mid-season counts 0.5.", "as above", "end of regular season t", OK),
 "coach_changed_during_regular_season": ("1 if more than one manager/coach ran the team during regular season t.", "as above", "end of regular season t", "Post-season firings/hires before the moment are not captured."),
 "coach_tenure_left_censored": ("Tenure streak reaches the start of the coach history (true tenure may be longer).", "Derived", "-", OK),
 "manager_resolved_by_fallback": ("MLB: season-end manager resolved by the interim rule (titled manager on leave + interim; 4 rows).", "MLB Stats API", "-", OK),
 "personnel_lead_name": ("GM at the prediction moment (NaN if vacant or unknown).", WIKI, PM, "All Wikipedia spans are needs_verification."),
 "personnel_lead_tenure_left_censored": ("GM tenure reaches the start of available spans (<=1999).", "Derived", "-", OK),
 "personnel_lead_gap_carried": ("1 if no active GM span and the last GM (ended <=400 days earlier, imprecise dates) was carried.", "Derived", PM, OK),
 "personnel_lead_vacant": ("1 if the source shows no one held the GM title at the moment (president with no GM, page statement, or an exactly dated gap with a known successor).", WIKI, PM, OK),
 "attendance_per_game": ("MLB average home attendance. 2020 = NaN (fans barred). NHL not collected.", MLBAPI + " attendance", END_T, OK),
 "attendance_restricted": ("MLB 2020 and 2021 (COVID limits).", "Derived", "-", OK),
 "attendance_rank": ("MLB within-season rank of attendance_per_game (1 = highest).", "Derived", END_T, OK),
 "age_weighted": ("Playing-time-weighted age. Weight MLB = PA + batters faced per team stint; NHL = time on ice. Age on MLB Jun 30 t / NHL Feb 1 t+1.", MLBAPI + " / " + NHLAPI + " (stints, bios)", END_T, "Traded players counted by stint with each team."),
 "age_weighted_hitters": ("MLB PA-weighted age.", MLBAPI, END_T, OK),
 "age_weighted_pitchers": ("MLB batters-faced-weighted age.", MLBAPI, END_T, OK),
 "share_production_age32plus": ("Share of playing time (MLB PA+BF; NHL TOI) from players aged 32+.", "as age_weighted", END_T, OK),
 "top3_concentration": ("MLB: top-3 players' share of PA+BF. NHL: top-3 skaters' share of team skater points.", "as age_weighted", END_T, OK),
 "roster_players_used": ("Players with playing time for the team in t.", "as age_weighted", END_T, OK),
 "age_weight_coverage": ("Share of playing time with a known birthdate (1.0 everywhere).", "Derived", "-", "Audit."),
 "team_pa": ("MLB sum of player PA (equals official team PA exactly).", MLBAPI, END_T, "Audit."),
 "team_bf": ("MLB sum of batters faced (equals official team total exactly).", MLBAPI, END_T, "Audit."),
 "share_points_age32plus": ("NHL share of skater points from players aged 32+.", NHLAPI, END_T, OK),
 "skater_gp_sum": ("NHL sum of skater games (≈18 per team game).", NHLAPI, END_T, "Audit."),
 "goalie_gp_sum": ("NHL sum of goalie games.", NHLAPI, END_T, "Audit."),
 "xgoals_pct": ("NHL expected-goals share, all situations.", "MoneyPuck team season CSV", END_T, "**Soft leakage:** MoneyPuck's xG model is trained on all seasons, including seasons after t. Values are season-t outcomes, but the model weights saw the future."),
 "corsi_pct": ("NHL shot-attempt share, all situations.", "MoneyPuck", END_T, OK + " (counting stat, no model)."),
 "pdo_5v5": ("NHL 5v5 shooting % + save %: GF/SOGF + 1 - GA/SOGA.", "MoneyPuck", END_T, OK),
 "payroll_opening_day_usd": ("MLB Opening Day active-roster payroll (salaries + pro-rated signing bonuses). 2020 values pro-rated to 60 games.", "Cot's Baseball Contracts (Baseball Prospectus) team pages; cross-checked vs Lahman 2000-16 (r = 0.986)", "Opening Day of t", "Year-end and CBT payrolls not used (published after the moment)."),
 "cbt_threshold_usd": ("MLB Competitive Balance Tax base threshold (none 2000-02).", "Cot's CBA history (data/manual/mlb_cbt_threshold.csv)", "season t", OK),
 "payroll_pct_of_cbt": ("payroll_opening_day_usd / cbt_threshold_usd (2020 distorted by pro-rating).", "Derived", "Opening Day of t", OK),
 "payroll_rank": ("MLB within-season payroll rank (1 = highest), recomputed from values.", "Derived", "Opening Day of t", OK),
 "payroll_rel_league_mean": ("Payroll / league mean payroll that season (robust to 2020 pro-rating).", "Derived", "Opening Day of t", OK),
 "cap_upper_limit_usd": ("NHL salary cap upper limit (2012-13 shown pro-rated as charted).", "Wikipedia 'NHL salary cap' chart (data/manual/nhl_salary_cap.csv)", "season t", OK),
 "team_cap_hit_usd": ("NHL team cap hit. **Empty** (no accessible historical source) -> payroll_template.csv.", "-", "season t", OK),
 "team_name_then": ("Name used by the source that season (e.g. Montreal Expos).", "Standings APIs", "-", "Audit."),
 "team_id": ("Source team ID (MLB team id / NHL team id).", "Standings APIs", "-", "Audit."),
 "payroll_source": ("Cot's team page for the payroll.", "-", "-", "Audit."),
 "underlying_source": ("MoneyPuck CSV URL.", "-", "-", "Audit."),
 "y_pct_t1": ("win_pct_percentile in season t+1. **LABEL.**", "Derived", "t+1", "Label."),
 "y_pct_t2": ("win_pct_percentile in season t+2. **LABEL.**", "Derived", "t+2", "Label."),
 "y_pct_t3": ("win_pct_percentile in season t+3. **LABEL.**", "Derived", "t+3", "Label."),
 "y_doom_3yr": ("100 - mean(y_pct_t1..t3); NaN unless all three exist (last 3 seasons per league). **LABEL.**", "Derived", "t+1..t+3", "Label."),
 "y_doomed_bottom25": ("y_doom_3yr >= 75. **LABEL.**", "Derived", "t+1..t+3", "Label."),
}


def cov(c):
    out = []
    for lg in ("MLB", "NHL"):
        s = df[df.league == lg]
        nn = s[s[c].notna()]
        if not len(nn):
            out.append(f"{lg} 0%")
        else:
            out.append(f"{lg} {100 * len(nn) / len(s):.0f}% ({nn.season_start_year.min()}–{nn.season_start_year.max()})")
    return "; ".join(out)


missing = [c for c in df.columns if c not in D]
assert not missing, missing
lines = ["# Data dictionary: `data/processed/mlb_nhl_team_seasons.csv`", "",
         "One row per MLB/NHL team-season *t* (MLB 2000–2026, NHL 2005-06…2025-26). 1,454 rows. "
         "The first 19 columns are the teammate's NBA/NFL core schema, in order. Labels (`y_*`, "
         "`observed_doom_next_3_seasons`) come from seasons t+1..t+3 and must never be used as features.", "",
         "**Prediction moment:** MLB Nov 15 of t; NHL Jun 15 of t+1. Every feature is knowable by then, with two "
         "known caveats: MoneyPuck xG (soft leakage, below), and coach changes after the regular season "
         "(not captured, which is conservative). Decisions are in `DECISIONS.md` (D01–D56).", "",
         "**Known systematic artifact:** `personnel_lead_changed_past_year` is 0 for every MLB 2026 row. All 2026 "
         "MLB GM changes in the sources are year-only and fall after the Nov 15 2026 prediction moment. MLB 2026 is "
         "unlabelled, so this does not affect training.", "",
         "| Column | Definition | Source | As of | Coverage (non-missing) | Leakage note |",
         "|---|---|---|---|---|---|"]
for c in df.columns:
    d, s, a, l = D[c]
    lines.append(f"| `{c}` | {d} | {s} | {a} | {cov(c)} | {l} |")
open(os.path.join(ROOT, "DATA_DICTIONARY.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"DATA_DICTIONARY.md: {len(df.columns)} columns")
