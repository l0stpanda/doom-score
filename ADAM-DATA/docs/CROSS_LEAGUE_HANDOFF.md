# Cross-league handoff (MLB + NHL → all leagues)

What a groupmate's league output needs to match so all leagues can be compared on one scale. MLB/NHL reference
files: `dashboard/data/doom_predictions.csv` and `reports/RESULTS.md` (section 4). D-numbers: `docs/DECISIONS.md`
(full log in tag `adam-full-pipeline`).

## 1. Outcome (must be identical)

- Percentile within league-season: `(average rank of win_pct − 1)/(n − 1) × 100`, worst 0, best 100. Ties get the
  average rank (D10). Use `win_pct = (W + 0.5·T)/G`, with the league's own tie/OT convention stated (NHL: OT/SO
  losses count as half, so it equals points %; D07).
- `doom = 100 − mean(percentile in t+1, t+2, t+3)` over the franchise's next three **played** seasons (D11). NaN
  unless all three exist. Doom ≥ 75 = bottom quarter on average.
- Prediction moment = end of season t's playoffs, before the next draft (MLB Nov 15 t; NHL Jun 15 t+1; D29).
  Features must be knowable by then.
- Franchise continuity: one `franchise_id` per club through moves and renames; `team` = current name (D03–D06).

Because doom is a percentile, leagues of different sizes are comparable in level. A one-place move is still a
bigger percentile step in a smaller league (step = 100/(n − 1)).

## 2. Standardization

- Features: within-league-season percentiles (`_lpct`, same formula as `win_pct_percentile`), never raw league units
  (D59).
- Models: fitted **separately per league** with identical code and settings, then z-scored inside each fold on
  training seasons only (D66, D67).
- Evaluation: walk-forward, test season T trained on seasons ≤ T−3 (labels known by the end of T; D64). Test
  seasons start at the first T with ≥ 6 training seasons. Δ intervals use a moving-block bootstrap over test
  seasons, block 3 (D72).
- Baselines to report: B0 = 100 − current percentile; B1 = OLS on current percentile; B2 = B1 + 3-season record
  (D68). The final model is the simplest whose Spearman and MAE are within noise of the best (D76).

## 3. `doom_predictions.csv` schema (one row per team-season; backtest + live)

| Column | Type | Meaning |
|---|---|---|
| `league` | str | League code (`MLB`, `NHL`, …) |
| `season_start_year` | int | Calendar year season t starts (NHL 2017 = 2017-18) |
| `franchise_id` | str | Stable lowercase-hyphenated franchise key |
| `team` | str | Current franchise name |
| `wins`, `losses`, `games` | int | Season-t record (NHL `losses` = regulation losses) |
| `ot_losses` | float | NHL OT/SO losses; NaN where the league has none |
| `win_pct` | float | Season-t win % (NHL = points %) |
| `win_pct_percentile` | float | Current standing, 0–100 |
| `doom_pred` | float | Predicted doom, 0–100 scale |
| `doom_lo80`, `doom_hi80` | float | 80% split-conformal interval from walk-forward residuals of seasons ≤ T−3, clipped to 0–100 (D80, D96) |
| `interval_available` | int 0/1 | 1 if the interval and `p_doom75` exist (needs ≥ 2 calibration seasons; D101) |
| `p_doom75` | float | P(actual doom ≥ 75 \| predicted doom): share of the same residuals ≥ 75 − doom_pred (D99) |
| `doom_band` | str | Band on `p_doom75`: Low < 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50%, "Not available" (D100) |
| `p_doomed` | float | Direct classifier probability of doom ≥ 75 (diagnostic; D95) |
| `b1_pred` | float | Standing-only (B1) prediction on the same training rows (D102) |
| `doom_vs_standing` | float | `doom_pred − b1_pred`: what the non-standing features add (0 for MLB by construction) |
| `proj_pct_t1..t3` | float | Projected percentile in t+1..t+3 from horizon models (gap = horizon), shifted so 100 − mean = `doom_pred`, clipped 0–100 (D87, D88) |
| `path_clipped` | bool | Projection was clipped, so the average is not exact |
| `pred_type` | str | `backtest` (out-of-sample) or `live` |
| `actual_doom`, `actual_pct_t1..t3` | float | Realised outcomes where known |
| `driver_up_1..3`, `driver_down_1..3` | str | Top contributions as "Phrase (+x.x)" doom points (D94) |
| `driver_note` | str | Plain-English note (MLB: standing-only model) |

Companion files: `doom_drivers_long.csv` (league, season, franchise, pred_type, feature, feature_label, z,
contribution), `team_profile.csv` (+ `team_profile_columns.csv`), `comparables.csv`, `team_meta.csv` (logo URL,
source team id).

## 4. Calibration and Brier reporting (match `reports/RESULTS.md`, section 4)

Computed on **backtest rows with `interval_available = 1` and a known label**, per league:

- **Calibration table:** rows ranked by `p_doom75` and cut into 10 equal-count deciles. Columns: `league, decile,
  n, p_min, p_max, mean_predicted, observed_rate` (observed = share with actual doom ≥ 75). File:
  printed by `src/export_dashboard.py`.
- **Brier:** for `p_doom75`, for `p_doomed`, and for a base-rate-only forecast, with n and the base rate. Current:
  MLB 0.139 / 0.140 / 0.151 (n = 360, base rate 18.6%); NHL 0.144 / 0.143 / 0.167 (n = 188, 21.3%).
- **Band check:** per league and band, `rows, labelled, share_actual_ge75` (also printed by `src/export_dashboard.py`).

## 5. Open questions

1. **MLB standings-only (B1) vs. adding features** chosen by the same selection procedure as NHL. The M1b
   combined model was +0.026 [−0.032, +0.077] Spearman vs B1, which is not beyond noise. BaseRuns margin alone
   passed but was not pre-registered (D86).
2. **Empty "Very high" band.** Max `p_doom75` is 0.47 in MLB; only 2 NHL rows reach ≥ 0.50 (neither ended ≥ 75).
   Switch to three bands?
3. **Low-decile underprediction** of `p_doom75` (e.g. NHL decile 4: 6% predicted vs 17% observed).
4. **Loose comparables:** median distance 17 percentile points (D103).
5. **Logo overlap in the All-leagues view** of the older Plotly scatter (`dashboard/doom_scatter.html`; 62+ logos,
   MLB sits on one line). More leagues will make it worse; the Doom Map's scatter uses small shapes instead.
6. Teammate core-schema check: the NBA/NFL file is on the teammate's branch (`origin/leo`). Its franchise ids are
   used by the map registry and its standings by the demo scores (snapshot in `map/inputs/demo_standings_nba_nfl.csv`), but its percentile formula has not been
   cross-checked against D10 (D15).

## 6. Send me your scores (Doom Map)

The map needs only one file from you: **one CSV of doom scores for your league**, in the format of
`docs/SCORES_FORMAT.md`. Start from `map/inputs/scores_template.csv` (replace its three `example_` rows).

- **Required:** `league`, `season_start_year`, `franchise_id`, `doom_pred` (0–100, defined as in §1). Those four
  columns are enough for the map.
- **Optional, if you have them:** `doom_lo80`/`doom_hi80`, `band`, `p_doom75`, `win_pct`, `win_pct_percentile`,
  `record`, `driver_up_1..3`/`driver_down_1..3`, `proj_pct_t1..t3`, `actual_doom`. Anything you leave out is hidden
  for your league. Nothing else breaks.
- **Team names:** use the `franchise_id` values from your own file (`raiders`, `philadelphia-sixers`, ...); the
  map's NBA and NFL registry uses the same ids. Abbreviations and season names (`OAK`, `Seattle SuperSonics`) also
  work.
- **Seasons:** any range within 2000–2026. You don't need city, venue, region, logo or performance data: the map
  has those.

I run `python map/add_scores.py your_file.csv`. It lists any team name it can't match before anything changes.
