# Data dictionary

All exports live in `data/exports/`. Conventions used everywhere:

* **Missing values are empty (null), never zero.** Why a value is missing is recorded in a
  `*_status` column where it matters (`contract_data_status`, `financial_data_status`,
  `career_match_status`, `future_pick_inventory_completeness`), and per field in
  `missingness_report.csv`. Codes used: `not_applicable` (field does not exist for that league, e.g. `ties`, `ws` in the PWHL;
  documented below rather than stored row by row), `not_reported` (source exists but does not publish it for that
  season), `not_collected_no_permitted_automated_source`, `not_yet_available` / `drafted_after_last_completed_season` /
  `expansion_not_yet_played`.
* **Season labels.** WNBA: `"2024"` = the 2024 calendar-year season (May–Oct), `season_start_year = season_end_year = 2024`.
  PWHL: `"2023-24"` style, `season_start_year` = first year in the label. The inaugural PWHL season is `"2023-24"`
  (the league branded it the "2024 season"; first regular-season game 2024-01-01; original label kept in
  `source_season_label`). The 2026-27 PWHL season had not started at the snapshot (2026-11-19).
* **IDs.** `team_id` is a stable franchise id from `config/teams.csv` (e.g. `WNBA-CON` is the Connecticut Sun, which
  plays as the Houston Comets from 2027; `PWHL-BOS` was "PWHL Boston" in 2023-24 and "Boston Fleet" since). Name
  variants map to ids through `config/team_aliases.csv`. `player_id` is the Basketball-Reference id for WNBA players
  (e.g. `wilsoaj01w`) and `pwhl-<HockeyTech id>` for PWHL players. Player-name variants used for matching across sources are
  listed in `config/player_name_aliases.csv`.
* **Units.** Money in USD (nominal). Minutes in minutes. Ages in decimal years. Percentages are proportions in [0, 1]
  unless the column name ends in `_pct` *and* comes from Basketball-Reference rate stats where the source uses
  percentage points (e.g. `usg_pct = 24.1`); the source scale is retained.
* **Source suffixes.** `_bbref` = Basketball-Reference definition, `_espn` = ESPN, `_source` = verbatim text from the source.

---

## `team_season_data.csv`

Grain: one row per team per league-season. Key: `league, season, team_id`. Script: `01_collect_team_data.py`.
Regular-season values unless the column says playoff.

| field | definition | units | source / calculation |
|---|---|---|---|
| league | `WNBA` or `PWHL` | | |
| season, season_start_year, season_end_year | see conventions | | |
| in_core_scope | False for WNBA 2019–2020 context seasons (collected only for lag features) | bool | config |
| source_season_label | the league/source's own season name (PWHL) | | settings |
| team_id / team_name / team_abbr_source | franchise id / name used that season / source abbreviation | | BBRef / fastRhockey |
| conference | Eastern / Western (WNBA) | | BBRef standings |
| games_played | regular-season games | games | BBRef team totals `G`; PWHL count of final regular-season games |
| wins | all wins. **PWHL includes OT and shootout wins** | games | BBRef / calculated from games |
| losses | WNBA: losses. **PWHL: regulation losses only** | games | |
| ties | not applicable in either league (always null) | | |
| overtime_losses | PWHL OT + shootout losses (hockey "OTL"); null for WNBA | games | calculated |
| regulation_wins, ot_wins, so_wins, ot_losses, so_losses | PWHL decision splits | games | from `game_status` (`Final OT*`, `Final SO`) / `has_shootout` |
| win_percentage | wins / games_played (definition text in `win_percentage_definition`) | proportion | calculated |
| points | PWHL standings points = 3·RW + 2·(OTW+SOW) + 1·(OTL+SOL) | points | calculated; matches Wikipedia standings for all 20 team-seasons |
| points_percentage | PWHL points / (3·games_played). **Not the same as win_percentage** | proportion | calculated |
| points_for, points_against, point_differential (+ `_per_game`) | WNBA points scored/allowed | points | BBRef team & opponent totals; differential calculated |
| goals_for, goals_against, goal_differential (+ `_per_game`) | PWHL goals; shootout winner credited +1 GF as in the official final score | goals | calculated from game scores |
| home_wins/home_losses, away_wins/away_losses | splits (WNBA from ESPN; PWHL calculated). PWHL also `*_overtime_losses` | games | |
| mov_bbref, sos_bbref, srs_bbref | margin of victory, strength of schedule, simple rating system (pts/game vs average) | points/game | BBRef advanced team table |
| pythag_wins_bbref / pythag_losses_bbref | Pythagorean expected W/L | games | BBRef |
| off_rtg_bbref, def_rtg_bbref, net_rtg_bbref, pace_bbref | points per 100 possessions; possessions per 40 min | | BBRef |
| team_avg_age_bbref | BBRef's team age (playing-time weighted, BBRef convention) | years | BBRef |
| bbref_points_for_per_game / bbref_points_against_per_game | per-game scoring from the standings table (cross-check) | | BBRef |
| arena_name | home arena | | BBRef |
| playoff_qualified | WNBA: asterisk in BBRef standings | bool | |
| playoff_seed_espn | seed published by ESPN | | ESPN |
| playoff_appearance, playoff_series_won/lost, playoff_game_wins/losses | from series results | | BBRef playoff table / PWHL playoff games |
| playoff_round_reached / _label | deepest round (1 = first round); `did_not_qualify` if no series | | calculated |
| finalist, champion | reached / won the final series | bool | calculated |
| prior_season_win_pct | the franchise's win_percentage in the previous league-season (null for first season) | | calculated |
| win_pct_change_yoy | win_percentage − prior_season_win_pct | | calculated |
| win_pct_rolling3_mean | mean win_percentage over t, t−1, t−2 (null unless all 3 exist) | | calculated |
| win_pct_3season_pooled | Σwins / Σgames over t, t−1, t−2 | | calculated |
| prior_season_points_pct, points_pct_change_yoy, points_pct_rolling3_mean, points_pct_3season_pooled | same for PWHL points % (pooled = Σpoints / Σ3·GP) | | calculated |
| prior_season_point_differential_per_game / prior_season_goal_differential_per_game | lagged scoring margin | | calculated |
| first/last_regular_season_game_date | used as the age reference date | date | BBRef schedule page / PWHL game dates |

## `player_season_data.csv`

Grain: one row per **player × team × season** (a stint). Key: `league, season, team_id, player_id`. A player traded
mid-season has one row per team containing only that team's games (`multi_team_season = True`,
`n_teams_in_season` = number of teams). Script: `02_collect_player_data.py`.

| field | definition | units / notes |
|---|---|---|
| player_id, player_id_source, player_name, first_name, last_name | identifiers | |
| position / position_group | source position (WNBA G/F/C combos; PWHL C, LW, RW, LD, RD, G) / grouped G-F-C (WNBA) or F-D-G (PWHL) | |
| position_source | WNBA: `team_roster_table` or `other_team_row_same_player_latest` (player omitted from that team's roster table); null position = not available | |
| jersey_number | | |
| roster_status | `appeared` (≥1 game dressed/played for team), `rostered_no_appearance`, `under_contract_no_appearance_for_team` (PWHLPA-listed, no game) | |
| developmental_contract | WNBA "(DC)" developmental-contract marker (2026 CBA) | bool |
| birth_date | | date |
| age_reference_date | first regular-season game date of the league-season | date |
| age_at_reference | (age_reference_date − birth_date) / 365.2425 | years |
| age_source | integer season age published by Basketball-Reference (its own convention) | years |
| experience_years | WNBA: BBRef prior WNBA seasons ("R" → 0). PWHL: prior PWHL seasons with ≥1 game (definition in `experience_definition`; excludes PHF/PWHPA/Europe) | seasons |
| experience_years_raw | source text, or `computed_from_player_page_seasons` | |
| bio_fill_method | where birth date came from when the team roster table omitted the player (`team_roster_table`, `birth_date_from_other_team_row`, `birth_date_from_player_page`) | |
| height_raw, height_in, weight_lb, college_or_prior | WNBA roster table | inches, lb |
| is_goalie | PWHL | bool |
| games_played | WNBA games; PWHL skaters = games dressed, goalies = games with TOI > 0 | games |
| games_dressed | PWHL games in the official game roster | games |
| games_started | | games |
| minutes, minutes_per_game | WNBA | minutes |
| time_on_ice_total_min, toi_per_game, toi_games_with_data, toi_note | PWHL TOI from per-game box scores | minutes |
| points, points_per_game | WNBA points; PWHL goals + assists | |
| rebounds, orb, drb, assists, steals, blocks, turnovers, pf | WNBA totals | counts |
| fg, fga, fg_pct, fg3*, fg2*, ft, fta, ft_pct | WNBA shooting (attempts and %) | counts / proportion |
| per, ts_pct, efg_pct, usg_pct, orb_pct … tov_pct, off_rtg, def_rtg | BBRef advanced metrics (BBRef definitions & scales) | |
| ows, dws, ws, ws_per_40 | BBRef Win Shares (offensive/defensive/total/per 40 min) | |
| goals, assists, shots, hits, blocked_shots, penalty_minutes, faceoff_* | PWHL totals | counts |
| plus_minus | PWHL as published — **noisy, context-dependent; retain with caveat** | |
| saves, shots_against, goals_against | PWHL goalies | counts |
| save_pct | saves / shots_against | proportion |
| gaa | goals_against × 60 / goalie TOI | goals per 60 |
| playoff_g, playoff_mp, playoff_pts | WNBA playoff totals | |
| playoff_games_dressed/played, playoff_goals/assists/points, playoff_time_on_ice_total_min | PWHL playoff totals | |
| contract_data_status | `reported_pwhlpa`, `not_listed_in_pwhlpa_guide`, `not_reported` (season without disclosure), `not_collected_no_permitted_automated_source` (WNBA), `manual_import` | |
| salary_base_usd | PWHL 2025-26 base salary (PWHLPA, as of 2026-04-12; excludes bonuses/incentives/housing) | USD |
| salary_measure, salary_source, salary_source_url, salary_as_of, salary_match_method | provenance of the salary value; match method `team+name` | |
| contract_start_year, contract_end_year, contract_type, guaranteed_usd, free_agent_status_next | only populated from the optional WNBA manual import | |
| source_player_id, source_team_id | raw ids from fastRhockey/HockeyTech (PWHL) | |
| on_season_roster_table | WNBA: player appeared in the team page's roster table | bool |

## `draft_history.csv`

Grain: one row per draft selection. Key: `league, draft_year, selection_key`. Script: `03_collect_draft_data.py`.

| field | definition |
|---|---|
| draft_type | `entry`, `expansion` (expansion draft selection), `expansion_signing_or_selection` (PWHL exclusive expansion signing windows, laid out by team) |
| draft_name, draft_section | Wikipedia article title / section heading the row came from |
| selection_key | `<draft_type>-<pick_overall>` or `<draft_type>-<team>-<seq>` when no overall pick exists |
| round, round_source | round number; `heading`/`column`, or `inferred_from_pick_and_N_teams` (PWHL 2026 table without round headings) |
| pick_overall, pick_in_round | overall pick; rank within round |
| player_name, player_id, position, nationality, school_or_club | selection details; `player_id` = BBRef id (WNBA) or matched `pwhl-*` id |
| selecting_team_id / _name_source | team that made the selection (held the pick on draft day) |
| original_owner_team_id / _name_source | team named in "(from X)"; equals selecting team when no annotation. Expansion rows: the team the player was taken from |
| pick_traded_before_draft | original owner ≠ selecting team (entry drafts only) |
| acquisition_method | `own`, `trade`, `compensation_or_trade_see_note`, `expansion`, `expansion_signing_or_selection` |
| traded_from_team_id / traded_to_team_id | populated when the pick was traded before the draft |
| rights_traded_after_selection_to(_id) | "(traded to Y)" annotations: draft rights moved after selection |
| previous_team_name_source | expansion rows: player's former team |
| trade_note_text | footnoted trade description(s) from the article, verbatim (`||`-separated) |
| team_cell_raw | the verbatim team cell (audit) |
| career_* (WNBA) | BBRef career totals as of `career_stats_as_of`: seasons, games, MP/G, PTS/G, TRB/G, AST/G, Win Shares, WS/40 |
| career_* (PWHL) | sums over PWHL regular seasons collected: seasons with ≥1 game, games, goals, assists, points, TOI, goalie saves / shots against; `teams_played_for` |
| career_match_status | `matched_pick_and_name`, `matched_pick_name_differs` (name change — verified as same person), `matched_by_name`, `no_pwhl_games_found`, `drafted_after_last_completed_season` |
| bbref_player_name, bbref_player_id, bbref_draft_team | BBRef side of the match |
| source_url, source_revision_id, retrieved_at_utc | permanent Wikipedia revision link |

No composite career-outcome score is defined yet.

## `draft_pick_inventory.csv`

Known future picks for the next draft. Key: `league, inventory_key`.

| field | definition |
|---|---|
| draft_year, round, pick_overall | WNBA 2027: full order after the lottery, as shown on the article revision |
| pick_slot_status | `assigned_per_source_revision` or `unknown_not_yet_determined` |
| original_owner_team_id / current_rights_holder_team_id (+ `_name_source`) | ownership is never assumed: holder = team listed; original = "(from X)" or the holder |
| is_traded, conditional_or_protected_flag | flag set when note text mentions protection / condition / swap |
| trade_note_text, team_cell_raw, source_url, source_revision_id, snapshot_date | audit fields |

PWHL: no 2027 draft article exists. Only picks named in recorded trades would appear, and none have been traded
as of the snapshot. Teams' remaining own picks are **not** inferred.

## `team_financials.csv`

Grain: one row per team per season (`record_type = season`) + one dated row per active franchise
(`record_type = current_snapshot`). Key: `league, season, record_type, team_id`. Script: `04_collect_financial_data.py`.

| field | definition | units |
|---|---|---|
| financial_data_status | `player_salaries_reported`, `not_reported_by_source_for_season`, `not_collected_no_permitted_automated_source`, `contract_terms_partial_secondary_source` | |
| cba_regime, cap_measure | which agreement and what the cap number means | |
| team_salary_cap | WNBA hard cap (from `league_cba_parameters.csv`) | USD |
| team_average_salary_requirement | PWHL team-average base salary target (±10% band; no hard cap) | USD |
| league_min_salary, roster_size_rule | PWHL CBA values | USD / players |
| cap_value_verification | `official`, `secondary_source`, `calculated_unverified` | |
| payroll_reported_total | Σ reported base salaries | USD |
| n_players_on_team / n_players_salary_reported / salary_coverage_share | coverage of the payroll sum | |
| payroll_avg / median / max / min | over reported salaries | USD |
| top5_salary_share (WNBA) / top8_salary_share (PWHL) | share of payroll held by the N highest-paid | proportion |
| pct_of_cap_committed / cap_space | WNBA only, only when payroll is reported | proportion / USD |
| avg_salary_vs_requirement | PWHL payroll_avg / requirement | ratio |
| snapshot_roster_n, contract_team_basis | snapshot rows: roster size and how contracts were attributed to teams | |
| n_known_contracts_covering_upcoming_season, known_contract_share_of_roster, n_known_contracts_expiring_after_2026-27, n_known_contracts_multi_year_beyond_upcoming | PWHL counts from `contract_transactions.csv` for players on the current roster — **lower bounds** | players |

## `contract_transactions.csv`

PWHL signings/extensions with term, parsed from Wikipedia season articles (2025-26 and 2026-27). Key: `league, tx_key`.
Fields: `transaction_type` (`free_agent_signing`, `extension`, `extension_term_remaining`, `draft_signing`,
`reserve_contract`, `termination`), `transaction_date`, `player_name`, `team_id`, `previous_team_name_source`,
`term_raw`, `term_years`, `contract_first_season` / `contract_last_season` (inferred: May–Nov signing → starts that
autumn; Dec–Apr signing → season in progress; in-season extensions start next season), source URL and revision.

## `current_roster_snapshot.csv`

Dated roster of every active franchise (incl. 2026-27 PWHL expansion teams). Key: `league, snapshot_team_id, player_name`.
Fields: `player_name` (+`_source`), `position`, `jersey_number`, `birth_date` (+`birth_date_source`: `snapshot_page`
or `historical_player_record`), `age_at_snapshot`, `age_integer_source` (PWHL page), `experience_years(_raw)` (WNBA),
`acquired_year` and `shoots_catches` (PWHL), `player_id` + `player_id_match` (unique normalised-name match to history),
`last_historical_team_id/season`, `snapshot_date`, `source_title`, `source_revision_id`, `source_url`, `retrieved_at_utc`.
**Caveat:** WNBA roster templates in November largely reflect end-of-season rosters (before 2027 free agency).

## `team_features.csv`

Descriptive team-level aggregates (script `05_build_team_features.py`; thresholds in `team_features_params.json`).
**No Doom Score, no weights, no standardisation.** Definitions are in the script docstring; summary:

* roster: `roster_n_listed`, `roster_n_appeared`
* age: `age_mean`, `age_median`, `age_playtime_weighted`, `pct_players_under_25`, `pct_players_over_30`,
  `playtime_share_under_25/over_30`, `age_mean_top{5|8}_by_<minutes|win_shares|points|toi|goals>`, `age_coverage_share`
* experience: `experience_mean`, `experience_playtime_weighted`
* playing-time concentration: `playtime_hhi`, `skater_toi_hhi`, `goalie_top1_toi_share`, `n_meaningful_playtime`, `n_young_meaningful`
* production concentration: `top{1,3,N}_share_<metric>`, `team_total_<metric>`, `per_minutes_weighted`,
  `ws_per_40_minutes_weighted`, `goalie_save_pct_toi_weighted`, `n_above_league_median_<metric>` (+ the median used)
* availability: `top_playtime_players_games_missed_share` = 1 − mean(GP)/team GP for the top-N single-team players by playing time
* continuity: `continuity_playtime_share`, `retention_prior_playtime_share`, `n_new_players`, `n_departed_players`
* draft (draft held before the season): `draft_n_picks_made`, `draft_n_round1_picks`, `draft_best_pick_overall`,
  `draft_n_picks_acquired_by_trade`, `draft_n_own_picks_traded_away`, `n_own_draftees_appeared`, `own_draftee_playtime_share`
* finance (copied): payroll fields above
* snapshot rows only: `snapshot_*` (roster size, age, retention of latest-season playing time, incoming players),
  `future_*` pick fields + `future_pick_inventory_completeness`, `fin_*` contract counts, `snapshot_caveat`

## `team_season_sources.csv` (provenance)

One row per (league, team, season, dataset, variable group, source URL). Fields: `source_organization`, `source_url`,
`retrieval_timestamp_utc`, `source_update_date` (e.g. fastRhockey commit date, PWHLPA "accurate as of"), `value_origin`
(`direct` / `calculated`), `calculation_definition`, `quality_notes`, `verification_status`, `collected_by_script`.

Verification rubric: `official` / `official_players_association` (league or union publication) · `cross_checked_against_<source>`
(values matched a second independent source) · `cross_checked_pick_and_name_against_bbref` · `single_source` (reputable
specialist source, not cross-checked) · `secondary_source` (press / specialist site, manually transcribed) ·
`secondary_unverified` (crowd-edited, e.g. Wikipedia) · `calculated_unverified` (derived from a rule, not confirmed).

## Other exports

* `league_cba_parameters.csv` — copy of `config/cba_parameters.csv` (league × season × parameter, value, units, measure,
  regime, source, verification).
* `missingness_report.csv` — % null by dataset × league × column (from `06_validate_data.py`).
* `team_features_params.json` — thresholds used by `05`.
* `data/processed/` — intermediates: `pwhl_games.csv` (one row per PWHL game), `playoff_series.csv`,
  `team_record_crosschecks.csv` (source-vs-source comparisons), `draft_pick_transactions.csv` (pick assets in PWHL trades).
