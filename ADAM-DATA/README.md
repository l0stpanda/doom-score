# Doom Score: MLB + NHL

**Doom** for a team-season = 100 minus the team's average league percentile over the **next three seasons**.
0 means top of the league all three years; 100 means bottom all three. We predict it at the end of each season
(MLB 2000–2026, NHL 2005-06 to 2025-26), one model per league, and show it in an interactive logo scatter.

## Headline results (out-of-sample backtest; details in `reports/RESULTS.md`)

| | MLB (test 2008–2023) | NHL (test 2013-14 to 2022-23) |
|---|---|---|
| Final model | **Current standings only** (B1) | Elastic net on 13 features |
| Rank correlation with actual doom (Spearman) | 0.41 | 0.61 (standings only: 0.52) |
| Mean absolute error (doom points) | 18.5 | 15.9 |
| 80% interval coverage / half-width | 82% / ±30 | 85% / ±26 |

- In **NHL**, the extra features clearly beat standings alone. Shot share (Corsi), scoring margin, the 3-season
  record, roster age, star concentration and draft capital all help.
- In **MLB**, no feature set beat standings beyond noise. That includes six pre-registered MLB features, the
  best being BaseRuns margin (future work).
- Doom is a rough ranking, not a precise forecast: intervals are wide.

## Open the dashboard

`dashboard/doom_scatter.html` is self-contained and needs no server. It is git-ignored because it embeds team logos
(trademarks), so build it once:

```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt    # Python 3.13
.venv/Scripts/python scripts/build_dashboard.py                          # ~3 min
```

The build starts **only from `data/mlb_nhl_model_slim.csv`**: it fits the models and writes `dashboard/data/`
(reproduced byte for byte), then downloads the logos once and builds the page. Screenshots are in
`reports/figures/`.

## Where things are

| Path | What |
|---|---|
| `docs/DOOM_SCORE.md` | The project in plain English: definition, data, modelling, results, limitations |
| `docs/FEATURES.md`, `docs/KEY_DECISIONS.md` | Features with rationale; the ~15 decisions that matter most |
| `docs/CROSS_LEAGUE_HANDOFF.md` | What other leagues' outputs must match to be comparable |
| `reports/RESULTS.md`, `reports/MODEL_CARD.md` | Consolidated results; model card |
| `data/` | The slim model table (one row per team-season) |
| `src/`, `dashboard/`, `scripts/` | Models + exports, viz scripts, the build command |

**Rebuilding from raw sources** (league APIs, Wikipedia, MoneyPuck → full 104-column table → slim table), the
M1/M2/M1b backtests, all phase reports and the full decision log (D01–D108) live in the tag
**`adam-full-pipeline`**: `git checkout adam-full-pipeline`.
