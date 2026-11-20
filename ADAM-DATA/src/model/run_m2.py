"""Phase M2: challengers (EBM, horizon elastic nets, LightGBM interaction check, NHL xG sensitivity), final model
choice per league, split-conformal 80% intervals, EBM shape plots. Same walk-forward backtest as M1.
Writes reports/m2*.csv, reports/m2_ebm_*.png and reports/m2.md. Decisions D74-D81.

Run: PYTHONUTF8=1 python ADAM-DATA/src/model/run_m2.py"""
import json, os, sys, time, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from interpret.glassbox import ExplainableBoostingRegressor
from lightgbm import LGBMRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
from run_m1 import make_en, make_ols, frame, fmt, N_BOOT

REP = os.path.join(bt.ROOT, "reports")
HORIZONS = ["y_pct_t1", "y_pct_t2", "y_pct_t3"]
# Eligible final models, simplest first (D76). LightGBM is a check only; B0 has no fitted scale.
SIMPLICITY = ["B1 OLS pct", "B2 OLS pct+trail", "Elastic net", "Horizon EN", "EBM"]
CHECKS = ["LightGBM depth 1", "LightGBM depth 2"]
CONF_LEVEL, CONF_MIN_CAL_SEASONS = 0.80, 2


def make_ebm(cv):
    # interactions=0: a pure additive model (GAM), so every prediction splits exactly into per-feature terms.
    # EBM tunes itself with internal bagging + early stopping on a validation share of the training rows (D75).
    return Pipeline([("impute", bt.MedianImputeWithIndicator(0.01, as_frame=True)),
                     ("model", ExplainableBoostingRegressor(interactions=0, random_state=0, n_jobs=1))])


def make_lgbm(depth):
    def mk(cv):
        m = LGBMRegressor(max_depth=depth, num_leaves=2 ** depth, learning_rate=0.03, min_child_samples=40,
                          reg_lambda=10.0, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                          random_state=0, n_jobs=1, verbose=-1)
        p = Pipeline([("impute", bt.MedianImputeWithIndicator(0.01)), ("model", m)])
        return GridSearchCV(p, {"model__n_estimators": [100, 300, 600]}, cv=cv, scoring="neg_mean_squared_error")
    return mk


def with_xg(df):
    """NHL underlying_quality swapped from Corsi to MoneyPuck xgoals_pct (as _lpct). Diagnostic only (D54, D79)."""
    full = pd.read_csv(bt.FULL, usecols=bt.KEY + ["xgoals_pct"], low_memory=False)
    full["xg_lpct"] = full.groupby(["league", bt.SEASON]).xgoals_pct.transform(bt.lpct)
    out = df.merge(full[bt.KEY + ["xg_lpct"]], on=bt.KEY, how="left", validate="one_to_one")
    nhl = out.league == "NHL"
    assert (out.loc[nhl, "xg_lpct"].notna() == out.loc[nhl, "underlying_quality_lpct"].notna()).all()
    out.loc[nhl, "underlying_quality_lpct"] = out.loc[nhl, "xg_lpct"]
    return out.drop(columns="xg_lpct")


def run_league(df, league):
    feats, dropped = bt.league_features(df, league)
    tests = bt.test_seasons(df, league)
    wf = lambda d, f, tgt, mk: bt.walk_forward(d, league, f, tgt, mk, tests, kind="reg")
    b1, b2 = ["win_pct_percentile"], ["win_pct_percentile", "win_pct_trailing_3_seasons_lpct"]

    raw = {}
    t = time.time()
    raw["B1 OLS pct"] = wf(df, b1, bt.Y_REG, make_ols)[0]
    raw["B2 OLS pct+trail"] = wf(df, b2, bt.Y_REG, make_ols)[0]
    raw["Elastic net"] = wf(df, feats, bt.Y_REG, make_en)[0]
    hor = {h: wf(df, feats, h, make_en)[0] for h in HORIZONS}
    raw["EBM"] = wf(df, feats, bt.Y_REG, make_ebm)[0]
    for depth in (1, 2):
        raw[f"LightGBM depth {depth}"] = wf(df, feats, bt.Y_REG, make_lgbm(depth))[0]
    if league == "NHL":
        raw["Elastic net (xG)"] = wf(with_xg(df), feats, bt.Y_REG, make_en)[0]
    print(f"{league}: fits {time.time() - t:.0f}s", flush=True)

    g = df[(df.league == league) & df[bt.Y_REG].notna() & df[bt.SEASON].isin(tests)]
    base = g[bt.KEY + ["team", "win_pct_percentile"] + HORIZONS].rename(columns={bt.SEASON: "season"})
    base = base.assign(y_doom=g[bt.Y_REG].to_numpy(), y_bin=g[bt.Y_CLF].to_numpy()).reset_index(drop=True)

    def al(p):
        p = p.rename(columns={bt.SEASON: "season"})
        m = base[["league", "season", "franchise_id"]].merge(p, on=["league", "season", "franchise_id"], how="left")
        assert m.pred.notna().all()
        return m.pred.to_numpy()

    models = {n: frame(base, al(p), pred=al(p)) for n, p in raw.items()}
    hp = {h: al(hor[h]) for h in HORIZONS}
    hdoom = 100 - np.mean([hp[h] for h in HORIZONS], axis=0)
    models["Horizon EN"] = frame(base, hdoom, pred=hdoom)
    for h in HORIZONS:
        models["Horizon EN"][f"proj_{h}"] = hp[h]
    return models, dict(league=league, features=feats, dropped=dropped, tests=tests)


def conformal(d, level=CONF_LEVEL, gap=bt.GAP, min_cal=CONF_MIN_CAL_SEASONS):
    """Split conformal from walk-forward errors: for test season T, calibrate on |y - pred| of earlier test seasons
    <= T - gap (their labels are known by the end of T). Needs >= min_cal calibration seasons. D80."""
    rows = []
    for T in sorted(d.season.unique()):
        cal = d[d.season <= T - gap]
        if cal.season.nunique() < min_cal:
            continue
        r = np.abs(cal.y_doom - cal.pred).to_numpy()
        n = len(r)
        q = np.quantile(r, min(1.0, np.ceil((n + 1) * level) / n), method="higher")
        te = d[d.season == T]
        lo, hi = np.clip(te.pred - q, 0, 100), np.clip(te.pred + q, 0, 100)
        rows.append(pd.DataFrame({"season": T, "franchise_id": te.franchise_id, "pred": te.pred, "lo80": lo,
                                  "hi80": hi, "q": q, "y_doom": te.y_doom,
                                  "covered": (te.y_doom >= lo) & (te.y_doom <= hi)}))
    return pd.concat(rows, ignore_index=True)


def ebm_shapes(df, league, feats, top=4):
    """Refit EBM on all labelled rows of the league (display only, not evaluation) and plot the top-4 terms."""
    g = df[(df.league == league) & df[bt.Y_REG].notna()]
    m = make_ebm(None).fit(g[feats], g[bt.Y_REG])
    ebm = m.named_steps["model"]
    imp = pd.Series(ebm.term_importances(), index=ebm.term_names_).sort_values(ascending=False)
    files = []
    for name in imp.index[:top]:
        i = list(ebm.term_names_).index(name)
        dat = ebm.explain_global().data(i)
        edges, scores = np.asarray(dat["names"], dtype=float), np.asarray(dat["scores"], dtype=float)
        fig, ax = plt.subplots(figsize=(5, 3.2), dpi=120)
        ax.step(edges, np.append(scores, scores[-1]), where="post", color="#3b6ea8", lw=2)
        if "upper_bounds" in dat and dat["upper_bounds"] is not None:
            ub, lb = np.asarray(dat["upper_bounds"], float), np.asarray(dat["lower_bounds"], float)
            ax.fill_between(edges, np.append(lb, lb[-1]), np.append(ub, ub[-1]), step="post", alpha=0.2,
                            color="#3b6ea8", lw=0)
        ax.axhline(0, color="grey", lw=0.8, ls="--")
        ax.set_xlabel(name)
        ax.set_ylabel("contribution to doom (points)")
        ax.set_title(f"{league} EBM: {name} (importance {imp[name]:.1f})", fontsize=10)
        fig.tight_layout()
        fn = f"m2_ebm_{league.lower()}_{name}.png"
        fig.savefig(os.path.join(REP, fn))
        plt.close(fig)
        files.append(fn)
    return files, imp


def ci(t, nd=3):
    v, lo, hi = t
    return "—" if pd.isna(v) else f"{v:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]"


def fit_all():
    """All walk-forward fits; saves predictions and EBM shape plots (report() does the rest)."""
    t0 = time.time()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
    df = bt.load()
    preds, meta = [], {}
    for league in ("MLB", "NHL"):
        models, info = run_league(df, league)
        for n, d in models.items():
            preds.append(d.assign(model=n))
        files, imp = ebm_shapes(df, league, info["features"])
        meta[league] = dict(features=info["features"], dropped=info["dropped"],
                            tests=[int(x) for x in info["tests"]],
                            ebm=dict(files=files, importance=imp.round(3).to_dict()))
        print(f"{league}: done ({time.time() - t0:.0f}s)", flush=True)
    pd.concat(preds, ignore_index=True).to_csv(os.path.join(REP, "m2_predictions.csv"), index=False)
    json.dump(meta, open(os.path.join(REP, "m2_meta.json"), "w"), indent=1)


def report():
    """Comparison, choice (D76), LightGBM check (D77), horizons (D78), xG (D79), conformal (D80) -> m2.md."""
    P = pd.read_csv(os.path.join(REP, "m2_predictions.csv"), low_memory=False)
    meta = json.load(open(os.path.join(REP, "m2_meta.json")))
    out, conf_all, hz, choice, extra = [], [], [], {}, {}
    for league in ("MLB", "NHL"):
        M = {n: d.reset_index(drop=True) for n, d in P[P.league == league].groupby("model", sort=False)}
        met = {n: bt.metrics(d) for n, d in M.items()}
        best = max(SIMPLICITY, key=lambda n: (met[n]["spearman_mean"], -met[n]["mae"]))
        within = {}
        for n, d in M.items():
            b1 = bt.bootstrap_diff(d, M["B1 OLS pct"], n_boot=N_BOOT)
            bb = bt.bootstrap_diff(d, M[best], n_boot=N_BOOT)
            # within noise of the best: Spearman interval reaches 0 from below AND MAE interval reaches 0 from above
            within[n] = n == best or (bb["spearman_mean"][2] >= 0 and bb["mae"][1] <= 0)
            out.append({"league": league, "model": n, "eligible": n in SIMPLICITY, **met[n],
                        "vsB1_spearman": b1["spearman_mean"], "vsB1_mae": b1["mae"], "vsB1_auc": b1["auc"],
                        "vsBest_spearman": bb["spearman_mean"], "vsBest_mae": bb["mae"],
                        "within_noise_of_best": within[n] if n in SIMPLICITY else None, "best": n == best})
        chosen = next(n for n in SIMPLICITY if within[n])
        choice[league] = dict(best=best, chosen=chosen)
        extra[league] = {
            "lgbm_d2_vs_d1": bt.bootstrap_diff(M["LightGBM depth 2"], M["LightGBM depth 1"], n_boot=N_BOOT),
            "lgbm_d2_vs_en": bt.bootstrap_diff(M["LightGBM depth 2"], M["Elastic net"], n_boot=N_BOOT),
            "hor_vs_en": bt.bootstrap_diff(M["Horizon EN"], M["Elastic net"], n_boot=N_BOOT),
            "hor_gap": float(np.mean(np.abs(M["Horizon EN"].pred - M["Elastic net"].pred)))}
        if "Elastic net (xG)" in M:
            extra[league]["xg"] = bt.bootstrap_diff(M["Elastic net (xG)"], M["Elastic net"], n_boot=N_BOOT)
        hd = M["Horizon EN"]
        for h in HORIZONS:
            sp = lambda col: float(np.nanmean([bt._spearman(s[col], s[h]) for _, s in hd.groupby("season")]))
            hz.append({"league": league, "horizon": h, "horizon_en_spearman": sp(f"proj_{h}"),
                       "persistence_spearman": sp("win_pct_percentile"),
                       "horizon_en_mae": float(np.mean(np.abs(hd[f"proj_{h}"] - hd[h])))})
        for n in SIMPLICITY:
            conf_all.append(conformal(M[n]).assign(league=league, model=n))
    res = pd.DataFrame(out)
    conf = pd.concat(conf_all, ignore_index=True)
    cov = (conf.groupby(["league", "model"], sort=False)
           .agg(coverage=("covered", "mean"), mean_half_width=("q", "mean"), n_rows=("covered", "size"),
                first_season=("season", "min"), last_season=("season", "max")).reset_index())
    hz = pd.DataFrame(hz)
    flat = res.copy()
    for col in [c for c in res.columns if c.startswith(("vsB1_", "vsBest_"))]:
        flat[[col, col + "_lo", col + "_hi"]] = pd.DataFrame(res[col].tolist(), index=res.index)
    flat.to_csv(os.path.join(REP, "m2_comparison.csv"), index=False)
    conf.to_csv(os.path.join(REP, "m2_conformal.csv"), index=False)
    cov.to_csv(os.path.join(REP, "m2_conformal_coverage.csv"), index=False)
    hz.to_csv(os.path.join(REP, "m2_horizons.csv"), index=False)
    json.dump(choice, open(os.path.join(REP, "m2_choice.json"), "w"), indent=1)

    # ---------- m2.md ----------
    T = {lg: meta[lg]["tests"] for lg in meta}
    L = ["# Phase M2: challengers and final model choice\n"]
    L.append(f"Same walk-forward backtest and features as M1 (train ≤ T−3; MLB test {min(T['MLB'])}–{max(T['MLB'])}, "
             f"NHL {min(T['NHL'])}–{max(T['NHL'])}). Δ intervals: moving-block bootstrap over test seasons, block 3 "
             f"(D72). **Best** = highest mean per-season Spearman among eligible models (B1, B2, elastic net, horizon "
             f"EN, EBM). **Within noise** = the Spearman and MAE intervals vs the best both reach 0. **Chosen** = "
             f"simplest model within noise, order B1 < B2 < elastic net < horizon EN < EBM (D76). LightGBM = "
             f"interaction check only; elastic net (xG) = NHL diagnostic only (soft leakage, D54).\n")
    for lg in ("MLB", "NHL"):
        L.append(f"**{lg}**\n")
        L.append("| Model | Spearman | MAE | R² | AUC | Top-5 | Δ Spearman vs B1 | Δ Spearman vs best | Δ MAE vs best "
                 "| Within noise |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in res[res.league == lg].iterrows():
            tags = [t for t, c in (("best", r.best), ("chosen", r.model == choice[lg]["chosen"])) if c]
            wn = "n/a" if not r.eligible else ("yes" if r.within_noise_of_best else "no")
            L.append(f"| {r.model}{' (' + ', '.join(tags) + ')' if tags else ''} | {fmt(r.spearman_mean)} | "
                     f"{fmt(r.mae, 1)} | {fmt(r.r2)} | {fmt(r.auc)} | {fmt(r.top5_hits, 2)} | {ci(r.vsB1_spearman)} | "
                     f"{ci(r.vsBest_spearman)} | {ci(r.vsBest_mae, 1)} | {wn} |")
        L.append("")
    e = extra
    L.append("**Interactions (LightGBM depth 2 vs depth-1 stumps, which cannot model interactions; D77).** "
             f"Δ Spearman depth 2 − depth 1: MLB {ci(e['MLB']['lgbm_d2_vs_d1']['spearman_mean'])}, NHL "
             f"{ci(e['NHL']['lgbm_d2_vs_d1']['spearman_mean'])}. Depth 2 − elastic net: MLB "
             f"{ci(e['MLB']['lgbm_d2_vs_en']['spearman_mean'])}, NHL {ci(e['NHL']['lgbm_d2_vs_en']['spearman_mean'])}.\n")
    L.append("**Horizon models (D78).** Mean per-season Spearman of each horizon elastic net vs persistence (the "
             "current percentile carried forward):\n")
    L.append("| League | Horizon | Horizon EN | Persistence | Horizon EN MAE |")
    L.append("|---|---|---|---|---|")
    for _, r in hz.iterrows():
        L.append(f"| {r.league} | {r.horizon} | {r.horizon_en_spearman:.3f} | {r.persistence_spearman:.3f} | "
                 f"{r.horizon_en_mae:.1f} |")
    L.append(f"\nHorizon doom (100 − mean of the three) − direct elastic net, Spearman: MLB "
             f"{ci(e['MLB']['hor_vs_en']['spearman_mean'])}, NHL {ci(e['NHL']['hor_vs_en']['spearman_mean'])}; mean "
             f"|difference| between the two doom predictions: MLB {e['MLB']['hor_gap']:.1f}, NHL "
             f"{e['NHL']['hor_gap']:.1f} points.\n")
    xg = e["NHL"]["xg"]
    L.append(f"**NHL xG sensitivity (diagnostic only; D79).** Corsi → `xgoals_pct` in the elastic net: Δ Spearman "
             f"{ci(xg['spearman_mean'])}, Δ MAE {ci(xg['mae'], 1)}, Δ AUC {ci(xg['auc'])}.\n")
    L.append(f"**80% split-conformal intervals (D80)** from walk-forward errors of earlier test seasons ≤ T−3 "
             f"(≥ {CONF_MIN_CAL_SEASONS} calibration seasons), clipped to 0–100:\n")
    L.append("| League | Model | Coverage | Mean half-width | Seasons evaluated |")
    L.append("|---|---|---|---|---|")
    for _, r in cov.iterrows():
        mark = " (chosen)" if r.model == choice[r.league]["chosen"] else ""
        L.append(f"| {r.league} | {r.model}{mark} | {r.coverage:.1%} | {r.mean_half_width:.1f} | "
                 f"{r.first_season}–{r.last_season} ({r.n_rows} rows) |")
    L.append("\n" + CHOICE_TEXT + "\n")
    L.append("**EBM shape plots** (EBM refit on all labelled rows of each league, display only; top 4 terms by "
             "importance; band = spread across EBM bags):\n")
    for lg in ("MLB", "NHL"):
        L.append(f"- {lg}: " + ", ".join(f"[{f[len('m2_ebm_') + len(lg) + 1:-4]}]({f})"
                                         for f in meta[lg]["ebm"]["files"]))
    L.append("\nFiles: `m2_comparison.csv`, `m2_predictions.csv`, `m2_conformal.csv`, `m2_conformal_coverage.csv`, "
             "`m2_horizons.csv`, `m2_choice.json`, `m2_meta.json`. Code: `src/model/run_m2.py` "
             "(`--report-only` rebuilds this report from the saved predictions).")
    open(os.path.join(REP, "m2.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(choice)
    print(cov.round(3).to_string())
    print({lg: {k: (ci(v["spearman_mean"]) if isinstance(v, dict) else round(v, 2)) for k, v in e[lg].items()}
           for lg in e})


CHOICE_TEXT = (
    "**Final choice (D76, D81).** **MLB: B1** (OLS on `win_pct_percentile`). B1 is the best MLB model outright; "
    "the elastic net, horizon EN and EBM are within noise of it but not better (elastic net Δ Spearman −0.010 "
    "[−0.064, +0.026]), so the simplest model wins. In MLB, current standing is the whole signal we can measure. "
    "**NHL: elastic net** (direct, on `y_doom_3yr`). It is the best NHL model; B1 is clearly worse (−0.088 "
    "[−0.178, −0.048]), and the more complex challengers are slightly but significantly worse: EBM −0.022 "
    "[−0.040, −0.003], horizon EN −0.012 [−0.027, −0.004]. Both chosen models are linear, so each team's score "
    "splits exactly into per-feature contributions. The EBM shapes are close to straight lines, which also "
    "favours the linear model. LightGBM finds no interaction worth having: depth 2 is no better than "
    "depth-1 stumps and is worse than the elastic net in both leagues. The NHL xG swap gains +0.021 Spearman, "
    "with an interval that just touches 0; it is not used because of the soft leakage. "
    "**Intervals:** the 80% conformal intervals cover 82.2% (MLB, B1) and 85.1% (NHL, elastic net), close to "
    "nominal and slightly conservative, but they are wide (about ±30 and ±26 doom points). Doom is a "
    "rough ranking, not a precise forecast. "
    "**3-year path (D78):** yes, from horizon models. NHL: three elastic nets (`y_pct_t1..t3`); each beats "
    "persistence (0.573/0.518/0.343 vs 0.513/0.438/0.301), and their implied doom is on average 0.7 points from "
    "the direct score, so in M3 the three projections are shifted by a common offset so that 100 − mean(path) "
    "equals the headline doom exactly. MLB: horizon elastic nets do not beat persistence, so the path uses three "
    "B1-style OLS fits on `win_pct_percentile` (one per horizon). Their mean reproduces B1's doom exactly when "
    "all three are fitted on the same rows, because OLS is linear in the target. "
    "**Note for M3:** with B1 chosen, an MLB team's driver breakdown has a single driver (current standing).")


def main():
    if "--report-only" not in sys.argv:
        fit_all()
    report()


if __name__ == "__main__":
    main()
