"""dashboard/data/comparables.csv: for every exported team-season, the 3 most similar earlier team-seasons in the
same league whose 3-year outcome was already known at prediction time (seasons <= T-3). Decision D103.

Similarity = root-mean-square difference over the team-profile percentile columns both rows have (percentile
points; lower = more similar). Columns: the league's profile percentiles (team_profile.csv) excluding MLB
underlying_quality (a near-duplicate of margin, D63) and NHL spending (unavailable). Context only, not a model input.
Run: python src/build_comparables.py"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
DATA = os.path.join(ROOT, "dashboard", "data")
SLIM = os.path.join(ROOT, "data", "mlb_nhl_model_slim.csv")
KEY = ["league", "season_start_year", "franchise_id"]
GAP, K = 3, 3
BASE = ["win_pct_percentile", "win_pct_trailing_3_seasons_lpct", "margin_per_game_lpct", "luck_lpct",
        "underlying_quality_lpct", "roster_age_weighted_lpct", "star_concentration_lpct", "draft_capital_lpct",
        "gm_tenure_lpct", "coach_tenure_lpct", "spending_lpct"]
COLS = {"MLB": [c for c in BASE if c != "underlying_quality_lpct"]
               + ["baserun_margin_lpct", "second_half_margin_lpct", "value_age_hitters_lpct"],
        "NHL": [c for c in BASE if c != "spending_lpct"]}


def main():
    prof = pd.read_csv(os.path.join(DATA, "team_profile.csv"))
    pred = pd.read_csv(os.path.join(DATA, "doom_predictions.csv"))
    slim = pd.read_csv(SLIM, usecols=KEY + ["team", "y_doom_3yr", "y_pct_t1", "y_pct_t2", "y_pct_t3", "wins",
                                             "losses", "ot_losses"])
    pool = prof.merge(slim.drop(columns="team"), on=KEY, how="left")
    out = []
    for lg in ("MLB", "NHL"):
        cols = COLS[lg]
        P = pool[pool.league == lg].reset_index(drop=True)
        X = P[cols].to_numpy(dtype=float)
        lab = P.y_doom_3yr.notna().to_numpy()
        seasons = P.season_start_year.to_numpy()
        for _, r in pred[pred.league == lg].iterrows():
            i = P.index[(P.season_start_year == r.season_start_year) & (P.franchise_id == r.franchise_id)][0]
            cand = np.where(lab & (seasons <= r.season_start_year - GAP))[0]
            assert seasons[cand].max() <= r.season_start_year - GAP
            diff = X[cand] - X[i]
            ok = ~np.isnan(diff)
            dist = np.sqrt(np.where(ok, diff ** 2, 0).sum(axis=1) / np.maximum(ok.sum(axis=1), 1))
            dist[ok.sum(axis=1) < len(cols) // 2] = np.inf          # need at least half the columns in common
            for rank, j in enumerate(cand[np.argsort(dist, kind="stable")[:K]], 1):
                c = P.loc[j]
                out.append({"league": lg, "season_start_year": r.season_start_year, "franchise_id": r.franchise_id,
                            "comp_rank": rank, "comp_season": int(c.season_start_year),
                            "comp_franchise_id": c.franchise_id, "comp_team": c.team,
                            "comp_wins": int(c.wins), "comp_losses": int(c.losses),
                            "comp_ot_losses": None if pd.isna(c.ot_losses) else int(c.ot_losses),
                            "distance": round(float(dist[list(cand).index(j)]), 2),
                            "comp_win_pct_percentile": c.win_pct_percentile, "comp_actual_doom": c.y_doom_3yr,
                            "comp_pct_t1": c.y_pct_t1, "comp_pct_t2": c.y_pct_t2, "comp_pct_t3": c.y_pct_t3,
                            "features_compared": len(cols)})
    df = pd.DataFrame(out)
    df.to_csv(os.path.join(DATA, "comparables.csv"), index=False, lineterminator="\n")
    print(df.shape, df.distance.describe().round(1).to_dict())


if __name__ == "__main__":
    main()
