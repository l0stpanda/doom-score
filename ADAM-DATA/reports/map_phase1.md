# Doom Map: Phase 1 (foundations)

**Audit.** Out-of-scope work on the other four leagues (team-list research and a drafted metro list) stopped before
anything was committed. Kept with your approval: Node tooling, the raw boundary files and the world-atlas basemap.
Deleted: the six-league `regions.csv` / `metros.csv`. Regions were rebuilt with all 23 originals. Differences from
the pivot methods were fixed in this phase (decisions M01–M23 in `docs/MAP_DECISIONS.md`).

**Built** (`python map/build_map.py` rebuilds all of it):
- Team-location table `map/data/team_locations.csv`: 974 team-seasons, one per prediction row; MLB 2008–2026,
  NHL 2013–2025. Each row has a source URL; 939 are confirmed on official league or team pages, 35 flagged
  unverified (M04).
- 23 region shapes from 3,392 counties / census divisions (`regions.topo.json`, 160 KB), with the assignment of
  each unit in `unit_regions.csv`.
- Logo manifest: 69 team identities, 65 logos and 4 monograms (`logo_manifest.csv`).
- Map table `team_seasons.csv`.
- Derived numbers in `derived.json`.
- `docs/ADD_A_LEAGUE.md`.

**Coverage.** Too new to score = **0** team-seasons: Vegas and Seattle have predictions from their first season.
Relocations in range are confirmed on mlb.com / nhl.com:
- Coyotes: Glendale → Tempe (2022) → Utah (2024).
- Athletics: West Sacramento from 2025.
- Blue Jays: Buffalo in 2020.
- Rays: Tampa in 2025.
- Marlins: Miami in 2012.

Thrashers → Jets (2011) falls before the NHL prediction seasons.

**Region counts** (full table by season and league: `reports/map_derived/region_counts_by_season_league.csv`).
Scored teams per region when both leagues are scored (2013–25):

| Teams | Regions |
|---|---|
| 5 | NYC, SCA |
| 4 | OHV |
| 3 | CHI, DMV, GHS, GLK, HRT, NCA, PRA, UMW |
| 2–3 | CAS, DSW, MTW |
| 2 | CFL, NEN, NTX, OTM, PHI, SE, SFL |
| 1 | MSO, STX |

Mid-South, Ottawa–Montréal and the Prairies are NHL-only, so they are empty (grey) in the MLB-only seasons
2008–12 and 2026.

## Derived numbers

| Quantity | Value | How |
|---|---|---|
| z by league (doom_pred) | MLB raw SD 11.6 (25.7–74.3) → z −1.68…1.68; NHL raw SD 12.6 (18.8–84.9) → z −2.24…2.31 | within league-season, population SD |
| Colour-scale ends | z −1.677 / +1.678; 19 + 20 of 974 clamped (actual view: 57 of 788) | 2nd / 98th percentile, pooled |
| σ (falloff) | **100 mi** | largest σ passing all three tests (M18) |
| own-metro share at σ 100 | median 0.75, min 0.17 | target median ≥ 0.6 |
| pair blending at σ 100 | Balt←DC 0.33, DC←Balt 0.19, LA↔Anaheim 0.42/0.41, Tor←Buf 0.24, Buf←Tor 0.45, Sea↔Van 0.32, LA←SD 0.12, SD←LA 0.30; far pair Dal←Hou 0.04, Hou←Dal 0.13 | median over seasons |
| empty interior | 38% of land is > 300 mi from every team; 0% of it gets visible colour at σ 100 (3.5% at 125, 25% at 150) | W ≥ 0.1 counts as visible |
| opacity cutoffs | 0 at W ≤ 0.0122, full at W ≥ 1.0703 | P95 of W on far land; P10 of W at metro centres |
| palette checks | all pass for the default: ends ΔE 42–63, gold–grey ≥ 25.8, dark contrast blue 3.14 / crimson 3.02 / grey 7.54, text ≥ 6.3. Green–red fails deuteranopia ends (8.9) | `reports/map_palette.png` |

**Screenshots** (`reports/figures/`):
- `map_check_regions_latest.png` and `_2015.png`: region check map with team points.
- `map_heatmap_sigma075/100/125.png`: heatmap test maps.
- `reports/map_palette.png`: palette ramps and checks.

## Needs your decision before Phase 2

1. **Palette (M22).** Blending blue → gold in OKLab passes through grey. At z ≈ −0.84 the ramp is `#8C949C`,
   ΔE ≈ 6.5 from the "no teams" grey. On the test maps, moderately good areas look empty, and gold shows as bright
   bands where good and bad teams meet. A lighter grey (`#C4C7CE`) is the smallest fix and passes everywhere
   (ΔE ≥ 13.8), but the dull zone stays. The only full fix is changing the midpoint or the blending.
2. **σ = 100 vs 125 (M18).** 125 looks smoother, but Houston would pick up 27% of its colour from Dallas.
3. **Fan-region judgment calls (M08, M09)**: e.g. Kingston and Thunder Bay with Toronto, Syracuse with NYC,
   Atlantic Canada with Ottawa–Montréal.
