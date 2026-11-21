"""Model core: load the slim table, per-league features, leakage-safe preprocessing and the model definitions used
for the dashboard (MLB = B1, NHL = elastic net; key decisions in docs/KEY_DECISIONS.md).

Leakage rules:
  1. Season T is predicted by a model trained only on seasons <= T - GAP (GAP = 3; asserted by the callers).
  2. Median fill, missing indicators and scaling live inside an sklearn Pipeline, so they are fitted on the
     training seasons only.
  3. Hyperparameters are tuned on a time-based inner split inside the training seasons, with the same gap.
"""
import os
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import ElasticNet, LinearRegression, LogisticRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
SLIM = os.path.join(ROOT, "data", "mlb_nhl_model_slim.csv")
KEY = ["league", "season_start_year", "franchise_id"]
SEASON = "season_start_year"
GAP = 3                    # labels of season s are known only after season s + 3
MIN_TRAIN_SEASONS = 6
TEST_LAST = {"MLB": 2023, "NHL": 2022}

FEATURES = ["win_pct_percentile", "win_pct_trailing_3_seasons_lpct", "margin_per_game_lpct", "luck_lpct",
            "underlying_quality_lpct", "roster_age_weighted_lpct", "star_concentration_lpct", "draft_capital_lpct",
            "gm_tenure_lpct", "coach_tenure_lpct", "spending_lpct", "personnel_lead_vacant", "short_season",
            "seasons_of_history"]
# MLB underlying_quality is Pythagorean win%, a near-duplicate of margin_per_game, so it is excluded (D63).
SPEC_EXCLUDE = {"MLB": {"underlying_quality_lpct": "near-duplicate of margin (Pythagorean win%)"}}
Y_REG, Y_CLF = "y_doom_3yr", "y_doomed_bottom25"

EN_GRID = {"model__alpha": np.logspace(-2, 1.5, 15), "model__l1_ratio": [0.1, 0.3, 0.5, 0.7, 0.9, 1.0]}
L1_GRID = {"model__C": np.logspace(-3, 1, 15)}


def load():
    df = pd.read_csv(SLIM, low_memory=False)
    missing = [f for f in FEATURES if f not in df.columns]
    assert not missing, f"slim table lacks {missing}"
    assert not df.duplicated(KEY).any()
    df["short_season"] = df.short_season.astype(str).eq("True").astype(float)
    df["personnel_lead_vacant"] = pd.to_numeric(df.personnel_lead_vacant, errors="coerce")
    df[Y_CLF] = df[Y_CLF].map({"True": 1.0, "False": 0.0, True: 1.0, False: 0.0})
    return df


def league_features(df, league, features=FEATURES):
    """Features usable for one league: drops all-missing columns and exclusions. Returns (kept, dropped)."""
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
        self.medians_ = X.median().fillna(0.0)          # a column all-missing in training is filled with 0
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
    """Time-based inner CV: validate on each of the last `n_val` training seasons V, train on seasons <= V - gap."""
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


# ---------------- model definitions ----------------
def pipe(model):
    return Pipeline([("impute", MedianImputeWithIndicator(0.01)), ("scale", StandardScaler()), ("model", model)])


def make_ols(cv):                       # B1 (and MLB per-horizon paths)
    return pipe(LinearRegression())


def make_logit_plain(cv):               # MLB p_doomed
    return pipe(LogisticRegression(C=np.inf, max_iter=5000))


def make_en(cv):                        # NHL doom and horizon paths
    return GridSearchCV(pipe(ElasticNet(max_iter=100000)), EN_GRID, cv=cv, scoring="neg_mean_squared_error")


def make_l1(cv):                        # NHL p_doomed
    return GridSearchCV(pipe(LogisticRegression(l1_ratio=1.0, solver="saga", max_iter=20000, random_state=0)), L1_GRID,
                        cv=cv, scoring="neg_log_loss")
