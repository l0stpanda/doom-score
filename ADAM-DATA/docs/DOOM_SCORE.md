# The Doom Score (MLB + NHL)

## 1. What doom means

At the end of every season we ask: **how badly will this team do over the next three seasons?**

- A team's **standing** in a season is its league percentile by win % (NHL: points %): worst team 0, best 100.
- **Doom** = 100 − the team's average standing over the next three seasons. A team that finishes last three years
  running scores 100; a team that finishes first three years running scores 0.
- **Doom ≥ 75** means the team averaged bottom-quarter finishes over those three years. That happened to 18% of
  team-seasons in both leagues.
- The prediction is made when season t is over: MLB on Nov 15, NHL on Jun 15 of the following year. It may only
  use information available by then.

Because doom is built from percentiles, it is a **ranking within a league**, not a win total, and it compares
across leagues and eras.

## 2. Data

| | MLB | NHL |
|---|---|---|
| Seasons (rows) | 2000–2026 (810 team-seasons) | 2005-06 to 2025-26 (644) |
| Seasons with a known 3-year outcome | 2000–2023 (720) | 2005-06 to 2022-23 (548) |
| Out-of-sample test seasons | 2008–2023 | 2013-14 to 2022-23 |
| Live (current) predictions | 2024–2026 | 2023-24 to 2025-26 |

**Sources:**
- MLB Stats API: standings, draft, managers, player stints and birthdates, team batting and pitching totals,
  schedules, minor-league standings.
- NHL stats and web APIs: standings, skater/goalie stints, draft.
- Wikipedia: GM and coach tenures.
- MoneyPuck: NHL shot share (Corsi), 2008 onward.
- Cot's Baseball Contracts: MLB payroll.

Franchises keep one id through moves and renames and are shown under their current name. The team-season table
the models use is `data/mlb_nhl_model_slim.csv`. It is built from a 104-column table assembled from those sources,
kept in tag `adam-full-pipeline`.

## 3. How it was modelled

- **One model per league,** same code and settings, so the leagues can be compared.
- **Honest testing (walk-forward):** to predict season T, a model sees only seasons up to T−3. Those are the only
  outcomes fully known at the end of season T. Settings are tuned the same way inside the training seasons.
- **Baselines first:** every model must beat "current standing only" (B1), a straight line from this season's
  percentile to doom.
- **Candidates tried:** an elastic net (a regularized linear model); per-season "horizon" models; an Explainable
  Boosting Machine (smooth, non-linear); and gradient-boosted trees, only to check for feature interactions.
- **Choice rule:** pick the **simplest** model whose accuracy is within statistical noise of the best. Noise is
  measured by resampling blocks of three test seasons.
- **What the dashboard shows:**
  - the predicted doom, with an 80% range built from past prediction errors;
  - `p_doom75`, the chance doom ends ≥ 75, as a band: Low < 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50%;
  - a projected 3-year path;
  - the drivers: each feature's contribution in doom points, exact for a linear model.

## 4. Results

| | MLB | NHL |
|---|---|---|
| Final model | **Standings only (B1)** | **Elastic net, 13 features** |
| Spearman with actual doom (mean per test season) | 0.41 | 0.61 |
| Same for standings only | 0.41 | 0.52 |
| Gain over standings only | none beyond noise | +0.09 (95% interval +0.05 to +0.18) |
| Mean absolute error (doom points) | 18.5 | 15.9 |
| 80% interval: actual coverage / half-width | 82% / ±30 | 85% / ±26 |

- **NHL:** the features add real information beyond standings. The most stable ones (same sign in every test
  fold):
  - doom up: being out-shot (Corsi), a weak scoring margin, a weak 3-season record, an older roster;
  - doom down: relying on a few stars, and many early draft picks.

  Non-linear models and interactions did not help; the shapes are close to straight lines.
- **MLB = standings only.** Neither the general features nor six pre-registered MLB-specific features beat
  current standing beyond noise. Those six were second-half margin, BaseRuns margin, sequencing luck, hitter and
  pitcher age weighted by value, and farm-system record. The combined model gained +0.026 (−0.03 to +0.08).
  BaseRuns margin, MLB's closest equivalent to Corsi, was the strongest single feature and is future work. MLB
  dashboard drivers therefore show standing only, and the other MLB numbers appear as context.
- **Calibration:** `p_doom75` tracks observed rates (Brier 0.139 MLB, 0.144 NHL, vs 0.151 / 0.167 for the base
  rate alone). Of teams banded High, 32% (MLB) and 49% (NHL) actually ended at doom ≥ 75.
- Full tables: `reports/RESULTS.md`.

## 5. Limitations

- **Wide uncertainty.** Typical errors are 16–19 doom points; treat differences of a few points as noise.
- **Few independent test seasons:** 16 MLB and 10 NHL, and neighbouring seasons share future seasons.
- **Predictions are pulled toward the middle,** so the "Very high" band is almost empty (max `p_doom75` 0.47 in
  MLB; 2 NHL rows).
- **Missing pieces:**
  - No NHL payroll.
  - No independent MLB "underlying quality" measure (its Pythagorean win % duplicates run margin).
  - NHL Corsi starts in 2008: earlier seasons are filled, with a flag.
  - The earliest test seasons (MLB 2008–2011, NHL 2013–2016) have no range or band.
- **Data quality:** front-office dates come from Wikipedia and are imperfect. Short seasons (MLB 2020; NHL
  2012-13, 2019-20, 2020-21) are flagged, not down-weighted.
- **Live seasons** (MLB 2024–26, NHL 2023–25) come from models whose training outcomes overlap those seasons'
  futures, so they are not strictly out-of-sample.
