# Phase M1b: pre-registered MLB feature test, horizon gaps

Plan: `m1b_preregistration.md` (committed before any result). MLB walk-forward test 2008–2023, train ≤ T−3, moving-block bootstrap (block 3). Features: `src/m1b_features.py` → `data/processed/mlb_m1b_features.csv` (D82–D85).

**Data checks.** schedule games = standings games: 1; schedule runs scored = standings runs (share of rows): 1; team-totals runs = standings runs (share of rows): 1; team-totals actual margin vs standings margin, max abs diff: 1.55e-15; BaseRuns margin vs actual margin, Pearson r: 0.958; farm affiliates per org, min: 4; farm affiliates per org, median: 4; value age: player PA/BF sum = official team total (share of team-season-groups): 1; value age: league BRAA sum, max abs over seasons: 8.02e-12; value age: stints with birthdate (share): 1; value age: hitter stints: 3.19e+04; value age: pitcher stints: 2.14e+04; coverage second_half_margin: 1; coverage baserun_margin: 1; coverage sequencing_luck: 1; coverage value_age_hitters: 1; coverage value_age_pitchers: 1; coverage farm_strength: 0.778. `farm_strength` is missing for 2000–2004 (the MLB Stats API returns no minor-league standings before 2005) and 2020 (no season); the pipeline fills it with the training median plus a missing indicator, as for every feature (D85).

**Every feature.** Incremental = OLS on `win_pct_percentile` + feature, Δ vs B1 [95% CI]. Combined = standardized coefficient in the combined elastic net (median [min, max]; % folds at 0; % minority sign). Spearman raw/partial (controlling for standing, D55) on all labelled MLB rows, descriptive only.

| Feature | Expected | Δ Spearman (incremental) | Δ MAE | Δ AUC | Combined EN coefficient | Spearman raw / partial |
|---|---|---|---|---|---|---|
| `second_half_margin` | − | +0.012 [+0.003, +0.021] | -0.14 [-0.23, +0.05] | +0.007 [+0.001, +0.012] | -0.09 [-2.24, -0.00]; 0: 44%; minority: 0% | -0.437 / -0.126 |
| `baserun_margin` | − | +0.035 [+0.006, +0.074] | -0.56 [-1.07, -0.08] | +0.024 [+0.000, +0.045] | -4.39 [-9.71, -1.35]; 0: 0%; minority: 0% | -0.489 / -0.222 |
| `sequencing_luck` | + | +0.010 [-0.012, +0.039] | -0.28 [-0.65, +0.06] | +0.003 [-0.020, +0.032] | +0.00 [+0.00, +2.75]; 0: 69%; minority: 0% | -0.017 / +0.155 |
| `value_age_hitters` | + | +0.005 [+0.000, +0.011] | -0.09 [-0.22, -0.02] | +0.002 [-0.005, +0.008] | +0.12 [+0.00, +2.07]; 0: 50%; minority: 0% | +0.023 / +0.106 |
| `value_age_pitchers` | + | -0.006 [-0.018, +0.001] | -0.02 [-0.13, +0.18] | -0.002 [-0.010, +0.003] | +0.00 [-0.51, -0.00]; 0: 75%; minority: 0% | -0.125 / -0.038 |
| `farm_strength` | − | +0.006 [-0.015, +0.032] | -0.31 [-0.72, +0.00] | +0.012 [-0.010, +0.031] | -0.40 [-2.76, -0.00]; 0: 50%; minority: 0% | -0.236 / -0.197 |

**Combined model vs B1.**

| Model | Spearman | MAE | R² | AUC | Top-5 | Δ Spearman vs B1 | Δ MAE vs B1 |
|---|---|---|---|---|---|---|---|
| B1 | 0.414 | 18.5 | 0.157 | 0.730 | 2.00 | — | — |
| EN (M1 features) | 0.404 | 18.7 | 0.138 | 0.719 | 2.00 | -0.010 [-0.064, +0.026] | +0.26 [-0.11, +0.99] |
| EN (M1 + M1b features) | 0.440 | 18.4 | 0.174 | 0.739 | 2.19 | +0.026 [-0.032, +0.077] | -0.10 [-0.52, +0.57] |

Combined − M1-feature elastic net: Δ Spearman +0.036 [+0.016, +0.063], Δ MAE -0.36 [-0.62, -0.19].

**Pre-registered decision.** Δ Spearman interval +0.026 [-0.032, +0.077] (includes 0); Δ MAE -0.10 (≤ 0). The combined MLB model **does not beat B1 beyond noise**. MLB stays on B1; the M2 selection is not re-run.

**Deviation from the pre-registration (D90, user instruction).** The value-weighted ages were first built from Baseball-Reference WAR files with no tracked fetch script. They are now recomputed from MLB Stats API player stints, with value = batting runs above average (hitters) or FIP-based runs above average (pitchers), as originally specified, and the WAR files were deleted. The recomputed ages correlate 0.88 (hitters) and 0.81 (pitchers) with the WAR versions. Effect on the M1b results: the decision is unchanged. Hitter age goes from +0.007 [+0.002, +0.015] to +0.005 [+0.000, +0.011]; its lower bound is +0.0002, so it still just excludes 0. Pitcher age goes from slightly worse than B1 (−0.003 [−0.005, −0.000]) to within noise (−0.006 [−0.018, +0.001]). The combined model goes from +0.028 [−0.037, +0.080] to +0.026 [−0.032, +0.077]. The other four features are unchanged.

**Findings.** The new features improve the MLB elastic net (+0.036 Spearman over the M1-feature version, interval +0.016 to +0.063, MAE −0.36). That lifts it slightly above B1 on average (0.440 vs 0.414), but the gain over B1 is within noise (+0.026 [−0.032, +0.077]). By the pre-registered rule **MLB stays on B1**. Per feature: BaseRuns margin is the strongest. Added to B1 on its own it gains +0.035 [+0.006, +0.074] Spearman and −0.56 MAE, and it is the only new feature the combined model uses in every fold (coefficient −4.4). Second-half margin (+0.012 [+0.003, +0.021]) and value-weighted hitter age (+0.005 [+0.000, +0.011]) add small amounts. Sequencing luck, farm strength and value-weighted pitcher age have intervals that include 0. Pitcher age's rare non-zero coefficients go against the expected sign; the other five features match their expected sign. **Caveat on BaseRuns:** B1 + BaseRuns margin would pass the M2 selection rule against B1, but it was not a pre-registered candidate. Adopting it now would be choosing a model after seeing its result, with six features tested, so it is recorded as a hypothesis for a future pre-registered test (e.g. on 2024+ seasons as their labels arrive), not as a model change.

## Horizon models with training gap = horizon (D87)

Horizon k is trained on seasons ≤ T−k (its labels are known by the end of T), inner split with the same gap. Same test seasons as M2. Mean per-season Spearman with the actual percentile in t+k:

| League | Model | Horizon | Gap = horizon | Gap = 3 (M2) | Persistence | MAE (gap = horizon) |
|---|---|---|---|---|---|---|
| MLB | per-horizon OLS on win_pct_percentile | y_pct_t1 (gap 1) | 0.489 | 0.489 | 0.489 | 22.0 |
| MLB | per-horizon OLS on win_pct_percentile | y_pct_t2 (gap 2) | 0.337 | 0.337 | 0.337 | 23.9 |
| MLB | per-horizon OLS on win_pct_percentile | y_pct_t3 (gap 3) | 0.162 | 0.162 | 0.162 | 25.5 |
| NHL | per-horizon elastic net | y_pct_t1 (gap 1) | 0.577 | 0.573 | 0.513 | 20.1 |
| NHL | per-horizon elastic net | y_pct_t2 (gap 2) | 0.513 | 0.518 | 0.438 | 21.2 |
| NHL | per-horizon elastic net | y_pct_t3 (gap 3) | 0.343 | 0.343 | 0.301 | 23.6 |

**Do the paths still average to the headline score? (D88)** Raw horizon paths no longer average exactly to the headline doom, because each horizon now trains on a different set of seasons. M3 therefore shifts each team's three projections by one common offset; after the shift 100 − mean(path) equals the headline score:

| League | Headline model | Rows | Mean / max raw gap (points) | Max error after shift | Path values outside 0–100 |
|---|---|---|---|---|---|
| MLB | B1 OLS pct | 480 | 0.20 / 1.67 | 2.1e-14 | 0 |
| NHL | Elastic net | 308 | 1.24 / 8.88 | 2.1e-14 | 1 |

Files: `m1b_features.csv`, `m1b_coef_stability.csv`, `m1b_predictions.csv`, `m1b_horizons.csv`, `m1b_path_consistency.csv`, `m1b_feature_checks.csv`. Code: `src/m1b_features.py`, `src/model/run_m1b.py`.
