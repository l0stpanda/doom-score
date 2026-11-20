"""Shared-concept aliases (for stacking with NBA/NFL), within-league-season percentiles (_lpct), vet_share_lq,
spending availability. Reads/writes data/processed/mlb_nhl_team_seasons.csv (idempotent: drops its own columns
first) and writes reports/feature_crosswalk.md. Decisions D57-D60."""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_phase3 as p3
from common import lpct

ROOT = p3.ROOT
OUT = os.path.join(ROOT, "data", "processed", "mlb_nhl_team_seasons.csv")
KEY = ["league", "season_start_year", "franchise_id"]
N_CORE = 19

# concept -> (MLB column, NHL column, definition, notes)
CONCEPTS = {
    "roster_age_weighted": ("age_weighted", "age_weighted", "Playing-time-weighted roster age",
                            "Age on MLB Jun 30 t / NHL Feb 1 t+1"),
    "vet_share": ("share_production_age32plus", "share_production_age32plus",
                  "Share of playing time from players aged 32+", "Fixed age cut"),
    "vet_share_lq": ("vet_share_lq", "vet_share_lq",
                     "Share of playing time from the league-season's oldest quartile (playing-time-weighted age q75)",
                     "Cut adapts per league-season"),
    "star_concentration": ("top3_concentration", "top3_concentration", "Top-3 players' share of team production",
                           "MLB: share of PA+BF; NHL: share of skater points"),
    "margin_per_game": ("point_diff_per_game", "point_diff_per_game", "(scored - allowed) / games", "Runs vs goals"),
    "luck": ("luck", "luck", "win_pct - Pythagorean win%", "Exponent 1.83 MLB, 2.0 NHL"),
    "underlying_quality": ("pythag_win_pct", "corsi_pct", "Quality beyond W-L record",
                           "MLB: Pythagorean win% (run-based, overlaps margin); NHL: Corsi% 2008+ (no model). "
                           "Alternative NHL: xgoals_pct (stronger, soft leakage D54)"),
    "draft_capital": ("draft_picks_rd1_2", "draft_picks_rd1_2", "Picks in rounds 1-2 of the year-t draft",
                      "MLB incl. supplemental 1st, CB-A, PPI. Alternative: draft_first_pick_number"),
    "gm_tenure": ("personnel_lead_tenure_years", "personnel_lead_tenure_years", "GM tenure at the prediction moment",
                  "NaN when vacant (personnel_lead_vacant = 1)"),
    "coach_tenure": ("coach_tenure_years", "coach_tenure_years", "Manager/head-coach tenure at end of regular season",
                     "Mid-season first season = 0.5"),
    "spending": ("payroll_rel_league_mean", None, "Payroll relative to league-season mean",
                 "MLB: Cot's Opening Day payroll / league mean. NHL: unavailable (spending_available = 0)"),
    "market": ("attendance_per_game", None, "Market / demand proxy",
               "MLB: home attendance per game (partly endogenous to winning; 2020 NaN). NHL: unavailable"),
}




def wquantile(x, w, q):
    o = np.argsort(x)
    x, w = np.asarray(x)[o], np.asarray(w)[o]
    cw = np.cumsum(w) / w.sum()
    return x[np.searchsorted(cw, q)]


def vet_share_lq():
    ms = p3.mlb_stints()
    mp = ms.groupby(["season_start_year", "franchise_id", "player_id"]).agg(pa=("pa", "sum"), bf=("bf", "sum"),
                                                                             age=("age", "first")).reset_index()
    mp["w"] = mp.pa + mp.bf
    mp["league"] = "MLB"
    ns = p3.nhl_stints()
    ns = ns.rename(columns={"toi": "w"})
    ns["league"] = "NHL"
    allp = pd.concat([mp[["league", "season_start_year", "franchise_id", "player_id", "age", "w"]],
                      ns[["league", "season_start_year", "franchise_id", "player_id", "age", "w"]]])
    allp = allp[(allp.w > 0) & allp.age.notna()]
    cut = allp.groupby(["league", "season_start_year"]).apply(lambda g: wquantile(g.age, g.w, 0.75),
                                                              include_groups=False).rename("vet_age_cut_lq")
    allp = allp.merge(cut.reset_index(), on=["league", "season_start_year"])
    allp["old"] = allp.age >= allp.vet_age_cut_lq
    g = allp.groupby(KEY)
    return pd.DataFrame({"vet_share_lq": g.apply(lambda x: x.w[x.old].sum() / x.w.sum(), include_groups=False),
                         "vet_age_cut_lq": g.vet_age_cut_lq.first()}).reset_index()


def main():
    df = pd.read_csv(OUT)
    mine = ["playing_time_weight", "spending_available", "market_available", "vet_share_lq", "vet_age_cut_lq"] + \
           [c for c in CONCEPTS if c not in df.columns or c == "vet_share_lq"] + [c + "_lpct" for c in CONCEPTS]
    df = df.drop(columns=[c for c in set(mine) if c in df.columns and c != "luck"])
    df = df.merge(vet_share_lq(), on=KEY, how="left")
    df["playing_time_weight"] = np.where(df.league == "MLB", "PA+BF", "TOI")
    for concept, (mcol, ncol, _, _) in CONCEPTS.items():
        vals = pd.Series(np.nan, index=df.index, dtype=float)
        for lg, col in (("MLB", mcol), ("NHL", ncol)):
            if col:
                vals[df.league == lg] = df.loc[df.league == lg, col].astype(float)
        df[concept] = vals
        df[concept + "_lpct"] = df.groupby(["league", "season_start_year"])[concept].transform(lpct)
    df["spending_available"] = (df.league == "MLB").astype(int)  # D57
    df["market_available"] = (df.league == "MLB").astype(int)

    shared = ["playing_time_weight"] + [c for c in CONCEPTS] + [c + "_lpct" for c in CONCEPTS] + \
             ["spending_available", "market_available"]
    core = list(df.columns[:N_CORE])
    labels = [c for c in df.columns if c.startswith("y_")]
    rest = [c for c in df.columns if c not in core + shared + labels]
    df = df[core + shared + rest + labels]
    df.to_csv(OUT, index=False)
    print(f"wrote {os.path.basename(OUT)}: {df.shape}")

    # checks
    w = np.where(df.league == "MLB", df.team_pa + df.team_bf, df.skater_gp_sum)  # playing-time proxy for weighting
    lq_means = df.assign(w=w).groupby(["league", "season_start_year"]).apply(
        lambda g: np.average(g.vet_share_lq, weights=g.w), include_groups=False)

    def endpoints_ok(d):
        for c in CONCEPTS:
            for _, g in d.groupby(["league", "season_start_year"]):
                s, p = g[c].dropna(), g[c + "_lpct"].dropna()
                n = len(s)
                if n < 2 or s.nunique() < 2:
                    continue
                lo = ((s == s.min()).sum() - 1) / 2 / (n - 1) * 100
                hi = 100 - ((s == s.max()).sum() - 1) / 2 / (n - 1) * 100
                if not (np.isclose(p.min(), lo) and np.isclose(p.max(), hi)):
                    return False
        return True
    checks = [
        ("core columns unchanged and first", core == list(pd.read_csv(OUT, nrows=0).columns[:N_CORE]), ""),
        ("every concept equals its source column (alias)",
         all(np.allclose(df.loc[df.league == lg, c].astype(float), df.loc[df.league == lg, col].astype(float), equal_nan=True)
             for c, (m, n, _, _) in CONCEPTS.items() for lg, col in (("MLB", m), ("NHL", n)) if col), ""),
        ("_lpct endpoints = 0/100 except tie adjustment, in every league-season", endpoints_ok(df), ""),
        ("_lpct NaN exactly where the concept is NaN", all((df[c].isna() == df[c + "_lpct"].isna()).all() for c in CONCEPTS), ""),
        ("NHL spending and market all NaN (unavailable)",
         df.loc[df.league == "NHL", ["spending", "market"]].isna().all().all(), ""),
        ("vet_share_lq in [0,1] for every row", df.vet_share_lq.between(0, 1).all(),
         f"mean MLB {df[df.league=='MLB'].vet_share_lq.mean():.3f}, NHL {df[df.league=='NHL'].vet_share_lq.mean():.3f}"),
        ("vet_share_lq playing-time-weighted league-season mean in 0.24..0.30 (oldest quartile; ties at the cut add a bit)",
         lq_means.between(0.24, 0.30).all(), f"{lq_means.min():.3f}-{lq_means.max():.3f}"),
        ("lpct of win_pct reproduces win_pct_percentile (formula check)",
         np.allclose(df.groupby(["league", "season_start_year"]).win_pct.transform(lpct), df.win_pct_percentile), ""),
        ("one row per key; 1,454 rows", (not df.duplicated(KEY).any()) and len(df) == 1454, ""),
    ]
    for c, ok, det in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {c} {det}")
    pd.DataFrame(checks, columns=["check", "pass", "detail"]).to_csv(os.path.join(ROOT, "reports", "crosswalk_checks.csv"),
                                                                    index=False)
    cut = df.groupby("league").vet_age_cut_lq.agg(["min", "max"]).round(1)
    print("vet age cut (q75 of playing-time-weighted age) range:", cut.to_dict("index"))

    # reports/feature_crosswalk.md (was FEATURE_CROSSWALK.md, archived)
    cov = lambda c, lg: f"{df[df.league == lg][c].notna().mean() * 100:.0f}%"
    lines = ["# Feature crosswalk (shared concepts across leagues)", "",
             "Shared concept columns sit right after the 19 core columns in `data/processed/mlb_nhl_team_seasons.csv`. "
             "Each concept is an **alias** (copy) of a league-specific column, so the NBA/NFL files can fill the same "
             "names. `<concept>_lpct` = within-league-season percentile, (average rank − 1)/(n − 1) × 100 over "
             "non-missing values, the same formula as `win_pct_percentile` (0 = lowest, 100 = highest). Use `_lpct` "
             "when stacking leagues, because raw scales differ (runs vs goals, PA+BF vs TOI, dollars vs none).", "",
             "| Concept | Definition | MLB column | NHL column | NBA | NFL | Coverage MLB / NHL | Notes |",
             "|---|---|---|---|---|---|---|---|",
             "| playing-time weight (`playing_time_weight`) | Weight used for roster aggregates | PA + batters faced per team stint | "
             "time on ice per team stint | TBD (e.g. minutes) | TBD (e.g. snaps) | 100% / 100% | Text column naming the basis |"]
    for c, (m, n, d, note) in CONCEPTS.items():
        lines.append(f"| `{c}` | {d} | `{m}` | {'`' + n + '`' if n else '**unavailable**'} | TBD | TBD | "
                     f"{cov(c, 'MLB')} / {cov(c, 'NHL')} | {note} |")
    lines += ["", "Flags: `spending_available`, `market_available` (1 = MLB, 0 = NHL). `vet_age_cut_lq` stores the "
              "league-season age cut used by `vet_share_lq` "
              f"(MLB {cut.loc['MLB','min']}–{cut.loc['MLB','max']}, NHL {cut.loc['NHL','min']}–{cut.loc['NHL','max']} years).",
              "", "Decisions: D57 (spending), D58 (concept choices), D59 (_lpct), D60 (vet_share_lq). "
              "NBA/NFL columns are TBD for the teammate to fill."]
    open(os.path.join(ROOT, "reports", "feature_crosswalk.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote reports/feature_crosswalk.md")


if __name__ == "__main__":
    main()
