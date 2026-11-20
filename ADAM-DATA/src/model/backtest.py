"""Reusable walk-forward backtest for the doom models (Phase M1+). Decisions D62-D70.

Leakage rules enforced here:
  1. Test season T is predicted by a model trained only on seasons <= T - GAP (GAP = 3), asserted per fold.
  2. All preprocessing (median fill, missing indicators, scaling) lives inside an sklearn Pipeline, so it is
     fitted on the training seasons of each fold only.
  3. Hyperparameters are tuned with a time-based inner split inside the training seasons, same 3-season gap.
  4. No `y_*` column may be in X (asserted per fold).
"""
import os
import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score, brier_score_loss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # ADAM-DATA
SLIM = os.path.join(ROOT, "data", "processed", "mlb_nhl_model_slim.csv")
FULL = os.path.join(ROOT, "data", "processed", "mlb_nhl_team_seasons.csv")
KEY = ["league", "season_start_year", "franchise_id"]
SEASON = "season_start_year"
GAP = 3                    # labels of season s are known only after season s + 3
MIN_TRAIN_SEASONS = 6
TEST_LAST = {"MLB": 2023, "NHL": 2022}

FEATURES = ["win_pct_percentile", "win_pct_trailing_3_seasons_lpct", "margin_per_game_lpct", "luck_lpct",
            "underlying_quality_lpct", "roster_age_weighted_lpct", "star_concentration_lpct", "draft_capital_lpct",
            "gm_tenure_lpct", "coach_tenure_lpct", "spending_lpct", "personnel_lead_vacant", "short_season",
            "seasons_of_history"]
# Excluded per the modeling spec even though the column has values (D63: MLB underlying_quality = Pythagorean
# win%, a near-duplicate of margin_per_game, not an independent quality measure).
SPEC_EXCLUDE = {"MLB": {"underlying_quality_lpct": "spec: MLB has no independent underlying-quality measure "
                                                   "(column = Pythagorean win%, near-duplicate of margin)"}}
Y_REG, Y_CLF = "y_doom_3yr", "y_doomed_bottom25"


def lpct(s):
    """Within-group percentile, same formula as win_pct_percentile: (average rank - 1)/(n - 1) * 100."""
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * np.nan


def load():
    """Slim table; personnel_lead_vacant and win_pct_trailing_3_seasons_lpct are built by src/build_slim.py (D71)."""
    df = pd.read_csv(SLIM, low_memory=False)
    missing = [f for f in FEATURES if f not in df.columns]
    assert not missing, f"slim table lacks {missing}; run src/build_slim.py"
    assert not df.duplicated(KEY).any()
    df["short_season"] = df.short_season.astype(str).eq("True").astype(float)
    df["personnel_lead_vacant"] = pd.to_numeric(df.personnel_lead_vacant, errors="coerce")
    df[Y_CLF] = df[Y_CLF].map({"True": 1.0, "False": 0.0, True: 1.0, False: 0.0})
    return df


def league_features(df, league, features=FEATURES):
    """Features usable for one league: drops all-missing columns and spec exclusions. Returns (kept, dropped)."""
    g = df[df.league == league]
    kept, dropped = [], {}
    for f in features:
        if f in SPEC_EXCLUDE.get(league, {}):
            dropped[f] = SPEC_EXCLUDE[league][f]
        elif g[f].isna().all():
            dropped[f] = "all missing in this league"
        else:
            kept.append(f)
    return kept, dropped


class MedianImputeWithIndicator(BaseEstimator, TransformerMixin):
    """Median fill + a 0/1 missing indicator for each column missing in > `threshold` of the *training* rows."""

    def __init__(self, threshold=0.01):
        self.threshold = threshold

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.columns_ = list(X.columns)
        med = X.median()
        self.medians_ = med.fillna(0.0)                 # a column all-missing in training is filled with 0
        self.indicator_cols_ = [c for c in X.columns if X[c].isna().mean() > self.threshold]
        return self

    def transform(self, X):
        X = pd.DataFrame(X, columns=self.columns_)
        out = X.fillna(self.medians_)
        for c in self.indicator_cols_:
            out[f"{c}__missing"] = X[c].isna().astype(float)
        return out.to_numpy(dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.array(self.columns_ + [f"{c}__missing" for c in self.indicator_cols_])


def test_seasons(df, league, target=Y_REG, gap=GAP, min_train=MIN_TRAIN_SEASONS, last=None):
    """First season with >= min_train labelled training seasons (<= T - gap), through TEST_LAST[league]."""
    lab = sorted(df[(df.league == league) & df[target].notna()][SEASON].unique())
    last = TEST_LAST[league] if last is None else last
    return [T for T in lab if T <= last and sum(s <= T - gap for s in lab) >= min_train]


def inner_splits(seasons, gap=GAP, n_val=3, min_train=2):
    """Time-based inner CV inside the training rows: validate on each of the last `n_val` training seasons V,
    training on seasons <= V - gap. `seasons` is the per-row season array of the training set."""
    seasons = np.asarray(seasons)
    uniq = np.sort(np.unique(seasons))
    splits = []
    for V in uniq[-n_val:]:
        tr = np.where(seasons <= V - gap)[0]
        va = np.where(seasons == V)[0]
        if len(np.unique(seasons[tr])) >= min_train and len(va):
            assert seasons[tr].max() <= V - gap
            splits.append((tr, va))
    assert splits, "no valid inner split"
    return splits


def walk_forward(df, league, features, target, make_model, tests, gap=GAP, kind="reg"):
    """Fit one model per test season. make_model(inner_cv) -> estimator (Pipeline or GridSearchCV over one).
    Returns (predictions, coefficients, chosen hyperparameters)."""
    assert not any(f.startswith("y_") for f in features), "label column in X"
    g = df[(df.league == league) & df[target].notna()].reset_index(drop=True)
    preds, coefs, params = [], [], []
    for T in tests:
        tr, te = g[g[SEASON] <= T - gap], g[g[SEASON] == T]
        assert tr[SEASON].max() <= T - gap, f"training row later than T-{gap}"
        assert not tr.empty and not te.empty
        X_tr, X_te = tr[features], te[features]
        assert not any(c.startswith("y_") for c in X_tr.columns)
        model = make_model(inner_splits(tr[SEASON].to_numpy(), gap=gap))
        model.fit(X_tr, tr[target])
        est = getattr(model, "best_estimator_", model)
        if hasattr(model, "best_params_"):
            params.append({"season": T, **model.best_params_})
        out = te[KEY].copy()
        out["y"] = te[target].to_numpy()
        out["pred"] = model.predict_proba(X_te)[:, 1] if kind == "clf" else model.predict(X_te)
        preds.append(out)
        final = est.steps[-1][1]
        if hasattr(final, "coef_"):
            names = est[:-1].get_feature_names_out() if len(est.steps) > 1 else np.array(features)
            for n, c in zip(names, np.ravel(final.coef_)):
                coefs.append({"season": T, "feature": n, "coef": float(c)})
    return pd.concat(preds, ignore_index=True), pd.DataFrame(coefs), pd.DataFrame(params)


# ---------------- metrics ----------------
def _spearman(a, b):
    return pd.Series(a).rank().corr(pd.Series(b).rank()) if len(a) > 2 else np.nan


def metrics(d):
    """d: rows with season, y_doom (0-100), y_bin (0/1), score (higher = more doomed) and optional pred (doom
    points, for MAE/R2) and prob (probability, for Brier). Returns a dict of metrics."""
    m = {}
    per = [_spearman(s.score, s.y_doom) for _, s in d.groupby("season")]
    m["spearman_mean"] = float(np.nanmean(per))
    m["spearman_pooled"] = _spearman(d.score, d.y_doom)
    if d["pred"].notna().all():
        m["mae"] = mean_absolute_error(d.y_doom, d.pred)
        m["r2"] = r2_score(d.y_doom, d.pred)
    else:
        m["mae"] = m["r2"] = np.nan
    m["auc"] = roc_auc_score(d.y_bin, d.score) if d.y_bin.nunique() == 2 else np.nan
    m["brier"] = brier_score_loss(d.y_bin, d.prob) if d["prob"].notna().all() else np.nan
    m["top5_hits"] = float(np.mean([s.nlargest(5, "score").y_bin.sum() for _, s in d.groupby("season")]))
    return m


METRICS = ["spearman_mean", "spearman_pooled", "mae", "r2", "auc", "brier", "top5_hits"]


def _fast_prep(d, idx):
    """Arrays + per-season metrics (unchanged by resampling whole seasons) for the vectorized bootstrap."""
    p = {k: d[k].to_numpy(dtype=float) for k in ("y_doom", "y_bin", "score", "pred", "prob")}
    p["sp_season"] = np.array([_spearman(p["score"][i], p["y_doom"][i]) for i in idx])
    p["top5_season"] = np.array([p["y_bin"][i][np.argsort(-p["score"][i], kind="stable")[:5]].sum() for i in idx])
    p["has_pred"], p["has_prob"] = bool(np.isfinite(p["pred"]).all()), bool(np.isfinite(p["prob"]).all())
    return p


def _fast_metrics(p, pick, rows):
    """Same definitions as metrics(), on a bootstrap draw (pick = season positions, rows = their row indices)."""
    y, yb, s = p["y_doom"][rows], p["y_bin"][rows], p["score"][rows]
    m = {"spearman_mean": float(np.nanmean(p["sp_season"][pick])),
         "spearman_pooled": float(np.corrcoef(rankdata(s), rankdata(y))[0, 1]),
         "top5_hits": float(np.mean(p["top5_season"][pick]))}
    if p["has_pred"]:
        e = p["pred"][rows]
        m["mae"] = float(np.mean(np.abs(y - e)))
        m["r2"] = float(1 - np.sum((y - e) ** 2) / np.sum((y - y.mean()) ** 2))
    else:
        m["mae"] = m["r2"] = np.nan
    n1 = yb.sum(); n0 = len(yb) - n1
    m["auc"] = float((rankdata(s)[yb == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else np.nan
    m["brier"] = float(np.mean((p["prob"][rows] - yb) ** 2)) if p["has_prob"] else np.nan
    return m


BLOCK = 3   # moving-block length in test seasons (D72): adjacent labels share up to two future seasons


def block_pick(rng, n, block=BLOCK):
    """Moving-block bootstrap draw of n season positions: ceil(n / block) blocks of `block` consecutive test
    seasons, start chosen uniformly from the n - block + 1 possible starts (no wrap-around), truncated to n.
    block = 1 is the ordinary per-season bootstrap."""
    k = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=k)
    return (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]


def bootstrap_diff(d_model, d_base, n_boot=2000, seed=2026, block=BLOCK):
    """95% interval for metric(model) - metric(base) from a moving-block bootstrap over test seasons (same draw
    for both). Returns {metric: (diff, lo, hi)}."""
    rng = np.random.default_rng(seed)
    assert (d_model[["season", "franchise_id"]].to_numpy() == d_base[["season", "franchise_id"]].to_numpy()).all()
    seasons = np.sort(d_model.season.unique())
    idx = [np.where(d_model.season.to_numpy() == s)[0] for s in seasons]
    point_m, point_b = metrics(d_model), metrics(d_base)
    fm, fb = _fast_prep(d_model, idx), _fast_prep(d_base, idx)
    draws = {k: [] for k in METRICS}
    for _ in range(n_boot):
        pick = block_pick(rng, len(seasons), block)
        rows = np.concatenate([idx[i] for i in pick])
        a, b = _fast_metrics(fm, pick, rows), _fast_metrics(fb, pick, rows)
        for k in METRICS:
            draws[k].append(a[k] - b[k])
    out = {}
    for k in METRICS:
        v = np.array(draws[k], dtype=float)
        diff = point_m[k] - point_b[k]
        out[k] = (diff, *np.nanpercentile(v, [2.5, 97.5])) if np.isfinite(diff) else (np.nan, np.nan, np.nan)
    return out


def coef_stability(coefs):
    """Per feature across folds: median, min, max, share of folds at exactly 0, share of non-zero folds whose
    sign is opposite to the majority sign, and the number of fold-to-fold sign changes."""
    rows = []
    for f, g in coefs.sort_values("season").groupby("feature", sort=False):
        c = g.coef.to_numpy()
        nz = c[c != 0]
        maj = np.sign(np.sum(np.sign(nz))) if len(nz) else 0
        s = np.sign(nz)
        rows.append(dict(feature=f, median=np.median(c), min=c.min(), max=c.max(), n_folds=len(c),
                         zero_share=float(np.mean(c == 0)),
                         opposite_sign_share=float(np.mean(s != maj)) if len(nz) and maj != 0 else
                         (0.5 if len(nz) else 0.0),
                         sign_changes=int(np.sum(s[1:] != s[:-1])) if len(nz) > 1 else 0))
    return pd.DataFrame(rows)
