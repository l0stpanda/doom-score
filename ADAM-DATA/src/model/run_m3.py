"""Phase M3: export everything the dashboard needs (dashboard/data/), MODEL_CARD.md, reports/m3.md.
Chosen models (D76, D86): MLB = B1 (OLS on win_pct_percentile), NHL = elastic net. Decisions D91-D98.

Run: PYTHONUTF8=1 python ADAM-DATA/src/model/run_m3.py"""
import json, os, sys, time, warnings
import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backtest as bt
from run_m1 import make_en, make_ols, make_l1, make_logit_plain
import fetch_phase1 as f1

ROOT, REP = bt.ROOT, os.path.join(bt.ROOT, "reports")
OUT = os.path.join(ROOT, "dashboard", "data")
HORIZONS = ["y_pct_t1", "y_pct_t2", "y_pct_t3"]
LIVE = {"MLB": [2024, 2025, 2026], "NHL": [2023, 2024, 2025]}
CONF_LEVEL, CONF_MIN_CAL = 0.80, 2
BANDS = [(75, "Very high"), (55, "High"), (35, "Moderate"), (-np.inf, "Low")]       # D89
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


def band(x):
    return next(lbl for cut, lbl in BANDS if x >= cut)


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


def finish(P):
    """Conformal intervals, path shift + clip (D88), bands."""
    P = P.copy()
    for lg in P.league.unique():
        b = P[(P.league == lg) & (P.pred_type == "backtest")]
        for T in P[P.league == lg].season_start_year.unique():
            q = conformal_q(b, T)
            m = (P.league == lg) & (P.season_start_year == T)
            P.loc[m, "doom_lo80"] = np.clip(P.loc[m, "doom_pred"] - q, 0, 100)
            P.loc[m, "doom_hi80"] = np.clip(P.loc[m, "doom_pred"] + q, 0, 100)
    raw = P[[f"raw_proj_pct_t{k}" for k in (1, 2, 3)]].to_numpy()
    off = (100 - P.doom_pred.to_numpy()) - raw.mean(axis=1)
    shifted = raw + off[:, None]
    P["path_clipped"] = ((shifted < 0) | (shifted > 100)).any(axis=1)
    shifted = np.clip(shifted, 0, 100)
    for k in (1, 2, 3):
        P[f"proj_pct_t{k}"] = shifted[:, k - 1]
    P["path_offset"] = off
    P["doom_band"] = [band(x) for x in P.doom_pred]
    return P


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
    full = pd.read_csv(bt.FULL, usecols=bt.KEY + ["team", "team_id"], low_memory=False)
    last = full.sort_values(bt.SEASON).groupby(["league", "franchise_id"]).tail(1)
    teams = f1.get("nhl_stats_api", "team", f1.NHL_TEAM_URL)
    tri = {t["id"]: t["triCode"] for t in teams["data"]}
    st = f1.get("nhl_web_api", "standings_now", "https://api-web.nhle.com/v1/standings/now")
    logo = {s["teamAbbrev"]["default"]: s["teamLogo"] for s in st["standings"]}
    rows, missing = [], []
    for _, r in last.iterrows():
        if r.league == "MLB":
            url = f"https://www.mlbstatic.com/team-logos/{int(r.team_id)}.svg"
        else:
            url = logo.get(tri.get(int(r.team_id)))
            if url is None:
                missing.append(r.franchise_id)
        rows.append({"league": r.league, "franchise_id": r.franchise_id, "team": r.team, "logo_url": url,
                     "team_id": int(r.team_id)})
    return pd.DataFrame(rows).sort_values(["league", "franchise_id"]), missing


def team_profile(df):
    m1b = pd.read_csv(os.path.join(ROOT, "data", "processed", "mlb_m1b_features.csv"))
    prof_cols = list(PLAIN)[:11]                       # standing, trajectory and the nine concept percentiles
    p = df[bt.KEY + ["team"] + prof_cols].merge(m1b[bt.KEY + list(CONTEXT_PLAIN)], on=bt.KEY, how="left")
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


def ci(v, lo, hi, nd=3):
    return f"{v:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]"


def model_card(S):
    comp = pd.read_csv(os.path.join(REP, "m2_comparison.csv"))
    cov = pd.read_csv(os.path.join(REP, "m2_conformal_coverage.csv"))
    m1 = pd.read_csv(os.path.join(REP, "m1_metrics.csv"))
    choice = json.load(open(os.path.join(REP, "m2_choice.json")))
    T = S["tests"]
    rows = []
    for lg in ("MLB", "NHL"):
        b0 = m1[(m1.run == lg) & (m1.model == "B0 100-pct")].iloc[0]
        rows.append(f"| {lg} | B0: 100 − current percentile (no fit) | {b0.spearman_mean:.3f} | {b0.mae:.1f} | "
                    f"{b0.auc:.3f} | {b0.top5_hits:.2f} | — |")
        for mdl in ("B1 OLS pct", "B2 OLS pct+trail", "Elastic net"):
            r = comp[(comp.league == lg) & (comp.model == mdl)].iloc[0]
            tag = " **(chosen)**" if mdl == choice[lg]["chosen"] else ""
            d = "—" if mdl == "B1 OLS pct" else ci(r.vsB1_spearman, r.vsB1_spearman_lo, r.vsB1_spearman_hi)
            rows.append(f"| {lg} | {mdl}{tag} | {r.spearman_mean:.3f} | {r.mae:.1f} | {r.auc:.3f} | "
                        f"{r.top5_hits:.2f} | {d} |")
    cv = {lg: cov[(cov.league == lg) & (cov.model == choice[lg]["chosen"])].iloc[0] for lg in ("MLB", "NHL")}
    txt = f"""# Model card: Doom Score (MLB + NHL)

*Generated by `src/model/run_m3.py`. D-numbers refer to `DECISIONS.md`; phase reports are in `reports/`.*

## What it predicts

**Doom** for team-season *t* = 100 − the team's average league percentile over the next three seasons
(t+1..t+3); 0 = finishes top of the league three years running, 100 = bottom three years running. `doom_pred` is
the predicted doom made at the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1). Also exported:
- `doom_lo80`/`doom_hi80`: 80% split-conformal interval (D80).
- `p_doomed`: probability that doom ≥ 75 (bottom quarter on average). MLB: logistic regression on current
  standing; NHL: L1 logistic on the NHL feature set (M1).
- `proj_pct_t1..t3`: projected percentile in each of the next three seasons, from per-horizon models (training
  gap = horizon, D87), shifted by one common offset per team so that 100 − mean(path) equals `doom_pred`
  exactly (D88). Values are clipped to 0–100; clipped rows have `path_clipped` = True ({S['path_clipped']} rows),
  and for those the average is no longer exact.
- `doom_band`: Low < 35, Moderate 35–55, High 55–75, Very high ≥ 75 (D89).

## Models

| League | Model | Inputs |
|---|---|---|
| MLB | **B1**: OLS on `win_pct_percentile` | Current standing only |
| NHL | **Elastic net** (median fill + missing indicators + scaling, alpha/l1_ratio tuned on a time split) | Current standing, 3-season record, margin, luck, Corsi, roster age, star concentration, draft capital, GM and coach tenure, GM vacancy, short season, seasons of history (no spending: unavailable for NHL) |

Choice rule (D76): the simplest model whose Spearman and MAE are within block-bootstrap noise of the best
model. In MLB nothing beat current standing: not the M1 features (M1/M2), and not six pre-registered MLB features
(M1b, D86).

## Training data

`data/processed/mlb_nhl_model_slim.csv`: MLB 2000–2026, NHL 2005-06 to 2025-26, one row per team-season.
Labels exist through MLB 2023 / NHL 2022. Backtest (`pred_type = backtest`): walk-forward, each test season T
predicted by a model trained on seasons ≤ T−3, with all preprocessing and tuning inside the training seasons;
MLB {T['MLB'][0]}–{T['MLB'][1]}, NHL {T['NHL'][0]}–{T['NHL'][1]}. Live (`pred_type = live`, MLB 2024–2026, NHL
2023–2025): refit on all labelled seasons before the first live season (D92); the latest season is the
current view.

## Backtest performance vs baselines

Mean per-season Spearman with actual doom, MAE in doom points, AUC for doom ≥ 75, top-5 = how many of each
season's 5 predicted most-doomed teams actually finished in the bottom quarter (of 5). Δ = difference from B1 with
a 95% moving-block bootstrap interval (D72).

| League | Model | Spearman | MAE | AUC | Top-5 | Δ Spearman vs B1 |
|---|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

80% intervals: coverage {cv['MLB'].coverage:.1%} (MLB, mean half-width {cv['MLB'].mean_half_width:.0f} points),
{cv['NHL'].coverage:.1%} (NHL, {cv['NHL'].mean_half_width:.0f} points). Backtest seasons with fewer than two
earlier calibration seasons have no interval ({S['intervals_missing']} rows).

## How to read the score

- Doom is a **relative ranking within a league**, not a forecast of wins. A 70 means "expected to finish around
  the 30th percentile on average over the next three seasons".
- The intervals are wide (about ±{cv['MLB'].mean_half_width:.0f} points in MLB, ±{cv['NHL'].mean_half_width:.0f} in NHL). Treat
  differences of a few points between teams as noise.
- **Drivers** (`driver_up_*`, `driver_down_*`, `doom_drivers_long.csv`) are exact contributions of a linear
  model: coefficient × the team's standardized deviation from the training mean, in doom points. They add up
  to the prediction minus the intercept.
- **MLB drivers are current standing only**, with a note saying so: no other MLB feature improved the backtest.
  `team_profile.csv` shows every slim feature's percentile, plus MLB BaseRuns margin, second-half margin and
  value-weighted hitter age, as **context, not drivers**. `team_profile_columns.csv` marks which columns each
  league's model uses.

## Known limitations

- **Short seasons:** MLB 2020 (60 games) and NHL 2012-13, 2019-20 and 2020-21 have noisier standings; they are
  flagged (`short_season`) but not down-weighted.
- **Overlapping labels:** adjacent seasons share up to two future seasons, so the backtest has fewer independent
  observations than rows (16 MLB and 10 NHL test seasons). The block bootstrap accounts for this only roughly.
  Live predictions for MLB 2024–2025 and NHL 2023–2024 come from a model whose training labels overlap those
  seasons' futures, so they are not strictly out-of-sample.
- **NHL has no spending data** (team cap hits unavailable, D57); the NHL model has no payroll term.
- **MLB has no independent underlying-quality measure:** its `underlying_quality` column is Pythagorean win%,
  a near-duplicate of run margin (Spearman 0.997, D63), so it is excluded. NHL Corsi is missing for 2005–07
  (filled + indicator, D70).
- Front-office data (GM tenure, vacancies) come from Wikipedia with imperfect dates (D28, D39).
- No soft-leakage features are used: NHL xG (D54, D79) and Baseball-Reference WAR (removed, D90) are not inputs.

## Future work

- **D86: BaseRuns margin (MLB).** Added to current standing it beat B1 in the backtest (Δ Spearman +0.035 [+0.006,
  +0.074]), but it was not a pre-registered candidate and six features were tested. Re-test it, pre-registered,
  on new seasons as their labels arrive (MLB 2024+), before it can enter the MLB model.

## Files (`dashboard/data/`)

`doom_predictions.csv` ({S['rows']} rows: {S['backtest']} backtest, {S['live']} live), `doom_drivers_long.csv`
({S['drivers_rows']} rows), `team_profile.csv`, `team_profile_columns.csv`, `team_meta.csv`.
"""
    open(os.path.join(ROOT, "MODEL_CARD.md"), "w", encoding="utf-8").write(txt)


def m3_report(S, P):
    L = ["# Phase M3: dashboard exports\n"]
    L.append(f"Chosen models (D76, D86): MLB = B1, NHL = elastic net. Files in `dashboard/data/`: "
             f"`doom_predictions.csv` ({S['rows']} rows: {S['backtest']} backtest, {S['live']} live), "
             f"`doom_drivers_long.csv` ({S['drivers_rows']} rows), `team_profile.csv` + `team_profile_columns.csv`, "
             f"`team_meta.csv`. Model card: `MODEL_CARD.md`.\n")
    L.append("**Checks.**\n")
    L.append(f"- Backtest `doom_pred` reproduces the M2 walk-forward predictions of the chosen models: max |diff| = "
             f"{S['max_diff_vs_m2']:.1e}.")
    L.append("- Driver contributions + intercept = prediction for every row (asserted in code).")
    L.append(f"- Paths: 100 − mean(proj_pct_t1..t3) = doom_pred, max error {S['path_max_err_unclipped']:.1e} on "
             f"unclipped rows; {S['path_clipped']} row(s) clipped to 0–100 and flagged `path_clipped` (D88).")
    L.append(f"- 80% intervals: {S['intervals_missing']} backtest rows have none (fewer than 2 calibration seasons ≤ "
             f"T−3: MLB 2008–2011, NHL 2013–2016).")
    L.append(f"- Logos: {'all teams have a logo URL' if not S['missing_logo'] else 'missing: ' + ', '.join(S['missing_logo'])}.\n")
    bands = pd.crosstab(P.league, P.doom_band).reindex(columns=["Low", "Moderate", "High", "Very high"],
                                                      fill_value=0)
    L.append("**Doom bands (D89) across all exported rows:**\n")
    L.append("| League | " + " | ".join(bands.columns) + " |")
    L.append("|---|" + "---|" * len(bands.columns))
    for lg, r in bands.iterrows():
        L.append(f"| {lg} | " + " | ".join(str(int(v)) for v in r) + " |")
    mx = P.groupby("league").doom_pred.max()
    L.append(f"\nPredicted doom is shrunk toward the middle, as regression predictions are (max: MLB "
             f"{mx['MLB']:.1f}, NHL {mx['NHL']:.1f}), so **\"Very high\" (≥ 75) almost never occurs in the "
             f"predictions**, although {(P.actual_doom >= 75).mean():.0%} of labelled exported rows have actual doom "
             f"≥ 75. The bands are as specified; if \"Very high\" should be reachable, the cut-offs need a rethink "
             f"(e.g. on `p_doomed` or on within-season ranks). Not changed here.\n")
    L.append("**Current view (latest season), most and least doomed:**\n")
    for lg in ("MLB", "NHL"):
        cur = P[(P.league == lg) & (P.season_start_year == P[P.league == lg].season_start_year.max())]
        top = ", ".join(f"{r.team} {r.doom_pred:.0f}" for _, r in cur.nlargest(5, "doom_pred").iterrows())
        low = ", ".join(f"{r.team} {r.doom_pred:.0f}" for _, r in cur.nsmallest(5, "doom_pred").iterrows())
        L.append(f"- {lg} {cur.season_start_year.iloc[0]}: most doomed {top}; least doomed {low}.")
    L.append("\nLive predictions refit on all labelled seasons before the first live season (D92). MLB drivers are "
             "current standing only, with `driver_note` (D89). `team_profile.csv` is context only and includes MLB "
             "BaseRuns margin, second-half margin and value-weighted hitter age (D93). Code: `src/model/run_m3.py`.")
    open(os.path.join(REP, "m3.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    t0 = time.time()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
    os.makedirs(OUT, exist_ok=True)
    df = bt.load()
    choice = json.load(open(os.path.join(REP, "m2_choice.json")))
    assert choice["MLB"]["chosen"] == "B1 OLS pct" and choice["NHL"]["chosen"] == "Elastic net"
    Ps, Ds, tests = [], [], {}
    for lg in ("MLB", "NHL"):
        feats, _ = bt.league_features(df, lg)
        P, D, tests[lg] = run_league(df, lg, feats, choice[lg]["chosen"])
        Ps.append(P); Ds.append(D)
        print(f"{lg}: {time.time() - t0:.0f}s", flush=True)
    P = finish(pd.concat(Ps, ignore_index=True))
    D, P = driver_text(pd.concat(Ds, ignore_index=True), P)

    # check: backtest doom predictions reproduce M2's chosen-model walk-forward predictions
    m2 = pd.read_csv(os.path.join(REP, "m2_predictions.csv"), low_memory=False)
    m2 = pd.concat([m2[(m2.league == lg) & (m2.model == choice[lg]["chosen"])] for lg in ("MLB", "NHL")])
    chk = P[P.pred_type == "backtest"].merge(m2.rename(columns={"season": bt.SEASON})[bt.KEY + ["pred"]], on=bt.KEY)
    max_diff_m2 = float((chk.doom_pred - chk.pred).abs().max())
    path_err = np.abs(100 - P[["proj_pct_t1", "proj_pct_t2", "proj_pct_t3"]].mean(axis=1) - P.doom_pred)

    cols = (["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ot_losses", "games",
             "win_pct", "win_pct_percentile", "doom_pred", "doom_lo80", "doom_hi80", "p_doomed", "doom_band",
             "proj_pct_t1", "proj_pct_t2", "proj_pct_t3", "path_clipped", "pred_type", "actual_doom",
             "actual_pct_t1", "actual_pct_t2", "actual_pct_t3"]
            + [f"driver_up_{i}" for i in (1, 2, 3)] + [f"driver_down_{i}" for i in (1, 2, 3)] + ["driver_note"])
    P = P.sort_values(["league", "season_start_year", "doom_pred"], ascending=[True, True, False])
    P[cols].to_csv(os.path.join(OUT, "doom_predictions.csv"), index=False)
    D[["league", "season_start_year", "franchise_id", "pred_type", "feature", "feature_label", "z",
       "contribution"]].to_csv(os.path.join(OUT, "doom_drivers_long.csv"), index=False)
    meta, missing_logo = team_meta(df)
    meta.to_csv(os.path.join(OUT, "team_meta.csv"), index=False)
    prof, dic = team_profile(df)
    prof.to_csv(os.path.join(OUT, "team_profile.csv"), index=False)
    dic.to_csv(os.path.join(OUT, "team_profile_columns.csv"), index=False)

    S = dict(rows=len(P), backtest=int((P.pred_type == "backtest").sum()), live=int((P.pred_type == "live").sum()),
             tests={k: [min(v), max(v)] for k, v in tests.items()}, max_diff_vs_m2=max_diff_m2,
             path_max_err_unclipped=float(path_err[~P.path_clipped].max()), path_clipped=int(P.path_clipped.sum()),
             intervals_missing=int(P.doom_lo80.isna().sum()),
             bands=P.groupby(["league", "doom_band"]).size().to_dict(), missing_logo=missing_logo,
             drivers_rows=len(D))
    json.dump({k: (v if not isinstance(v, dict) else {str(kk): vv for kk, vv in v.items()}) for k, v in S.items()},
              open(os.path.join(REP, "m3_stats.json"), "w"), indent=1, default=str)
    model_card(S)
    m3_report(S, P)
    print(open(os.path.join(REP, "m3_stats.json")).read())
    print(f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
