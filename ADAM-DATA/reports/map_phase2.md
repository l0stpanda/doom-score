# Doom Map: Phase 2 (Level 1 overview)

**Before Phase 2** (all six review changes are in commit `15489c1`; decisions M04, M09, M18, M24–M27):
- **Palette:** OKLCh blending with the stops unchanged. The whole-ramp check (101 points, ΔE2000 ≥ 15 from the grey,
  four vision types) failed for plain OKLCh, for chroma floors and for a single teal stop. It passes with a teal stop
  plus a darker yellow-green stop.
- **Seams:** σ = 100 final, with render-time smoothing.
- **Regions:** the three calls accepted; the OTM region is renamed "Montréal, Ottawa & Atlantic Canada".
- **Default season:** 2025 (latest with both leagues), with a banner in MLB-only seasons.
- **Ranking:** empirical-Bayes region ranking.
- **Locations:** the 35 unverified rows are now city-verified with secondary sources.

**Built** (`python map/build_map.py` writes the self-contained, git-ignored `dashboard/doom_map.html`):
- Heat surface (`map/src/heat.js`) and faint region outlines.
- Region hover card: name, verdict and average doom, n and too-new count, rank, best hope, biggest worry, the four
  quadrants, change since last season, trend sparkline, and an "at this spot" read-out (teams with ≥ 5% of the
  weight, three nearest teams).
- Ranked region list, linked both ways with the map (hover a row ↔ highlight the region).
- League toggles and season control, both read from the data.
- Legend.
- Light / dark / auto theme and palette toggle.
- Banner for seasons missing a selected league.
- Phone layout.
- URL hash for season, leagues, palette and theme.
- No page errors in any screenshot run.

## Derived numbers

| Quantity | Value |
|---|---|
| Palette (chosen variant) | OKLCh + teal (0.52 / 0.14 / 175° at t 0.20) + yellow-green (0.58 / 0.13 / 120° at t 0.35); whole-ramp min ΔE vs grey: normal 27.8, deutan 22.9, protan 19.0, tritan 15.4; min C*ab 27.4; max \|Δ²L*\| 2.33 |
| Green–red toggle | fails deutan ends (8.9) and tritan whole ramp (9.0), as expected for the toggle |
| Opacity curve | smootherstep between W = 0.0122 and 1.0703: the clamped linear ramp drew a visible ellipse at full opacity |
| EB constants | s² = 1.00, τ² = 0.030, so B = 0.03 (n = 1) … 0.13 (n = 5); τ² is 0 in 11 of 19 seasons |
| 2025 regions | raw averages −0.76 (Philadelphia) … +0.91 (Cascadia); shrunk −0.043 … +0.076 |
| Verdict words | thirds of the colour scale: \|z\| ≥ 0.56 → "Bright future" / "Doomed" |
| Performance | load to first paint 0.8–1.0 s; season or league change repaints in ~0.6 s |

**Screenshots** (`reports/figures/map_p2_*.png`):
- Overview in both palettes, light and dark: `overview_{default,greenred}_{light,dark}`.
- Hover cards: `hover_region_newyork_light`, `hover_region_prairies_light`, `hover_region_socal_dark`.
- List ↔ map link: `hover_list_southeast_light`.
- MLB-only banner: `mlb_only_2026_light`.
- League toggle: `nhl_only_toggle_light`.
- Phone width: `phone_light`.

## For your review

1. **Regional differences are mostly noise (M27).** Regions differ by little more than chance, so the adjusted
   ranking is compressed. The list makes that visible: short bars, ordered honestly. Worth a line in the write-up.
2. **Dark-mode grey (M32).** The fixed `#A3A8B3` is bright on a dark page, so empty land doesn't recede. A darker
   grey (≥ 3:1 against the background) would need your approval and a re-run of the whole-ramp check.
3. **Olive stretch (M24).** The ramp stop that clears tritanopia adds a short olive stretch just below average
   (z ≈ −0.5). It shows around Montréal, New England and Texas in the 2025 view.
4. **Verdict thresholds (M28)** and **list encoding (M29)**: bar length = adjusted value, bar colour = the region's
   map colour.
