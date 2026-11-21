# Doom Map: Phase 4 (polish and integration)

**Phase 3 review fixes:**
- **M34 resolved.** The dark-mode grey `#383C46` is kept: the 3:1 rule applies to the data colours, not to the
  no-data grey. The legend swatch is outlined at 4.37:1 (light) and 5.22:1 (dark), checked in `palette_checks.csv`.
- **Region framing (M38).** Regions are framed around their venues padded ~150 mi, so the outline and the dimmed
  neighbours stay in view.

**Built.** `dashboard/index.html` combines three views (M43–M48):
- **Map**, a native d3 **projected-standing scatter**, and **one shared team panel**: doom + band, actual outcome,
  80% range, quadrant, trend, model drivers, "Show on map", and "Full diagnostics (coming soon)", disabled.
- **Shared state** for season, leagues, mode and selected team, working in both directions.
- **URL state:** view, region, season, leagues, mode, team.
- **Predicted / actual toggle,** enabled only where actuals exist and always labelled.
- **Search** across teams, cities and regions.
- **Touch:** tap pins a card with a Zoom in or Details button.
- **Keyboard:** Tab through badges and list, Enter opens, Esc goes up.
- **README map section,** and the decision log's final review (48 decisions, none still open).

## Checks (browser-run, `map/build/shots_phase4.mjs`): 17 of 17 pass, no page errors

| Area | Check |
|---|---|
| Linking | scatter click → map marker + panel; map badge click → scatter badge + panel; season change keeps the team in all three views |
| URL | view, region, season, leagues and team are written; opening the link restores the zoomed region, season and team |
| Actual | labelled in toolbar, legend and scatter axis; disabled in 2025, with a predicted label; 2023 flagged "MLB only" |
| Search | finds team, city and region for "toro"; Enter flies to the Golden Horseshoe |
| Keyboard | Enter on a list item zooms; Tab from the breadcrumb reaches a badge (1 Tab); Enter opens the panel; Esc closes the panel, then zooms out |
| Touch | tap region → card + Zoom in (no zoom yet); button zooms; tap scatter point → card + Details; Details opens the panel |

## Derived numbers: performance (`reports/map_derived/perf_phase4.csv`; Edge, 1440×1250)

| Metric | dpr 1 | dpr 2 |
|---|---|---|
| Load to first paint | 0.77 s | 0.83 s |
| Season switch (map + scatter + list redraw), median | 36 ms | 72 ms |
| Zoom continent → New York: frame rate / worst frame | 61 fps / 28 ms | 59 fps / 28 ms |
| Long jump New York → Cascadia: frame rate / worst frame | 60 fps / 17 ms | 62 fps / 18 ms |

**Screenshots and GIF** (`reports/figures/map_p4_*`):
- `linked_selection.gif` (real time: scatter → map → map → scatter → season change).
- Linked views: `linked_scatter_to_map`, `linked_map_to_scatter`, `url_restored`.
- Full page: `dashboard_light`, `dashboard_dark`.
- Actual mode: `actual_2019`, `actual_2023_partial`.
- Search and keyboard: `search_results`, `search_flown_toronto`, `keyboard_focus_badge`.
- Touch: `touch_region_card`, `touch_zoomed`, `touch_scatter_card`.

The GIF is built from full-page captures at a few frames per second, so the zoom in it looks choppy. The 60 fps
above is measured in the page.

## Notes

- **Stacked scatter points.** Teams with the same standing and similar doom (e.g. the 2025 Yankees and Blue Jays)
  overlap. The hovered point is raised to the top, and search reaches every team (M45).
- **The older Plotly page** `doom_scatter.html` is unchanged and still builds. The new page doesn't link to it,
  because its panel replaces that link.
