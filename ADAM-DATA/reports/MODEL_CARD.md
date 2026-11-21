# Model card: Doom Score (MLB + NHL)

*Key decisions (D-numbers): `docs/KEY_DECISIONS.md`; full log and phase reports in tag `adam-full-pipeline`. Consolidated results: `reports/RESULTS.md`. Exports are rebuilt by `scripts/build_dashboard.py`.*

## What it predicts

**Doom** for team-season *t* = 100 − the team's average league percentile over the next three seasons
(t+1..t+3); 0 = finishes top of the league three years running, 100 = bottom three years running. `doom_pred` is
the predicted doom made at the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1). Also exported:
- `doom_lo80`/`doom_hi80`: 80% split-conformal interval (D80).
- `p_doomed` (diagnostic): direct classifier probability that doom ≥ 75. MLB: logistic regression on current
  standing; NHL: L1 logistic on the NHL feature set (M1).
- `proj_pct_t1..t3`: projected percentile in each of the next three seasons, from per-horizon models (training
  gap = horizon, D87), shifted by one common offset per team so that 100 − mean(path) equals `doom_pred`
  exactly (D88). Values are clipped to 0–100; clipped rows have `path_clipped` = True (1 rows),
  and for those the average is no longer exact.
- `p_doom75`: probability that actual doom ends ≥ 75, given the predicted doom: the share of earlier
  walk-forward residuals (same calibration set as the intervals) that would carry the prediction to 75+ (D99).
- `doom_band` on `p_doom75`: Low < 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50%; "Not available" where
  `interval_available` = 0 (D100). `doom_pred` itself is unchanged; `p_doomed` (direct classifier) is kept as a
  diagnostic.
- `interval_available`: 1 if the row has an 80% interval and `p_doom75` (0 for the earliest backtest seasons).

## Models

| League | Model | Inputs |
|---|---|---|
| MLB | **B1**: OLS on `win_pct_percentile` | Current standing only |
| NHL | **Elastic net** (median fill + missing indicators + scaling, alpha/l1_ratio tuned on a time split) | Current standing, 3-season record, margin, luck, Corsi, roster age, star concentration, draft capital, GM and coach tenure, GM vacancy, short season, seasons of history (no spending: unavailable for NHL) |

Choice rule (D76): the simplest model whose Spearman and MAE are within block-bootstrap noise of the best
model. In MLB nothing beat current standing: not the M1 features (M1/M2), and not six pre-registered MLB features
(M1b, D86).

## Training data

`data/mlb_nhl_model_slim.csv`: MLB 2000–2026, NHL 2005-06 to 2025-26, one row per team-season.
Labels exist through MLB 2023 / NHL 2022. Backtest (`pred_type = backtest`): walk-forward, each test season T
predicted by a model trained on seasons ≤ T−3, with all preprocessing and tuning inside the training seasons;
MLB 2008–2023, NHL 2013–2022. Live (`pred_type = live`, MLB 2024–2026, NHL
2023–2025): refit on all labelled seasons before the first live season (D92); the latest season is the
current view.

## Backtest performance vs baselines

Mean per-season Spearman with actual doom, MAE in doom points, AUC for doom ≥ 75, top-5 = how many of each
season's 5 predicted most-doomed teams actually finished in the bottom quarter (of 5). Δ = difference from B1 with
a 95% moving-block bootstrap interval (D72).

| League | Model | Spearman | MAE | AUC | Top-5 | Δ Spearman vs B1 |
|---|---|---|---|---|---|---|
| MLB | B0: 100 − current percentile (no fit) | 0.414 | 24.1 | 0.732 | 2.00 | — |
| MLB | B1 OLS pct **(chosen)** | 0.414 | 18.5 | 0.730 | 2.00 | — |
| MLB | B2 OLS pct+trail | 0.392 | 18.7 | 0.711 | 1.94 | -0.023 [-0.054, -0.004] |
| MLB | Elastic net | 0.404 | 18.7 | 0.719 | 2.00 | -0.010 [-0.064, +0.026] |
| NHL | B0: 100 − current percentile (no fit) | 0.519 | 21.9 | 0.751 | 2.10 | — |
| NHL | B1 OLS pct | 0.519 | 17.1 | 0.746 | 2.10 | — |
| NHL | B2 OLS pct+trail | 0.527 | 16.7 | 0.758 | 1.90 | +0.008 [-0.017, +0.026] |
| NHL | Elastic net **(chosen)** | 0.607 | 15.9 | 0.779 | 2.30 | +0.088 [+0.048, +0.178] |

80% intervals: coverage 82.2% (MLB, mean half-width 30 points),
85.1% (NHL, 26 points). Backtest seasons with fewer than two
earlier calibration seasons have no interval (240 rows).

## How to read the score

- Doom is a **relative ranking within a league**, not a forecast of wins. A 70 means "expected to finish around
  the 30th percentile on average over the next three seasons".
- The intervals are wide (about ±30 points in MLB, ±26 in NHL). Treat
  differences of a few points between teams as noise.
- **Drivers** (`driver_up_*`, `driver_down_*`, `doom_drivers_long.csv`) are exact contributions of a linear
  model: coefficient × the team's standardized deviation from the training mean, in doom points. They add up
  to the prediction minus the intercept.
- **MLB drivers are current standing only**, with a note saying so: no other MLB feature improved the backtest.
  `team_profile.csv` shows every slim feature's percentile, plus MLB BaseRuns margin, second-half margin and
  value-weighted hitter age, as **context, not drivers**. `team_profile_columns.csv` marks which columns each
  league's model uses.

## Known limitations

- **Short seasons:** MLB 2020 (60 games) and NHL 2012-13, 2019-20 and 2020-21 have noisier standings; they are
  flagged (`short_season`) but not down-weighted.
- **Overlapping labels:** adjacent seasons share up to two future seasons, so the backtest has fewer independent
  observations than rows (16 MLB and 10 NHL test seasons). The block bootstrap accounts for this only roughly.
  Live predictions for MLB 2024–2025 and NHL 2023–2024 come from a model whose training labels overlap those
  seasons' futures, so they are not strictly out-of-sample.
- **NHL has no spending data** (team cap hits unavailable, D57); the NHL model has no payroll term.
- **MLB has no independent underlying-quality measure:** its `underlying_quality` column is Pythagorean win%,
  a near-duplicate of run margin (Spearman 0.997, D63), so it is excluded. NHL Corsi is missing for 2005–07
  (filled + indicator, D70).
- Front-office data (GM tenure, vacancies) come from Wikipedia with imperfect dates (D28, D39).
- No soft-leakage features are used: NHL xG (D54, D79) and Baseball-Reference WAR (removed, D90) are not inputs.

## Future work

- **D86: BaseRuns margin (MLB).** Added to current standing it beat B1 in the backtest (Δ Spearman +0.035 [+0.006,
  +0.074]), but it was not a pre-registered candidate and six features were tested. Re-test it, pre-registered,
  on new seasons as their labels arrive (MLB 2024+), before it can enter the MLB model.

## Files (`dashboard/data/`)

`doom_predictions.csv` (974 rows: 788 backtest, 186 live), `doom_drivers_long.csv`
(6226 rows), `team_profile.csv`, `team_profile_columns.csv`, `team_meta.csv`, `comparables.csv`. Schema:
`docs/CROSS_LEAGUE_HANDOFF.md`.
