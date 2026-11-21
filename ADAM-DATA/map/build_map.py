"""Rebuild everything the Doom Map uses, in order. Run from ADAM-DATA/:

    .venv/Scripts/python map/build_map.py              # data + derived numbers + check renders
    .venv/Scripts/python map/build_map.py --no-renders # skip the Edge screenshots
    .venv/Scripts/python map/build_map.py --fetch-logos # also run dashboard/fetch_logos.py (team_meta.csv URLs)
    .venv/Scripts/python map/build_map.py --shots       # also run the Phase 4 browser checks, screenshots, timing and GIF
(map/build/shots_phase2.mjs and shots_phase3.mjs are kept for reference; they would overwrite the approved Phase 2/3
screenshots with the current page, so they are not run by default.)

Needs: the Python venv (requirements.txt + map/requirements.txt), Node 18+ with `npm install` run in map/,
and the raw boundary files in data/raw/geo/ (see docs/MAP_DECISIONS.md, M05-M06, for where they come from).
Steps: team_locations.py -> regions.mjs -> logos.py -> derive.py -> palette.py -> render_checks.mjs -> build_page.mjs
Output page: dashboard/index.html (map + scatter + team panel; self-contained, git-ignored like doom_scatter.html).
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    args = set(sys.argv[1:])
    if "--fetch-logos" in args:
        run([PY, "dashboard/fetch_logos.py"])
    run([PY, "map/build/team_locations.py"])
    run(["node", "map/build/regions.mjs"])
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
