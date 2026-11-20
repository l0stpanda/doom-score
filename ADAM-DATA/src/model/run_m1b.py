"""Phase M1b: pre-registered MLB feature test (reports/m1b_preregistration.md) + horizon models with training
gap = horizon. Writes reports/m1b*.csv and reports/m1b.md. Decisions D82-D88.

Run: PYTHONUTF8=1 python ADAM-DATA/src/model/run_m1b.py"""
import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
from run_m1 import make_en, make_ols, frame, fmt, N_BOOT
import run_m2

REP = os.path.join(bt.ROOT, "reports")
FEAT_FILE = os.path.join(bt.ROOT, "data", "processed", "mlb_m1b_features.csv")
NEW = ["second_half_margin", "baserun_margin", "sequencing_luck", "value_age_hitters", "value_age_pitchers",
       "farm_strength"]
NEW_LPCT = [f"{c}_lpct" for c in NEW]
EXPECTED = {"second_half_margin": "−", "baserun_margin": "−", "sequencing_luck": "+", "value_age_hitters": "+",
            "value_age_pitchers": "+", "farm_strength": "−"}
HORIZONS = ["y_pct_t1", "y_pct_t2", "y_pct_t3"]


def ci(t, nd=3):
    v, lo, hi = t
    return "—" if pd.isna(v) else f"{v:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]"


def load():
    df = bt.load()
    f = pd.read_csv(FEAT_FILE)
    df = df.merge(f[bt.KEY + NEW_LPCT], on=bt.KEY, how="left", validate="one_to_one")
    return df


def base_frame(df, league, tests):
    g = df[(df.league == league) & df[bt.Y_REG].notna() & df[bt.SEASON].isin(tests)]
    b = g[bt.KEY + ["win_pct_percentile"] + HORIZONS].rename(columns={bt.SEASON: "season"})
    return b.assign(y_doom=g[bt.Y_REG].to_numpy(), y_bin=g[bt.Y_CLF].to_numpy()).reset_index(drop=True)


def align(base, p):
    p = p.rename(columns={bt.SEASON: "season"})
    m = base[["league", "season", "franchise_id"]].merge(p, on=["league", "season", "franchise_id"], how="left")
    assert m.pred.notna().all()
    return m.pred.to_numpy()


def partial_spearman(d, x, y="y_doom_3yr", ctrl="win_pct_percentile"):
    """D55: Pearson of residuals of rank(x) and rank(y) after OLS on rank(ctrl)."""
    d = d[[x, y, ctrl]].dropna()
    r = d.rank()
    Z = np.column_stack([np.ones(len(r)), r[ctrl]])
    res = lambda v: v - Z @ np.linalg.lstsq(Z, v, rcond=None)[0]
    return float(np.corrcoef(res(r[x].to_numpy()), res(r[y].to_numpy()))[0, 1]), len(d)


# ---------------- part 1: MLB feature test ----------------
def feature_test(df):
    league = "MLB"
    m1_feats, _ = bt.league_features(df, league)
    combined = m1_feats + NEW_LPCT
    tests = bt.test_seasons(df, league)
    base = base_frame(df, league, tests)
    wf = lambda f, mk: align(base, bt.walk_forward(df, league, f, bt.Y_REG, mk, tests)[0])
    wf_coef = lambda f, mk: bt.walk_forward(df, league, f, bt.Y_REG, mk, tests)

    p_b1 = wf(["win_pct_percentile"], make_ols)
    b1 = frame(base, p_b1, pred=p_b1)
    rows = []
    lab = df[(df.league == league) & df[bt.Y_REG].notna()]
    for c, cl in zip(NEW, NEW_LPCT):
        p = wf(["win_pct_percentile", cl], make_ols)
        d = frame(base, p, pred=p)
        m, diff = bt.metrics(d), bt.bootstrap_diff(d, b1, n_boot=N_BOOT)
        raw = lab[[cl, bt.Y_REG]].dropna()
        ps, n = partial_spearman(lab, cl)
        rows.append({"feature": c, "expected_sign": EXPECTED[c], "coverage": float(df.loc[df.league == league, cl].notna().mean()),
                     "spearman_raw": float(raw[cl].rank().corr(raw[bt.Y_REG].rank())), "spearman_partial": ps,
                     "n_labelled": n, **{f"inc_{k}": m[k] for k in ("spearman_mean", "mae", "auc")},
                     "d_spearman": diff["spearman_mean"], "d_mae": diff["mae"], "d_auc": diff["auc"]})
    feat = pd.DataFrame(rows)

    p_en1, _, _ = wf_coef(m1_feats, make_en)
    en1 = frame(base, align(base, p_en1), pred=align(base, p_en1))
    p_enc, k_enc, h_enc = wf_coef(combined, make_en)
    enc = frame(base, align(base, p_enc), pred=align(base, p_enc))
    stab = bt.coef_stability(k_enc)
    comb = {"B1": bt.metrics(b1), "EN (M1 features)": bt.metrics(en1), "EN (M1 + M1b features)": bt.metrics(enc)}
    d_comb = bt.bootstrap_diff(enc, b1, n_boot=N_BOOT)
    d_en1 = bt.bootstrap_diff(en1, b1, n_boot=N_BOOT)
    d_vs_en1 = bt.bootstrap_diff(enc, en1, n_boot=N_BOOT)
    beats = bool(d_comb["spearman_mean"][1] > 0 and d_comb["mae"][0] <= 0)
    preds = pd.concat([b1.assign(model="B1"), en1.assign(model="EN (M1 features)"),
                       enc.assign(model="EN (M1 + M1b features)")])
    return dict(feat=feat, stab=stab, comb=comb, d_comb=d_comb, d_en1=d_en1, d_vs_en1=d_vs_en1, beats=beats,
                tests=tests, combined=combined, preds=preds, params=h_enc)


def rerun_m2_mlb(df, combined, tests):
    """Only if the combined model beats B1 (pre-registered): M2 selection for MLB with the new features."""
    league = "MLB"
    base = base_frame(df, league, tests)
    wf = lambda f, tgt, mk, gap=bt.GAP: align(base, bt.walk_forward(df, league, f, tgt, mk, tests, gap=gap)[0])
    M = {}
    for n, f, mk in (("B1 OLS pct", ["win_pct_percentile"], make_ols),
                     ("B2 OLS pct+trail", ["win_pct_percentile", "win_pct_trailing_3_seasons_lpct"], make_ols),
                     ("Elastic net", combined, make_en), ("EBM", combined, run_m2.make_ebm)):
        p = wf(f, bt.Y_REG, mk)
        M[n] = frame(base, p, pred=p)
    hp = [wf(combined, h, make_en, gap=k) for k, h in enumerate(HORIZONS, 1)]
    hd = 100 - np.mean(hp, axis=0)
    M["Horizon EN"] = frame(base, hd, pred=hd)
    met = {n: bt.metrics(d) for n, d in M.items()}
    best = max(run_m2.SIMPLICITY, key=lambda n: (met[n]["spearman_mean"], -met[n]["mae"]))
    out = []
    for n in run_m2.SIMPLICITY:
        bb = bt.bootstrap_diff(M[n], M[best], n_boot=N_BOOT)
        ok = n == best or (bb["spearman_mean"][2] >= 0 and bb["mae"][1] <= 0)
        out.append({"model": n, **met[n], "vsBest_spearman": bb["spearman_mean"], "vsBest_mae": bb["mae"],
                    "within": ok})
    res = pd.DataFrame(out)
    return res, best, next(r.model for _, r in res.iterrows() if r.within)


# ---------------- part 2: horizon models with gap = horizon ----------------
def shift_to_headline(paths, doom):
    """Common per-row offset so that 100 - mean(path) == doom exactly (D78)."""
    paths = np.asarray(paths, dtype=float)                       # shape (3, n)
    off = (100 - np.asarray(doom)) - paths.mean(axis=0)
    return paths + off, off


def horizon_test(df):
    m2p = pd.read_csv(os.path.join(REP, "m2_predictions.csv"), low_memory=False)
    choice = json.load(open(os.path.join(REP, "m2_choice.json")))
    rows, conf = [], []
    for league, spec in (("MLB", (["win_pct_percentile"], make_ols, "per-horizon OLS on win_pct_percentile")),
                         ("NHL", (None, make_en, "per-horizon elastic net"))):
        feats = spec[0] or bt.league_features(df, league)[0]
        tests = bt.test_seasons(df, league)
        base = base_frame(df, league, tests)
        head = m2p[(m2p.league == league) & (m2p.model == choice[league]["chosen"])]
        doom = base[["league", "season", "franchise_id"]].merge(head, on=["league", "season", "franchise_id"],
                                                                 how="left").pred.to_numpy()
        assert np.isfinite(doom).all()
        P = {}
        for gap_rule in ("gap = horizon", "gap = 3"):
            P[gap_rule] = []
            for k, h in enumerate(HORIZONS, 1):
                gap = k if gap_rule == "gap = horizon" else bt.GAP
                p, _, _ = bt.walk_forward(df, league, feats, h, spec[1], tests, gap=gap)
                P[gap_rule].append(align(base, p))
                arr, act, cur = P[gap_rule][-1], base[h].to_numpy(), base.win_pct_percentile.to_numpy()
                idx = [np.where(base.season.to_numpy() == s)[0] for s in tests]
                per = [bt._spearman(arr[i], act[i]) for i in idx]            # plain arrays: no index alignment
                pers = [bt._spearman(cur[i], act[i]) for i in idx]
                rows.append({"league": league, "model": spec[2], "gap_rule": gap_rule, "horizon": h, "gap": gap,
                             "spearman_mean": float(np.nanmean(per)), "persistence": float(np.nanmean(pers)),
                             "mae": float(np.mean(np.abs(P[gap_rule][-1] - base[h])))})
        raw = np.asarray(P["gap = horizon"])
        shifted, off = shift_to_headline(raw, doom)
        err = np.abs(100 - shifted.mean(axis=0) - doom)
        conf.append({"league": league, "headline_model": choice[league]["chosen"], "n_rows": len(doom),
                     "raw_mean_abs_gap": float(np.mean(np.abs(off))), "raw_max_abs_gap": float(np.max(np.abs(off))),
                     "max_abs_error_after_shift": float(err.max()),
                     "path_values_outside_0_100": int(((shifted < 0) | (shifted > 100)).sum())})
    return pd.DataFrame(rows), pd.DataFrame(conf)


def main():
    t0 = time.time()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
    df = load()
    ft = feature_test(df)
    print(f"feature test {time.time() - t0:.0f}s; beats B1: {ft['beats']}", flush=True)
    m2 = rerun_m2_mlb(df, ft["combined"], ft["tests"]) if ft["beats"] else None
    hz, hconf = horizon_test(df)
    print(f"horizons {time.time() - t0:.0f}s", flush=True)

    flat = ft["feat"].copy()
    for c in ("d_spearman", "d_mae", "d_auc"):
        flat[[c, c + "_lo", c + "_hi"]] = pd.DataFrame(flat[c].tolist(), index=flat.index)
    flat.to_csv(os.path.join(REP, "m1b_features.csv"), index=False)
    ft["stab"].to_csv(os.path.join(REP, "m1b_coef_stability.csv"), index=False)
    ft["preds"].to_csv(os.path.join(REP, "m1b_predictions.csv"), index=False)
    hz.to_csv(os.path.join(REP, "m1b_horizons.csv"), index=False)
    hconf.to_csv(os.path.join(REP, "m1b_path_consistency.csv"), index=False)
    chk = pd.read_csv(os.path.join(REP, "m1b_feature_checks.csv"))

    # ---------- report ----------
    T = ft["tests"]
    L = ["# Phase M1b: pre-registered MLB feature test, horizon gaps\n"]
    L.append(f"Plan: `m1b_preregistration.md` (committed before any result). MLB walk-forward test {min(T)}–{max(T)}, "
             f"train ≤ T−3, moving-block bootstrap (block 3). Features: `src/m1b_features.py` → "
             f"`data/processed/mlb_m1b_features.csv` (D82–D85).\n")
    L.append("**Data checks.** " + "; ".join(f"{r.check}: {r.value:.3g}" for _, r in chk.iterrows()) +
             ". `farm_strength` is missing for 2000–2004 (the MLB Stats API returns no minor-league standings before "
             "2005) and 2020 (no season); the pipeline fills it with the training median plus a missing indicator, "
             "as for every feature (D85).\n")
    L.append("**Every feature.** Incremental = OLS on `win_pct_percentile` + feature, Δ vs B1 [95% CI]. Combined = "
             "standardized coefficient in the combined elastic net (median [min, max]; % folds at 0; % minority sign). "
             "Spearman raw/partial (controlling for standing, D55) on all labelled MLB rows, descriptive only.\n")
    L.append("| Feature | Expected | Δ Spearman (incremental) | Δ MAE | Δ AUC | Combined EN coefficient | Spearman raw / partial |")
    L.append("|---|---|---|---|---|---|---|")
    st = ft["stab"].set_index("feature")
    for _, r in ft["feat"].iterrows():
        s = st.loc[r.feature + "_lpct"]
        L.append(f"| `{r.feature}` | {r.expected_sign} | {ci(r.d_spearman)} | {ci(r.d_mae, 2)} | {ci(r.d_auc)} | "
                 f"{s['median']:+.2f} [{s['min']:+.2f}, {s['max']:+.2f}]; 0: {s.zero_share:.0%}; minority: "
                 f"{s.opposite_sign_share:.0%} | {r.spearman_raw:+.3f} / {r.spearman_partial:+.3f} |")
    c = ft["comb"]
    L.append("\n**Combined model vs B1.**\n")
    L.append("| Model | Spearman | MAE | R² | AUC | Top-5 | Δ Spearman vs B1 | Δ MAE vs B1 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for n, dd in (("B1", None), ("EN (M1 features)", ft["d_en1"]), ("EN (M1 + M1b features)", ft["d_comb"])):
        m = c[n]
        L.append(f"| {n} | {fmt(m['spearman_mean'])} | {fmt(m['mae'], 1)} | {fmt(m['r2'])} | {fmt(m['auc'])} | "
                 f"{fmt(m['top5_hits'], 2)} | {ci(dd['spearman_mean']) if dd else '—'} | "
                 f"{ci(dd['mae'], 2) if dd else '—'} |")
    L.append(f"\nCombined − M1-feature elastic net: Δ Spearman {ci(ft['d_vs_en1']['spearman_mean'])}, "
             f"Δ MAE {ci(ft['d_vs_en1']['mae'], 2)}.\n")
    dc = ft["d_comb"]
    verdict = ("**beats B1 beyond noise**" if ft["beats"] else "**does not beat B1 beyond noise**")
    L.append(f"**Pre-registered decision.** Δ Spearman interval {ci(dc['spearman_mean'])} "
             f"({'entirely above 0' if dc['spearman_mean'][1] > 0 else 'includes 0'}); Δ MAE {dc['mae'][0]:+.2f} "
             f"({'≤ 0' if dc['mae'][0] <= 0 else '> 0'}). The combined MLB model {verdict}. " +
             ("M2 selection re-run below." if ft["beats"] else "MLB stays on B1; the M2 selection is not re-run.")
             + "\n")
    if m2 is not None:
        res, best, chosen = m2
        L.append(f"**M2 selection re-run for MLB** (best {best}, chosen {chosen}):\n")
        L.append("| Model | Spearman | MAE | Δ Spearman vs best | Δ MAE vs best | Within noise |")
        L.append("|---|---|---|---|---|---|")
        for _, r in res.iterrows():
            L.append(f"| {r.model} | {fmt(r.spearman_mean)} | {fmt(r.mae, 1)} | {ci(r.vsBest_spearman)} | "
                     f"{ci(r.vsBest_mae, 1)} | {'yes' if r.within else 'no'} |")
        L.append("")
    L.append(FINDINGS + "\n")
    L.append("## Horizon models with training gap = horizon (D87)\n")
    L.append("Horizon k is trained on seasons ≤ T−k (its labels are known by the end of T), inner split with the same "
             "gap. Same test seasons as M2. Mean per-season Spearman with the actual percentile in t+k:\n")
    L.append("| League | Model | Horizon | Gap = horizon | Gap = 3 (M2) | Persistence | MAE (gap = horizon) |")
    L.append("|---|---|---|---|---|---|---|")
    for (lg, h), g in hz.groupby(["league", "horizon"], sort=False):
        a, b = g[g.gap_rule == "gap = horizon"].iloc[0], g[g.gap_rule == "gap = 3"].iloc[0]
        L.append(f"| {lg} | {a.model} | {h} (gap {a.gap}) | {a.spearman_mean:.3f} | {b.spearman_mean:.3f} | "
                 f"{a.persistence:.3f} | {a.mae:.1f} |")
    L.append("\n**Do the paths still average to the headline score? (D88)** Raw horizon paths no longer average "
             "exactly to the headline doom, because each horizon now trains on a different set of seasons. M3 "
             "therefore shifts each team's three projections by one common offset; after the shift "
             "100 − mean(path) equals the headline score:\n")
    L.append("| League | Headline model | Rows | Mean / max raw gap (points) | Max error after shift | Path values outside 0–100 |")
    L.append("|---|---|---|---|---|---|")
    for _, r in hconf.iterrows():
        L.append(f"| {r.league} | {r.headline_model} | {r.n_rows} | {r.raw_mean_abs_gap:.2f} / {r.raw_max_abs_gap:.2f} | "
                 f"{r.max_abs_error_after_shift:.1e} | {r.path_values_outside_0_100} |")
    L.append("\nFiles: `m1b_features.csv`, `m1b_coef_stability.csv`, `m1b_predictions.csv`, `m1b_horizons.csv`, "
             "`m1b_path_consistency.csv`, `m1b_feature_checks.csv`. Code: `src/m1b_features.py`, `src/model/run_m1b.py`.")
    open(os.path.join(REP, "m1b.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(flat[["feature", "d_spearman", "d_spearman_lo", "d_spearman_hi", "d_mae", "spearman_raw",
                "spearman_partial"]].round(3).to_string())
    print(ft["stab"].round(2).to_string())
    print({k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in c.items()})
    print("d_comb", {k: tuple(round(x, 3) for x in v) for k, v in ft["d_comb"].items()})
    print("d_vs_en1", {k: tuple(round(x, 3) for x in v) for k, v in ft["d_vs_en1"].items()})
    print(hz.round(3).to_string())
    print(hconf.round(4).to_string())
    if m2 is not None:
        print(m2[0], m2[1], m2[2])
    print(f"{time.time() - t0:.0f}s")


FINDINGS = (
    "**Findings.** The new features improve the MLB elastic net (+0.037 Spearman over the M1-feature version, "
    "interval +0.018 to +0.064, MAE −0.45). That lifts it slightly above B1 on average (0.442 vs 0.414), but the "
    "gain over B1 is within noise (+0.028 [−0.037, +0.080]). By the pre-registered rule **MLB stays on B1**. "
    "Per feature: BaseRuns margin is the strongest. Added to B1 on its own it gains +0.035 [+0.006, +0.074] "
    "Spearman and −0.56 MAE, and it is the only new feature the combined model uses in every fold (coefficient "
    "−4.4). Second-half margin (+0.012 [+0.003, +0.021]) and value-weighted hitter age (+0.007 [+0.002, +0.015]) "
    "add small but consistent amounts. Sequencing luck and farm strength have intervals that include 0. "
    "Value-weighted pitcher age is very slightly worse than B1 (−0.003 [−0.005, −0.000]), and its rare non-zero "
    "coefficients go against the expected sign. The other five features match their expected sign. "
    "**Caveat on BaseRuns:** B1 + BaseRuns margin would pass the M2 selection rule against B1, but it was not a "
    "pre-registered candidate. Adopting it now would be choosing a model after seeing its result, with six "
    "features tested, so it is recorded as a hypothesis for a future pre-registered test (e.g. on 2024+ seasons "
    "as their labels arrive), not as a model change.")

if __name__ == "__main__":
    main()
