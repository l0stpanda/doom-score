"""Run the full collection pipeline in order (01 -> 06).

Usage:  python scripts/run_all.py [--refresh]
Each step is idempotent (upserts on primary keys) and reuses the raw cache
unless --refresh is given. Stops at the first failing step.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["01_collect_team_data.py", "02_collect_player_data.py", "03_collect_draft_data.py",
         "04_collect_financial_data.py", "05_build_team_features.py", "06_validate_data.py"]


def main() -> int:
    extra = sys.argv[1:]
    for step in STEPS:
        args = [sys.executable, str(HERE / step)] + ([a for a in extra if a == "--refresh"] if step != "06_validate_data.py" else [])
        print(f"\n=== {step} {' '.join(args[2:])}", flush=True)
        rc = subprocess.call(args, cwd=HERE.parent)
        if rc != 0:
            print(f"step {step} exited with {rc}; stopping", flush=True)
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
