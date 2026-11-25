"""Play with the Doom Map using fake NBA and NFL scores (M60). Run from ADAM-DATA/:

    .venv/Scripts/python map/demo.py            # demo on: write the fake scores, build, open dashboard/index.html
    .venv/Scripts/python map/demo.py --no-open  # same, without opening the browser
    .venv/Scripts/python map/demo.py --off      # demo off: remove the fake scores, rebuild, check nothing changed

Demo on first records checksums of every map input and generated file (map/inputs, map/data, map/data_src,
reports/map_derived) in map/inputs/.demo_snapshot.json (git-ignored), then runs map/make_demo_scores.py and
`map/build_map.py --demo --no-renders`. The page shows a "DEMO DATA" banner and "Demo" tags (M59). Demo off deletes
the DEMO_* files, rebuilds normally and confirms every file matches its pre-demo checksum. It also installs a
pre-commit check that blocks demo data from commits (map/check_no_demo.py, M61). Things to try: docs/DEMO_GUIDE.md.
"""
import glob, hashlib, json, os, pathlib, subprocess, sys, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))          # map/
ROOT = os.path.dirname(HERE)                                # ADAM-DATA
SNAP = os.path.join(HERE, "inputs", ".demo_snapshot.json")
SCORES = os.path.join(HERE, "inputs", "scores")
WATCH = [os.path.join(HERE, "inputs"), os.path.join(HERE, "data"), os.path.join(HERE, "data_src"),
         os.path.join(ROOT, "reports", "map_derived")]
PAGE = os.path.join(ROOT, "dashboard", "index.html")
sys.path.insert(0, HERE)
from check_no_demo import install_hook                     # noqa: E402


def run(cmd):
    print(">>", " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def demo_files():
    return sorted(glob.glob(os.path.join(SCORES, "DEMO_*")))


def checksums():
    out = {}
    for d in WATCH:
        for dirpath, _, files in os.walk(d):
            for f in files:
                p = os.path.join(dirpath, f)
                if f.startswith("DEMO_") or os.path.abspath(p) == os.path.abspath(SNAP):
                    continue
                out[os.path.relpath(p, ROOT).replace("\\", "/")] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


def built_with_demo():
    try:
        return bool(json.load(open(os.path.join(HERE, "data", "derived.json"))).get("demo_leagues"))
    except (OSError, ValueError):
        return False


def build(demo):
    run([sys.executable, "map/build_map.py", "--no-renders"] + (["--demo"] if demo else []))


def on(open_page):
    if not os.path.exists(SNAP):
        if built_with_demo() or demo_files():                # leftovers from an earlier demo: get back to normal first
            print("leftover demo state found; rebuilding without it before taking the snapshot")
            for f in demo_files():
                os.remove(f)
            build(False)
        json.dump(checksums(), open(SNAP, "w"), indent=0, sort_keys=True)
        print(f"recorded {len(checksums())} file checksums in {os.path.relpath(SNAP, ROOT)}")
    else:
        print(f"demo already on (snapshot from before the demo kept: {os.path.relpath(SNAP, ROOT)})")
    install_hook()
    run([sys.executable, "map/make_demo_scores.py"])
    build(True)
    print("\nDEMO ON: NBA and NFL scores are FAKE. Things to try: docs/DEMO_GUIDE.md. Turn off: python map/demo.py --off")
    if open_page:
        webbrowser.open(pathlib.Path(PAGE).resolve().as_uri())


def off():
    for f in demo_files():
        os.remove(f)
        print(f"removed {os.path.relpath(f, ROOT)}")
    build(False)
    if not os.path.exists(SNAP):
        print("no pre-demo snapshot to compare with; check `git status`")
        return
    before, after = json.load(open(SNAP)), checksums()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if changed:
        print(f"\nDEMO OFF, but {len(changed)} file(s) differ from before the demo (snapshot kept):")
        for k in changed:
            print("  " + k + ("" if k in before and k in after else " (new)" if k in after else " (missing)"))
        sys.exit(1)
    os.remove(SNAP)
    print(f"\nDEMO OFF: all {len(after)} map inputs and generated files match their pre-demo checksums.")


def main():
    args = set(sys.argv[1:])
    if args - {"--off", "--no-open"}:
        sys.exit(__doc__)
    off() if "--off" in args else on("--no-open" not in args)


if __name__ == "__main__":
    main()
