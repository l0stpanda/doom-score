# Data dictionary: `data/processed/mlb_nhl_team_seasons.csv`

One row per MLB/NHL team-season *t* (MLB 2000–2026, NHL 2005-06…2025-26). 1,454 rows. The first 19 columns are the teammate's NBA/NFL core schema, in order. Labels (`y_*`, `observed_doom_next_3_seasons`) come from seasons t+1..t+3 and must never be used as features.

**Prediction moment:** MLB Nov 15 of t; NHL Jun 15 of t+1. Every feature is knowable by then, with two known caveats: MoneyPuck xG (soft leakage, below), and coach changes after the regular season (not captured, which is conservative). Decisions are in `DECISIONS.md` (D01–D56).

**Known systematic artifact:** `personnel_lead_changed_past_year` is 0 for every MLB 2026 row. All 2026 MLB GM changes in the sources are year-only and fall after the Nov 15 2026 prediction moment. MLB 2026 is unlabelled, so this does not affect training.

| Column | Definition | Source | As of | Coverage (non-missing) | Leakage note |
|---|---|---|---|---|---|
| `league` | MLB or NHL. | - | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Identifier. |
| `season_start_year` | Calendar year season t starts (NHL 2017 = 2017-18). | - | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Identifier. |
| `franchise_id` | Lowercase-hyphenated current franchise name, constant through relocations/renames. | Derived | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Identifier. |
| `team` | Franchise's current name (same for all years). | MLB/NHL APIs | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Identifier. |
| `wins` | Regular-season wins. | MLB Stats API (statsapi.mlb.com) / NHL stats REST (api.nhle.com) | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `losses` | Regular-season losses (NHL: regulation losses). | MLB Stats API (statsapi.mlb.com) / NHL stats REST (api.nhle.com) | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `ties` | MLB: tie games. NHL: OT/SO losses (+ real ties 2002-04) so that win_pct = NHL points %. | MLB Stats API (statsapi.mlb.com) / NHL stats REST (api.nhle.com) | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `games` | Games played (MLB W+L+T; NHL W+L+OTL). | MLB Stats API (statsapi.mlb.com) / NHL stats REST (api.nhle.com) | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct` | (wins + 0.5*ties) / games. | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `point_diff_per_game` | (runs/goals for - against) / games. | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct_percentile` | Within league-season: (average ascending rank - 1)/(n - 1)*100; worst 0, best 100. | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct_trailing_3_seasons` | Mean win_pct of the franchise's last 3 played seasons incl. t (min 1). | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `observed_doom_next_3_seasons` | = y_doom_3yr (teammate schema name). **LABEL, not a feature.** | Derived | seasons t+1..t+3 | MLB 89% (2000–2023); NHL 85% (2005–2022) | Label - never use as a feature. |
| `draft_picks_used` | Picks made by the team in the year-t draft (MLB Jun/Jul t; NHL Jun t, before season t). | MLB Stats API draft / NHL api-web draft | draft of year t | MLB 100% (2000–2026); NHL 100% (2005–2025) | MLB July draft is before Nov; NHL uses the June t draft only (June t+1 is after the moment). |
| `cap_space_pct` | NHL: (cap ceiling - team cap hit)/ceiling. **Empty: no historical team cap hits available** (Spotrac 403, PuckPedia anti-bot, CapWages current-season only) -> data/manual/payroll_template.csv. MLB: not defined (no cap); see payroll_pct_of_cbt. | - | season t | MLB 0%; NHL 0% | Season t or earlier only. |
| `personnel_lead_tenure_years` | Years the current GM has been the team's GM at the prediction moment (GM only, both leagues). | Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs) | prediction moment (MLB Nov 15 t; NHL Jun 15 t+1) | MLB 94% (2000–2026); NHL 100% (2005–2025) | Measured at the moment, never total tenure. Year-only dates are placed after that year's season (MLB except Giants/Rays). |
| `personnel_lead_changed_past_year` | 1 if the GM at the moment differs from the GM 365 days earlier (VACANT counts as a state). **MLB 2026 is systematically 0**: every 2026 MLB change in the sources is year-only and is placed on Dec 31, after the Nov 15 moment. | Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs) | prediction moment (MLB Nov 15 t; NHL Jun 15 t+1) | MLB 95% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `standings_source` | API URL for the standings row. | - | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Audit. |
| `draft_source` | API URL for the draft data. | - | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Audit. |
| `ot_losses` | NHL overtime/shootout losses. | NHL stats REST (api.nhle.com) | end of season t | MLB 0%; NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct_raw` | wins / games (NHL without OTL credit). | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `scored_per_game` | Runs/goals scored per game. | Standings APIs | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `allowed_per_game` | Runs/goals allowed per game. | Standings APIs | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `pythag_win_pct` | RS^k/(RS^k+RA^k); k = 1.83 MLB, 2.0 NHL. | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `luck` | win_pct - pythag_win_pct. | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct_change_1yr` | win_pct(t) - win_pct(previous played season). | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `win_pct_slope_3yr` | OLS slope of win_pct over the last 3 played seasons (needs >= 2). | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `seasons_of_history` | Number of franchise seasons available up to t (from 1997 MLB / 2002 NHL). | Derived | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `short_season` | MLB 2020; NHL 2012, 2019, 2020. | Derived | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `expansion_first_3_seasons` | Vegas 2017-19, Seattle 2021-23. | Derived | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `draft_picks_rd1_2` | Picks listed up to and incl. round 2 (MLB incl. supplemental 1st, Competitive Balance Round A, PPI; NHL rounds 1-2). | Draft APIs | draft of year t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `draft_first_pick_number` | Team's earliest overall pick in the year-t draft. | Draft APIs | draft of year t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `draft_rounds_in_year` | Distinct round labels in that year's draft (MLB 2020 had 5 rounds). | Draft APIs | draft of year t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `draft_picks_used_pctile` | Within league-season percentile of draft_picks_used (comparable across MLB round-count changes). | Derived | draft of year t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `coach_name` | Manager/head coach at the end of the regular season t. | MLB Stats API coaches / Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs) | last regular-season game of t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Changes after the last regular-season game are not captured. |
| `coach_tenure_years` | Consecutive seasons as season-end coach incl. t; a first season taken over mid-season counts 0.5. | as above | end of regular season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `coach_changed_during_regular_season` | 1 if more than one manager/coach ran the team during regular season t. | as above | end of regular season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Post-season firings/hires before the moment are not captured. |
| `coach_tenure_left_censored` | Tenure streak reaches the start of the coach history (true tenure may be longer). | Derived | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `manager_resolved_by_fallback` | MLB: season-end manager resolved by the interim rule (titled manager on leave + interim; 4 rows). | MLB Stats API | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `personnel_lead_name` | GM at the prediction moment (NaN if vacant or unknown). | Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs) | prediction moment (MLB Nov 15 t; NHL Jun 15 t+1) | MLB 94% (2000–2026); NHL 100% (2005–2025) | All Wikipedia spans are needs_verification. |
| `personnel_lead_tenure_left_censored` | GM tenure reaches the start of available spans (<=1999). | Derived | - | MLB 96% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `personnel_lead_gap_carried` | 1 if no active GM span and the last GM (ended <=400 days earlier, imprecise dates) was carried. | Derived | prediction moment (MLB Nov 15 t; NHL Jun 15 t+1) | MLB 96% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `personnel_lead_vacant` | 1 if the source shows no one held the GM title at the moment (president with no GM, page statement, or an exactly dated gap with a known successor). | Wikipedia (team GM/coach lists; individual articles for BAL/ATL/CIN GMs) | prediction moment (MLB Nov 15 t; NHL Jun 15 t+1) | MLB 96% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `attendance_per_game` | MLB average home attendance. 2020 = NaN (fans barred). NHL not collected. | MLB Stats API (statsapi.mlb.com) attendance | end of season t | MLB 96% (2000–2026); NHL 0% | Season t or earlier only. |
| `attendance_restricted` | MLB 2020 and 2021 (COVID limits). | Derived | - | MLB 100% (2000–2026); NHL 0% | Season t or earlier only. |
| `attendance_rank` | MLB within-season rank of attendance_per_game (1 = highest). | Derived | end of season t | MLB 96% (2000–2026); NHL 0% | Season t or earlier only. |
| `age_weighted` | Playing-time-weighted age. Weight MLB = PA + batters faced per team stint; NHL = time on ice. Age on MLB Jun 30 t / NHL Feb 1 t+1. | MLB Stats API (statsapi.mlb.com) / NHL stats REST (api.nhle.com) (stints, bios) | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Traded players counted by stint with each team. |
| `age_weighted_hitters` | MLB PA-weighted age. | MLB Stats API (statsapi.mlb.com) | end of season t | MLB 100% (2000–2026); NHL 0% | Season t or earlier only. |
| `age_weighted_pitchers` | MLB batters-faced-weighted age. | MLB Stats API (statsapi.mlb.com) | end of season t | MLB 100% (2000–2026); NHL 0% | Season t or earlier only. |
| `share_production_age32plus` | Share of playing time (MLB PA+BF; NHL TOI) from players aged 32+. | as age_weighted | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `top3_concentration` | MLB: top-3 players' share of PA+BF. NHL: top-3 skaters' share of team skater points. | as age_weighted | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `roster_players_used` | Players with playing time for the team in t. | as age_weighted | end of season t | MLB 100% (2000–2026); NHL 100% (2005–2025) | Season t or earlier only. |
| `age_weight_coverage` | Share of playing time with a known birthdate (1.0 everywhere). | Derived | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Audit. |
| `team_pa` | MLB sum of player PA (equals official team PA exactly). | MLB Stats API (statsapi.mlb.com) | end of season t | MLB 100% (2000–2026); NHL 0% | Audit. |
| `team_bf` | MLB sum of batters faced (equals official team total exactly). | MLB Stats API (statsapi.mlb.com) | end of season t | MLB 100% (2000–2026); NHL 0% | Audit. |
| `share_points_age32plus` | NHL share of skater points from players aged 32+. | NHL stats REST (api.nhle.com) | end of season t | MLB 0%; NHL 100% (2005–2025) | Season t or earlier only. |
| `skater_gp_sum` | NHL sum of skater games (≈18 per team game). | NHL stats REST (api.nhle.com) | end of season t | MLB 0%; NHL 100% (2005–2025) | Audit. |
| `goalie_gp_sum` | NHL sum of goalie games. | NHL stats REST (api.nhle.com) | end of season t | MLB 0%; NHL 100% (2005–2025) | Audit. |
| `xgoals_pct` | NHL expected-goals share, all situations. | MoneyPuck team season CSV | end of season t | MLB 0%; NHL 86% (2008–2025) | **Soft leakage:** MoneyPuck's xG model is trained on all seasons, including seasons after t. Values are season-t outcomes, but the model weights saw the future. |
| `corsi_pct` | NHL shot-attempt share, all situations. | MoneyPuck | end of season t | MLB 0%; NHL 86% (2008–2025) | Season t or earlier only. (counting stat, no model). |
| `pdo_5v5` | NHL 5v5 shooting % + save %: GF/SOGF + 1 - GA/SOGA. | MoneyPuck | end of season t | MLB 0%; NHL 86% (2008–2025) | Season t or earlier only. |
| `payroll_opening_day_usd` | MLB Opening Day active-roster payroll (salaries + pro-rated signing bonuses). 2020 values pro-rated to 60 games. | Cot's Baseball Contracts (Baseball Prospectus) team pages; cross-checked vs Lahman 2000-16 (r = 0.986) | Opening Day of t | MLB 100% (2000–2026); NHL 0% | Year-end and CBT payrolls not used (published after the moment). |
| `cbt_threshold_usd` | MLB Competitive Balance Tax base threshold (none 2000-02). | Cot's CBA history (data/manual/mlb_cbt_threshold.csv) | season t | MLB 89% (2003–2026); NHL 0% | Season t or earlier only. |
| `payroll_pct_of_cbt` | payroll_opening_day_usd / cbt_threshold_usd (2020 distorted by pro-rating). | Derived | Opening Day of t | MLB 89% (2003–2026); NHL 0% | Season t or earlier only. |
| `payroll_rank` | MLB within-season payroll rank (1 = highest), recomputed from values. | Derived | Opening Day of t | MLB 100% (2000–2026); NHL 0% | Season t or earlier only. |
| `payroll_rel_league_mean` | Payroll / league mean payroll that season (robust to 2020 pro-rating). | Derived | Opening Day of t | MLB 100% (2000–2026); NHL 0% | Season t or earlier only. |
| `cap_upper_limit_usd` | NHL salary cap upper limit (2012-13 shown pro-rated as charted). | Wikipedia 'NHL salary cap' chart (data/manual/nhl_salary_cap.csv) | season t | MLB 0%; NHL 100% (2005–2025) | Season t or earlier only. |
| `team_cap_hit_usd` | NHL team cap hit. **Empty** (no accessible historical source) -> payroll_template.csv. | - | season t | MLB 0%; NHL 0% | Season t or earlier only. |
| `team_name_then` | Name used by the source that season (e.g. Montreal Expos). | Standings APIs | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Audit. |
| `team_id` | Source team ID (MLB team id / NHL team id). | Standings APIs | - | MLB 100% (2000–2026); NHL 100% (2005–2025) | Audit. |
| `payroll_source` | Cot's team page for the payroll. | - | - | MLB 100% (2000–2026); NHL 0% | Audit. |
| `underlying_source` | MoneyPuck CSV URL. | - | - | MLB 0%; NHL 86% (2008–2025) | Audit. |
| `y_pct_t1` | win_pct_percentile in season t+1. **LABEL.** | Derived | t+1 | MLB 96% (2000–2025); NHL 95% (2005–2024) | Label. |
| `y_pct_t2` | win_pct_percentile in season t+2. **LABEL.** | Derived | t+2 | MLB 93% (2000–2024); NHL 90% (2005–2023) | Label. |
| `y_pct_t3` | win_pct_percentile in season t+3. **LABEL.** | Derived | t+3 | MLB 89% (2000–2023); NHL 85% (2005–2022) | Label. |
| `y_doom_3yr` | 100 - mean(y_pct_t1..t3); NaN unless all three exist (last 3 seasons per league). **LABEL.** | Derived | t+1..t+3 | MLB 89% (2000–2023); NHL 85% (2005–2022) | Label. |
| `y_doomed_bottom25` | y_doom_3yr >= 75. **LABEL.** | Derived | t+1..t+3 | MLB 89% (2000–2023); NHL 85% (2005–2022) | Label. |
