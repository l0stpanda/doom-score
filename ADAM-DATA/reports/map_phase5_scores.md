# Doom Map: scores-only input (M50–M56)

**Goal.** The map depends only on per-team doom scores, so adding a league means adding one scores file.

**Built.**
- **One input:** `map/inputs/scores/*.csv` (format: `docs/SCORES_FORMAT.md`). MLB and NHL are exported there by
  `scripts/export_map_scores.py`. Nothing else in the map reads predictions.
- **Graceful fallback (M51):** every optional column is per league; what depends on a missing column is hidden for
  that league only.
- **Team registry (M52)** for MLB, NHL, NBA and NFL in `map/data/team_registry.csv`, with NBA and NFL covering
  2000–2026. Includes regions from the committed shapes, logos (M53) and aliases (M54).
- **`map/add_scores.py`:** validate → resolve names → coverage report → copy → rebuild, printing old vs new
  parameters, or `--freeze-params`.
- **Handoff:** `map/inputs/scores_template.csv` and `docs/CROSS_LEAGUE_HANDOFF.md` §6.

## Check 1: MLB with the required columns only

The build used a copy of `mlb_scores.csv` with only `league, season_start_year, franchise_id, doom_pred`. NHL was
unchanged.

| Shown (same as with the full file) | Hidden for MLB |
|---|---|
| Map colours, region averages, ranks (New York 2019: average 52, 12th of 23, best hope Yankees 35, biggest worry Devils 68) | Band chip and hover band text, "% chance of doom ≥ 75" |
| Region cards; MLB team cards with doom and the trend line | 80% range, "This season" row, quadrant row, projected finish |
| NHL sections in full | Drivers and the MLB note; actual line and trend dots |
| Region card quadrants for NHL teams: "Quadrants count 3 of 5 teams (MLB scores have no standing)" | MLB points in the scatter (its key says "Not shown: MLB"); with MLB alone, the whole scatter and the Predicted/Actual toggle |

Figures: `figures/map_p5_mlb_required_only_team_panel.png`, `_region_card.png`, `_alone.png`.

## Check 2: fake NBA and NFL scores, end to end

These are **fake data**: random `doom_pred`, in git-ignored files named `FAKE_*`.
- **NBA:** 806 rows, 2000–2026, with `band` and `win_pct_percentile`.
- **NFL:** 640 rows, 2005–2024, required columns only.

Team identifiers were mixed on purpose: ids, season names, abbreviations and nicknames.

1. **Unmatched names stop the run.** A file with "Seattle Supersonix" and "Charlotte Bobcatz" was rejected with both
   names and their seasons listed, and nothing was copied.
2. **NBA was added, with parameters re-derived.**
   - 81 names were resolved, including "Seattle SuperSonics" → `oklahoma-city-thunder` and "CHH" →
     `charlotte-hornets`.
   - "Hornets" resolved by season: `new-orleans-pelicans` in 2010, `charlotte-hornets` in 2016.
   - Every registry team was scored in every season.
   - σ stayed at 100 mi; opacity cutoffs went from 0.0122 / 1.0703 to 0.0111 / 1.081; the colour range was
     unchanged at ±1.677.
3. **NFL was added with `--freeze-params`.**
   - "Oakland Raiders", "SD", "STL" and "Redskins" resolved.
   - σ and the colour range were kept. A re-derive would have set the opacity cutoffs to 0.0133 / 1.2167.
   - The default season moved to 2024, the latest season all four leagues share (M55).
4. **Screenshots**, with no console errors:
   - All four leagues: `figures/map_p5_FAKE_four_leagues_overview.png`.
   - New York zoomed in, with NBA and NFL logos: `map_p5_FAKE_zoom_new_york.png`.
   - New York region card (9 teams; quadrants count 7 of 9): `map_p5_FAKE_region_card_new_york.png`.
   - NBA team panel. The Raptors' 2020–21 season is placed in Tampa; band and standing show, range and actual are
     hidden: `map_p5_FAKE_nba_team_panel.png`.
   - NFL team panel, doom and trend only: `map_p5_FAKE_nfl_team_panel.png`.
   - NFL alone, with the scatter and Actual toggle hidden: `map_p5_FAKE_nfl_alone.png`.
5. **Removal.** The `FAKE_*` files and `frozen_params.json` were deleted and the map rebuilt. Every input and
   generated file (81) was byte-identical to before the test, `git status` was clean, and the map showed MLB and
   NHL only.

## Line endings (M56)

After `.gitattributes` (`*.csv text eol=lf`) and a re-checkout, a fresh `python map/build_map.py --fetch-logos` left
every CSV and JSON unchanged. Only the three check renders (`map_check_regions_*.png`, `map_heatmap_sigma100.png`)
differed, by at most 4/255 per channel: antialiasing from this machine's Edge version, not data. They were restored.
`--no-renders` builds leave `git status` fully clean.
