# Results (M1, M2, M1b, M3)

Out-of-sample walk-forward backtest: season T is predicted from seasons ≤ T−3. Test seasons: MLB 2008–2023 (16),
NHL 2013-14 to 2022-23 (10). Metrics:
- **Spearman:** rank correlation of predicted vs actual doom, mean over test seasons.
- **MAE:** mean absolute error, in doom points.
- **AUC:** for doom ≥ 75.
- **Top-5:** how many of each season's 5 predicted most-doomed teams actually finished bottom-quarter (out of 5).
- **[ ]:** 95% interval from a moving-block bootstrap over test seasons (block 3).

Phase reports with all tables are in tag `adam-full-pipeline` (`ADAM-DATA/reports/`).

## 1. M1: baselines vs main models

| League | Model | Spearman | MAE | R² | AUC | Top-5 | Δ Spearman vs B1 | Δ MAE vs B1 |
|---|---|---|---|---|---|---|---|---|
| MLB | B0: 100 − current percentile | 0.414 | 24.1 | −0.539 | 0.732 | 2.00 | 0 (same ranking) | +5.6 [+4.7, +6.7] |
| MLB | **B1: OLS on current percentile** | 0.414 | 18.5 | 0.157 | 0.730 | 2.00 | — | — |
| MLB | B2: B1 + 3-season record | 0.392 | 18.7 | 0.130 | 0.711 | 1.94 | −0.023 [−0.054, −0.004] | +0.2 [+0.0, +0.5] |
| MLB | Elastic net | 0.404 | 18.7 | 0.138 | 0.719 | 2.00 | −0.010 [−0.064, +0.026] | +0.3 [−0.1, +1.0] |
| MLB | L1 logistic (doom ≥ 75) | 0.394 | — | — | 0.704 | 1.94 | −0.020 [−0.083, +0.024] | — |
| NHL | B0 | 0.519 | 21.9 | −0.252 | 0.751 | 2.10 | 0 | +4.8 [+2.8, +6.6] |
| NHL | B1 | 0.519 | 17.1 | 0.262 | 0.746 | 2.10 | — | — |
| NHL | B2 | 0.527 | 16.7 | 0.283 | 0.758 | 1.90 | +0.008 [−0.017, +0.026] | −0.4 [−0.4, −0.3] |
| NHL | **Elastic net** | 0.607 | 15.9 | 0.365 | 0.779 | 2.30 | **+0.088 [+0.048, +0.178]** | **−1.2 [−2.4, −1.0]** |
| NHL | L1 logistic | 0.566 | — | — | 0.771 | 2.20 | +0.046 [+0.011, +0.117] | — |

NHL elastic-net coefficients with the same sign in every fold (doom points per SD): margin −4.0, 3-season record
−3.4, Corsi −3.2, current percentile −2.9, roster age +2.9, star concentration −2.5, draft capital −2.4.

## 2. M2: challengers and final choice

Rule: the simplest model whose Spearman and MAE are within noise of the best one. Order of simplicity:
B1 < B2 < elastic net < horizon EN < EBM. LightGBM was an interaction check and xG a diagnostic; neither was
eligible.

| League | Model | Spearman | MAE | Δ Spearman vs best | Δ MAE vs best | Within noise |
|---|---|---|---|---|---|---|
| MLB | **B1 (best, chosen)** | 0.414 | 18.5 | — | — | yes |
| MLB | Elastic net | 0.404 | 18.7 | −0.010 [−0.064, +0.026] | +0.3 [−0.1, +1.0] | yes (but not simpler) |
| MLB | EBM | 0.386 | 18.5 | −0.028 [−0.086, +0.019] | +0.1 [−0.5, +0.7] | yes |
| MLB | Horizon EN | 0.394 | 18.7 | −0.020 [−0.070, +0.010] | +0.2 [−0.1, +0.8] | yes |
| MLB | LightGBM depth 2 | 0.351 | 19.2 | −0.063 [−0.102, −0.027] | +0.7 [+0.0, +1.5] | check only |
| NHL | **Elastic net (best, chosen)** | 0.607 | 15.9 | — | — | yes |
| NHL | EBM | 0.586 | 16.0 | −0.022 [−0.040, −0.003] | +0.1 [−0.2, +0.5] | no |
| NHL | Horizon EN | 0.595 | 16.0 | −0.012 [−0.027, −0.004] | +0.1 [−0.1, +0.4] | no |
| NHL | B1 | 0.519 | 17.1 | −0.088 [−0.178, −0.048] | +1.2 [+1.0, +2.4] | no |
| NHL | LightGBM depth 2 | 0.566 | 16.4 | −0.041 [−0.073, −0.015] | +0.5 [+0.1, +1.4] | check only |
| NHL | Elastic net with xG instead of Corsi | 0.629 | 15.6 | +0.021 [−0.001, +0.033] | −0.3 [−0.5, +0.0] | diagnostic (soft leakage) |

- **Interactions:** none worth having. LightGBM with depth-2 trees is no better than depth-1 stumps (MLB −0.026,
  NHL +0.015 [−0.003, +0.042]) and is worse than the elastic net.
- **80% intervals (split conformal):** coverage 82.2% (MLB, ±30 points), 85.1% (NHL, ±26).
- Shape of the NHL Corsi effect: `figures/ebm_nhl_corsi_shape.png` (close to a straight line).

## 3. M1b: pre-registered MLB features

The plan was committed before any result. Rule: the combined model must beat B1 with the Spearman interval
entirely above 0 and MAE no worse.

| Feature (added to B1 alone) | Expected sign | Δ Spearman vs B1 | Δ MAE |
|---|---|---|---|
| BaseRuns margin | − | **+0.035 [+0.006, +0.074]** | −0.56 |
| Second-half margin | − | +0.012 [+0.003, +0.021] | −0.14 |
| Sequencing luck | + | +0.010 [−0.012, +0.039] | −0.28 |
| Hitter age (weighted by batting runs above average) | + | +0.005 [+0.000, +0.011] | −0.09 |
| Pitcher age (weighted by FIP runs above average) | + | −0.006 [−0.018, +0.001] | −0.02 |
| Farm strength (affiliate win %, 2005+) | − | +0.006 [−0.015, +0.032] | −0.31 |

| Model | Spearman | MAE | Δ Spearman vs B1 |
|---|---|---|---|
| B1 | 0.414 | 18.5 | — |
| Elastic net, M1 features | 0.404 | 18.7 | −0.010 [−0.064, +0.026] |
| Elastic net, M1 + M1b features | 0.440 | 18.4 | +0.026 [−0.032, +0.077] |

**Decision:** not beyond noise, so **MLB stays on standings only**. BaseRuns margin passes on its own but was not
a pre-registered candidate; it is future work, to be tested on new seasons.

## 4. M3: exported probabilities (`p_doom75`)

Computed on backtest rows that have an interval and a known outcome. Brier score, lower is better:

| League | n | Base rate | `p_doom75` | `p_doomed` (direct classifier) | Base rate only |
|---|---|---|---|---|---|
| MLB | 360 | 18.6% | 0.139 | 0.140 | 0.151 |
| NHL | 188 | 21.3% | 0.144 | 0.143 | 0.167 |

Calibration by decile of `p_doom75` (mean predicted → observed rate of doom ≥ 75):

| Decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| MLB | .01→.03 | .04→.06 | .06→.11 | .09→.06 | .14→.22 | .17→.17 | .22→.22 | .27→.36 | .33→.22 | .39→.42 |
| NHL | .00→.00 | .02→.05 | .03→.11 | .06→.17 | .09→.05 | .14→.11 | .19→.39 | .26→.32 | .35→.47 | .44→.47 |

Bands (share of labelled rows that actually ended at doom ≥ 75):

| League | Low (< 10%) | Moderate (10–30%) | High (30–50%) | Very high (≥ 50%) | Not available |
|---|---|---|---|---|---|
| MLB | 7% (n 130) | 22% (152) | 32% (78) | — (0) | 18% (120) |
| NHL | 8% (91) | 26% (58) | 49% (37) | 0% (2) | 15% (120) |
