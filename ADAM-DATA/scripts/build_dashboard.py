"""Rebuild the dashboard from the slim table: models → exports → comparables → logos → scatter page.

    python scripts/build_dashboard.py           # ~3 min
    python scripts/build_dashboard.py --clean   # delete dashboard/data/ and the built page first

Input: data/mlb_nhl_model_slim.csv only (plus a one-time logo download, cached in dashboard/assets/logos/).
Output: dashboard/data/*.csv and dashboard/doom_scatter.html (git-ignored: it embeds team logos).
Rebuilding the slim table itself from raw sources needs the full pipeline: git checkout adam-full-pipeline.
"""
import argparse, glob, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # ADAM-DATA
STEPS = ["src/export_dashboard.py", "src/build_comparables.py", "dashboard/fetch_logos.py", "dashboard/build_scatter.py"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", action="store_true", help="delete dashboard/data/*.csv and the built page first")
    a = ap.parse_args()
    t0 = time.time()
    if a.clean:
        old = glob.glob(os.path.join(ROOT, "dashboard", "data", "*.csv")) + \
            glob.glob(os.path.join(ROOT, "dashboard", "doom_scatter.html"))
        for f in old:
            os.remove(f)
        print(f"[clean] removed {len(old)} files", flush=True)
    for s in STEPS:
        t = time.time()
        print(f"[run] {s}", flush=True)
        r = subprocess.run([sys.executable, os.path.join(ROOT, s)], cwd=ROOT, env=dict(os.environ, PYTHONUTF8="1"))
        if r.returncode:
            sys.exit(f"[fail] {s} exited {r.returncode}")
        print(f"[ok] {s} ({time.time() - t:.0f}s)", flush=True)
    print(f"[done] {(time.time() - t0) / 60:.1f} min -> {os.path.join(ROOT, 'dashboard', 'doom_scatter.html')}")


if __name__ == "__main__":
    main()
