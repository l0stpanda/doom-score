# Adding a league to the Doom Map

The map covers the four men's leagues (**MLB, NHL, NBA, NFL**; WNBA and PWHL are out of scope for now, M57). Each
already has a team registry, so adding its scores takes **one scores file**:

```
.venv/Scripts/python map/add_scores.py path/to/nba_scores.csv
```

The format and the script are described in `docs/SCORES_FORMAT.md`; the template is `map/inputs/scores_template.csv`.
Paths are relative to `ADAM-DATA/`. The script validates the file, resolves team names, reports season coverage,
copies it to `map/inputs/scores/` and rebuilds. It also re-derives σ, the opacity cutoffs and the colour-scale ends,
printing old and new values; `--freeze-params` keeps today's values instead. To remove a league, delete its file from
`map/inputs/scores/` and run `python map/build_map.py`. For NBA and NFL, also set `data_status=real` (and
`backtested`, `model_note`) in `map/inputs/leagues.csv`, or the page keeps labelling them as demo data.

What the rebuild re-derives from the set of teams (review the outputs; see M18-M20, M27, M28, M34 in
`docs/DECISIONS.md`):
- the z-scores (within league-season);
- the colour-scale ends;
- σ and the opacity cutoffs (same rule; check `reports/map_derived/sigma_diagnostics.csv`, because a denser set of
  teams may move σ);
- region counts, reliability shrinkage (EB constants) and verdict thresholds.

## A league with no registry yet

Data rows only, no code changes. Add these, then use `add_scores.py` as above.

### 1. League: `map/inputs/leagues.csv` and `map/data_src/leagues.csv`

`map/inputs/leagues.csv`: `league, display_name, season_convention (single-year / two-year), data_status (real /
demo), backtested (Y/N), model_note`. `map/data_src/leagues.csv`: `league, order, registry_first, registry_last`. The
registry range is the span of seasons the location table covers; a stint with a blank first or last season runs to
that end.

### 2. Locations: `map/data_src/team_location_stints.csv`

One row per stint (a span of seasons at one venue under one name):

`league, franchise_id, first_season, last_season, season_team_name, venue, city, metro, lat, lon, verified, source_url, note, secondary_source_url`

- `franchise_id` is stable through moves and renames (Seattle SuperSonics and Oklahoma City Thunder are one id).
- Temporary homes count where the team played most home games (M03).
- `metro` groups teams for clusters and diagnostics. Reuse an existing name where the metro already exists
  (e.g. `New York`, `Los Angeles`, `Bay Area`).
- `verified`: `official-city`, `official-arena` (arena named on an official page, city from the arena's location),
  `city-verified` (city from `secondary_source_url`) or `unverified`; `source_url` is the official page used.
- The build stops with a list if stints overlap, or a scored team-season has no location.

Regions don't change: they are geography, and every venue in the study area falls in one. The build assigns each venue
to a region with the committed shapes and writes the result to `map/data/team_registry.csv`.

### 3. Logos: `map/data_src/team_logos.csv`

One row per franchise: `league, franchise_id, team, logo_url` (current name and an official SVG logo URL).
`python map/build/fetch_logos.py` caches them (git-ignored). A missing or failed logo falls back to a monogram, and a
season name that no longer contains the current nickname (e.g. "Washington Redskins") always uses one. If the
automatic monogram is wrong, add `league, name, monogram, note` to `map/data_src/monogram_overrides.csv`.

### 4. Aliases (optional): `map/data_src/team_aliases.csv`

`league, alias, franchise_id, kind, note` for abbreviations and common names. Season names, current names, nicknames
and franchise ids are added automatically (`map/data/team_aliases.csv`).

## Changing the regions

Only needed after changing `map/data_src/region_*.csv` or `regions.csv`. Run
`.venv/Scripts/python map/build_map.py --rebuild-regions`. This needs the raw boundary files in `data/raw/geo/`
(git-ignored), and stops with a list of any that are missing:
- **US counties** (Census cartographic boundary 2023, 1:5M): `.venv/Scripts/python scripts/fetch_geo.py` writes
  `data/raw/geo/us_county/cb_2023_us_county_5m.*`.
- **Canadian census divisions** (StatCan 2021, cartographic): a **manual** download. StatCan's zip returns HTTP 403
  to scripts, so they were taken from StatCan's ArcGIS REST service at 0.005° generalisation (293 divisions; the file
  names suggest three pages of 100 features at offsets 0, 100, 200), saved as GeoJSON `data/raw/geo/cd_0.geojson`, `cd_100.geojson` and
  `cd_200.geojson`, with at least the fields `CDUID`, `CDNAME` and `PRUID`. **The original query URL was not
  recorded**, so a re-download may not match the committed shapes exactly: check `git diff map/data/` afterwards.
