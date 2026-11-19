# Data collection report

Generated: 2026-11-19T10:33:11+00:00 (UTC). Produced by `scripts/06_validate_data.py`.

## Row counts

| dataset | league | rows | seasons / years |
|---|---|---|---|
| team_season_data.csv | PWHL | 20 | 2023-24, 2024-25, 2025-26 |
| team_season_data.csv | WNBA | 100 | 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 |
| player_season_data.csv | PWHL | 548 | 2023-24, 2024-25, 2025-26 |
| player_season_data.csv | WNBA | 1167 | 2021, 2022, 2023, 2024, 2025, 2026 |
| draft_history.csv | PWHL | 314 | 2023, 2024, 2025, 2026 |
| draft_history.csv | WNBA | 441 | 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 |
| draft_pick_inventory.csv | WNBA | 45 | 2027 |
| team_financials.csv | PWHL | 32 | 2023-24, 2024-25, 2025-26, 2026-27 |
| team_financials.csv | WNBA | 91 | 2021, 2022, 2023, 2024, 2025, 2026, offseason_after_2026 |
| team_season_sources.csv | PWHL | 166 | 2023, 2023-24, 2024, 2024-25, 2025, 2025-26, 2026, 2026-27, snapshot_2026-11-19 |
| team_season_sources.csv | WNBA | 772 | 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, snapshot_2026-11-19 |
| team_features.csv | PWHL | 32 | 2023-24, 2024-25, 2025-26, current_snapshot |
| team_features.csv | WNBA | 91 | 2021, 2022, 2023, 2024, 2025, 2026, current_snapshot |
| current_roster_snapshot.csv | PWHL | 268 |  |
| current_roster_snapshot.csv | WNBA | 229 |  |
| contract_transactions.csv | PWHL | 374 |  |
| league_cba_parameters.csv | PWHL | 11 | 2023-24, 2024-25, 2025-26, 2026-27 |
| league_cba_parameters.csv | WNBA | 15 | 2021, 2022, 2023, 2024, 2025, 2026 |

## Team-season coverage

| league | season | teams | games per team | in core scope |
|---|---|---|---|---|
| PWHL | 2023-24 | 6 | 24.0 | True |
| PWHL | 2024-25 | 6 | 30.0 | True |
| PWHL | 2025-26 | 8 | 30.0 | True |
| WNBA | 2019 | 12 | 34.0 | False |
| WNBA | 2020 | 12 | 22.0 | False |
| WNBA | 2021 | 12 | 32.0 | True |
| WNBA | 2022 | 12 | 36.0 | True |
| WNBA | 2023 | 12 | 40.0 | True |
| WNBA | 2024 | 12 | 40.0 | True |
| WNBA | 2025 | 13 | 44.0 | True |
| WNBA | 2026 | 15 | 44.0 | True |

## Missingness of key fields (% of rows null)

**team_season_data.csv**

| field | PWHL | WNBA |
|---|---|---|
| wins | 0.0 | 0.0 |
| losses | 0.0 | 0.0 |
| overtime_losses | 0.0 | 100.0 |
| win_percentage | 0.0 | 0.0 |
| points_percentage | 0.0 | 100.0 |
| points_for | 100.0 | 0.0 |
| goals_for | 0.0 | 100.0 |
| home_wins | 0.0 | 0.0 |
| sos_bbref | 100.0 | 0.0 |
| playoff_round_reached | 0.0 | 0.0 |
| prior_season_win_pct | 40.0 | 15.0 |
| win_pct_rolling3_mean | 70.0 | 28.0 |

**player_season_data.csv**

| field | PWHL | WNBA |
|---|---|---|
| birth_date | 0.0 | 0.0 |
| age_at_reference | 0.0 | 0.0 |
| experience_years | 0.0 | 0.0 |
| position | 0.0 | 1.4 |
| games_played | 0.0 | 0.8 |
| minutes | 100.0 | 0.8 |
| time_on_ice_total_min | 1.8 | 100.0 |
| points | 0.0 | 0.8 |
| ws | 100.0 | 0.8 |
| plus_minus | 10.8 | 100.0 |
| save_pct | 91.1 | 100.0 |
| salary_base_usd | 64.6 | 100.0 |
| contract_end_year | 100.0 | 100.0 |

**draft_history.csv**

| field | PWHL | WNBA |
|---|---|---|
| round | 19.7 | 2.7 |
| player_id | 27.7 | 7.9 |
| original_owner_team_id | 0.0 | 0.0 |
| trade_note_text | 94.3 | 64.4 |
| career_games | 27.7 | 37.0 |

**team_financials.csv**

| field | PWHL | WNBA |
|---|---|---|
| team_salary_cap | 100.0 | 16.5 |
| team_average_salary_requirement | 0.0 | 100.0 |
| payroll_reported_total | 75.0 | 100.0 |
| cap_space | 100.0 | 100.0 |
| top8_salary_share | 75.0 | 100.0 |

Interpretation: a missing value is null, never zero. Large percentages above are expected where a field does not apply to a league (e.g. `ws` for the PWHL, `goals_for` for the WNBA) or no permitted source exists (WNBA salaries). See `docs/source_coverage_matrix.md`.

## Source coverage (provenance rows by dataset and source)

| league | dataset | source | rows | verification |
|---|---|---|---|---|
| PWHL | contract_transactions | Wikipedia (crowd-edited) | 2 | secondary_unverified |
| PWHL | current_roster_snapshot | Wikipedia (crowd-edited) | 12 | secondary_unverified |
| PWHL | draft_history | Wikipedia (crowd-edited) | 4 | secondary_unverified |
| PWHL | player_season_data | PWHL Players' Association (PWHLPA) | 8 | official_players_association |
| PWHL | player_season_data | sportsdataverse fastRhockey-pwhl-data (from PWHL/HockeyTech official stats) | 40 | single_source |
| PWHL | team_financials | PWHLPA Player Salary Guide | 8 | official_players_association |
| PWHL | team_financials | config/cba_parameters.csv (see per-row source_url) | 32 | calculated_unverified, secondary_source |
| PWHL | team_season_data | sportsdataverse fastRhockey-pwhl-data (from PWHL/HockeyTech official stats) | 60 | cross_checked_against_wikipedia |
| WNBA | current_roster_snapshot | Wikipedia (crowd-edited) | 15 | secondary_unverified |
| WNBA | draft_history | Sports Reference LLC (Basketball-Reference) | 11 | single_source |
| WNBA | draft_history | Wikipedia (crowd-edited) | 13 | cross_checked_pick_and_name_against_bbref, secondary_unverified |
| WNBA | draft_pick_inventory | Wikipedia (crowd-edited) | 1 | secondary_unverified |
| WNBA | player_season_data | Sports Reference LLC (Basketball-Reference) | 256 | single_source |
| WNBA | team_financials | config/cba_parameters.csv (see per-row source_url) | 76 | calculated_unverified, official, secondary_source |
| WNBA | team_season_data | ESPN (public site API) | 100 | single_source |
| WNBA | team_season_data | Sports Reference LLC (Basketball-Reference) | 300 | cross_checked_against_espn, single_source |

## Validation results

70 PASS, 3 WARN, 0 FAIL (full table: `logs/validation_results.csv`).

| check | status | n | detail |
|---|---|---|---|
| draft:WNBA bbref name mismatches (spelling variants) | WARN | 9 |  draft_year pick_overall player_name bbref_player_name 315 2016 10.0 Imani Boyette Imani McGee-Stafford 381 2017 5.0 Nia Coffey Nia Brodie 388 2018 11.0 Maria Vadeeva Maria Kliundikova 394 2018 17.0 Park Ji-su JiSu Park  |
| financial:team payroll available | WARN | 88 | league financial_data_status PWHL not_reported_by_source_for_season 12 WNBA not_collected_no_permitted_automated_source 76 |
| crosscheck:team records vs second source | WARN | 4 |  league season team_id source_b mismatched_fields 44 WNBA 2021 WNBA-ATL ESPN allowed 52 WNBA 2021 WNBA-NYL ESPN scored 92 WNBA 2025 WNBA-ATL ESPN scored 98 WNBA 2025 WNBA-LAS ESPN scored |
