# Doom Map: Phase 3 (zoom and logos)

**Before Phase 3** (commit `f774c62`):
- **Ranked list:** sorted by the shrunk average, drawn as a bar on a diverging axis from 0, with the raw average as
  a dot and n beside each region. It carries the caption *"Most differences between regions are within what chance
  alone would produce."* (M29).
- **Dark-mode grey:** `#383C46`, derived by a whole-ramp check per theme. The spec's 3:1 rule can't hold alongside
  "recedes" and ΔE ≥ 15; the conflict is logged (M34).
- **Verdicts:** tertiles of the pooled raw region averages (−0.336 / +0.289), plus "based on 1 team" (M28). Team
  cards keep the p_doom75 bands (M36).
- **Heat cache:** see below (M35).

**Built (Level 2):** click a region, or zoom past k = 1.8, to see:
- animated zoom under ~1 s, zooming out first on long jumps;
- logos on neutral plates with a 5-px ring in the doom colour, constant 20-px radius, monogram fallback and a
  Logos/Monograms switch;
- tidy, non-overlapping metro clusters with leader lines and metro labels; neighbouring regions and their badges
  dimmed;
- team hover cards and a team panel that links to the scatter (its hash highlights the team);
- breadcrumb, Back button and Esc;
- wheel zoom only after a click or with Ctrl/⌘, with a hint;
- reduced-motion jump;
- `region=` kept in the URL.

Decisions M36–M42.

## Derived numbers

| Quantity | Value |
|---|---|
| Season change, **before** cache (Phase 2) | ~600–625 ms (full redraw) |
| Season change, **after**: cached image / cached field (colouring only) | 5–15 ms / 22 ms (dpr 1), 75 ms (dpr 2) |
| First paint; all 19 seasons prefetched | 0.78 s; ~2.5 s in the background (3 workers, ~410 ms per field) |
| Zoom: highlight + camera + settle | 706 ms measured (100 + 380–600 camera; ≤ 150 stagger + 140 fade) |
| Reduced motion | jump, 32 ms |
| Wheel | plain wheel: no zoom (page scrolls); Ctrl + one notch: ×1.49 |
| Overlap check | 0 overlapping badges (NY 5, LA 4, Chicago 3, Toronto–Buffalo, plus all neighbours in view) |
| Logos | 65 of 69 identities inline (Phoenix/Arizona Coyotes, Utah Hockey Club and Cleveland Indians use monograms) |

**Screenshots and recordings** (`reports/figures/map_p3_*`):
- Zoom recordings, real-time GIFs: `zoom_in_newyork.gif`, `long_jump_cascadia_to_southflorida.gif`.
- Busiest clusters: `cluster_newyork` (5), `cluster_losangeles` (4) and its `_dark` version, `cluster_chicago`,
  `cluster_toronto_buffalo`.
- Team views: `team_card_yankees`, `team_panel_yankees`.
- Other states: `cluster_newyork_monograms`, `desert_sw_2015_coyotes_greenred` (era monogram ARI),
  `scroll_hint`, `after_esc_level1`, `phone_newyork`.

## For your review

1. **Team click (M41):** it opens an in-map panel with an "Open in the doom scatter" link, so the scatter
   highlights the team on its own page. True two-way linking inside one dashboard page is Phase 4.
2. **Region framing (M38):** a clicked region is framed by its venues (padded), not its full shape. For example,
   Cascadia shows Seattle and Vancouver, not all of BC. Regions without venues fall back to their shape.
3. **Heat at Level 2** dims to 50%, so the badges read first. During the camera move the surface is the scaled
   continent bitmap; it sharpens once the camera settles.
