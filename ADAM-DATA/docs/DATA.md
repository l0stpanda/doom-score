# Data

D-numbers refer to `docs/decisions_full.md`.

## Rows and seasons

| | MLB | NHL |
|---|---|---|
| Team-seasons (rows) | 810: 2000–2026, 30 teams | 644: 2005-06 to 2025-26, 30 → 31 (2017) → 32 (2021) |
| History-only seasons (trailing features, then dropped) | 1997–1999 | 2002-03, 2003-04 (2004-05 cancelled) |
| Labelled rows (doom known) | 720: 2000–2023 | 548: 2005-06 to 2022-23 |
| Doom ≥ 75 rate, labelled rows | 17.9% | 18.4% |
| Backtest predictions (`pred_type = backtest`) | 480: 2008–2023 | 308: 2013-14 to 2022-23 |
| Live predictions (`pred_type = live`) | 90: 2024–2026 | 96: 2023-24 to 2025-26 |
| Prediction moment (D29) | Nov 15 of t | Jun 15 of t+1 |

NHL seasons are labelled by start year (`2017` = 2017-18). `franchise_id` and `team` use the franchise's
**current** name for every season (e.g. Expos → `washington-nationals`, Coyotes → `utah-mammoth`; D03, D05, D06).

## Outcome

- **Percentile** (D10): within league-season, `(average rank of win_pct − 1)/(n − 1) × 100`; worst 0, best 100.
  NHL `win_pct` = points % (OT/SO losses get half credit, D07).
- **Doom** `y_doom_3yr = 100 − mean(percentile in t+1, t+2, t+3)`, using the franchise's next three **played**
  seasons (D11). NaN unless all three exist, so each league's last three seasons are unlabelled.
- **Doom ≥ 75** `y_doomed_bottom25`: averaged bottom quarter over the three seasons. In the exports:
  `p_doom75` = P(actual doom ≥ 75 | predicted doom), from walk-forward residuals (D99); `p_doomed` = a direct
  classifier, kept as a diagnostic (D95).
- **3-year outcome window:** seasons t+1..t+3 after the prediction moment; horizon labels `y_pct_t1..t3`.

## Sources

| Source | Used for | MLB | NHL |
|---|---|---|---|
| MLB Stats API (`statsapi.mlb.com`) | standings, draft, managers, attendance, player stints + birthdates, team totals, schedules (scores), minor-league standings | 1997–2026 (managers 1990+; MiLB 2005+) | — |
| NHL stats REST (`api.nhle.com`) | team summary, skater/goalie stints, bios, team list | — | 2002–2025 |
| NHL web API (`api-web.nhle.com`) | draft picks, current standings (logos) | — | 2002–2025 |
| Wikipedia (MediaWiki API) | GM and head-coach spans; NHL cap ceilings (D17, D32, D38, D51) | GMs | GMs, coaches, cap |
| MoneyPuck team CSVs | Corsi %, xG % (diagnostic only), PDO (D48) | — | 2008–2025 |
| Cot's Baseball Contracts | Opening Day payroll, CBT thresholds (D50, D53) | 2000–2026 | — |
| Lahman `Salaries` | payroll cross-check only (r = 0.986) | 2000–2016 | — |
| mlbstatic.com / NHL `teamLogo` | logos (viz only, not committed; D105) | current | current |

Raw responses are cached in `data/raw/` (git-ignored). Most phase 1–4 caches are not on this machine, so the
default build starts from the committed full table (`docs/cleanup_plan.md`). Baseball-Reference was not used for
any current output (D90).

## Tables

| File | Rows × cols | Notes |
|---|---|---|
| `data/processed/mlb_nhl_team_seasons.csv` | 1,454 × 104 | Frozen full table: teammate's 19 core columns, league columns, concept aliases + `_lpct`, labels |
| `data/processed/mlb_nhl_model_slim.csv` | 1,454 × 29 | Model inputs, chosen by concept, not by correlation (D61, D71; `reports/slim_selection.md`) |
| `data/processed/mlb_m1b_features.csv` | 810 × 19 | M1b MLB features (tested, context only; D82–D90) |
| `dashboard/data/*.csv` | 974 prediction rows | Exports; schema in `docs/CROSS_LEAGUE_HANDOFF.md` |

## Known gaps

- **No 80% interval / `p_doom75` / band** (`interval_available = 0`) for MLB 2008–2011 and NHL 2013–2016
  (120 rows each): fewer than two earlier calibration seasons ≤ T−3 (D80, D96).
- NHL has no spending data (team cap hits unavailable, D52, D57); NHL Corsi missing 2005–07 (filled + indicator,
  D70).
- MLB `underlying_quality` is Pythagorean win %, a near-duplicate of run margin (Spearman 0.997), so it is excluded
  (D63).
- GM tenure missing for 6% of MLB rows (vacant or unknown, D42); front-office dates from Wikipedia are imperfect
  (D28, D39). MLB 2026 GM changes are always 0 (D43).
- MLB `farm_strength` missing 2000–2004 and 2020 (D85). MLB 2020 attendance NaN (D25).
- Short seasons (MLB 2020; NHL 2012-13, 2019-20, 2020-21) are flagged, not down-weighted (D14).
- Live predictions for the earlier live seasons are not strictly out-of-sample (D92).
