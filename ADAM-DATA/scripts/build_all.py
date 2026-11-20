"""Single entry point: run the Doom pipeline end to end, then build the viz.

    python scripts/build_all.py                 # features -> models -> exports -> viz (default)
    python scripts/build_all.py --clean         # first delete every regenerable output, then build
    python scripts/build_all.py --from-raw      # also rebuild the full table from data/raw (phases 1-4)
    python scripts/build_all.py --skip-backtests  # reuse the committed M1/M2/M1b results (fast, ~3 min)

Stages
  raw       (--from-raw only) fetch_phase1..4 + build_phase1..4 + build_crosswalk -> data/processed/mlb_nhl_team_seasons.csv
            Every fetch is cached under data/raw/, but most phase 1-4 caches are not on this machine
            (docs/cleanup_plan.md), so this stage refetches from the network (hours; Wikipedia and other live
            pages can have changed). The default build starts from the committed full table instead.
  features  build_slim -> m1b_value_age fetch -> m1b_features         (MLB Stats API calls are cached)
  models    run_m1 -> run_m2 -> run_m1b -> run_m3                     (~17 min; run_m3 alone ~2.5 min)
  viz       fetch_logos -> build_comparables -> build_scatter         -> dashboard/doom_scatter.html
"""
import argparse, glob, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # ADAM-DATA
S = lambda *p: os.path.join(ROOT, "src", *p)

RAW = [[S("fetch_phase1.py")], [S("build_phase1.py")],
       [S("fetch_phase2.py")], [S("fetch_wiki_batch.py")], [S("fetch_wiki_people.py")], [S("build_phase2.py")],
       [S("fetch_phase3.py"), "mlb"], [S("fetch_phase3.py"), "mlb_repair"], [S("fetch_phase3.py"), "nhl"],
       [S("fetch_phase3.py"), "nhl_births"], [S("fetch_phase3.py"), "mp"], [S("build_phase3.py")],
       [S("fetch_phase4.py")], [S("build_phase4.py")], [S("build_crosswalk.py")]]
FEATURES = [[S("build_slim.py")], [S("m1b_value_age.py"), "fetch"], [S("m1b_features.py")]]
BACKTESTS = [[S("model", "run_m1.py")], [S("model", "run_m2.py")], [S("model", "run_m1b.py")]]
EXPORT = [[S("model", "run_m3.py")]]
VIZ = [[S("viz", "fetch_logos.py")], [S("viz", "build_comparables.py")], [S("viz", "build_scatter.py")]]

# Regenerable outputs removed by --clean (never data/raw, data/manual, the frozen full table, or hand-written reports)
CLEAN = ["data/processed/mlb_nhl_model_slim.csv", "data/processed/mlb_m1b_features.csv",
         "reports/m1.md", "reports/m1_*", "reports/m2.md", "reports/m2_*", "reports/m1b.md", "reports/m1b_coef*",
         "reports/m1b_feature*", "reports/m1b_horizons.csv", "reports/m1b_path*", "reports/m1b_predictions.csv",
         "reports/m3.md", "reports/m3_*", "reports/model_card.md", "reports/slim_selection.md",
         "dashboard/data/*", "dashboard/doom_scatter.html", "dashboard/assets/logos/*"]
KEEP = {"reports/m1b_preregistration.md"}


def clean():
    n = 0
    for pat in CLEAN:
        for f in glob.glob(os.path.join(ROOT, pat)):
            if os.path.relpath(f, ROOT).replace(os.sep, "/") in KEEP or not os.path.isfile(f):
                continue
            os.remove(f)
            n += 1
    print(f"[clean] removed {n} regenerable files", flush=True)


def run(step):
    t = time.time()
    rel = os.path.relpath(step[0], ROOT)
    print(f"[run] {rel} {' '.join(step[1:])}", flush=True)
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, *step], cwd=ROOT, env=env)
    if r.returncode:
        sys.exit(f"[fail] {rel} exited {r.returncode}")
    print(f"[ok] {rel} ({time.time() - t:.0f}s)", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean", action="store_true", help="delete regenerable outputs first")
    ap.add_argument("--from-raw", action="store_true", help="also rebuild the full table from data/raw (phases 1-4)")
    ap.add_argument("--skip-backtests", action="store_true", help="skip run_m1/run_m2/run_m1b (reuse committed results)")
    a = ap.parse_args()
    if a.clean and a.skip_backtests:
        sys.exit("--clean deletes the backtest results that --skip-backtests reuses; use one or the other")
    t0 = time.time()
    if a.clean:
        clean()
    steps = (RAW if a.from_raw else []) + FEATURES + ([] if a.skip_backtests else BACKTESTS) + EXPORT + VIZ
    for s in steps:
        run(s)
    print(f"[done] {len(steps)} steps in {(time.time() - t0) / 60:.1f} min -> "
          f"{os.path.join(ROOT, 'dashboard', 'doom_scatter.html')}", flush=True)


if __name__ == "__main__":
    main()
