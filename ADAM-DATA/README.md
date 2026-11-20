# Doom Viz: MLB + NHL (ADAM-DATA)

Predicts each team's **doom**: 100 minus its average league percentile over the next three seasons
(0 = top of the league all three years, 100 = bottom all three). One row per team-season. MLB 2000–2026 and
NHL 2005-06 to 2025-26. Fitted per league with a walk-forward backtest, then shown as an interactive logo scatter.
This folder is my part; `BEN-DATA/` and `LEO-DATA/` belong to groupmates.

## Layout

| Path | What |
|---|---|
| `src/` | Raw → full-table pipeline (`fetch_*`, `build_phase1-4`, `build_crosswalk`), feature tables (`build_slim`, `m1b_*`), shared helpers (`common.py`) |
| `src/model/` | Backtest framework and phases M1, M2, M1b, M3 (`run_m3.py` writes the dashboard exports) |
| `src/viz/` | Logos, comparables, scatter page |
| `scripts/build_all.py` | The one build command |
| `data/processed/` | `mlb_nhl_team_seasons.csv` (frozen full table, 104 cols), `mlb_nhl_model_slim.csv` (model inputs), `mlb_m1b_features.csv` |
| `data/manual/` | Hand-maintained inputs (CBT thresholds, cap ceilings, templates) |
| `dashboard/data/` | Exports: `doom_predictions.csv`, drivers, team profile, comparables, team meta |
| `reports/` | Phase results (`m1`, `m2`, `m1b`, `m3`, `v1`), `model_card.md`, `slim_selection.md` |
| `docs/` | `PROJECT_LOG.md`, `DATA.md`, `FEATURES.md`, `CROSS_LEAGUE_HANDOFF.md`, `decisions_full.md` (D01–D110) |
| `archive/` | Superseded docs, prompts and data-build logs (see `archive/README.md`) |

## Build and open the viz

```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Python 3.13
.venv/Scripts/python scripts/build_all.py            # features → models → exports → viz (~20 min)
.venv/Scripts/python scripts/build_all.py --skip-backtests   # reuse committed M1/M2/M1b results (~3 min)
```

Then open `dashboard/doom_scatter.html` in a browser (self-contained, no server). It and
`dashboard/assets/logos/` are git-ignored because they contain team logos (trademarks). `--clean` deletes all
regenerable outputs first. `--from-raw` also rebuilds the full table from the APIs (slow, network).

Start with `docs/CROSS_LEAGUE_HANDOFF.md` for the next phase.
