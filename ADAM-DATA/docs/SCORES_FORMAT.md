# Doom Map scores format

The Doom Map takes **one input from a league's model: a CSV of per-team doom scores**. Everything else (team names
by season, cities, venues, regions, logos) comes from the map's team registry. Paths are relative to `ADAM-DATA/`.

- Score files live in `map/inputs/scores/`, one per league by convention (`mlb_scores.csv`, `nhl_scores.csv`, ...).
  The map reads every `*.csv` there and nothing else from the model side (M50).
- Add or replace a league with `python map/add_scores.py <file>` (below). Remove one by deleting its file and running
  `python map/build_map.py`.
- Start from `map/inputs/scores_template.csv` (header plus 3 example rows). The example rows' `franchise_id`s start
  with `example_`, which validation rejects: replace them with your rows.
- Leagues must be listed in `map/inputs/leagues.csv` (MLB, NHL, NBA, NFL for now; M57), which also says whether a
  league's scores are real or demo, and whether they were backtested.
- Files named `FAKE_*` in that folder are git-ignored, for tests. Files named `DEMO_*` are fake demo scores
  (`map/demo.py`, `docs/DEMO_GUIDE.md`): git-ignored, read only by a demo build, and labelled DEMO on the page.

## Columns

One row per team-season. A team-season may appear only once across all files.

### Required

| Column | Type | Meaning |
|---|---|---|
| `league` | text | League code, e.g. `NBA`. Must be in `map/inputs/leagues.csv` and have a team registry (MLB, NHL, NBA and NFL do). |
| `season_start_year` | whole year | Calendar year the season starts (NBA 2024-25 → `2024`). Must be inside the league's registry (NBA/NFL 2000–2026). |
| `franchise_id` | text | The franchise. Canonical ids are lowercase with hyphens (`raiders`, `philadelphia-sixers`), but `add_scores.py` also accepts names, former names, nicknames and abbreviations (see "Team names"). |
| `doom_pred` | number 0–100 | Predicted doom: 100 minus the team's mean league percentile over its next three seasons (`docs/CROSS_LEAGUE_HANDOFF.md` §1). |

With only these four columns the map works fully: colour, region averages, rankings, region cards and team cards.

### Optional

Each optional column is per league: if a league's file leaves it out (or leaves it empty on every row), everything
that depends on it is hidden for that league only (M51). A blank cell in a column the league does provide shows as
"not available" for that team.

| Column | Type | Shown as | Hidden without it |
|---|---|---|---|
| `doom_lo80`, `doom_hi80` | numbers 0–100 (both or neither) | "Likely range (80%)" in the team panel | the range row |
| `band` | `Low`, `Moderate`, `High`, `Very high` | "High risk of a doomed stretch" chip, hover card | the chip and the band text |
| `p_doom75` | probability 0–1 | "(34% chance of doom ≥ 75)" on the chip | the percentage |
| `win_pct` | 0–1 | "This season: 63.6% wins" | that part of the row |
| `win_pct_percentile` | 0–100 | "93rd percentile"; scatter x-axis; quadrant | the scatter points, quadrant row and the league's quadrant counts in region cards |
| `record` | text, e.g. `103-59` or `40-30-12` | "(103-59)" | that part of the row |
| `driver_up_1..3`, `driver_down_1..3` | text, e.g. `Weak current standing (+24.3)` | "What moves this prediction" | the section |
| `driver_note` | text | a note under the drivers | the note |
| `proj_pct_t1..t3` | numbers 0–100 | "Projected finish: 71st, 66th, 57th percentile" | the row |
| `actual_doom` | number 0–100 | Predicted/Actual toggle, actual line in the team panel, dots on the trend | the toggle (when no selected league has it) and the actual line |

Other columns are ignored with a warning. `driver_note` is the one addition to the agreed list: the MLB scores use
it to explain why MLB has a single driver.

## Team names

`add_scores.py` resolves each `franchise_id` value within its league, in this order:

1. that season's registry entry: the franchise id, the season's team name ("Seattle SuperSonics" in 2005), the current
   name, the nickname, or city + nickname. A nickname used by two franchises is resolved by season
   (NBA "Hornets" → `charlotte-hornets` in 2016, `new-orleans-pelicans` in 2010);
2. the aliases table `map/data/team_aliases.csv`: abbreviations (`OAK`, `SEA`, `BKN`), common names (`Sixers`,
   `Niners`) and former names. Hand-made entries are in `map/data_src/team_aliases.csv`.

Matching ignores case, accents, punctuation and spacing. Any name that does not resolve is listed with its seasons,
and nothing is copied. Add it to `map/data_src/team_aliases.csv` or fix the file. A name that resolves to a franchise
with no location that season (e.g. the Texans before 2002) also stops the run.

## Adding scores

```
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv                 # validate, resolve, copy, rebuild
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv --check         # validate and resolve only
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv --freeze-params # keep sigma and the colour range
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv --replace       # overwrite a file of the same name
```

The script validates columns, types and ranges (line numbers on every error), stops on seasons outside the league's
registry (naming the league and seasons), resolves team names, reports season coverage against the registry, and copies the file with canonical ids into `map/inputs/scores/`. It then rebuilds the
map. A team in the registry with no score that season shows as "too new to score".

Adding a league changes the set of teams, so the map re-derives σ (the blending distance), the opacity cutoffs and
the colour-scale ends, and prints old and new values. `--freeze-params` keeps today's values instead, by writing
`map/data_src/frozen_params.json`. Delete that file, or run `add_scores.py` without the flag, to re-derive (M54).

When real scores replace a demo league, set its row in `map/inputs/leagues.csv` to `data_status=real` (with
`backtested` and `model_note`); until then the map labels it as demo (M59). `add_scores.py` refuses `DEMO_*` files
unless given `--demo`.

## Exporting MLB and NHL

`python scripts/export_map_scores.py` writes `map/inputs/scores/mlb_scores.csv` and `nhl_scores.csv` from the
model's `dashboard/data/doom_predictions.csv`. Run it whenever the predictions change, then `python map/build_map.py`.
