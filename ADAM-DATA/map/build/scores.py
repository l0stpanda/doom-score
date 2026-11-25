"""The one input the Doom Map takes from the model side: per-team doom scores (docs/SCORES_FORMAT.md, M50).

Every *.csv in map/inputs/scores/ is read; nothing else in the map reads predictions. A file holds one or more
leagues; a (league, season_start_year, franchise_id) may appear only once across all files.
Required columns: league, season_start_year, franchise_id, doom_pred (0-100). Everything else is optional, per league:
a column that is missing, or empty for every row of a league, counts as "not provided" for that league, and the
page hides what depends on it (M51).
"""
import glob, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
SCORES_DIR = os.path.join(MAP, "inputs", "scores")

REQUIRED = ["league", "season_start_year", "franchise_id", "doom_pred"]
# column -> (kind, lo, hi); kind: num | text | band. Ranges are inclusive; None = open.
OPTIONAL = {
    "doom_lo80": ("num", 0, 100), "doom_hi80": ("num", 0, 100),
    "win_pct": ("num", 0, 1), "win_pct_percentile": ("num", 0, 100),
    "record": ("text", None, None), "band": ("band", None, None), "p_doom75": ("num", 0, 1),
    **{f"driver_{d}_{i}": ("text", None, None) for d in ("up", "down") for i in (1, 2, 3)},
    "driver_note": ("text", None, None),
    **{f"proj_pct_t{i}": ("num", 0, 100) for i in (1, 2, 3)},
    "actual_doom": ("num", 0, 100),
}
BANDS = ["Low", "Moderate", "High", "Very high"]
COLUMNS = REQUIRED + list(OPTIONAL)
# features the page can show, and the optional columns each one needs (all of them, per league)
FEATURES = {
    "range80": ["doom_lo80", "doom_hi80"], "band": ["band"], "p_doom75": ["p_doom75"],
    "win_pct": ["win_pct"], "standing": ["win_pct_percentile"], "record": ["record"],
    "drivers": [f"driver_{d}_{i}" for d in ("up", "down") for i in (1, 2, 3)],
    "driver_note": ["driver_note"], "projection": ["proj_pct_t1", "proj_pct_t2", "proj_pct_t3"],
    "actual": ["actual_doom"],
}


class ScoresError(Exception):
    pass


def validate(df, name="scores"):
    """Check columns, types and ranges. Returns (clean frame, warnings). Raises ScoresError listing every problem."""
    errs, warns = [], []
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ScoresError(f"{name}: missing required column(s): {', '.join(missing)} "
                          f"(required: {', '.join(REQUIRED)})")
    extra = [c for c in df.columns if c not in COLUMNS]
    if extra:
        warns.append(f"{name}: ignoring unknown column(s): {', '.join(extra)} (see docs/SCORES_FORMAT.md)")
        df = df.drop(columns=extra)
    if df.empty:
        raise ScoresError(f"{name}: no rows")

    def rows(mask, k=8):
        idx = list(np.flatnonzero(mask.to_numpy()) + 2)       # +2: header line and 1-based numbering
        return ", ".join(map(str, idx[:k])) + (f" (+{len(idx) - k} more)" if len(idx) > k else "")

    for c in ("league", "franchise_id"):
        df[c] = df[c].astype("string").str.strip()
        bad = df[c].isna() | (df[c] == "")
        if bad.any():
            errs.append(f"{c} is empty on line(s) {rows(bad)}")
    df["league"] = df["league"].str.upper()
    yr = pd.to_numeric(df.season_start_year, errors="coerce")
    bad = yr.isna() | (yr != yr.round()) | (yr < 1900) | (yr > 2100)
    if bad.any():
        errs.append(f"season_start_year must be a whole year, e.g. 2024 (line(s) {rows(bad)})")
    df["season_start_year"] = yr.astype("Int64")
    dp = pd.to_numeric(df.doom_pred, errors="coerce")
    bad = dp.isna() | (dp < 0) | (dp > 100)
    if bad.any():
        errs.append(f"doom_pred must be a number from 0 to 100 on every row (line(s) {rows(bad)})")
    df["doom_pred"] = dp

    for c, (kind, lo, hi) in OPTIONAL.items():
        if c not in df.columns:
            continue
        if kind == "num":
            raw = df[c]
            v = pd.to_numeric(raw, errors="coerce")
            notnum = raw.notna() & (raw.astype("string").str.strip() != "") & v.isna()
            if notnum.any():
                errs.append(f"{c} must be numeric (line(s) {rows(notnum)})")
            out = v.notna() & (((v < lo) if lo is not None else False) | ((v > hi) if hi is not None else False))
            if out.any():
                errs.append(f"{c} must be within {lo}-{hi} (line(s) {rows(out)})")
            df[c] = v
        else:
            s = df[c].astype("string").str.strip()
            df[c] = s.where(s != "", pd.NA)
            if kind == "band":
                bad = df[c].notna() & ~df[c].isin(BANDS)
                if bad.any():
                    errs.append(f"band must be one of {', '.join(BANDS)} or empty (line(s) {rows(bad)})")
    if {"doom_lo80", "doom_hi80"} <= set(df.columns):
        bad = df.doom_lo80.notna() & df.doom_hi80.notna() & (df.doom_lo80 > df.doom_hi80)
        if bad.any():
            errs.append(f"doom_lo80 is above doom_hi80 (line(s) {rows(bad)})")
        one = df.doom_lo80.isna() != df.doom_hi80.isna()
        if one.any():
            errs.append(f"doom_lo80 and doom_hi80 must both be given or both be empty (line(s) {rows(one)})")
    dup = df.duplicated(["league", "season_start_year", "franchise_id"], keep=False)
    if dup.any():
        errs.append(f"duplicate (league, season_start_year, franchise_id) on line(s) {rows(dup)}")
    if errs:
        raise ScoresError(f"{name}:\n  - " + "\n  - ".join(errs))
    return df, warns


def read_file(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig")


def load_scores(folder=SCORES_DIR, quiet=False):
    """All score files in the folder -> (one frame with every COLUMN, {league: [features provided]}, {file: leagues})."""
    files = sorted(glob.glob(os.path.join(folder, "*.csv")))
    if not files:
        raise ScoresError(f"no score files in {os.path.relpath(folder)} (add one with map/add_scores.py)")
    frames, by_file = [], {}
    for f in files:
        df, warns = validate(read_file(f), os.path.basename(f))
        if not quiet:
            for w in warns:
                print("WARNING", w)
        df["_file"] = os.path.basename(f)
        by_file[os.path.basename(f)] = sorted(df.league.unique())
        frames.append(df)
    S = pd.concat(frames, ignore_index=True)
    dup = S[S.duplicated(["league", "season_start_year", "franchise_id"], keep=False)]
    if len(dup):
        raise ScoresError("the same team-season is in more than one score file:\n"
                          + dup.sort_values(["league", "season_start_year", "franchise_id"])
                          [["_file", "league", "season_start_year", "franchise_id"]].head(20).to_string(index=False))
    for c in OPTIONAL:
        if c not in S.columns:
            S[c] = pd.NA
    S = S[COLUMNS + ["_file"]]
    S["season_start_year"] = S.season_start_year.astype(int)
    for c, (kind, _, _) in OPTIONAL.items():
        S[c] = pd.to_numeric(S[c]) if kind == "num" else S[c].astype("object").where(S[c].notna(), None)
    provided = {}
    for lg, g in S.groupby("league"):
        provided[lg] = [k for k, cols in FEATURES.items() if any(g[c].notna().any() for c in cols)]
    return S, provided, by_file


if __name__ == "__main__":
    try:
        S, provided, by_file = load_scores()
    except ScoresError as e:
        sys.exit(f"Scores problem: {e}")
    for f, lgs in by_file.items():
        print(f"{f}: {', '.join(lgs)}")
    for lg, g in S.groupby("league"):
        print(f"{lg}: {len(g)} team-seasons, {g.season_start_year.min()}-{g.season_start_year.max()}, "
              f"{g.franchise_id.nunique()} franchises; provides: {', '.join(provided[lg]) or 'required columns only'}")
