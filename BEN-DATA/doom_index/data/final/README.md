# Final datasets for Doom Score work

| file | rows | columns |
|---|---|---|
| `wnba_team_doom_dataset.csv` | 91 = 76 team-seasons (2021–2026) + 15 current (2027) | 70 |
| `pwhl_team_doom_dataset.csv` | 32 = 20 team-seasons (2023-24 → 2025-26) + 12 current (2026-27) | 75 |

Built by `scripts/05_build_final_datasets.py` from the normalised tables in `data/exports/`. Thresholds are in
`feature_params.json`. Snapshot date of the current rows: 2026-11-19.

## Rows

* **Key:** `team_id` + `season`.
* `row_type = season`: one row per franchise per completed season. Features describe that season's roster using that
  season's stats. `out_*` holds the franchise's **next** season (null for the latest season). Use these rows for
  "which features predict future performance?"
* `row_type = current`: one row per active franchise for the upcoming season (WNBA `2027`, PWHL `2026-27`). Features
  describe the **current roster** (dated Wikipedia snapshot), with each player evaluated on their latest completed
  season wherever they played. `perf_*` = the latest completed season, so `perf_win_pct` is the planned Y-axis.
  Expansion teams (PWHL Detroit, Hamilton, San Jose, Vegas) have roster features but null `perf_*`.
* `is_latest_completed_season` marks the season rows for WNBA 2026 / PWHL 2025-26.

## Column roles

| prefix | role | use in Doom Score? |
|---|---|---|
| `perf_` | current / lagged performance (win %, margin, playoffs, SRS) | **No.** These are the Y-axis and outcome context. Keep win % out of the score, per the brief. |
| `out_` | next-season results | No. These are outcome labels for testing predictive value. |
| `age_`, `exp_` | roster age / experience | candidate |
| `conc_` | how concentrated production / playing time is | candidate |
| `qual_` | roster production rate (WS/40, points/60) | candidate. These are partly performance; check for overlap with `perf_` |
| `cont_` | roster continuity / turnover | candidate |
| `avail_` | games missed by top players (season rows only) | candidate |
| `draft_` | draft capital | candidate |
| `fin_` | payroll (WNBA 2021–23, PWHL 2025-26) and PWHL contract terms | candidate, sparse |
| `ctx_` | franchise age, expansion, relocation, data-quality flags | context / filters |

Nothing in either file is a score, a weight or a standardised value.

## Columns (shared unless noted)

| column | definition |
|---|---|
| league, team_id, team_name, season, season_start_year | identifiers (`team_id` is stable across renames/relocation) |
| row_type, is_latest_completed_season | see Rows |
| feature_basis | `season_roster_same_season_stats` or `current_roster_snapshot_<date>_x_<season>_stats` |
| perf_basis_season | season the `perf_*` values come from |
| perf_games_played, perf_wins, perf_losses | regular season. PWHL wins include OT/SO wins; PWHL losses are regulation losses |
| perf_otl *(PWHL)* | overtime + shootout losses |
| perf_win_pct | wins / games played |
| perf_points_pct *(PWHL)* | standings points / (3 × games played). Not the same as win % |
| perf_margin_per_game | points (WNBA) or goals (PWHL) differential per game |
| perf_srs, perf_sos *(WNBA)* | Basketball-Reference simple rating / strength of schedule |
| perf_playoff_round_reached | 0 = missed playoffs, 1 = first round, … |
| perf_champion | won the title |
| perf_prior_win_pct, perf_win_pct_change_yoy, perf_win_pct_3season_pooled | lagged win % (pooled = Σwins/ΣGP over t, t−1, t−2; null unless all three exist) |
| out_next_win_pct, out_next_win_pct_change, out_next_playoff_round_reached, out_next_points_pct *(PWHL)* | next season's values |
| roster_n, roster_n_with_playtime | roster size; players with playing time in the stats season |
| age_mean, age_median | unweighted ages (season rows: on the first game date; current rows: on the snapshot date) |
| age_playtime_weighted | age weighted by minutes (WNBA) / time on ice (PWHL) |
| age_top_n_by_playtime, age_top_n_by_production | mean age of the top N players (N = 5 WNBA, 8 PWHL) by playtime / by production (WNBA Win Shares, PWHL points) |
| age_pct_players_under_25, age_pct_players_30_plus | share of roster |
| age_share_playtime_under_25, age_share_playtime_30_plus | share of team playtime |
| age_n_young_meaningful | players under 25 with ≥ 10 games and ≥ 15 min/game (WNBA) or ≥ 12 TOI/game (PWHL; goalies qualify on games) |
| age_data_coverage | share of roster with a known age |
| exp_mean, exp_playtime_weighted | WNBA: prior WNBA seasons. PWHL: prior PWHL seasons |
| conc_top1/top3/top_n_share_production | share of positive team production from the top 1 / 3 / N players |
| conc_top3_share_playtime, conc_playtime_hhi | playing-time concentration (Herfindahl index of playtime shares) |
| conc_n_meaningful_playtime | players meeting the meaningful-playtime rule |
| conc_goalie_top1_share_playtime *(PWHL)* | starting goalie's share of goalie TOI |
| qual_production_per_playtime | WNBA team Win Shares per 40 min; PWHL skater points per 60 TOI |
| qual_n_above_league_median_rate | players above the league-season median rate (WNBA ≥ 200 min; PWHL skaters ≥ 10 GP) |
| cont_share_playtime_from_returning | share of the roster's playtime earned for this franchise last season |
| cont_share_prior_playtime_retained | share of the franchise's last-season playtime still on the roster |
| cont_n_new_players | roster players who did not play for this franchise last season |
| avail_top_players_games_missed_share | 1 − mean GP / team GP for the top N single-team players by playtime (season rows only) |
| draft_year_used, draft_pick_status | the entry draft held before the season; `picks_made` or `picks_held_future` (WNBA current = 2027 draft order) |
| draft_n_picks, draft_n_round1_picks, draft_best_pick | picks; first-round picks; best (lowest) overall pick |
| draft_n_picks_acquired_by_trade, draft_n_own_picks_traded_away | pick trading |
| draft_own_draftee_playtime_share | share of roster playtime from players this franchise drafted (drafts since 2016 WNBA / 2023 PWHL) |
| fin_basis | what the fin values are and where they come from (season rows with salary data only) |
| fin_payroll_reported_total | sum of reported player salaries. WNBA 2021–23: Spotrac cash **earnings** (incl. waived/prorated players). PWHL 2025-26: PWHLPA base salaries |
| fin_payroll_top_n_share | share of payroll held by the top N earners (N = 5 WNBA, 8 PWHL) |
| fin_salary_coverage_share | players with a reported salary / players on the team-season |
| fin_payroll_share_of_cap *(WNBA)* | payroll / hard cap. Can exceed 1, because earnings include released players |
| fin_avg_salary_vs_requirement *(PWHL)* | average salary / the CBA team-average requirement (±10% band) |
| fin_known_contract_share_of_roster, fin_n_known_contracts_expiring_after_season, fin_n_known_multi_year_contracts *(PWHL, current rows)* | known contract terms. These are lower bounds |
| ctx_franchise_prior_seasons | seasons since the franchise's founding season (incl. prior cities) |
| ctx_expansion_first_season | franchise's first season |
| ctx_relocating_next_season | WNBA Connecticut → Houston (2027) |
| ctx_n_teams_in_league | league size that season |
| ctx_roster_players_without_prior_stats | current rows: rostered players with no latest-season stats (rookies, imports) |
| ctx_roster_snapshot_quality | current rows: WNBA rosters are pre-free-agency templates that largely reflect end-of-2026 rosters |

## Known limitations

* **Salary coverage is thin:** WNBA payroll exists for 2021–2023 only (36 of 76 season rows; none for 2024–2026 or current
  rows) and PWHL for 2025-26 only (8 rows). WNBA and PWHL salary measures differ (earnings vs base salary). Compare
  within league only. PWHL contract counts are lower bounds; WNBA contract terms have no source.
* **WNBA current rows ≈ end-of-2026 rosters**, which is why `cont_share_prior_playtime_retained` is about 0.95. Re-run
  `02` → `05` after free agency to refresh them.
* **Small samples:** PWHL has 3 seasons, so only 12 season rows have `out_*` values; WNBA has 61.
* Win % has different noise in each league (40–44 vs 24–30 games). Compare within league, not across.
