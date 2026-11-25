"""Rebuild everything the Doom Map uses, in order. Run from ADAM-DATA/:

    .venv/Scripts/python map/build_map.py                   # data + derived numbers + check renders
    .venv/Scripts/python map/build_map.py --no-renders      # skip the Edge screenshots
    .venv/Scripts/python map/build_map.py --fetch-logos     # also run map/build/fetch_logos.py (team_logos.csv URLs)
    .venv/Scripts/python map/build_map.py --shots           # also run the Phase 4 browser checks, screenshots, timing and GIF
    .venv/Scripts/python map/build_map.py --rebuild-regions # rebuild the regions from the raw boundary files (M49)
(map/build/shots_phase2.mjs and shots_phase3.mjs are kept for reference; they would overwrite the approved Phase 2/3
screenshots with the current page, so they are not run by default.)

Needs: the Python venv (requirements.txt + map/requirements.txt) and Node 18+ with `npm ci` run in map/.
By default the build uses the committed region shapes (map/data/regions.topo.json, unit_regions.csv, land_grid.csv)
and only re-assigns team venues to regions (team_regions.mjs), so it needs no raw boundary files. --rebuild-regions
runs regions.mjs instead, which needs the files in data/raw/geo/ (scripts/fetch_geo.py and the README; M06-M07, M49).
The only model input is map/inputs/scores/*.csv (docs/SCORES_FORMAT.md; add a league with map/add_scores.py, M50).
Steps: scores.py (check) -> team_locations.py (registry, aliases, shown team-seasons) -> team_regions.mjs (or
       regions.mjs, then team_regions.mjs) -> logos.py -> derive.py -> palette.py -> render_checks.mjs -> build_page.mjs
Output page: dashboard/index.html (map + scatter + team panel; self-contained, git-ignored like doom_scatter.html).
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
GEO = os.path.join(ROOT, "data", "raw", "geo")
GEO_FILES = [  # read by map/build/regions.mjs (the .shp needs its .shx/.dbf/.prj sidecars)
    "us_county/cb_2023_us_county_5m.shp", "us_county/cb_2023_us_county_5m.shx",
    "us_county/cb_2023_us_county_5m.dbf", "us_county/cb_2023_us_county_5m.prj",
    "cd_0.geojson", "cd_100.geojson", "cd_200.geojson",
]
KNOWN = {"--no-renders", "--fetch-logos", "--shots", "--rebuild-regions"}


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def check_geo():
    missing = [f for f in GEO_FILES if not os.path.isfile(os.path.join(GEO, f))]
    if missing:
        sys.exit("--rebuild-regions needs the raw boundary files in data/raw/geo/. Missing:\n"
                 + "\n".join("  data/raw/geo/" + f for f in missing)
                 + "\nUS counties: python scripts/fetch_geo.py. Canadian census divisions (cd_*.geojson): "
                   "manual download, see the README section 'Rebuilding the regions'.")


def main():
    args = set(sys.argv[1:])
    unknown = args - KNOWN
    if unknown:
        sys.exit(f"unknown option(s): {' '.join(sorted(unknown))}; known: {' '.join(sorted(KNOWN))}")
    if "--rebuild-regions" in args:
        check_geo()
    run([PY, "map/build/scores.py"])                  # validate map/inputs/scores/ first (clear errors, M50)
    if "--fetch-logos" in args:
        run([PY, "map/build/fetch_logos.py"])
    run([PY, "map/build/team_locations.py"])
    if "--rebuild-regions" in args:
        run(["node", "map/build/regions.mjs"])        # region shapes, unit assignments and land grid
    run(["node", "map/build/team_regions.mjs"])       # team venues (registry + shown) -> region shapes
    run([PY, "map/build/logos.py"])
    run([PY, "map/build/derive.py"])
    run([PY, "map/build/palette.py"])
    if "--no-renders" not in args:
        run(["node", "map/build/render_checks.mjs", "regions"])
        run(["node", "map/build/render_checks.mjs", "heatmap"])
    run(["node", "map/build/build_page.mjs"])
    if "--shots" in args:
        frames = os.path.join(HERE, "check", "frames")
        run(["node", "map/build/shots_phase4.mjs", frames])
        run([PY, "map/build/make_gif.py", frames, "map_p4", "linked_selection"])
        run(["node", "map/build/perf_heat.mjs"])


if __name__ == "__main__":
    main()
