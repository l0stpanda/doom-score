# Doom Score modeling + first visualization — run ONE phase at a time

How to use: tell Claude Code **"Read this file and do Phase M1 only."** Each phase ends with a short report (`reports/<phase>.md`, at most one page), new rows in `DECISIONS.md`, a commit, a push, and a **stop**. I review each report before starting the next phase.

---

## Ground rules (every phase)

**Data:** `data/processed/mlb_nhl_model_slim.csv`, one row per team-season. Read `SLIM_SELECTION.md`, `FEATURE_CROSSWALK.md` and `DATA_DICTIONARY.md` first.

**Targets** (`y_*` columns are labels and are never used as features):
- `y_doom_3yr`: 0–100, higher = more doomed. This is the regression target.
- `y_doomed_bottom25`: 1 if the team is doomed. This is the classification target.
- `y_pct_t1`, `y_pct_t2`, `y_pct_t3`: the team's percentile in each of the next three seasons. These are used for the per-season (horizon) models.

**Features (slim set):** `win_pct_percentile`, `win_pct_trailing_3_seasons_lpct`, `margin_per_game_lpct`, `luck_lpct`, `underlying_quality_lpct`, `roster_age_weighted_lpct`, `star_concentration_lpct`, `draft_capital_lpct`, `gm_tenure_lpct`, `coach_tenure_lpct`, `spending_lpct`, `personnel_lead_vacant`, `short_season`, `seasons_of_history`.
- Some features don't exist in a league: MLB `underlying_quality` (all missing) and NHL `spending` (all missing). Leave them out of that league's model and log it.

**One model per league.** MLB and NHL are fitted separately, with identical code and settings, so their results can be compared.

**Leakage rules:**
1. **Walk-forward evaluation with a 3-season gap.** To predict test season T, train only on seasons up to T−3, because those are the only labels fully known by the end of season T. Add an assertion that fails if a training row has a season later than T−3.
2. **Fit all preprocessing on the training seasons only:** filling in missing values, missing-value indicators, and scaling. Use an sklearn `Pipeline` so this happens automatically.
3. **Tune hyperparameters with a time-based split inside the training seasons,** using the same 3-season gap. Never tune on the test season.
4. **Assert that no `y_*` column is in X.**

**Missing values:** fill with the training median, plus a missing indicator for any feature that is missing in more than 1% of rows (e.g. `gm_tenure`). NHL `underlying_quality` is missing for 2005–07. The default is to fill it and add an indicator; log this, and also report results for NHL trained on 2008 onward only.

**Test seasons:**
- MLB: the first season that has at least 6 training seasons, through 2023.
- NHL: the same rule, through 2022.
- Report the exact test range in the phase report.

---

## Phase M1: backtest framework, baselines, main models

1. Build a reusable walk-forward backtest function: `src/model/backtest.py`.
2. **Baselines**, which every model must be compared to:
   - B0: `doom = 100 − win_pct_percentile`, with no fitting.
   - B1: linear regression on `win_pct_percentile` only.
   - B2: B1 plus `win_pct_trailing_3_seasons_lpct`.
3. **Main models**, per league:
   - Elastic net regression on `y_doom_3yr` (`ElasticNetCV`-style tuning over alpha and l1_ratio, with the time-based inner split).
   - L1 logistic regression on `y_doomed_bottom25`.
4. **Metrics,** computed on out-of-sample predictions:
   - Spearman correlation: the average of the per-season values, plus the pooled value.
   - Mean absolute error (MAE) in percentile points.
   - R².
   - Classification: AUC and Brier score.
   - **Top-5 hit rate:** of each season's 5 teams predicted most doomed, how many actually ended up in the bottom quarter.
   - For each metric, show the difference from B1, with a 95% interval from a bootstrap over test seasons.
5. **Coefficient stability:** the standardized coefficients in every walk-forward fold. Report each feature's median and range, and how often its sign flips.
6. **Report:** a metrics table (models × leagues), the coefficient table, and a plain-English paragraph on whether the features beat current standing alone. If they barely do, say so plainly; that's a valid finding.

Commit, push. **Stop.**

---

## Phase M2: challengers and final model choice

Run each of these through the same backtest:
1. **Explainable Boosting Machine** (`interpret` package) on `y_doom_3yr`. If the package isn't available, use a GAM (`pygam`) and log it.
2. **Horizon models:** separate elastic nets for `y_pct_t1`, `y_pct_t2` and `y_pct_t3`. Compute `doom = 100 − mean of the three predictions` and compare it to the direct elastic net.
3. **LightGBM** with shallow trees and strong regularization, as a check for combined effects (interactions) only.
4. **NHL sensitivity:** swap `underlying_quality` from Corsi to `xgoals_pct` (taken from the full table). Report the difference only, as a diagnostic; it is not a candidate for the final model, because of the soft leakage.
5. **Prediction intervals:** split conformal intervals for the chosen model, built from the walk-forward errors. Report how often the actual value falls inside the 80% interval.

**Choosing the final model:** pick the simplest model whose Spearman correlation and MAE are within the bootstrap noise of the best model. Prefer models whose results can be explained per team. Also decide whether the dashboard's 3-year path comes from the horizon models. Log the reasoning in `DECISIONS.md`.

**Report:** a comparison table, the chosen model and why, and EBM shape plots for the top 4 features saved as PNGs.

Commit, push. **Stop.**

---

## Phase M3: export everything the dashboard needs

1. **Backtest predictions:** out-of-sample predictions for every test season.
2. **Live predictions:** refit the chosen model on all labeled rows in each league, then predict every unlabeled season: MLB 2024–2026 and NHL 2023–2025. The latest season in each league is the live "current" view.
3. **Driver breakdown:** split each prediction into per-feature contributions in doom points (for linear models, coefficient × the standardized feature's deviation from the training mean; for EBM, its local explanations). Map each feature to a plain-English name, e.g. `luck_lpct` → "Won more games than their scoring margin suggests". Keep the top 3 drivers that push doom up and the top 3 that push it down.
4. **Write these files to `dashboard/data/`:**
   - `doom_predictions.csv`, one row per team-season, with columns:
     - `league, season_start_year, franchise_id, team, wins, losses, ot_losses, games, win_pct, win_pct_percentile`
     - `doom_pred, doom_lo80, doom_hi80, p_doomed`
     - `proj_pct_t1, proj_pct_t2, proj_pct_t3`
     - `pred_type` (backtest or live)
     - `actual_doom` and `actual_pct_t1..t3` (where they exist)
     - `driver_up_1..3, driver_down_1..3` (as text like "Aging roster (+6.2)")
   - `doom_drivers_long.csv`: every contribution, one row per team-season-feature.
   - `team_meta.csv`: `league, franchise_id, team, logo_url, team_id`.
5. **`MODEL_CARD.md`:** what the model predicts, its training data, backtest performance compared to the baselines, known limitations (short seasons, overlapping labels, NHL with no spending data, MLB with no underlying-quality measure), and how to read the score.

Commit, push. **Stop.**

---

## Phase V1: scatter plot prototype with team logos

Build `dashboard/doom_scatter.html` with Plotly (Python), as a **self-contained** file that opens in any browser with no server. Use only the files in `dashboard/data/`.

**Chart:**
- One point per team, drawn as its **logo**, about 28–36 px.
- x = current win %; y = predicted doom (0–100, higher = more doomed).
- Controls:
  - **League** dropdown: MLB, NHL, All.
    - In single-league views, x = raw `win_pct`. The NHL axis is labeled "Points %".
    - In the "All" view, x switches to `win_pct_percentile`, labeled "Current standing (league percentile)", because raw win % isn't comparable across leagues.
  - **Season** slider, defaulting to the latest season. Past seasons show backtest predictions.
- Quadrant guides: a dashed line at x = league median (or 50 in percentile view) and at y = 50, with light corner labels: "Contender" (good now, low doom), "Cliff ahead" (good now, high doom), "Rising" (bad now, low doom), "Stuck" (bad now, high doom).
- **Hover** shows: team, record, win %, doom with its 80% interval, and the top 2 drivers up and down. In past seasons, also show the actual doom.
- Next to the chart: "Most doomed" and "Least doomed" top-5 lists for the selected league and season.
- Accessible design: the logos carry team identity. Add a light outline circle behind each logo so light-colored logos stay visible, a clear title and subtitle that define doom in one sentence, and axis labels with units.

**Logos:**
- MLB: `https://www.mlbstatic.com/team-logos/{team_id}.svg` (MLB Stats API team IDs).
- NHL: the `teamLogo` URL in the NHL API standings/team data (`assets.nhle.com/logos/nhl/svg/...`).
- Use each franchise's **current** logo for every season, consistent with the `team` naming.
- Download once to `dashboard/assets/logos/` and convert SVG to PNG if Plotly needs it. Embed them in the HTML as base64 so the file is self-contained.
- Add `dashboard/assets/logos/` to `.gitignore` and fetch them with `src/viz/fetch_logos.py`, because team logos are trademarks. They're fine for a class prototype, but don't redistribute them in the repo.
- If a logo fails to load, fall back to a labeled dot and list the failures in the report.

**Report:** a screenshot (PNG) of the default view and the "All leagues" view, plus notes on any overlap or readability problems. Crowding is likely in the "All" view; suggest fixes such as a smaller logo size or jitter.

Commit, push. **Stop.**
