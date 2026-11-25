# Doom Score and Doom Map

**Doom** for a team-season = 100 minus the team's average league standing (percentile) over its **next three
seasons**: 0 = top of the league all three years, 100 = bottom. We predict it at the end of each season and show it
on the **Doom Map**: a map of the US and southern Canada coloured by how doomed nearby teams are, linked to a scatter
of each team's standing now against its projected standing, and a panel per team.

- **Models** (out-of-sample, `reports/RESULTS.md`): MLB = current standings only (rank correlation 0.41 with actual
  doom); NHL = elastic net on 13 features (0.61). Wide uncertainty: doom is a rough ranking, not a forecast.
- **Leagues:** MLB and NHL have real scores. NBA and NFL have a team registry and can be tried with clearly labelled
  **fake** demo scores until real ones arrive.

**Live demo:** (link to come)

## Run it locally

From `ADAM-DATA/`, with Python 3.13 and Node 18+ (on macOS/Linux use `.venv/bin/` instead of `.venv/Scripts/`):

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r map/requirements.txt
cd map && npm ci && cd ..
.venv/Scripts/python map/build_map.py --fetch-logos     # ~1 min; downloads team logos once (git-ignored)
```

Open `dashboard/index.html` in a browser (no server needed).

**Try four leagues (demo):** `.venv/Scripts/python map/demo.py` adds fake NBA/NFL scores, rebuilds and opens the page;
`.venv/Scripts/python map/demo.py --off` removes them and checks every file is back as it was. Things to try, with what
should happen at each step: `docs/DEMO_GUIDE.md`. Demo data is labelled on the page and can't be committed.

## Add a league's scores

Send or drop in one CSV per league (`league, season_start_year, franchise_id, doom_pred` required; more optional),
then:

```
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv
```

It validates the file, matches team names, reports coverage, copies it to `map/inputs/scores/` and rebuilds.
Format: `docs/SCORES_FORMAT.md` (template `map/inputs/scores_template.csv`). For groupmates:
`docs/CROSS_LEAGUE_HANDOFF.md` §6. Details and new leagues: `docs/ADD_A_LEAGUE.md`.

## Model side (MLB, NHL)

```
.venv/Scripts/python scripts/build_dashboard.py      # ~3 min: refit from data/mlb_nhl_model_slim.csv -> dashboard/data/
.venv/Scripts/python src/evaluate.py                 # headline backtest metrics -> reports/results_summary.csv
.venv/Scripts/python scripts/export_map_scores.py    # predictions -> map/inputs/scores/mlb_scores.csv, nhl_scores.csv
```

## Docs

`docs/DOOM_SCORE.md` (the project in plain English), `docs/FEATURES.md`, `docs/DECISIONS.md` (the 30 decisions that
shaped it; full logs in tags `adam-full-pipeline` and `adam-map-full`), `reports/RESULTS.md`, `reports/MODEL_CARD.md`.
