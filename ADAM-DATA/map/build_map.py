"""Rebuild everything the Doom Map uses, in order. Run from ADAM-DATA/:

    .venv/Scripts/python map/build_map.py                   # scores -> registry -> regions -> numbers -> page
    .venv/Scripts/python map/build_map.py --fetch-logos     # also download team logos (map/data_src/team_logos.csv)
    .venv/Scripts/python map/build_map.py --rebuild-regions # rebuild the regions from the raw boundary files
    .venv/Scripts/python map/build_map.py --demo            # include the fake DEMO_* scores (map/demo.py does this)
`--no-renders` is accepted for older commands and does nothing (the build writes no figures).

Needs: the Python venv (requirements.txt + map/requirements.txt) and Node 18+ with `npm ci` run in map/.
The only model input is map/inputs/scores/*.csv (docs/SCORES_FORMAT.md; add a league with map/add_scores.py).
By default the build uses the committed region shapes (map/data/regions.topo.json, unit_regions.csv, land_grid.csv)
and only assigns team venues to them, so it needs no raw boundary files. --rebuild-regions also runs regions.mjs,
which needs data/raw/geo/ (docs/ADD_A_LEAGUE.md, "Changing the regions").
Steps: scores.py (check) -> team_locations.py (registry, aliases, shown team-seasons) -> [regions.mjs] ->
       team_regions.mjs -> logos.py -> derive.py -> palette.py -> build_page.mjs
Output page: dashboard/index.html (map + scatter + team panel; self-contained, git-ignored: it embeds team logos).
Decisions: docs/DECISIONS.md.
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
KNOWN = {"--no-renders", "--fetch-logos", "--rebuild-regions", "--demo"}


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def check_geo():
    missing = [f for f in GEO_FILES if not os.path.isfile(os.path.join(GEO, f))]
    if missing:
        sys.exit("--rebuild-regions needs the raw boundary files in data/raw/geo/. Missing:\n"
                 + "\n".join("  data/raw/geo/" + f for f in missing)
                 + "\nUS counties: python scripts/fetch_geo.py. Canadian census divisions (cd_*.geojson): "
                   "manual download, see docs/ADD_A_LEAGUE.md, 'Changing the regions'.")


def main():
    args = set(sys.argv[1:])
    unknown = args - KNOWN
    if unknown:
        sys.exit(f"unknown option(s): {' '.join(sorted(unknown))}; known: {' '.join(sorted(KNOWN))}")
    if "--rebuild-regions" in args:
        check_geo()
    # --demo: also read the fake DEMO_* score files (map/make_demo_scores.py). Without it they are ignored, so a
    # normal build never puts demo data into the committed outputs.
    os.environ["DOOM_DEMO"] = "1" if "--demo" in args else "0"
    run([PY, "map/build/scores.py"])                  # validate map/inputs/scores/ first (clear errors)
    if "--fetch-logos" in args:
        run([PY, "map/build/fetch_logos.py"])
    run([PY, "map/build/team_locations.py"])
    if "--rebuild-regions" in args:
        run(["node", "map/build/regions.mjs"])        # region shapes, unit assignments and land grid
    run(["node", "map/build/team_regions.mjs"])       # team venues (registry + shown) -> region shapes
    run([PY, "map/build/logos.py"])
    run([PY, "map/build/derive.py"])
    run([PY, "map/build/palette.py"])
    run(["node", "map/build/build_page.mjs"])


if __name__ == "__main__":
    main()
