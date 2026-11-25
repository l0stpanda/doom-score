"""Dashboard exports (dashboard/data/) from the slim table: fits the chosen models per league walk-forward
(backtest seasons) and on all earlier labelled seasons (live seasons), then writes predictions, intervals,
p_doom75 bands, 3-year paths, drivers, team profile and team meta. MLB = B1 (standing only), NHL = elastic net.
Key decisions: docs/DECISIONS.md.

Run: python src/export_dashboard.py   (or scripts/build_dashboard.py)"""
import os, sys, time, warnings
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as bt
from pipeline import make_en, make_ols, make_l1, make_logit_plain

ROOT = bt.ROOT
OUT = os.path.join(ROOT, "dashboard", "data")
CHOSEN = {"MLB": "B1 OLS pct", "NHL": "Elastic net"}   # model choice (D76, D86)
HORIZONS = ["y_pct_t1", "y_pct_t2", "y_pct_t3"]
LIVE = {"MLB": [2024, 2025, 2026], "NHL": [2023, 2024, 2025]}
CONF_LEVEL, CONF_MIN_CAL = 0.80, 2
BANDS = [(0.50, "Very high"), (0.30, "High"), (0.10, "Moderate"), (-np.inf, "Low")]  # on p_doom75 (D100)
NO_BAND = "Not available"
MLB_NOTE = ("MLB score uses current standing only: in backtests no other MLB feature beat it beyond noise "
            "(M1, M1b). Other numbers in the team profile are context, not drivers.")

# feature -> (phrase when above the training mean, phrase when below)  (D94)
PLAIN = {
    "win_pct_percentile": ("Strong current standing", "Weak current standing"),
    "win_pct_trailing_3_seasons_lpct": ("Strong 3-season record", "Weak 3-season record"),
    "margin_per_game_lpct": ("Outscored opponents by a wide margin", "Outscored by opponents"),
    "luck_lpct": ("Won more games than their scoring margin suggests",
                  "Won fewer games than their scoring margin suggests"),
    "underlying_quality_lpct": ("Controlled shot attempts (Corsi)", "Out-shot by opponents (Corsi)"),
    "roster_age_weighted_lpct": ("Aging roster", "Young roster"),
    "star_concentration_lpct": ("Production concentrated in a few stars", "Production spread across the roster"),
    "draft_capital_lpct": ("Many early draft picks", "Few early draft picks"),
    "gm_tenure_lpct": ("Long-tenured GM", "Recently hired GM"),
    "coach_tenure_lpct": ("Long-tenured coach", "Recently hired coach"),
    "spending_lpct": ("High payroll", "Low payroll"),
    "personnel_lead_vacant": ("GM job vacant", "GM in place"),
    "short_season": ("Shortened season", "Full-length season"),
    "seasons_of_history": ("Long franchise history", "Short franchise history (recent expansion)"),
}
PROFILE_NAME = {  # neutral names for team_profile_columns.csv
    "win_pct_percentile": "Current standing",
    "win_pct_trailing_3_seasons_lpct": "Record over the last 3 seasons",
    "margin_per_game_lpct": "Scoring margin per game",
    "luck_lpct": "Luck (wins above what the scoring margin implies)",
    "underlying_quality_lpct": "Underlying quality (MLB: Pythagorean win %; NHL: Corsi shot share)",
    "roster_age_weighted_lpct": "Roster age (weighted by playing time)",
    "star_concentration_lpct": "Reliance on the top 3 players",
    "draft_capital_lpct": "Early draft picks (rounds 1-2)",
    "gm_tenure_lpct": "GM tenure",
    "coach_tenure_lpct": "Manager / head coach tenure",
    "spending_lpct": "Payroll relative to the league (MLB only)",
}
CONTEXT_PLAIN = {"baserun_margin_lpct": "Run margin expected from hits and walks (BaseRuns)",
                 "second_half_margin_lpct": "Second-half run margin",
                 "value_age_hitters_lpct": "Age of the most productive hitters"}


MISSING_NAME = {"gm_tenure_lpct": "GM tenure", "personnel_lead_vacant": "GM status",
                "underlying_quality_lpct": "Corsi (not tracked before 2008)"}


def plain(name, z):
    if name.endswith("__missing"):
        what = MISSING_NAME.get(name[:-9], name[:-9])
        return f"{what} unknown" if z > 0 else f"{what} known"
    hi, lo = PLAIN[name]
    return hi if z > 0 else lo


def band(p):
    return NO_BAND if pd.isna(p) else next(lbl for cut, lbl in BANDS if p >= cut)


# ---------------- fitting with exact linear contributions ----------------
def fit(train, feats, target, make, gap):
    cv = bt.inner_splits(train[bt.SEASON].to_numpy(), gap=gap)
    m = make(cv).fit(train[feats], train[target])
    return getattr(m, "best_estimator_", m)


def contributions(est, X):
    """Per-feature contributions in doom points: coef_j * z_j, z = standardized (training mean/SD) value after the
    pipeline's median fill / indicators. Sum + intercept = prediction (asserted)."""
    imp, sc, mdl = est.named_steps["impute"], est.named_steps["scale"], est.named_steps["model"]
    Z = sc.transform(imp.transform(X))
    C = Z * np.ravel(mdl.coef_)
    pred = est.predict(X)
    assert np.allclose(C.sum(axis=1) + mdl.intercept_, pred, atol=1e-8)
    return pred, C, Z, list(imp.get_feature_names_out())


def run_league(df, league, feats, chosen):
    g = df[df.league == league].copy()
    tests = bt.test_seasons(df, league)
    mk_doom, f_doom = (make_ols, ["win_pct_percentile"]) if chosen == "B1 OLS pct" else (make_en, feats)
    mk_clf, f_clf = (make_logit_plain, ["win_pct_percentile"]) if chosen == "B1 OLS pct" else (make_l1, feats)
    mk_hor, f_hor = mk_doom, f_doom
    rows, drivers = [], []

    def predict_block(T, pred_type):
        te = g[g[bt.SEASON] == T].reset_index(drop=True)
        last_lab = (T - bt.GAP) if pred_type == "backtest" else max(tests_all_lab)
        tr = g[g[bt.Y_REG].notna() & (g[bt.SEASON] <= last_lab)]
        assert tr[bt.SEASON].max() <= (T - bt.GAP if pred_type == "backtest" else T - 1)
        est = fit(tr, f_doom, bt.Y_REG, mk_doom, bt.GAP)
        pred, C, Z, names = contributions(est, te[f_doom])
        # B1 (standing only) on the same training rows, for the dashboard's "doom vs. standing" view (D102)
        b1 = fit(tr, ["win_pct_percentile"], bt.Y_REG, make_ols, bt.GAP).predict(te[["win_pct_percentile"]])
        trc = g[g[bt.Y_CLF].notna() & (g[bt.SEASON] <= last_lab)]
        p_doom = fit(trc, f_clf, bt.Y_CLF, mk_clf, bt.GAP).predict_proba(te[f_clf])[:, 1]
        proj = []
        for k, h in enumerate(HORIZONS, 1):
            # gap = horizon (D87); live: seasons before the first live season only (D92)
            lim = T - k if pred_type == "backtest" else min(LIVE[league]) - 1
            trh = g[g[h].notna() & (g[bt.SEASON] <= min(lim, T - k))]
            assert trh[bt.SEASON].max() <= T - k
            proj.append(fit(trh, f_hor, h, mk_hor, k).predict(te[f_hor]))
        out = te[bt.KEY + ["team", "wins", "losses", "ot_losses", "games", "win_pct", "win_pct_percentile"]].copy()
        out["doom_pred"], out["p_doomed"], out["pred_type"] = pred, p_doom, pred_type
        out["b1_pred"] = b1
        out["doom_vs_standing"] = pred - b1
        for h, p in zip(HORIZONS, proj):
            out[f"raw_proj_{h[2:]}"] = p
        out["actual_doom"] = te[bt.Y_REG].to_numpy()
        for h in HORIZONS:
            out[f"actual_{h[2:]}"] = te[h].to_numpy()
        for i in range(len(te)):
            for j, n in enumerate(names):
                drivers.append({"league": league, "season_start_year": T, "franchise_id": te.franchise_id[i],
                                "pred_type": pred_type, "feature": n, "z": Z[i, j], "contribution": C[i, j]})
        rows.append(out)

    tests_all_lab = sorted(g[g[bt.Y_REG].notna()][bt.SEASON].unique())
    for T in tests:
        predict_block(T, "backtest")
    for T in LIVE[league]:
        assert g[g[bt.SEASON] == T][bt.Y_REG].isna().all()
        predict_block(T, "live")
    return pd.concat(rows, ignore_index=True), pd.DataFrame(drivers), tests


def conformal_q(bt_rows, T, level=CONF_LEVEL):
    """q for season T from backtest residuals of seasons <= T-3 (labels known by the end of T); D80."""
    cal = bt_rows[bt_rows.season_start_year <= T - bt.GAP]
    if cal.season_start_year.nunique() < CONF_MIN_CAL:
        return np.nan
    r = np.abs(cal.actual_doom - cal.doom_pred).to_numpy()
    n = len(r)
    return float(np.quantile(r, min(1.0, np.ceil((n + 1) * level) / n), method="higher"))


def cal_residuals(bt_rows, T):
    """Signed walk-forward residuals (actual - predicted doom) of backtest seasons <= T-3, the same calibration set
    as the conformal intervals (D80); None if fewer than CONF_MIN_CAL seasons."""
    cal = bt_rows[bt_rows.season_start_year <= T - bt.GAP]
    if cal.season_start_year.nunique() < CONF_MIN_CAL:
        return None
    return (cal.actual_doom - cal.doom_pred).to_numpy()


def finish(P):
    """Conformal intervals, p_doom75 (D99), path shift + clip (D88), bands on p_doom75 (D100)."""
    P = P.copy()
    P["p_doom75"] = np.nan
    for lg in P.league.unique():
        b = P[(P.league == lg) & (P.pred_type == "backtest")]
        for T in P[P.league == lg].season_start_year.unique():
            q = conformal_q(b, T)
            m = (P.league == lg) & (P.season_start_year == T)
            P.loc[m, "doom_lo80"] = np.clip(P.loc[m, "doom_pred"] - q, 0, 100)
            P.loc[m, "doom_hi80"] = np.clip(P.loc[m, "doom_pred"] + q, 0, 100)
            r = cal_residuals(b, T)
            if r is not None:
                # P(actual >= 75 | predicted d) = share of calibration residuals >= 75 - d
                d = P.loc[m, "doom_pred"].to_numpy()
                P.loc[m, "p_doom75"] = (r[None, :] >= (75 - d)[:, None]).mean(axis=1)
    P["interval_available"] = P.doom_lo80.notna().astype(int)
    assert (P.interval_available == P.p_doom75.notna()).all()
    raw = P[[f"raw_proj_pct_t{k}" for k in (1, 2, 3)]].to_numpy()
    off = (100 - P.doom_pred.to_numpy()) - raw.mean(axis=1)
    shifted = raw + off[:, None]
    P["path_clipped"] = ((shifted < 0) | (shifted > 100)).any(axis=1)
    shifted = np.clip(shifted, 0, 100)
    for k in (1, 2, 3):
        P[f"proj_pct_t{k}"] = shifted[:, k - 1]
    P["path_offset"] = off
    P["doom_band"] = [band(x) for x in P.p_doom75]
    return P


def calibration(P, n_bins=10):
    """Backtest rows with p_doom75 and a label: predicted probability by decile vs observed rate, per league."""
    rows = []
    for lg in ("MLB", "NHL"):
        d = P[(P.league == lg) & (P.pred_type == "backtest") & P.p_doom75.notna() & P.actual_doom.notna()].copy()
        d["obs"] = (d.actual_doom >= 75).astype(float)
        d["decile"] = pd.qcut(d.p_doom75.rank(method="first"), n_bins, labels=False) + 1
        for k, g in d.groupby("decile"):
            rows.append({"league": lg, "decile": int(k), "n": len(g), "p_min": g.p_doom75.min(),
                         "p_max": g.p_doom75.max(), "mean_predicted": g.p_doom75.mean(), "observed_rate": g.obs.mean()})
    return pd.DataFrame(rows)


def band_check(P):
    order = ["Low", "Moderate", "High", "Very high", NO_BAND]
    rows = []
    for lg in ("MLB", "NHL"):
        for b in order:
            g = P[(P.league == lg) & (P.doom_band == b)]
            lab = g[g.actual_doom.notna()]
            rows.append({"league": lg, "band": b, "rows": len(g), "labelled": len(lab),
                         "share_actual_ge75": float((lab.actual_doom >= 75).mean()) if len(lab) else np.nan})
    return pd.DataFrame(rows)


def brier(P):
    out = {}
    for lg in ("MLB", "NHL"):
        d = P[(P.league == lg) & (P.pred_type == "backtest") & P.p_doom75.notna() & P.actual_doom.notna()]
        y = (d.actual_doom >= 75).astype(float)
        out[lg] = dict(n=len(d), base_rate=float(y.mean()), p_doom75=float(((d.p_doom75 - y) ** 2).mean()),
                       p_doomed=float(((d.p_doomed - y) ** 2).mean()), climatology=float(((y.mean() - y) ** 2).mean()))
    return out


def driver_text(D, P):
    D = D.copy()
    D["feature_label"] = [plain(f, z) for f, z in zip(D.feature, D.z)]
    D["text"] = [f"{l} ({c:+.1f})" for l, c in zip(D.feature_label, D.contribution)]
    up, down = {}, {}
    for key, g in D.groupby(["league", "season_start_year", "franchise_id"]):
        g = g[g.contribution.abs() >= 0.05]
        up[key] = g[g.contribution > 0].nlargest(3, "contribution").text.tolist()
        down[key] = g[g.contribution < 0].nsmallest(3, "contribution").text.tolist()
    keys = list(zip(P.league, P.season_start_year, P.franchise_id))
    for i in range(3):
        P[f"driver_up_{i + 1}"] = [up.get(k, [])[i] if len(up.get(k, [])) > i else "" for k in keys]
        P[f"driver_down_{i + 1}"] = [down.get(k, [])[i] if len(down.get(k, [])) > i else "" for k in keys]
    P["driver_note"] = np.where(P.league == "MLB", MLB_NOTE, "")
    return D, P


def team_meta(df):
    """Current logo and source team id per franchise (last season's row; logo_url stored in the slim table, D98)."""
    last = df.sort_values(bt.SEASON).groupby(["league", "franchise_id"]).tail(1)
    rows = [{"league": r.league, "franchise_id": r.franchise_id, "team": r.team, "logo_url": r.logo_url,
             "team_id": int(r.team_id)} for _, r in last.iterrows()]
    return pd.DataFrame(rows).sort_values(["league", "franchise_id"])


def team_profile(df):
    prof_cols = list(PLAIN)[:11]                       # standing, trajectory and the nine concept percentiles
    p = df[bt.KEY + ["team"] + prof_cols + list(CONTEXT_PLAIN)].copy()   # MLB context columns: NaN for NHL
    p["profile_role"] = "context"
    dic = [{"column": c, "plain_name": PROFILE_NAME[c],
            "scale": "within-league-season percentile, 0 = lowest, 100 = highest",
            "used_by_model": {"MLB": "yes" if c == "win_pct_percentile" else "no",
                              "NHL": "n/a (no NHL spending data)" if c == "spending_lpct" else "yes"}}
           for c in prof_cols]
    dic = [dict(d, used_by_mlb_model=d["used_by_model"]["MLB"], used_by_nhl_model=d["used_by_model"]["NHL"])
           for d in dic]
    dic += [{"column": c, "plain_name": n, "scale": "within-league-season percentile (MLB only)",
             "used_by_mlb_model": "no", "used_by_nhl_model": "n/a"} for c, n in CONTEXT_PLAIN.items()]
    dic = pd.DataFrame(dic).drop(columns="used_by_model")
    dic["note"] = "Context only; drivers come from doom_drivers_long.csv"
    return p, dic


def main():
    t0 = time.time()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
    os.makedirs(OUT, exist_ok=True)
    df = bt.load()
    Ps, Ds = [], []
    for lg in ("MLB", "NHL"):
        feats, _ = bt.league_features(df, lg)
        P, D, _ = run_league(df, lg, feats, CHOSEN[lg])
        Ps.append(P); Ds.append(D)
        print(f"{lg}: {time.time() - t0:.0f}s", flush=True)
    P = finish(pd.concat(Ps, ignore_index=True))
    D, P = driver_text(pd.concat(Ds, ignore_index=True), P)

    cols = (["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ot_losses", "games",
             "win_pct", "win_pct_percentile", "doom_pred", "doom_lo80", "doom_hi80", "interval_available", "p_doom75",
             "doom_band", "p_doomed", "b1_pred", "doom_vs_standing",
             "proj_pct_t1", "proj_pct_t2", "proj_pct_t3", "path_clipped", "pred_type", "actual_doom",
             "actual_pct_t1", "actual_pct_t2", "actual_pct_t3"]
            + [f"driver_up_{i}" for i in (1, 2, 3)] + [f"driver_down_{i}" for i in (1, 2, 3)] + ["driver_note"])
    P = P.sort_values(["league", "season_start_year", "doom_pred"], ascending=[True, True, False])
    P[cols].to_csv(os.path.join(OUT, "doom_predictions.csv"), index=False)
    D[["league", "season_start_year", "franchise_id", "pred_type", "feature", "feature_label", "z",
       "contribution"]].to_csv(os.path.join(OUT, "doom_drivers_long.csv"), index=False)
    team_meta(df).to_csv(os.path.join(OUT, "team_meta.csv"), index=False)
    prof, dic = team_profile(df)
    prof.to_csv(os.path.join(OUT, "team_profile.csv"), index=False)
    dic.to_csv(os.path.join(OUT, "team_profile_columns.csv"), index=False)

    # summary for the console (format of reports/RESULTS.md section 4)
    path_err = np.abs(100 - P[["proj_pct_t1", "proj_pct_t2", "proj_pct_t3"]].mean(axis=1) - P.doom_pred)
    print(f"rows {len(P)} (backtest {int((P.pred_type == 'backtest').sum())}, live {int((P.pred_type == 'live').sum())});"
          f" path max error (unclipped) {path_err[~P.path_clipped].max():.1e}; clipped {int(P.path_clipped.sum())};"
          f" no interval {int(P.doom_lo80.isna().sum())}")
    for lg, v in brier(P).items():
        print(f"Brier {lg}: p_doom75 {v['p_doom75']:.3f}, p_doomed {v['p_doomed']:.3f}, base rate only "
              f"{v['climatology']:.3f} (n = {v['n']})")
    print(calibration(P).round(3).to_string(index=False))
    print(band_check(P).round(3).to_string(index=False))
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
