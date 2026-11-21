# Features

All features are measured at the end of season t, before the prediction moment (MLB Nov 15; NHL Jun 15 of t+1).
D-numbers: `docs/KEY_DECISIONS.md`.

**MLB uses current standing only.** Its model (B1) is a linear regression on `win_pct_percentile`. The other
features exist for MLB but did not beat standings beyond noise in any test (D76, D86), so they appear only as
context in the dashboard. **NHL uses all 13 model features** below in an elastic net.

**How features are standardized** (two steps):
1. Within each league-season, each feature becomes a percentile, `(average rank − 1)/(n − 1) × 100`
   (the `_lpct` columns; same formula as `win_pct_percentile`, D59). This makes leagues and eras comparable.
   Flags and counts stay raw.
2. Inside each model fit: missing values get the training median plus a 0/1 "missing" indicator (when > 1% of
   training rows are missing). Then every input is z-scored using the training seasons only.

## Model features (NHL; MLB uses only the first)

| Feature | Plain English | Technical definition | Rationale |
|---|---|---|---|
| `win_pct_percentile` | Where the team finished this season | Percentile of win % (NHL: points %) within league-season | Where the team stands now; quality persists but drifts toward the middle, so this is the strongest single predictor |
| `win_pct_trailing_3_seasons_lpct` | Its record over the last three seasons | Percentile of mean win % over seasons t−2..t | Separates a one-year fluke from a sustained level |
| `margin_per_game_lpct` | How much it outscored opponents | Percentile of (goals for − against) / games | Scoring margin measures quality better than wins, which include close-game randomness |
| `luck_lpct` | Won more or fewer games than its margin suggests | Percentile of win % − Pythagorean win % (exponent 2.0) | Teams that win more than their margin implies tend to fall back; luck doesn't carry over |
| `underlying_quality_lpct` | Controls the puck (shot attempts) | Percentile of Corsi % (shot-attempt share, all situations; MoneyPuck, 2008+) | Shot-attempt share reflects puck control, which is steadier year to year than goals |
| `roster_age_weighted_lpct` | How old the roster is | Percentile of player age (Feb 1 of t+1) weighted by time on ice | Older rosters face decline; weighted by playing time so it reflects who actually plays |
| `star_concentration_lpct` | How much it relies on a few stars | Percentile of the top-3 skaters' share of team points | Teams that depend on a few players are fragile to one departure, injury or decline |
| `draft_capital_lpct` | Early draft picks this year | Percentile of picks in rounds 1–2 of the June draft before season t | High picks are the main source of incoming young talent, and also signal a rebuild |
| `gm_tenure_lpct` | How long the GM has been in charge | Percentile of GM tenure (years) at the prediction moment; NaN if vacant | Front-office stability vs. staleness; new GMs often overhaul rosters |
| `coach_tenure_lpct` | How long the head coach has been in charge | Percentile of consecutive seasons as season-end coach (mid-season start = 0.5) | The same logic for the bench |
| `personnel_lead_vacant` | No GM in place | 1 if the source shows no one held the GM title at the prediction moment | Separates a real vacancy (e.g. a president-led front office) from missing data |
| `short_season` | Shortened season | 1 for NHL 2012-13, 2019-20, 2020-21 (MLB 2020) | Shortened seasons give noisier records, so the model can discount them |
| `seasons_of_history` | How much history the team has | Number of franchise seasons available up to t | Tells the model how much history backs the trailing features (expansion teams) |

Not used: NHL `spending_lpct` (no NHL payroll data) and MLB `underlying_quality_lpct` (Pythagorean win %, a
near-duplicate of run margin, D63).

## MLB context features (shown in the dashboard's team profile; not model inputs)

| Feature | Plain English | Technical definition | Rationale |
|---|---|---|---|
| `spending_lpct` | Payroll compared with the league | Percentile of Opening Day payroll / league-season mean (Cot's Contracts) | Payroll is a commonly cited driver of sustained MLB success; tested, and shown as context |
| `baserun_margin_lpct` | Run margin the team "should" have had | Percentile of (BaseRuns scored − allowed) per game, from hits, walks and home runs | Run margin based on underlying hits, walks and home runs, with timing luck removed: MLB's closest equivalent to Corsi. The most promising MLB feature; listed as future work (D86) |
| `second_half_margin_lpct` | How it played late in the season | Percentile of run margin per game after the team's midpoint | Strong late-season teams tend to carry that form forward (pre-registered, M1b) |
| `value_age_hitters_lpct` | Age of its most productive hitters | Percentile of hitter age weighted by batting runs above average | Older productive hitters are more likely to decline (pre-registered, M1b) |

The other MLB versions of the concepts above (3-season record, margin, luck, roster age, star concentration,
draft capital, GM and coach tenure) are also shown as context, for the same reasons as in NHL.
