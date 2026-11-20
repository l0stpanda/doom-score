# Features

Current models (D76, D86): **MLB = B1, standings only** (OLS on `win_pct_percentile`); **NHL = elastic net** on the
13 features below. Nothing else enters an MLB prediction. Whether MLB should get non-standings features is an
open question (`docs/CROSS_LEAGUE_HANDOFF.md`).

**Standardization, all model features** (two steps):
1. In the data: `_lpct` = within-league-season percentile, `(average rank − 1)/(n − 1) × 100` over non-missing
   values, the same formula as `win_pct_percentile` (D10, D59; `src/common.py`). Flags and counts stay raw.
2. In each model fold: median fill, plus a 0/1 missing indicator for any feature missing in > 1% of that fold's
   training rows (D67), then a z-score (`StandardScaler`) fitted on the training seasons only (D66).

Coefficients and drivers are therefore in doom points per training SD.

**Model codes:** NHL-EN = NHL elastic net (doom; drivers); NHL-L1 = NHL L1 logistic (`p_doomed`); NHL-H = NHL
horizon elastic nets (`proj_pct_t1..t3`); MLB-B1 = MLB doom, MLB logistic `p_doomed` and MLB per-horizon OLS;
B1 = the standing-only model behind `b1_pred` in both leagues (D102).

**Where the "why" comes from:** reasons are quoted from the decisions log, reports or code. "Guide" = the
"Why it might relate to doom" line in `archive/docs/DATASET_GUIDE.md`, generated from `make_doc_stats.py`. Those
are hypotheses written while documenting the data, not a record of why you chose each concept. The concept list
itself comes from your M1 spec (`archive/prompts/doom_modeling_prompt.md`), which gives no reasons.

## Model features

| Feature | Measures | Scale | Used by | Why included (source) |
|---|---|---|---|---|
| `win_pct_percentile` | Current standing in season t | percentile (D10) | MLB-B1, B1, NHL-EN/L1/H | "Current standing; the doom label is built from future values of this" (guide). The baseline every model must beat (M1 spec, D68); the only MLB input after D76/D86 |
| `win_pct_trailing_3_seasons_lpct` | Mean win % over the last 3 played seasons incl. t | `_lpct` (D71) | NHL-EN/L1/H | "Smooths one-season noise" (guide); B2 baseline (D68) |
| `margin_per_game_lpct` | (scored − allowed) per game | `_lpct` | NHL-EN/L1/H | "Margin predicts future records better than wins do" (guide); crosswalk concept (D58) |
| `luck_lpct` | win % − Pythagorean win % (exp. 2.0) | `_lpct` | NHL-EN/L1/H | "Lucky teams tend to regress; unlucky teams to rebound" (guide) |
| `underlying_quality_lpct` | NHL Corsi % (shot-attempt share), 2008+ | `_lpct`; 2005–07 filled + indicator (D70) | NHL-EN/L1/H | "Measures puck control; predictive of future results" (guide). Corsi chosen over xG because xG has soft leakage (D54, D58) |
| `roster_age_weighted_lpct` | Age weighted by time on ice (age on Feb 1 of t+1) | `_lpct` | NHL-EN/L1/H | "Old rosters may decline; young ones may improve" (guide); weighting choice D45 |
| `star_concentration_lpct` | Top-3 skaters' share of team skater points | `_lpct` | NHL-EN/L1/H | "Star-dependent teams are fragile if a star leaves or ages" (guide). Points, not TOI, because top-3 TOI would just pick defensemen/goalies (D45) |
| `draft_capital_lpct` | Picks in rounds 1–2 of the June t draft | `_lpct` | NHL-EN/L1/H | "Early picks are the ones most likely to become good players" (guide); definition D18, D21 |
| `gm_tenure_lpct` | GM tenure at the prediction moment | `_lpct`; NaN when vacant | NHL-EN/L1/H | "New GMs often rebuild; long tenures can mean stability or stagnation" (guide); GM-only rule D36 |
| `coach_tenure_lpct` | Head-coach tenure at season end (mid-season start = 0.5) | `_lpct` | NHL-EN/L1/H | "Coaching changes often follow bad seasons" (guide); definition D24 |
| `personnel_lead_vacant` | 1 if no one held the GM title at the moment | 0/1 | NHL-EN/L1/H | "Vacancies often follow upheaval" (guide); "vacancy is known information, not missing data" (D42); added per M1 spec (D62) |
| `short_season` | MLB 2020; NHL 2012-13, 2019-20, 2020-21 | 0/1 | NHL-EN/L1/H | "Records from short seasons are noisier" (guide); flag per spec (D14) |
| `seasons_of_history` | Franchise seasons available up to t | count | NHL-EN/L1/H | "Low values = less reliable trailing features (expansion teams)" (guide); D09 |

The model features are the M1 spec's slim set. The concepts were chosen by concept, not by correlation with the
label (D61). Excluded: NHL `spending_lpct` (all missing, D57) and MLB `underlying_quality_lpct` (duplicate of margin,
D63). In MLB the other features are present but unused, because none beat B1 beyond noise (M1, M2, M1b; D76, D86).

## Context only (team profile, comparables; never model inputs)

| Feature | Measures | Scale | Where | Why (source) |
|---|---|---|---|---|
| MLB versions of the concepts above, plus `spending_lpct` (Opening Day payroll / league mean, D53, D57) | as above | `_lpct` | `team_profile.csv`, `comparables.csv` (D93, D103) | Shown as context because no MLB feature beat B1 (D89). For `spending` specifically, only the definition is recorded ("same as payroll but comparable across years"): **rationale not recorded — ask Adam** |
| `baserun_margin_lpct` | (BaseRuns scored − allowed) per game | `_lpct` | profile, comparables | Pre-registered M1b feature, expected sign −; strongest single MLB feature but not adopted (D86). **Rationale not recorded beyond the expected sign — ask Adam** |
| `second_half_margin_lpct` | Run margin per game after the team's midpoint | `_lpct` | profile, comparables | "Strong late teams carry form forward" (`reports/m1b_preregistration.md`) |
| `value_age_hitters_lpct` | Hitter age weighted by batting runs above average (D90) | `_lpct` | profile, comparables | "Older value = decline" (pre-registration) |

M1b also tested `sequencing_luck` ("luck regresses"), `value_age_pitchers` (expected sign + only) and
`farm_strength` (expected sign − only). They are not used anywhere downstream, so their missing rationales don't
block anything.
