# Doom Map demo: things to try

A 15-step walkthrough of the dashboard with **fake NBA and NFL scores** (MLB and NHL are real). Use it to try the
page yourself, or adapt it for usability tests. Each step says what should happen, so anything else is a bug worth
noting.

## Start and stop

```
cd ADAM-DATA
.venv/Scripts/python map/demo.py          # writes the fake scores, builds, opens dashboard/index.html
.venv/Scripts/python map/demo.py --off    # removes them, rebuilds, checks every file matches its pre-demo state
```

`demo.py --no-open` builds without opening the browser. While the demo is on, the map's generated files contain demo
data, and a pre-commit check refuses to commit them; run `--off` before committing anything.

About the demo data (`map/make_demo_scores.py`, M60):
- **Real:** NBA and NFL standings for 2017–2024 (win %, standing percentile, record), from the teammate file,
  snapshotted in `map/inputs/demo_standings_nba_nfl.csv`.
- **Fake:** everything else: doom, ranges, bands, projected paths, drivers, actuals.
- **Seasons:** NBA and NFL cover 2017–2024; MLB covers 2008–2026; NHL covers 2013–2025.
- **Actual outcomes:** NBA and NFL 2017–2021, MLB through 2023, NHL through 2022.

## Steps

**1. First impression (overview).** Open the page and don't touch anything for 20 seconds. *Usability prompt: "What
do you think this page shows?"*
- A yellow **"DEMO DATA: NBA and NFL scores are fake"** banner sits at the very top and stays there when you scroll.
- The season is **2024**: the latest season with scores for the most leagues.
- All four league buttons (MLB, NHL, NBA, NFL) are pressed.
- The map is coloured: blue = bright future, gold = average, crimson = doomed. Grey means no teams nearby (northern
  Canada, the Great Plains).
- The legend reads "Showing predicted doom: MLB 2024 · NHL 2024–25 · NBA 2024–25 · NFL 2024".
- The right column ranks 23 regions.
- The scatter below has four shapes (circle MLB, square NHL, triangle NBA, diamond NFL).
- No grey "This season shows" banner on the map, and **Actual** is greyed out (no actual outcomes for 2024).

**2. Hover a region and read its card.** Move the mouse over the South East (or its row in the list).
- The region gets a dark outline, the other regions dim, and its list row highlights.
- The card shows:
  - name and main cities;
  - a yellow line "Includes 4 demo teams (NBA, NFL): fake scores";
  - a verdict (Bright future / Middling / Doomed) and the average doom;
  - "Nth brightest of 23" and "Based on 6 teams (1 MLB, 2 NBA, 2 NFL, 1 NHL)";
  - best hope and biggest worry, each with league and doom;
  - four quadrant counts;
  - a small trend line with "▲ more doomed / ▼ brighter than in 2023".
- On the map itself, the card also says which teams shape the colour at that spot.

**3. Find your own region via search.** Type part of your city, e.g. `pitts`.
- A list shows the city ("Pittsburgh · City · 3 teams · Ohio Valley"), its teams (Penguins, Pirates, Steelers) and
  the region.
- ↑/↓ moves through the list. Enter on the first result flies the map to **Ohio Valley** (Level 2).
- The breadcrumb reads "← Back · All regions › Ohio Valley". Esc (twice) returns to the full map.

**4. Zoom into New York.** Click New York on the map or in the list.
- The map zooms in, other regions dim, and round **team badges** appear around the city with lines to their venues:
  Mets, Yankees, Nets, Knicks, Giants, Jets, Devils, Islanders, Rangers (9).
- Each badge ring is coloured by that team's doom.
- The New York points stay bright in the scatter; the rest fade.

**5. Zoom into Los Angeles.** Click **← Back**, then Southern California (or search `los angeles`).
- Nine badges: Angels, Dodgers, Padres, Clippers, Lakers, Chargers, Rams, Ducks, Kings.
- The Clippers badge sits at Inglewood (Intuit Dome, 2024–25).

**6. Hover a team.** Hover the Lakers badge.
- A card shows "Los Angeles Lakers **DEMO**", "NBA 2024–25 · Los Angeles CA · Southern California".
- It also shows the doom number with a coloured square, the risk band, "This season: 61.0% wins (50-32), 78th
  percentile", the quadrant, and a small trend line.
- MLB and NHL cards have **no** DEMO tag.

**7. Click a team.** Click the Lakers badge.
- The right column becomes the **team panel**:
  - name with the DEMO tag;
  - big doom number;
  - risk chip "(n% chance of doom ≥ 75)";
  - "Actual outcome not known yet.";
  - Likely range (80%), This season, Quadrant, and Projected finish (three percentiles);
  - doom-by-season chart (line = predicted, dots = actual);
  - "What moves this prediction" (toward / away from doom);
  - the grey note "DEMO: fake score and invented drivers…";
  - "About the NBA score (not backtested): Demo only…".
- The address bar gains `team=NBA:los-angeles-lakers`. Reloading the page restores the zoom, season and team.

**8. Follow the link to the scatter.** Scroll to the scatter.
- The Lakers' point carries a badge and the name.
- Hovering any point shows the same team card (DEMO tag for NBA/NFL).
- Clicking a point (e.g. the Chiefs, a diamond in the top right) switches the panel to that team.
- **Show on map** zooms the map to the team's region (Heartland for the Chiefs).
- ← All regions list (or Esc) closes the panel.

**9. Change the season, including one where a league is missing.** Use the season menu or ◀ ▶.
- **2019:** all four leagues, no coverage banner.
- **2025:** a grey banner on the map, "This season shows: MLB, NHL (no NBA, NFL)". NBA and NFL teams disappear from
  map, list and scatter, but their buttons stay pressed.
- **2026:** "This season shows: MLB (no NHL, NBA, NFL)".
- **2012:** "This season shows: MLB (no NHL, NBA, NFL)". Mid-South, Montréal–Ottawa–Atlantic and the Prairies have
  no team and list as "No teams with predicted doom this season".
- A selected team stays selected when it plays in the new season.

**10. League toggles.** Back in 2024, turn off MLB and NHL.
- The map, list, region cards and scatter use only NBA and NFL. The legend reads "NBA 2024–25 · NFL 2024".
- The DEMO banner stays.
- Turn off NBA and NFL too: the map shows "Pick at least one league to see the map." Turn all four back on.

**11. Predicted vs. actual.**
- **2024:** Actual is greyed out. Its tooltip says how far actual outcomes go.
- **2021:** Actual works. Click it:
  - the banner says "Actual outcomes: what happened over the next three seasons";
  - the legend says "Showing **actual** doom";
  - the colours change;
  - the scatter's y-axis becomes "Actual standing, next 3 seasons".
- **2022:** the banner says "Actual outcomes: MLB + NHL only (NBA known through 2021; NFL known through 2021)".
- Switch back to Predicted.

**12. Palette and dark mode.**
- **Green–red** recolours the map, legend, badges and scatter. Colorblind-safe switches back.
- **Dark** turns the page dark, and the yellow DEMO banner stays readable. **Auto** follows the computer's setting.
- **Monograms** (Badges) replaces logos with letters (LAL, NYK, ...).

**13. Keyboard only.** Reload, put the mouse away, use Tab, Shift+Tab, Enter, arrows and Esc.
- Tab order: search box → View buttons → Leagues → Season → Doom → Colors → Theme → Badges → breadcrumb → team badges
  (when zoomed) → scatter → region list. Focus is always visible.
- Enter on a region in the list zooms in. Shift+Tab back to the breadcrumb, then Tab: focus lands on a badge **in
  that region**, and its card appears.
- Enter or Space opens the team panel.
- **Esc goes up one level:** closes search results, then a pinned card, then the team panel, then zooms out.

**14. Phone size.** Use a phone, or the browser's device mode at 390 × 844 with touch.
- The DEMO banner wraps but stays at the top.
- Map, scatter and list stack vertically.
- Tapping a region pins its card with **Zoom in** and **Close**. Zoom in brings the map into view and zooms.
- Tapping a badge pins its team card with **Details**, which opens the team panel. Pinch or the buttons zoom; Close
  or Esc unpins.

**15. Turn the demo off.** Run `map/demo.py --off`.
- It ends with "DEMO OFF: all N map inputs and generated files match their pre-demo checksums."
- Reloading the page shows MLB and NHL only, with no DEMO banner or tags, and default season 2025.

## Reporting a problem

Note the step, what you expected (above), what happened, and the address bar (it holds the page state), plus a
screenshot.
