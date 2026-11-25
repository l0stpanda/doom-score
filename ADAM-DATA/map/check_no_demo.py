"""Refuse a commit that would put Doom Map demo data in the repo (M61). Exit 1 with a reason, else 0.

Checks the files staged for commit (and every tracked file) for:
- any DEMO_* scores file (DEMO_*.csv, or DEMO_* under map/inputs/; fake scores from map/make_demo_scores.py;
  git-ignored, but `git add -f` would get past that);
- generated map files built in demo mode: the staged map/data/derived.json lists demo leagues (run
  `python map/demo.py --off` to rebuild without them).
Installed as the repository's pre-commit hook by map/demo.py (or `python map/check_no_demo.py --install-hook`).
"""
import json, os, stat, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DERIVED = "ADAM-DATA/map/data/derived.json"
HOOK = """#!/bin/sh
# Installed by ADAM-DATA/map/check_no_demo.py: refuse commits that contain Doom Map demo data (M61).
PY=ADAM-DATA/.venv/Scripts/python.exe
[ -x "$PY" ] || PY=ADAM-DATA/.venv/bin/python
[ -x "$PY" ] || PY=python
exec "$PY" ADAM-DATA/map/check_no_demo.py
"""
MARK = "check_no_demo.py"


def git(*a):
    return subprocess.run(["git", *a], cwd=top(), capture_output=True, text=True, encoding="utf-8")


def top():
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, capture_output=True, text=True).stdout.strip()


def install_hook(quiet=False):
    """Install the pre-commit hook unless another hook is already there (then say how to add the check)."""
    hooks = git("rev-parse", "--git-path", "hooks").stdout.strip()
    path = os.path.join(top(), hooks, "pre-commit")
    if os.path.exists(path):
        if MARK in open(path, encoding="utf-8", errors="replace").read():
            return path
        print(f"NOTE: {path} already exists and is not ours; add this line to it to block demo data in commits:\n"
              f"  python ADAM-DATA/map/check_no_demo.py || exit 1")
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if not quiet:
        print(f"installed the pre-commit check that blocks demo data: {path}")
    return path


def is_demo_scores(path):
    """A demo scores file: DEMO_* under map/inputs/, or any DEMO_*.csv (not docs such as docs/DEMO_GUIDE.md)."""
    base = os.path.basename(path)
    return base.startswith("DEMO_") and ("/map/inputs/" in "/" + path or base.lower().endswith(".csv"))


def problems():
    out = []
    staged = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.splitlines() if p]
    tracked = [p for p in git("ls-files").stdout.splitlines() if p]
    demo_files = sorted({p for p in staged + tracked if is_demo_scores(p)})
    if demo_files:
        out.append("demo score files are staged or tracked: " + ", ".join(demo_files)
                   + " (unstage with `git rm --cached <file>`)")
    shown = git("show", f":{DERIVED}")                     # the staged (index) version
    if shown.returncode == 0:
        try:
            demo = json.loads(shown.stdout).get("demo_leagues") or []
        except json.JSONDecodeError:
            demo = []
        if demo:
            out.append(f"{DERIVED} in the index was built with demo data ({', '.join(demo)}); run "
                       f"`python ADAM-DATA/map/demo.py --off`, then `git add` the rebuilt map files again")
    return out


def main():
    if "--install-hook" in sys.argv[1:]:
        install_hook()
        return
    bad = problems()
    if bad:
        print("Commit blocked (Doom Map demo data, M61):\n  - " + "\n  - ".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
