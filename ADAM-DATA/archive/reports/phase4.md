# Phase 4: money and final table

**Outputs:**
- **Final table:** `data/processed/mlb_nhl_team_seasons.csv` (1,454 × 77, teammate core columns first).
- **Reference docs:** `DATA_DICTIONARY.md`, `DECISIONS.md` (D01–D56).
- **Manual inputs:** `data/manual/mlb_cbt_threshold.csv`, `nhl_salary_cap.csv`, `payroll_template.csv`.
- **Reports:** `reports/phase4_correlations.csv`, `phase4_checks.csv`.

**Code:** `src/fetch_phase4.py`, `src/build_phase4.py`, `src/make_data_dictionary.py`

## Source probes
| Source | Result |
|---|---|
| Cot's Baseball Contracts (30 team pages + CBA history) | ok: Opening Day payroll 2000–2026 for every team |
| Lahman Salaries mirror (chadwickbureau) | 404 (repo gone); seanlahman mirror ok (cross-check only) |
| Spotrac MLB / NHL | **BLOCKED** (403) |
| PuckPedia | **BLOCKED** (anti-bot page) |
| CapWages | ok, but only 2025-26 onward: no history |
| Wikipedia "NHL salary cap" | ok (cap ceiling chart) |

MLB payroll was the priority and took well under 10 minutes. NHL cap hits went to the template (644 rows) instead of more effort.

## Coverage
- **MLB:** `payroll_opening_day_usd`, `payroll_rank` and `payroll_rel_league_mean` 100% (2000–2026). `payroll_pct_of_cbt` is 100% for 2003–2026; there was no tax in 2000–02.
- **NHL:** `cap_upper_limit_usd` 100%. `cap_space_pct` and `team_cap_hit_usd` are **0%**, so they need the template.

## Checks: 8/8 PASS
- Core column order and 1,454 unique rows.
- MLB payroll for every team-season.
- Our own payroll rank is valid. Cot's printed ranks contradict its dollar values in 23 of 27 seasons, so they were dropped.
- Cot's vs Lahman 2000–16: n = 499, r = 0.986, median difference 0.27%, 89% within 10%.
- Every CBT value appears verbatim in the cited source.
- NHL cap ceiling for every season.
- Labels identical to Phase 1.

## Notes requested in review
- **MoneyPuck xG soft leakage** is logged as D54 and noted in the dictionary. Its model is trained on all seasons, including seasons after t.
- **MLB 2026 `personnel_lead_changed_past_year` is systematically 0.** All 2026 changes in the sources are year-only and fall after Nov 15. This is in the dictionary header and on the column itself.

## Spearman and partial Spearman vs `y_doom_3yr` (review only)
Partial = controlling for `win_pct_percentile` (ranks residualized by OLS; D55). Sorted by the larger absolute partial. Labelled rows only (MLB n ≈ 720, NHL ≈ 548; MoneyPuck NHL 2008+).

| Feature | MLB ρ | MLB partial | NHL ρ | NHL partial |
|---|---|---|---|---|
| `win_pct_percentile` | -0.45 |  | -0.50 |  |
| `xgoals_pct` |  |  | -0.55 | -0.30 |
| `corsi_pct` |  |  | -0.45 | -0.23 |
| `point_diff_per_game` | -0.47 | -0.15 | -0.54 | -0.23 |
| `pythag_win_pct` | -0.46 | -0.14 | -0.54 | -0.23 |
| `win_pct_trailing_3_seasons` | -0.38 | -0.05 | -0.48 | -0.17 |
| `luck` | -0.06 | +0.11 | -0.01 | +0.17 |
| `top3_concentration` | -0.08 | +0.04 | -0.23 | -0.17 |
| `age_weighted` | -0.12 | +0.06 | +0.04 | +0.15 |
| `win_pct_raw` | -0.45 | -0.06 | -0.52 | -0.13 |
| `win_pct_change_1yr` | -0.17 | +0.05 | -0.12 | +0.13 |
| `scored_per_game` | -0.29 | -0.05 | -0.40 | -0.13 |
| `attendance_rank` | +0.30 | +0.12 |  |  |
| `personnel_lead_tenure_left_censored` | -0.17 | -0.11 | +0.01 | +0.06 |
| `age_weighted_hitters` | -0.03 | +0.10 |  |  |
| `draft_picks_rd1_2` | +0.02 | +0.06 | +0.04 | -0.10 |
| `attendance_per_game` | -0.28 | -0.10 |  |  |
| `win_pct` | -0.45 | -0.06 | -0.51 | -0.10 |
| `share_points_age32plus` |  |  | +0.06 | +0.10 |
| `roster_players_used` | +0.06 | -0.09 | +0.23 | +0.01 |
| `coach_tenure_left_censored` | -0.11 | -0.09 | +0.02 | +0.05 |
| `coach_changed_during_regular_season` | +0.13 | +0.04 | +0.02 | -0.09 |
| `share_production_age32plus` | -0.10 | +0.02 | +0.06 | +0.09 |
| `payroll_rel_league_mean` | -0.22 | -0.08 |  |  |
| `payroll_rank` | +0.22 | +0.08 |  |  |
| `payroll_pct_of_cbt` | -0.20 | -0.07 |  |  |
| `coach_tenure_years` | -0.19 | -0.07 | -0.08 | +0.05 |
| `win_pct_slope_3yr` | -0.24 | -0.01 | -0.21 | +0.07 |
| `pdo_5v5` |  |  | -0.28 | +0.07 |
| `draft_first_pick_number` | -0.27 | -0.07 | -0.21 | -0.05 |
| `payroll_opening_day_usd` | -0.17 | -0.06 |  |  |
| `personnel_lead_vacant` | -0.10 | -0.06 | +0.04 | +0.03 |
| `draft_picks_used_pctile` | +0.05 | +0.06 | +0.06 | -0.04 |
| `ot_losses` |  |  | +0.14 | +0.06 |
| `team_bf` | +0.25 | +0.06 |  |  |
| `ties` | -0.01 | +0.01 | +0.14 | +0.06 |
| `team_pa` | -0.20 | -0.05 |  |  |
| `personnel_lead_tenure_years` | -0.06 | +0.01 | -0.09 | +0.05 |
| `personnel_lead_changed_past_year` | +0.05 | +0.02 | +0.14 | +0.04 |
| `goalie_gp_sum` |  |  | +0.15 | +0.04 |
| `allowed_per_game` | +0.33 | +0.03 | +0.37 | +0.04 |
| `draft_picks_used` | +0.01 | +0.01 | +0.07 | -0.03 |
| `age_weighted_pitchers` | -0.18 | -0.03 |  |  |
| `wins` | -0.42 | -0.02 | -0.42 | -0.02 |
| `losses` | +0.41 | +0.02 | +0.42 | +0.00 |
| `expansion_first_3_seasons` |  |  | -0.03 | -0.02 |
| `manager_resolved_by_fallback` | -0.01 | -0.02 |  |  |
| `personnel_lead_gap_carried` | +0.02 | +0.02 |  |  |
| `cap_upper_limit_usd` |  |  | -0.01 | -0.01 |
| `short_season` | +0.00 | +0.00 | -0.01 | -0.01 |
| `games` | -0.02 | +0.01 | +0.01 | +0.01 |
| `skater_gp_sum` |  |  | -0.00 | +0.01 |
| `cbt_threshold_usd` | +0.00 | +0.00 |  |  |
| `draft_rounds_in_year` | -0.00 | -0.00 |  |  |
| `attendance_restricted` | +0.00 | +0.00 |  |  |
| `seasons_of_history` | -0.00 | +0.00 | +0.01 | +0.00 |

**Reading:**
- Most of each feature's raw correlation is current standing. Once `win_pct_percentile` is controlled for, the largest remaining signals are:
  - NHL `xgoals_pct` (−0.30) and `corsi_pct` (−0.23), with the xG leakage caveat;
  - run/goal differential and Pythagorean win% (MLB −0.13 to −0.15, NHL −0.23);
  - `luck` (+0.11 MLB, +0.17 NHL): lucky teams regress;
  - NHL `age_weighted` (+0.15) and `top3_concentration` (−0.17);
  - MLB attendance (−0.10).
- Payroll adds little beyond standing in MLB (partial −0.08).

Phase 4 complete. All phases done; stopped.
