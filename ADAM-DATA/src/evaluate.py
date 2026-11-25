"""Recompute the headline out-of-sample results from the exported predictions -> reports/results_summary.csv.

    python src/evaluate.py

Input: dashboard/data/doom_predictions.csv (written by scripts/build_dashboard.py). Uses the walk-forward backtest
rows with a known outcome (MLB 2008-2023, NHL 2013-14 to 2022-23). For each league, the final model (`doom_pred`)
and the standings-only baseline B1 (`b1_pred`; for MLB they are the same model):
- spearman: rank correlation of predicted vs actual doom, mean over test seasons (as in reports/RESULTS.md);
- mae: mean absolute error in doom points;
- auc: area under the ROC curve for doom >= 75;
- top5: of each season's 5 most-doomed predictions, how many finished doom >= 75 (mean over seasons);
- cov80, halfwidth80: share of actual outcomes inside the 80% interval, and its mean half-width (rows with one);
- brier: Brier score of p_doom75 for doom >= 75 (rows with one).
The full metrics, bootstrap intervals and phase reports are in tag adam-full-pipeline (reports/).
"""
import os
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
PRED = os.path.join(ROOT, "dashboard", "data", "doom_predictions.csv")
OUT = os.path.join(ROOT, "reports", "results_summary.csv")
FINAL = {"MLB": "B1: current standings only", "NHL": "Elastic net (13 features)"}


def metrics(g, col):
    y, p, hit = g.actual_doom, g[col], g.actual_doom >= 75
    sp = g.groupby("season_start_year").apply(lambda s: s[col].corr(s.actual_doom, method="spearman"), include_groups=False)
    top5 = g.groupby("season_start_year").apply(lambda s: (s.nlargest(5, col).actual_doom >= 75).sum(), include_groups=False)
    return {"spearman": sp.mean(), "mae": (p - y).abs().mean(), "auc": roc_auc_score(hit, p), "top5": top5.mean()}


def main():
    P = pd.read_csv(PRED)
    B = P[(P.pred_type == "backtest") & P.actual_doom.notna()]
    rows = []
    for lg, g in B.groupby("league"):
        iv = g[g.interval_available == 1]
        pr = g[g.p_doom75.notna()]
        base = {"league": lg, "test_seasons": f"{g.season_start_year.min()}-{g.season_start_year.max()}",
                "n_seasons": g.season_start_year.nunique(), "n_team_seasons": len(g)}
        final = {**base, "model": FINAL.get(lg, "final"), "role": "final", **metrics(g, "doom_pred"),
                 "cov80": ((iv.actual_doom >= iv.doom_lo80) & (iv.actual_doom <= iv.doom_hi80)).mean(),
                 "halfwidth80": ((iv.doom_hi80 - iv.doom_lo80) / 2).mean(), "n_interval": len(iv),
                 "brier": ((pr.p_doom75 - (pr.actual_doom >= 75)) ** 2).mean(), "n_brier": len(pr)}
        rows.append(final)
        if not np.allclose(g.doom_pred, g.b1_pred):
            rows.append({**base, "model": "B1: current standings only", "role": "baseline", **metrics(g, "b1_pred")})
    R = pd.DataFrame(rows)
    R[["n_interval", "n_brier"]] = R[["n_interval", "n_brier"]].astype("Int64")
    R.to_csv(OUT, index=False, float_format="%.3f", lineterminator="\n")
    pd.set_option("display.width", 200)
    print(R.round(3).to_string(index=False))
    print(f"-> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
