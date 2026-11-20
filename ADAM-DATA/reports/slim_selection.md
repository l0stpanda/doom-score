# Slim model table: column selection

`data/processed/mlb_nhl_model_slim.csv` (1,454 rows × 29 columns) is a subset of the full table
`data/processed/mlb_nhl_team_seasons.csv` (1,454 rows × 104 columns), which is unchanged,
plus 1 derived column computed from it (marked "derived", last row). Built by `src/build_slim.py`.
Decisions **D61**, **D71** in `docs/decisions_full.md`.

**Chosen by concept, not by correlation with the label.** One `_lpct` column per concept; where a concept has
several candidate columns, the crosswalk choice (`docs/FEATURES.md`) is used. No column was picked or dropped
because of its relationship with `y_doom_3yr`.

Slim column order: ids/display → features → flags → labels. `y_*` columns are labels: never use them as features.

Coverage = share of all rows non-missing. `spending_lpct` is NaN for every NHL row (D57); `underlying_quality_lpct`
is NaN for NHL 2005–07 (Corsi starts 2008); `gm_tenure_lpct` is NaN where the GM is vacant or unknown.
No imputation.

| # | Column (full table order) | Status | Slim group | Coverage | Reason |
|---|---|---|---|---|---|
| 1 | `league` | **kept** | id | 100% | Row key: league. |
| 2 | `season_start_year` | **kept** | id | 100% | Row key: season t (NHL 2017 = 2017-18). |
| 3 | `franchise_id` | **kept** | id | 100% | Row key: franchise, stable through relocations/renames. |
| 4 | `team` | **kept** | id | 100% | Display name. |
| 5 | `wins` | **kept** | id | 100% | Display: season-t record. |
| 6 | `losses` | **kept** | id | 100% | Display: season-t record (NHL = regulation losses). |
| 7 | `ties` | dropped |  | 100% | MLB: 12 rows with a tie; NHL: duplicates ot_losses (D07). Not in the requested display set. |
| 8 | `games` | **kept** | id | 100% | Display: games played in t. |
| 9 | `win_pct` | **kept** | id | 100% | Display: season-t win% (NHL = points %). |
| 10 | `point_diff_per_game` | dropped |  | 100% | League source column of `margin_per_game`; slim table uses `margin_per_game_lpct`. |
| 11 | `win_pct_percentile` | **kept** | feature | 100% | Current standing, already a within-league-season percentile. |
| 12 | `win_pct_trailing_3_seasons` | **kept** | feature | 100% | Recent-trajectory concept: mean win% over the last 3 played seasons. |
| 13 | `observed_doom_next_3_seasons` | dropped |  | 87% | Duplicate of y_doom_3yr (teammate schema name). |
| 14 | `draft_picks_used` | dropped |  | 100% | Draft concept uses draft_capital (rounds 1-2) per the crosswalk. |
| 15 | `cap_space_pct` | dropped |  | 0% | Empty for both leagues (D57). |
| 16 | `personnel_lead_tenure_years` | dropped |  | 96% | League source column of `gm_tenure`; slim table uses `gm_tenure_lpct`. |
| 17 | `personnel_lead_changed_past_year` | dropped |  | 97% | GM concept is represented by gm_tenure; MLB 2026 systematically 0 (D43). |
| 18 | `standings_source` | dropped |  | 100% | Audit (source URL). |
| 19 | `draft_source` | dropped |  | 100% | Audit (source URL). |
| 20 | `playing_time_weight` | dropped |  | 100% | Text descriptor of the weighting basis, not a feature. |
| 21 | `roster_age_weighted` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `roster_age_weighted_lpct`. |
| 22 | `vet_share` | dropped |  | 100% | Concept not in the slim set (age is covered by roster_age_weighted). |
| 23 | `vet_share_lq` | dropped |  | 100% | Concept not in the slim set (age is covered by roster_age_weighted). |
| 24 | `star_concentration` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `star_concentration_lpct`. |
| 25 | `margin_per_game` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `margin_per_game_lpct`. |
| 26 | `luck` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `luck_lpct`. |
| 27 | `underlying_quality` | dropped |  | 94% | Raw alias; scales differ by league, so the slim table uses `underlying_quality_lpct`. |
| 28 | `draft_capital` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `draft_capital_lpct`. |
| 29 | `gm_tenure` | dropped |  | 96% | Raw alias; scales differ by league, so the slim table uses `gm_tenure_lpct`. |
| 30 | `coach_tenure` | dropped |  | 100% | Raw alias; scales differ by league, so the slim table uses `coach_tenure_lpct`. |
| 31 | `spending` | dropped |  | 56% | Raw alias; scales differ by league, so the slim table uses `spending_lpct`. |
| 32 | `market` | dropped |  | 54% | Concept not in the slim set: NHL unavailable; MLB attendance is partly endogenous to winning. |
| 33 | `roster_age_weighted_lpct` | **kept** | feature | 100% | Concept `roster_age_weighted`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 34 | `vet_share_lpct` | dropped |  | 100% | Concept not in the slim set (age is covered by roster_age_weighted). |
| 35 | `vet_share_lq_lpct` | dropped |  | 100% | Concept not in the slim set (age is covered by roster_age_weighted). |
| 36 | `star_concentration_lpct` | **kept** | feature | 100% | Concept `star_concentration`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 37 | `margin_per_game_lpct` | **kept** | feature | 100% | Concept `margin_per_game`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 38 | `luck_lpct` | **kept** | feature | 100% | Concept `luck`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 39 | `underlying_quality_lpct` | **kept** | feature | 94% | Concept `underlying_quality`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 40 | `draft_capital_lpct` | **kept** | feature | 100% | Concept `draft_capital`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 41 | `gm_tenure_lpct` | **kept** | feature | 96% | Concept `gm_tenure`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 42 | `coach_tenure_lpct` | **kept** | feature | 100% | Concept `coach_tenure`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 43 | `spending_lpct` | **kept** | feature | 56% | Concept `spending`: crosswalk alias as within-league-season percentile, comparable across leagues. |
| 44 | `market_lpct` | dropped |  | 54% | Concept not in the slim set: NHL unavailable; MLB attendance is partly endogenous to winning. |
| 45 | `spending_available` | dropped |  | 100% | Equals league == MLB; spending_lpct is NaN for NHL, recoverable from `league`. |
| 46 | `market_available` | dropped |  | 100% | Market concept dropped; also equals league == MLB. |
| 47 | `ot_losses` | **kept** | id | 44% | Display: NHL OT/SO losses; NaN for MLB by design (no such result). |
| 48 | `win_pct_raw` | dropped |  | 100% | Alternative win% (NHL without OTL credit); win_pct is kept. |
| 49 | `scored_per_game` | dropped |  | 100% | Component of margin_per_game. |
| 50 | `allowed_per_game` | dropped |  | 100% | Component of margin_per_game. |
| 51 | `pythag_win_pct` | dropped |  | 100% | League source column of `underlying_quality`; slim table uses `underlying_quality_lpct`. |
| 52 | `win_pct_change_1yr` | dropped |  | 100% | Trajectory concept uses win_pct_trailing_3_seasons. |
| 53 | `win_pct_slope_3yr` | dropped |  | 100% | Trajectory concept uses win_pct_trailing_3_seasons. |
| 54 | `seasons_of_history` | **kept** | flag | 100% | How many seasons the trailing features rest on (expansion teams). |
| 55 | `short_season` | **kept** | flag | 100% | Flags shortened seasons (MLB 2020; NHL 2012, 2019, 2020). |
| 56 | `expansion_first_3_seasons` | dropped |  | 100% | Only 6 NHL rows; seasons_of_history carries the same information. |
| 57 | `draft_picks_rd1_2` | dropped |  | 100% | League source column of `draft_capital`; slim table uses `draft_capital_lpct`. |
| 58 | `draft_first_pick_number` | dropped |  | 100% | Crosswalk alternative for draft_capital; the listed choice is rounds 1-2 picks. |
| 59 | `draft_rounds_in_year` | dropped |  | 100% | Context for the draft count, not a team feature. |
| 60 | `draft_picks_used_pctile` | dropped |  | 100% | Draft concept uses draft_capital (rounds 1-2) per the crosswalk. |
| 61 | `coach_name` | dropped |  | 100% | Name (text), not a feature. |
| 62 | `coach_tenure_years` | dropped |  | 100% | League source column of `coach_tenure`; slim table uses `coach_tenure_lpct`. |
| 63 | `coach_changed_during_regular_season` | dropped |  | 100% | Coach concept is represented by coach_tenure. |
| 64 | `coach_tenure_left_censored` | dropped |  | 100% | Data-quality flag for coach_tenure; kept in the full table. |
| 65 | `manager_resolved_by_fallback` | dropped |  | 100% | Audit flag (4 MLB rows). |
| 66 | `personnel_lead_name` | dropped |  | 96% | Name (text), not a feature. |
| 67 | `personnel_lead_tenure_left_censored` | dropped |  | 98% | Data-quality flag for gm_tenure; kept in the full table. |
| 68 | `personnel_lead_gap_carried` | dropped |  | 98% | Data-quality flag for gm_tenure; kept in the full table. |
| 69 | `personnel_lead_vacant` | **kept** | flag | 98% | Model feature (D71): explains NaN gm_tenure (vacancy is known, not missing). |
| 70 | `attendance_per_game` | dropped |  | 54% | League source column of `market`; market concept not in the slim set. |
| 71 | `attendance_restricted` | dropped |  | 56% | Market concept dropped. |
| 72 | `attendance_rank` | dropped |  | 54% | Market concept dropped. |
| 73 | `age_weighted` | dropped |  | 100% | League source column of `roster_age_weighted`; slim table uses `roster_age_weighted_lpct`. |
| 74 | `age_weighted_hitters` | dropped |  | 56% | MLB-only split of roster_age_weighted. |
| 75 | `age_weighted_pitchers` | dropped |  | 56% | MLB-only split of roster_age_weighted. |
| 76 | `share_production_age32plus` | dropped |  | 100% | League source column of `vet_share`; concept not in the slim set. |
| 77 | `top3_concentration` | dropped |  | 100% | League source column of `star_concentration`; slim table uses `star_concentration_lpct`. |
| 78 | `roster_players_used` | dropped |  | 100% | Not one of the slim concepts. |
| 79 | `age_weight_coverage` | dropped |  | 100% | Audit (1.0 everywhere). |
| 80 | `team_pa` | dropped |  | 56% | Audit (weight total). |
| 81 | `team_bf` | dropped |  | 56% | Audit (weight total). |
| 82 | `share_points_age32plus` | dropped |  | 44% | NHL-only variant of vet_share; concept not in the slim set. |
| 83 | `skater_gp_sum` | dropped |  | 44% | Audit (weight total). |
| 84 | `goalie_gp_sum` | dropped |  | 44% | Audit (weight total). |
| 85 | `xgoals_pct` | dropped |  | 38% | Crosswalk alternative for NHL underlying_quality; soft leakage (D54); NHL only. |
| 86 | `corsi_pct` | dropped |  | 38% | League source column of `underlying_quality`; slim table uses `underlying_quality_lpct`. |
| 87 | `pdo_5v5` | dropped |  | 38% | NHL-only luck gauge; luck concept uses the crosswalk `luck` column. |
| 88 | `payroll_opening_day_usd` | dropped |  | 56% | Raw dollars; spending uses payroll_rel_league_mean per the crosswalk. |
| 89 | `cbt_threshold_usd` | dropped |  | 50% | League-level context, not a team feature. |
| 90 | `payroll_pct_of_cbt` | dropped |  | 50% | Spending alternative; crosswalk uses payroll_rel_league_mean (2020 pro-rating). |
| 91 | `payroll_rank` | dropped |  | 56% | Spending alternative; spending_lpct is the within-season rank form. |
| 92 | `payroll_rel_league_mean` | dropped |  | 56% | League source column of `spending`; slim table uses `spending_lpct`. |
| 93 | `cap_upper_limit_usd` | dropped |  | 44% | League-level context, not a team feature. |
| 94 | `team_cap_hit_usd` | dropped |  | 0% | Empty (D57). |
| 95 | `team_name_then` | dropped |  | 100% | Audit (name used that season). |
| 96 | `team_id` | dropped |  | 100% | Audit (source team ID). |
| 97 | `payroll_source` | dropped |  | 56% | Audit (source URL). |
| 98 | `underlying_source` | dropped |  | 38% | Audit (source URL). |
| 99 | `vet_age_cut_lq` | dropped |  | 100% | Helper for vet_share_lq; concept not in the slim set. |
| 100 | `y_pct_t1` | **kept** | label | 96% | Component label: percentile in t+1. LABEL. |
| 101 | `y_pct_t2` | **kept** | label | 91% | Component label: percentile in t+2. LABEL. |
| 102 | `y_pct_t3` | **kept** | label | 87% | Component label: percentile in t+3. LABEL. |
| 103 | `y_doom_3yr` | **kept** | label | 87% | Primary label (t+1..t+3). LABEL, not a feature. |
| 104 | `y_doomed_bottom25` | **kept** | label | 87% | Binary label (doom >= 75). LABEL, not a feature. |
| 105 | `win_pct_trailing_3_seasons_lpct` (derived) | **kept** | feature | 100% | Derived (D71): within-league-season percentile of win_pct_trailing_3_seasons, comparable across leagues. |

Full-table columns: kept 28, dropped 76, total 104; plus 1 derived → 29 slim columns.
