"""Export the MLB and NHL doom predictions into the Doom Map scores format (docs/SCORES_FORMAT.md, M50).

    .venv/Scripts/python scripts/export_map_scores.py

Reads dashboard/data/doom_predictions.csv (written by scripts/build_dashboard.py) and writes one file per league:
map/inputs/scores/mlb_scores.csv and nhl_scores.csv. The map reads only those files. Columns a league never fills
are left out of its file. Run it again whenever the predictions change, then rebuild the map.
"""
import os, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
sys.path.insert(0, os.path.join(ROOT, "map", "build"))
from scores import COLUMNS, validate                                   # noqa: E402

PRED = os.path.join(ROOT, "dashboard", "data", "doom_predictions.csv")
OUT = os.path.join(ROOT, "map", "inputs", "scores")


def record(r):
    if pd.isna(r.wins) or pd.isna(r.losses):
        return None
    parts = [int(r.wins), int(r.losses)] + ([int(r.ot_losses)] if pd.notna(r.ot_losses) else [])
    return "-".join(map(str, parts))


def main():
    P = pd.read_csv(PRED)
    P["record"] = P.apply(record, axis=1)
    P["band"] = P.doom_band.where(P.doom_band != "Not available")
    os.makedirs(OUT, exist_ok=True)
    for lg, g in P.groupby("league"):
        g = g[[c for c in COLUMNS if c in g.columns]]
        g = g[[c for c in g.columns if g[c].notna().any()]]                # drop columns this league never fills
        g = g.sort_values(["season_start_year", "franchise_id"])
        validate(g, f"{lg} export")
        path = os.path.join(OUT, f"{lg.lower()}_scores.csv")
        g.to_csv(path, index=False, lineterminator="\n")
        print(f"{os.path.relpath(path, ROOT)}: {len(g)} rows, columns: {', '.join(g.columns)}")


if __name__ == "__main__":
    main()
