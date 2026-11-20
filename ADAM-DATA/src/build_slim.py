"""Slim model table: one column per concept, chosen by concept (not by correlation with the label). Decisions D61, D71.

Reads  data/processed/mlb_nhl_team_seasons.csv (never modified; checked by hash).
Writes data/processed/mlb_nhl_model_slim.csv and SLIM_SELECTION.md (kept/dropped + one-line reason per column).
Run:   PYTHONUTF8=1 python ADAM-DATA/src/build_slim.py"""
import hashlib, os
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
FULL = os.path.join(ROOT, "data", "processed", "mlb_nhl_team_seasons.csv")
SLIM = os.path.join(ROOT, "data", "processed", "mlb_nhl_model_slim.csv")
DOC = os.path.join(ROOT, "SLIM_SELECTION.md")

# Concepts in the slim table, in order. Each uses its FEATURE_CROSSWALK.md alias, as the _lpct version.
CONCEPTS = ["margin_per_game", "luck", "underlying_quality", "roster_age_weighted", "star_concentration",
            "draft_capital", "gm_tenure", "coach_tenure", "spending"]

# (slim column, group, reason kept)
KEPT = [
    ("league", "id", "Row key: league."),
    ("season_start_year", "id", "Row key: season t (NHL 2017 = 2017-18)."),
    ("franchise_id", "id", "Row key: franchise, stable through relocations/renames."),
    ("team", "id", "Display name."),
    ("wins", "id", "Display: season-t record."),
    ("losses", "id", "Display: season-t record (NHL = regulation losses)."),
    ("ot_losses", "id", "Display: NHL OT/SO losses; NaN for MLB by design (no such result)."),
    ("games", "id", "Display: games played in t."),
    ("win_pct", "id", "Display: season-t win% (NHL = points %)."),
] + [(f"{c}_lpct", "feature", f"Concept `{c}`: crosswalk alias as within-league-season percentile, comparable across leagues.")
     for c in CONCEPTS] + [
    ("win_pct_percentile", "feature", "Current standing, already a within-league-season percentile."),
    ("win_pct_trailing_3_seasons", "feature", "Recent-trajectory concept: mean win% over the last 3 played seasons."),
    ("win_pct_trailing_3_seasons_lpct", "feature", "Derived (D71): within-league-season percentile of "
                                                    "win_pct_trailing_3_seasons, comparable across leagues."),
    ("short_season", "flag", "Flags shortened seasons (MLB 2020; NHL 2012, 2019, 2020)."),
    ("seasons_of_history", "flag", "How many seasons the trailing features rest on (expansion teams)."),
    ("personnel_lead_vacant", "flag", "Model feature (D71): explains NaN gm_tenure (vacancy is known, not missing)."),
    ("y_doom_3yr", "label", "Primary label (t+1..t+3). LABEL, not a feature."),
    ("y_doomed_bottom25", "label", "Binary label (doom >= 75). LABEL, not a feature."),
    ("y_pct_t1", "label", "Component label: percentile in t+1. LABEL."),
    ("y_pct_t2", "label", "Component label: percentile in t+2. LABEL."),
    ("y_pct_t3", "label", "Component label: percentile in t+3. LABEL."),
]

# League source columns behind each crosswalk alias (from FEATURE_CROSSWALK.md).
SOURCE_OF = {"age_weighted": "roster_age_weighted", "top3_concentration": "star_concentration",
             "point_diff_per_game": "margin_per_game", "pythag_win_pct": "underlying_quality",
             "corsi_pct": "underlying_quality", "draft_picks_rd1_2": "draft_capital",
             "personnel_lead_tenure_years": "gm_tenure", "coach_tenure_years": "coach_tenure",
             "payroll_rel_league_mean": "spending", "share_production_age32plus": "vet_share",
             "attendance_per_game": "market"}

DROPPED = {
    "ties": "MLB: 12 rows with a tie; NHL: duplicates ot_losses (D07). Not in the requested display set.",
    "observed_doom_next_3_seasons": "Duplicate of y_doom_3yr (teammate schema name).",
    "draft_picks_used": "Draft concept uses draft_capital (rounds 1-2) per the crosswalk.",
    "cap_space_pct": "Empty for both leagues (D57).",
    "personnel_lead_changed_past_year": "GM concept is represented by gm_tenure; MLB 2026 systematically 0 (D43).",
    "standings_source": "Audit (source URL).",
    "draft_source": "Audit (source URL).",
    "playing_time_weight": "Text descriptor of the weighting basis, not a feature.",
    "vet_share": "Concept not in the slim set (age is covered by roster_age_weighted).",
    "vet_share_lq": "Concept not in the slim set (age is covered by roster_age_weighted).",
    "vet_share_lpct": "Concept not in the slim set (age is covered by roster_age_weighted).",
    "vet_share_lq_lpct": "Concept not in the slim set (age is covered by roster_age_weighted).",
    "market": "Concept not in the slim set: NHL unavailable; MLB attendance is partly endogenous to winning.",
    "market_lpct": "Concept not in the slim set: NHL unavailable; MLB attendance is partly endogenous to winning.",
    "spending_available": "Equals league == MLB; spending_lpct is NaN for NHL, recoverable from `league`.",
    "market_available": "Market concept dropped; also equals league == MLB.",
    "win_pct_raw": "Alternative win% (NHL without OTL credit); win_pct is kept.",
    "scored_per_game": "Component of margin_per_game.",
    "allowed_per_game": "Component of margin_per_game.",
    "win_pct_change_1yr": "Trajectory concept uses win_pct_trailing_3_seasons.",
    "win_pct_slope_3yr": "Trajectory concept uses win_pct_trailing_3_seasons.",
    "expansion_first_3_seasons": "Only 6 NHL rows; seasons_of_history carries the same information.",
    "draft_first_pick_number": "Crosswalk alternative for draft_capital; the listed choice is rounds 1-2 picks.",
    "draft_rounds_in_year": "Context for the draft count, not a team feature.",
    "draft_picks_used_pctile": "Draft concept uses draft_capital (rounds 1-2) per the crosswalk.",
    "coach_name": "Name (text), not a feature.",
    "coach_changed_during_regular_season": "Coach concept is represented by coach_tenure.",
    "coach_tenure_left_censored": "Data-quality flag for coach_tenure; kept in the full table.",
    "manager_resolved_by_fallback": "Audit flag (4 MLB rows).",
    "personnel_lead_name": "Name (text), not a feature.",
    "personnel_lead_tenure_left_censored": "Data-quality flag for gm_tenure; kept in the full table.",
    "personnel_lead_gap_carried": "Data-quality flag for gm_tenure; kept in the full table.",
    "attendance_per_game": "League source column of `market`; market concept not in the slim set.",
    "share_production_age32plus": "League source column of `vet_share`; concept not in the slim set.",
    "attendance_restricted": "Market concept dropped.",
    "attendance_rank": "Market concept dropped.",
    "age_weighted_hitters": "MLB-only split of roster_age_weighted.",
    "age_weighted_pitchers": "MLB-only split of roster_age_weighted.",
    "share_points_age32plus": "NHL-only variant of vet_share; concept not in the slim set.",
    "roster_players_used": "Not one of the slim concepts.",
    "age_weight_coverage": "Audit (1.0 everywhere).",
    "team_pa": "Audit (weight total).",
    "team_bf": "Audit (weight total).",
    "skater_gp_sum": "Audit (weight total).",
    "goalie_gp_sum": "Audit (weight total).",
    "xgoals_pct": "Crosswalk alternative for NHL underlying_quality; soft leakage (D54); NHL only.",
    "pdo_5v5": "NHL-only luck gauge; luck concept uses the crosswalk `luck` column.",
    "payroll_opening_day_usd": "Raw dollars; spending uses payroll_rel_league_mean per the crosswalk.",
    "cbt_threshold_usd": "League-level context, not a team feature.",
    "payroll_pct_of_cbt": "Spending alternative; crosswalk uses payroll_rel_league_mean (2020 pro-rating).",
    "payroll_rank": "Spending alternative; spending_lpct is the within-season rank form.",
    "cap_upper_limit_usd": "League-level context, not a team feature.",
    "team_cap_hit_usd": "Empty (D57).",
    "team_name_then": "Audit (name used that season).",
    "team_id": "Audit (source team ID).",
    "payroll_source": "Audit (source URL).",
    "underlying_source": "Audit (source URL).",
    "vet_age_cut_lq": "Helper for vet_share_lq; concept not in the slim set.",
}


# Slim-only columns computed here from full-table columns (not in the full table). D71.
DERIVED = {"win_pct_trailing_3_seasons_lpct": "win_pct_trailing_3_seasons"}


def lpct(s):
    """Within league-season percentile, same formula as win_pct_percentile / FEATURE_CROSSWALK _lpct (D59)."""
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * float("nan")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    before = sha(FULL)
    df = pd.read_csv(FULL, low_memory=False)
    slim_cols = [c for c, _, _ in KEPT]
    for c, src in DERIVED.items():
        df[c] = df.groupby(["league", "season_start_year"])[src].transform(lpct)
    # D59 check: the same formula reproduces win_pct_percentile exactly
    chk = df.groupby(["league", "season_start_year"]).win_pct.transform(lpct)
    assert (chk - df.win_pct_percentile).abs().max() < 1e-9
    full_cols = [c for c in df.columns if c not in DERIVED]
    reasons = {c: r for c, _, r in KEPT}
    for c in full_cols:
        if c in reasons:
            continue
        if c in DROPPED:
            reasons[c] = DROPPED[c]
        elif c in CONCEPTS:
            reasons[c] = f"Raw alias; scales differ by league, so the slim table uses `{c}_lpct`."
        elif c in SOURCE_OF and SOURCE_OF[c] in CONCEPTS:
            reasons[c] = f"League source column of `{SOURCE_OF[c]}`; slim table uses `{SOURCE_OF[c]}_lpct`."
        else:
            raise SystemExit(f"no reason for column {c}")

    missing = [c for c in slim_cols if c not in df.columns]
    assert not missing, missing
    assert set(reasons) == set(df.columns), set(reasons) ^ set(df.columns)
    assert set(DERIVED) <= set(slim_cols)
    assert len(slim_cols) == len(set(slim_cols))

    slim = df[slim_cols]
    slim.to_csv(SLIM, index=False)
    assert sha(FULL) == before, "full table changed"

    # round-trip check: every slim value equals the full-table value
    back = pd.read_csv(SLIM, low_memory=False)
    assert back.shape == (len(df), len(slim_cols))
    assert back.astype(str).equals(df[slim_cols].astype(str))
    vac = back.personnel_lead_vacant
    assert vac.isna().sum() == df.personnel_lead_vacant.isna().sum() and set(vac.dropna().unique()) <= {0, 1}

    group = {c: g for c, g, _ in KEPT}
    rows = []
    for i, c in enumerate(full_cols + list(DERIVED), 1):
        kept = c in group
        nn = df[c].notna().mean() * 100
        tag = " (derived)" if c in DERIVED else ""
        rows.append(f"| {i} | `{c}`{tag} | {'**kept**' if kept else 'dropped'} | {group.get(c, '')} | {nn:.0f}% | {reasons[c]} |")
    n_keep = len(slim_cols)
    md = f"""# Slim model table: column selection

`data/processed/mlb_nhl_model_slim.csv` ({len(df):,} rows × {n_keep} columns) is a subset of the full table
`data/processed/mlb_nhl_team_seasons.csv` ({len(df):,} rows × {len(full_cols)} columns), which is unchanged,
plus {len(DERIVED)} derived column computed from it (marked "derived", last row). Built by `src/build_slim.py`.
Decisions **D61**, **D71** in `DECISIONS.md`.

**Chosen by concept, not by correlation with the label.** One `_lpct` column per concept; where a concept has
several candidate columns, the one listed in `FEATURE_CROSSWALK.md` is used. No column was picked or dropped
because of its relationship with `y_doom_3yr`.

Slim column order: ids/display → features → flags → labels. `y_*` columns are labels: never use them as features.

Coverage = share of all rows non-missing. `spending_lpct` is NaN for every NHL row (D57); `underlying_quality_lpct`
is NaN for NHL 2005–07 (Corsi starts 2008); `gm_tenure_lpct` is NaN where the GM is vacant or unknown.
No imputation.

| # | Column (full table order) | Status | Slim group | Coverage | Reason |
|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

Full-table columns: kept {n_keep - len(DERIVED)}, dropped {len(full_cols) - n_keep + len(DERIVED)}, total {len(full_cols)}; plus {len(DERIVED)} derived → {n_keep} slim columns.
"""
    open(DOC, "w", encoding="utf-8").write(md)
    print(f"slim: {slim.shape}; kept {n_keep - len(DERIVED)} / {len(full_cols)} + {len(DERIVED)} derived; "
          f"full table unchanged ({before[:12]})")


if __name__ == "__main__":
    main()
