# Adding a league to the Doom Map

Adding NBA, NFL or any other league needs **data rows only, no code changes**. Paths are relative to `ADAM-DATA/`.

## 1. Predictions: `dashboard/data/doom_predictions.csv`

Append one row per team-season in the schema of `docs/CROSS_LEAGUE_HANDOFF.md` §3. The map reads these columns:

| Column | Used for |
|---|---|
| `league` | League toggle, standardisation group (any short code, e.g. `NBA`) |
| `season_start_year` | Season control (calendar year the season starts) |
| `franchise_id` | Join key with the location table and `team_meta.csv` (stable through moves) |
| `team` | Current name; its last word is the nickname used by the logo rule |
| `doom_pred` | Colour, averages and ranks (via z within league-season) |
| `doom_band`, `doom_lo80`, `doom_hi80`, `p_doom75` | Team card |
| `win_pct`, `win_pct_percentile` | Card and quadrant (x of the scatter) |
| `pred_type`, `actual_doom` | Predicted vs actual toggle (actual only where `actual_doom` exists) |

A team-season that should appear on the map but has no prediction (an expansion team) is shown as **too new to
score**: give it a location (step 3) and no prediction row.

## 2. Logos: `dashboard/data/team_meta.csv`

One row per franchise: `league, franchise_id, team, logo_url, team_id`. Logos are cached (git-ignored) by
`dashboard/fetch_logos.py`; a missing or failed logo falls back to a monogram. If the automatic monogram is wrong,
add `league, name, monogram, note` to `map/data_src/monogram_overrides.csv`.

## 3. Locations: `map/data_src/team_location_stints.csv`

One row per stint (a span of seasons at one venue under one name):

`league, franchise_id, first_season, last_season, season_team_name, venue, city, metro, lat, lon, verified, source_url, note`

- Blank `first_season` / `last_season` = from the league's first / to its last prediction season.
- `metro` groups teams for clusters and diagnostics. Reuse an existing name where the metro already exists
  (e.g. `New York`, `Los Angeles`).
- `verified`: `official-city`, `official-arena` or `unverified`; `source_url` is the official page used.
- The build stops with a list if any predicted team-season has no location, or two stints overlap.

Regions don't change: they are geography, and every venue in the study area falls in one.

## 4. Rebuild

```
.venv/Scripts/python map/build_map.py --fetch-logos
```

This re-derives everything that depends on the set of teams:
- the z-scores;
- the colour-scale ends;
- σ and the opacity cutoffs (same rule; check `reports/map_derived/sigma_diagnostics.csv`, because a denser set of
  teams may move σ);
- region counts.

Review the decisions marked "re-derive" in `docs/MAP_DECISIONS.md` (M18–M20).
