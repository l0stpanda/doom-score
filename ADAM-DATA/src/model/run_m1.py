"""Phase M1: walk-forward backtest of baselines (B0-B2), elastic net (y_doom_3yr) and L1 logistic
(y_doomed_bottom25), one model per league. Writes reports/m1*.csv and reports/m1.md. Decisions D62-D70.

Run: PYTHONUTF8=1 python ADAM-DATA/src/model/run_m1.py"""
import os, sys, time, warnings
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNet, LinearRegression, LogisticRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt

REP = os.path.join(bt.ROOT, "reports")
N_BOOT = 2000

EN_GRID = {"model__alpha": np.logspace(-2, 1.5, 15), "model__l1_ratio": [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]}
L1_GRID = {"model__C": np.logspace(-3, 1, 15)}


def pipe(model):
    return Pipeline([("impute", bt.MedianImputeWithIndicator(0.01)), ("scale", StandardScaler()), ("model", model)])


def make_ols(cv):
    return pipe(LinearRegression())


def make_logit_plain(cv):
    return pipe(LogisticRegression(C=np.inf, max_iter=5000))


def make_en(cv):
    return GridSearchCV(pipe(ElasticNet(max_iter=100000)), EN_GRID, cv=cv, scoring="neg_mean_squared_error")


def make_l1(cv):
    return GridSearchCV(pipe(LogisticRegression(l1_ratio=1.0, solver="saga", max_iter=20000, random_state=0)), L1_GRID, cv=cv,
                        scoring="neg_log_loss")


def frame(base, score, pred=None, prob=None):
    d = base.copy()
    d["score"] = score
    d["pred"] = np.nan if pred is None else pred
    d["prob"] = np.nan if prob is None else prob
    return d


def run_league(df, run, league, start=None):
    sub = df if start is None else df[df[bt.SEASON] >= start]
    feats, dropped = bt.league_features(sub, league)
    tests = bt.test_seasons(sub, league)
    wf = lambda f, tgt, mk, kind: bt.walk_forward(sub, league, f, tgt, mk, tests, kind=kind)

    b1 = ["win_pct_percentile"]
    b2 = b1 + ["win_pct_trailing_3_seasons_lpct"]
    p_b1, _, _ = wf(b1, bt.Y_REG, make_ols, "reg")
    c_b1, _, _ = wf(b1, bt.Y_CLF, make_logit_plain, "clf")
    p_b2, _, _ = wf(b2, bt.Y_REG, make_ols, "reg")
    c_b2, _, _ = wf(b2, bt.Y_CLF, make_logit_plain, "clf")
    p_en, k_en, h_en = wf(feats, bt.Y_REG, make_en, "reg")
    c_l1, k_l1, h_l1 = wf(feats, bt.Y_CLF, make_l1, "clf")

    g = sub[(sub.league == league) & sub[bt.Y_REG].notna() & sub[bt.SEASON].isin(tests)]
    base = g[bt.KEY + ["win_pct_percentile"]].rename(columns={bt.SEASON: "season"}).copy()
    base["y_doom"], base["y_bin"] = g[bt.Y_REG].to_numpy(), g[bt.Y_CLF].to_numpy()
    base = base.reset_index(drop=True)

    def al(p):  # align predictions to base row order
        p = p.rename(columns={bt.SEASON: "season"})
        m = base[["league", "season", "franchise_id"]].merge(p, on=["league", "season", "franchise_id"], how="left")
        assert m.pred.notna().all()
        return m.pred.to_numpy()

    b0 = 100 - base.win_pct_percentile.to_numpy()
    models = {
        "B0 100-pct": frame(base, b0, pred=b0),
        "B1 OLS pct": frame(base, al(p_b1), pred=al(p_b1), prob=al(c_b1)),
        "B2 OLS pct+trail": frame(base, al(p_b2), pred=al(p_b2), prob=al(c_b2)),
        "Elastic net": frame(base, al(p_en), pred=al(p_en)),
        "L1 logistic": frame(base, al(c_l1), prob=al(c_l1)),
    }
    rows = []
    for name, d in models.items():
        m = bt.metrics(d)
        diff = bt.bootstrap_diff(d, models["B1 OLS pct"], n_boot=N_BOOT) if name != "B1 OLS pct" else {}
        row = {"run": run, "league": league, "model": name, "test_first": min(tests), "test_last": max(tests),
               "n_test_rows": len(d), **m}
        for k, (v, lo, hi) in diff.items():
            row.update({f"d_{k}": v, f"d_{k}_lo": lo, f"d_{k}_hi": hi})
        rows.append(row)
    preds = pd.concat([d.assign(run=run, model=n) for n, d in models.items()], ignore_index=True)
    coefs = pd.concat([k_en.assign(model="Elastic net"), k_l1.assign(model="L1 logistic")]).assign(run=run)
    params = pd.concat([h_en.assign(model="Elastic net"), h_l1.assign(model="L1 logistic")]).assign(run=run)
    info = dict(run=run, league=league, features=feats, dropped=dropped, tests=tests)
    return pd.DataFrame(rows), preds, coefs, params, info


def fmt(v, nd=3):
    return "—" if pd.isna(v) else f"{v:.{nd}f}"


def fdiff(r, k, nd=3):
    v = r.get(f"d_{k}")
    if pd.isna(v):
        return "—"
    return f"{v:+.{nd}f} [{r[f'd_{k}_lo']:+.{nd}f}, {r[f'd_{k}_hi']:+.{nd}f}]"


FINDINGS = (
    "**MLB: the features do not beat current standing alone.** The elastic net's per-season Spearman is 0.404 vs "
    "0.414 for B1 (Δ −0.010, interval −0.049 to +0.024), its MAE is 0.3 points worse, and the L1 logistic is "
    "slightly worse than B1 on AUC and Brier. The regularization agrees: most MLB coefficients are exactly 0 in "
    "most folds, and only run margin (−5.1 doom points per SD) is used every time. In MLB, doom is almost entirely "
    "\"how good are you now\", and run margin is a slightly better measure of that than the record. "
    "**NHL: the features help, clearly but modestly.** Elastic net Spearman 0.607 vs 0.519 (+0.088 [+0.038, "
    "+0.148]), MAE −1.2 points [−2.1, −0.3], AUC +0.033 [+0.007, +0.060]. The L1 logistic gains less, and its "
    "Brier interval includes 0. The NHL signal is stable: Corsi, margin, trailing record, roster age (older → more "
    "doom, +2.9), star concentration and draft capital never change sign across folds. Top-5 hit rates (about 2 of "
    "5 in both leagues) do not improve significantly anywhere. Training NHL on 2008+ only is not better (Spearman "
    "0.614 vs 0.634 on 2016–22), so the fill-plus-indicator default stays. **Caveats:** there are only 16 MLB and "
    "10 NHL test seasons, and labels of adjacent seasons share up to two future seasons, so the season-bootstrap "
    "intervals are probably somewhat too narrow.")


def main():
    t0 = time.time()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    df = bt.load()
    runs = [("MLB", "MLB", None), ("NHL", "NHL", None), ("NHL 2008+", "NHL", 2008)]
    out = [run_league(df, *r) for r in runs]
    met = pd.concat([o[0] for o in out], ignore_index=True)
    preds = pd.concat([o[1] for o in out], ignore_index=True)
    coefs = pd.concat([o[2] for o in out], ignore_index=True)
    params = pd.concat([o[3] for o in out], ignore_index=True)
    infos = {o[4]["run"]: o[4] for o in out}
    stab = pd.concat([bt.coef_stability(g).assign(run=r, model=m) for (r, m), g in coefs.groupby(["run", "model"])],
                     ignore_index=True)

    # NHL main model on the NHL 2008+ test range, for a like-for-like comparison
    rng = infos["NHL 2008+"]["tests"]
    cmp_rows = []
    for run in ("NHL", "NHL 2008+"):
        for model in ("B1 OLS pct", "Elastic net", "L1 logistic"):
            d = preds[(preds.run == run) & (preds.model == model) & preds.season.isin(rng)]
            cmp_rows.append({"run": run, "model": model, **bt.metrics(d)})
    cmp = pd.DataFrame(cmp_rows)

    # MLB: how close is the excluded underlying_quality (Pythagorean win%) to margin_per_game?
    mlb = df[df.league == "MLB"]
    rho_uq = mlb.underlying_quality_lpct.corr(mlb.margin_per_game_lpct, method="spearman")

    met.to_csv(os.path.join(REP, "m1_metrics.csv"), index=False)
    preds.to_csv(os.path.join(REP, "m1_predictions.csv"), index=False)
    coefs.to_csv(os.path.join(REP, "m1_coefs_by_fold.csv"), index=False)
    stab.to_csv(os.path.join(REP, "m1_coef_stability.csv"), index=False)
    params.to_csv(os.path.join(REP, "m1_hyperparams.csv"), index=False)
    cmp.to_csv(os.path.join(REP, "m1_nhl2008_comparison.csv"), index=False)

    # ---------- report ----------
    L = []
    L.append("# Phase M1: walk-forward backtest, baselines, main models\n")
    ranges = "; ".join(f"{r}: test {min(i['tests'])}–{max(i['tests'])} ({len(i['tests'])} seasons)"
                       for r, i in infos.items())
    L.append(f"Data `mlb_nhl_model_slim.csv` (+ `personnel_lead_vacant`, D62). Walk-forward: test season T is "
             f"predicted from seasons ≤ T−3 (asserted); preprocessing in a Pipeline; tuning on an inner time split "
             f"with the same gap (D64–D66). {ranges}. Dropped: MLB `underlying_quality_lpct` (spec; Spearman "
             f"{rho_uq:.2f} with margin, D63), NHL `spending_lpct` (all missing). Missing indicators are created "
             f"per fold for features missing in >1% of training rows (D67). Δ = model − B1, 95% interval from "
             f"{N_BOOT} bootstrap draws of test seasons. Top-5 = mean bottom-quarter hits among each season's 5 "
             f"most-doomed predictions (of 5).\n")
    L.append("| League | Model | Spearman mean | Spearman pooled | MAE | R² | AUC | Brier | Top-5 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for _, r in met.iterrows():
        L.append(f"| {r.run} | {r.model} | {fmt(r.spearman_mean)} | {fmt(r.spearman_pooled)} | {fmt(r.mae, 1)} | "
                 f"{fmt(r.r2)} | {fmt(r.auc)} | {fmt(r.brier)} | {fmt(r.top5_hits, 2)} |")
    L.append("\n**Difference from B1 [95% CI]**\n")
    L.append("| League | Model | ΔSpearman mean | ΔMAE | ΔAUC | ΔBrier | ΔTop-5 |")
    L.append("|---|---|---|---|---|---|---|")
    for _, r in met[met.model != "B1 OLS pct"].iterrows():
        L.append(f"| {r.run} | {r.model} | {fdiff(r, 'spearman_mean')} | {fdiff(r, 'mae', 1)} | {fdiff(r, 'auc')} | "
                 f"{fdiff(r, 'brier')} | {fdiff(r, 'top5_hits', 2)} |")
    L.append("\n**Elastic net standardized coefficients across folds** (doom points per SD; median [min, max], "
             "% folds at 0, % non-zero folds with the minority sign). L1 logistic: `m1_coef_stability.csv`.\n")
    en = stab[stab.model == "Elastic net"]
    feats = list(dict.fromkeys(en[en.run == "MLB"].feature.tolist() + en[en.run == "NHL"].feature.tolist()))
    L.append("| Feature | MLB | NHL |")
    L.append("|---|---|---|")
    for f in feats:
        cells = []
        for run in ("MLB", "NHL"):
            s = en[(en.run == run) & (en.feature == f)]
            if s.empty:
                cells.append("—")
            else:
                s = s.iloc[0]
                cells.append(f"{s['median']:+.1f} [{s['min']:+.1f}, {s['max']:+.1f}], 0: {s.zero_share:.0%}, "
                             f"flip: {s.opposite_sign_share:.0%}")
        L.append(f"| `{f}` | {cells[0]} | {cells[1]} |")
    c = cmp.set_index(["run", "model"])
    L.append(f"\n**NHL trained on 2008+ only** (no Corsi gap), compared on its test range {min(rng)}–{max(rng)}: "
             + "; ".join(f"{m}: Spearman mean {c.loc[('NHL', m), 'spearman_mean']:.3f} (all seasons) vs "
                         f"{c.loc[('NHL 2008+', m), 'spearman_mean']:.3f} (2008+)"
                         for m in ("Elastic net", "L1 logistic")) + ". Full table: `m1_nhl2008_comparison.csv`.\n")
    L.append("**Findings.** " + FINDINGS + "\n")
    L.append("Files: `m1_metrics.csv`, `m1_predictions.csv`, `m1_coefs_by_fold.csv`, `m1_coef_stability.csv`, "
             "`m1_hyperparams.csv`, `m1_nhl2008_comparison.csv`. Code: `src/model/backtest.py`, `src/model/run_m1.py`.")
    open(os.path.join(REP, "m1.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(met[["run", "model"] + bt.METRICS].round(3).to_string())
    print(cmp.round(3).to_string())
    print(f"rho(uq, margin) MLB = {rho_uq:.3f}; {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
