# Phase M1b pre-registration: MLB feature test

Written and committed **before** any of these features was computed or compared with a label. The definitions,
expected signs, model and decision rule below are fixed. Results go to `reports/m1b.md`; any deviation from this
plan is listed there as a deviation, with a reason.

## Question

M1/M2 found that in MLB no feature beats current standing (B1). Do six better-measured MLB features change that?

## Features (MLB only, season t, all known before the Nov 15 prediction moment)

Each is converted to a within-league-season percentile (`_lpct`, D59 formula) before modeling.

| Feature | Definition | Source | Expected sign on doom |
|---|---|---|---|
| `second_half_margin` | (runs scored − runs allowed) per game over the team's regular-season games after its own midpoint: games ordered by date (then game number), second half = games after the first ⌊G/2⌋. Final games only, de-duplicated by gamePk | MLB Stats API `/schedule` (gameType R) | − (strong late teams carry form forward) |
| `baserun_margin` | (BaseRuns scored − BaseRuns allowed) per game. BaseRuns: A = H + BB + HBP − HR; B = 1.02 × (1.4·TB − 0.6·H − 3·HR + 0.1·(BB + HBP)); C = AB − H; D = HR; BsR = A·B/(B + C) + D. Offense from the hitting group, allowed from the pitching group. BsR is rescaled per season so the league total equals actual league runs (removes the arbitrary B multiplier and era drift) | MLB Stats API `/teams/stats` (hitting, pitching) | − |
| `sequencing_luck` | actual run margin per game − `baserun_margin` | as above | + (luck regresses) |
| `value_age_hitters` | Hitter age weighted by max(WAR, 0) per player-team stint; age = Baseball-Reference season age; rows with `pitcher = N` | Baseball-Reference `war_daily_bat.txt` | + (older value = decline) |
| `value_age_pitchers` | Pitcher age weighted by max(WAR, 0) per player-team stint | Baseball-Reference `war_daily_pitch.txt` | + |
| `farm_strength` | Games-weighted win% of the organization's full-season affiliates (Triple-A, Double-A, High-A, Low-A; MLB sport ids 11–14), matched by `parentOrgId`. 2020 has no minor-league season → missing | MLB Stats API `/teams`, `/standings` (sport ids 11–14) | − |

Team mapping: MLB Stats API team ids are the franchise key (D03). Baseball-Reference codes map to franchises
by a fixed table (ANA/LAA → Angels, FLA/MIA → Marlins, MON/WSN → Nationals, TBD/TBR → Rays, OAK/ATH →
Athletics, others one-to-one).

Known caveats, accepted in advance: Baseball-Reference WAR uses multi-year park factors and is revised over
time (soft leakage, like MoneyPuck xG, D54); minor-league win% is a weak proxy for prospect quality.

## Backtest (unchanged from M1/M2)

Walk-forward, train ≤ T−3 (asserted), MLB test seasons 2008–2023, Pipeline preprocessing (median fill + >1%
missing indicator + scaling), inner time split with the same gap, moving-block bootstrap over test seasons
(block 3, 2,000 draws, seed 2026).

## Tests

1. **Per feature (reported for every feature):**
   - Incremental model: OLS on `win_pct_percentile` + the feature vs B1, with Δ Spearman (mean per season),
     Δ MAE and Δ AUC and their block-bootstrap intervals.
   - Sign and stability of its standardized coefficient across folds in the combined model (median, range,
     share of folds at 0, share of folds with the minority sign).
   - Descriptive only: Spearman with `y_doom_3yr` on labelled rows, raw and partial (controlling for
     `win_pct_percentile`, the D55 method).
2. **Combined model:** elastic net on the M1 MLB features plus all six new `_lpct` features, with the same
   tuning grid as M1.

## Decision rule

The combined MLB model **beats B1 beyond noise** if and only if both:
- the 95% block-bootstrap interval of Δ mean per-season Spearman vs B1 lies entirely above 0, and
- Δ MAE vs B1 is ≤ 0 (not worse on average).

If it does, the M2 selection is re-run for MLB with the new features available to every eligible feature model
(elastic net, horizon EN, EBM) and the same rule (D76). If it does not, MLB stays on B1. The per-feature results
are descriptive and do not change the choice on their own: six features are tested, so one interval excluding 0
by chance is plausible.

No feature definition, weight or threshold will be changed after seeing results.
