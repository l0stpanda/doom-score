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

## Doom Map and the dashboard page

`dashboard/index.html` puts three views on one page: the **Doom Map**, a **projected-standing scatter**, and a
**team panel**. They share the season, leagues, doom mode (predicted or actual) and selected team. The page is
self-contained and git-ignored (it embeds the logos). Build it after the steps above:

```
cd map && npm ci && cd ..                                        # Node 18+: mapshaper, d3, playwright-core
.venv/Scripts/pip install -r map/requirements.txt
.venv/Scripts/python map/build_map.py --fetch-logos               # add --shots for screenshots, checks and GIFs
```

**The map's only model input is per-team doom scores**: `map/inputs/scores/mlb_scores.csv` and `nhl_scores.csv`
(`docs/SCORES_FORMAT.md`; written from the model by `scripts/export_map_scores.py`). Team names by season, cities,
venues, regions and logos come from the map's team registry (`map/data/team_registry.csv`: MLB, NHL, NBA and NFL).

The build needs no raw boundary files: it uses the committed region shapes in `map/data/` and only re-assigns
team venues to regions (M49). Add `--no-renders` to skip the Edge check screenshots. Sources and methods are in
`docs/MAP_DECISIONS.md` (M06–M07 for the boundaries, 56 decisions in all).

**Rebuilding the regions** (only after changing `map/data_src/region_*.csv` or `regions.csv`):
`.venv/Scripts/python map/build_map.py --rebuild-regions`. This needs the raw boundary files in `data/raw/geo/`
(git-ignored), and stops with a list of any that are missing:
- **US counties** (Census cartographic boundary 2023, 1:5M): `.venv/Scripts/python scripts/fetch_geo.py` writes
  `data/raw/geo/us_county/cb_2023_us_county_5m.*`.
- **Canadian census divisions** (StatCan 2021, cartographic): a **manual** download. StatCan's zip returns HTTP 403
  to scripts, so they were taken from StatCan's ArcGIS REST service at 0.005° generalisation (293 divisions; the file
  names suggest three pages of 100 features at offsets 0, 100, 200), saved as GeoJSON `data/raw/geo/cd_0.geojson`, `cd_100.geojson` and
  `cd_200.geojson`, with at least the fields `CDUID`, `CDNAME` and `PRUID`. **The original query URL was not
  recorded**, so a re-download may not match the committed shapes exactly: check `git diff map/data/` afterwards.

**What the map shows.** For every point, the *local outlook*: a distance-weighted average of the doom of nearby
teams. Weights fall off with a Gaussian (σ = 100 mi), and each team counts once.
- **Color:** blue = bright future, gold = league average, crimson = doomed.
- **Grey:** no teams nearby. Color fades into grey where no team is within a few hundred miles.
- **Regions:** 23 fan regions (e.g. "Golden Horseshoe" = Toronto, Hamilton, Buffalo), built from counties and
  census divisions. Each has a card: verdict, average doom, how many teams it rests on, rank, best hope, biggest
  worry, quadrant counts, and trend.
- **Teams:** click a region (or zoom in) to see team badges. The ring color is the team's doom, and clicking a
  badge or a scatter point selects the team in both views and opens its panel.

**How to read it.**
- **Colors are relative.** They compare each team with its own league that season (z-scores), then put leagues
  side by side ("Colors compare teams within their league, then across leagues").
- **Regions with few teams swing to extremes.** The ranked list orders regions by a reliability-adjusted average
  (bar) and shows the raw average as a dot. Most differences between regions are within what chance alone would
  produce.
- **Predicted vs. actual.** Actual shows what really happened over the next three seasons. It exists only for
  seasons that are three years old (MLB through 2023, NHL through 2022) and is always labeled.
- **Team uncertainty is large.** Team cards show the model's risk band (chance of a doom ≥ 75 stretch) and the 80%
  range.

**New teams.** A team that played but has no prediction is *too new to score*. It gets a hollow, dashed neutral
ring, and it is left out of every average, ranking and the heat surface. Its card says why. In MLB and NHL today
this is zero teams: Vegas (2017) and Seattle (2021) have predictions from their first season.

**Known limitations.**
- Only MLB and NHL are scored. Mid-South, Ottawa–Montréal–Atlantic and the Prairies have no MLB team, so they are
  grey in the MLB-only seasons (2008–12 and 2026).
- A map season pairs MLB *Y* with NHL *Y*–*Y+1*.
- Standardizing makes MLB look as certain as NHL, but the MLB model is standings-only and less accurate (rank
  correlation 0.41 vs 0.61).
- Region boundaries are fan-identity judgment calls (`map/data_src/region_*.csv`).
- Hairline gaps (≤ 300 m) between US and Canadian boundary files are hidden at render time.
- The colorblind-safe ramp has a short olive stretch just below average.
- Teams with the same standing and similar doom overlap in the scatter. Use search to select them.
- "Full diagnostics" in the team panel is a placeholder.

**Adding a league.** One scores file: `python map/add_scores.py nba_scores.csv`. It validates the file, matches
team names (ids, names, former names, abbreviations), reports season coverage, copies it to `map/inputs/scores/`
and rebuilds. Only `league, season_start_year, franchise_id, doom_pred` are required; any optional column a league
leaves out is hidden for that league. The rebuild re-derives everything that depends on the set of teams (z-scores,
color scale, σ and opacity cutoffs, region shrinkage, verdict thresholds) and prints old vs new values;
`--freeze-params` keeps σ and the color range. NBA and NFL already have a registry (2000–2026); another league needs
registry rows first. Step by step: `docs/ADD_A_LEAGUE.md`; for groupmates: `docs/CROSS_LEAGUE_HANDOFF.md` §6.

## Where things are

| Path | What |
|---|---|
| `docs/DOOM_SCORE.md` | The project in plain English: definition, data, modelling, results, limitations |
| `docs/FEATURES.md`, `docs/KEY_DECISIONS.md` | Features with rationale; the ~15 decisions that matter most |
| `docs/CROSS_LEAGUE_HANDOFF.md` | What other leagues' outputs must match to be comparable |
| `reports/RESULTS.md`, `reports/MODEL_CARD.md` | Consolidated results; model card |
| `data/` | The slim model table (one row per team-season) |
| `src/`, `dashboard/`, `scripts/` | Models + exports, viz scripts, the build command |
| `map/` | Doom Map: `inputs/scores/` (the only model input), `data_src/` (hand-made tables: team locations, logos, aliases, regions, rules), `build/` (pipeline), `src/` (page code), `data/` (generated, incl. the team registry) |
| `docs/MAP_DECISIONS.md`, `docs/ADD_A_LEAGUE.md`, `docs/SCORES_FORMAT.md` | Map decision log (M01–M56); how to add a league; the scores format |
| `reports/map_phase*.md`, `reports/map_palette.png` | Map phase reports, palette validation; screenshots and GIFs in `reports/figures/map_*` |

**Rebuilding from raw sources** (league APIs, Wikipedia, MoneyPuck → full 104-column table → slim table), the
M1/M2/M1b backtests, all phase reports and the full decision log (D01–D108) live in the tag
**`adam-full-pipeline`**: `git checkout adam-full-pipeline`.
