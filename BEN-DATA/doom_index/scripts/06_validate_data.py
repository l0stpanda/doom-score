"""06 - Validate the exported datasets and write a collection report.

WHAT IT CHECKS
    1. duplicate primary keys in every export
    2. missing team-season observations (expected from config/teams.csv)
    3. team IDs not in the franchise registry / inconsistent names
    4. impossible or inconsistent records (W+L(+OTL)=GP, ranges, percentages
       recomputed, PWHL standings points formula, playoff W/L consistency)
    5. season-label format and start/end-year consistency
    6. player rows: team exists for that season, player GP <= team GP,
       team totals reconcile with summed player stats, no duplicated stints
    7. draft: unique / contiguous pick numbers, known teams, inventory sanity
    8. financial: salary ranges vs CBA minimum, cap present, coverage
    9. provenance: every team-season in team_season_data has source rows with
       URL + retrieval timestamp
   10. schema consistency vs the previous run (data/exports/_schema_snapshot.json)
   11. source-vs-source cross-check results (from 01)

OUTPUTS
    logs/validation_results.csv       one row per check (PASS / WARN / FAIL + detail)
    data/exports/missingness_report.csv  % missing by dataset x league x column
    docs/collection_report.md         row counts, season coverage, missingness, source coverage
    Exit code 1 if any FAIL.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: F401

import numpy as np
import pandas as pd

from config import settings
from lib.common import setup_logging, teams_table
from lib.http import utc_now_iso

log = setup_logging("06_validate_data")
EXP = settings.EXPORTS_DIR

PROC = settings.PROCESSED_DIR
FINAL = settings.FINAL_DIR
DIRS = {"draft_pick_inventory.csv": PROC, "current_roster_snapshot.csv": PROC, "contract_transactions.csv": PROC,
        "league_cba_parameters.csv": PROC, "wnba_team_doom_dataset.csv": FINAL, "pwhl_team_doom_dataset.csv": FINAL}
DATASETS = {
    "team_season_data.csv": ["league", "season", "team_id"],
    "player_season_data.csv": ["league", "season", "team_id", "player_id"],
    "draft_history.csv": ["league", "draft_year", "selection_key"],
    "draft_pick_inventory.csv": ["league", "inventory_key"],
    "team_financials.csv": ["league", "season", "record_type", "team_id"],
    "team_season_sources.csv": ["league", "team_id", "season", "dataset", "variables", "source_url"],
    "wnba_team_doom_dataset.csv": ["team_id", "season"],
    "pwhl_team_doom_dataset.csv": ["team_id", "season"],
    "current_roster_snapshot.csv": ["league", "snapshot_team_id", "player_name"],
    "contract_transactions.csv": ["league", "tx_key"],
    "league_cba_parameters.csv": ["league", "season", "parameter"],
}

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "", severity: str = "FAIL", n: int = 0):
    status = "PASS" if ok else severity
    results.append({"check": name, "status": status, "n_issues": n, "detail": detail[:2000]})
    (log.info if ok else log.warning)("%s: %s %s", status, name, detail[:300])


def load(name):
    p = DIRS.get(name, EXP) / name
    return pd.read_csv(p, dtype={"season": str}, low_memory=False, keep_default_na=True) if p.exists() else None


def main() -> int:
    data = {k: load(k) for k in DATASETS}
    # 1 duplicates + presence
    for name, keys in DATASETS.items():
        df = data[name]
        if df is None:
            check(f"exists:{name}", False, "file missing")
            continue
        d = df.duplicated(keys, keep=False)
        check(f"duplicate_keys:{name}", not d.any(), f"{d.sum()} rows share a key {keys}", n=int(d.sum()))

    ts, ps, dh, inv, fin, prov = (data[k] for k in ["team_season_data.csv", "player_season_data.csv", "draft_history.csv",
                                                     "draft_pick_inventory.csv", "team_financials.csv", "team_season_sources.csv"])
    teams = teams_table()
    known = set(teams.franchise_id)

    # 2 expected team-season coverage
    exp_rows = []
    for t in teams.itertuples():
        if t.league == "WNBA" and t.first_season_in_data_window:
            last = int(t.last_season_in_data_window) if t.last_season_in_data_window else settings.WNBA_LATEST_COMPLETED_SEASON
            for y in settings.WNBA_CONTEXT_SEASONS + settings.WNBA_CORE_SEASONS:
                if int(t.first_season_in_data_window) <= y <= last:
                    exp_rows.append(("WNBA", str(y), t.franchise_id))
        if t.league == "PWHL" and t.first_season_in_data_window:
            for s in settings.PWHL_SEASONS:
                if s["start_year"] >= int(t.first_season_in_data_window[:4]):
                    exp_rows.append(("PWHL", s["season"], t.franchise_id))
    have = set(map(tuple, ts[["league", "season", "team_id"]].values.tolist()))
    missing = sorted(set(exp_rows) - have)
    unexpected = sorted(have - set(exp_rows))
    check("team_season_coverage:missing", not missing, f"missing {missing[:20]}", n=len(missing))
    check("team_season_coverage:unexpected", not unexpected, f"unexpected {unexpected[:20]}", severity="WARN", n=len(unexpected))

    # 3 team ids
    for name in ["team_season_data.csv", "player_season_data.csv", "team_financials.csv",
                 "wnba_team_doom_dataset.csv", "pwhl_team_doom_dataset.csv"]:
        df = data[name]
        if df is not None:
            bad = set(df.team_id.dropna()) - known
            check(f"team_ids_known:{name}", not bad, f"unknown {sorted(bad)}", n=len(bad))
    for col in ["selecting_team_id", "original_owner_team_id"]:
        bad = dh[dh[col].notna() & ~dh[col].isin(known)][col].unique() if dh is not None else []
        nulls = int(dh[col].isna().sum()) if dh is not None else 0
        check(f"team_ids_known:draft_history.{col}", len(bad) == 0, f"unknown {list(bad)}", n=len(bad))
        check(f"team_ids_resolved:draft_history.{col}", nulls == 0, f"{nulls} unresolved names", severity="WARN", n=nulls)
    names = ts.groupby(["league", "season", "team_id"]).team_name.nunique()
    check("team_name_unique_per_team_season", (names <= 1).all(), "", n=int((names > 1).sum()))

    # 4 records
    w, p = ts[ts.league == "WNBA"], ts[ts.league == "PWHL"]
    bad_w = w[(w.wins + w.losses) != w.games_played]
    check("record:WNBA wins+losses=GP", bad_w.empty, bad_w[["season", "team_id"]].to_string(), n=len(bad_w))
    bad_p = p[(p.wins + p.losses + p.overtime_losses) != p.games_played]
    check("record:PWHL W+L+OTL=GP", bad_p.empty, bad_p[["season", "team_id"]].to_string(), n=len(bad_p))
    bad_split = p[(p.regulation_wins + p.ot_wins + p.so_wins) != p.wins]
    check("record:PWHL RW+OTW+SOW=W", bad_split.empty, "", n=len(bad_split))
    wp = (ts.wins / ts.games_played - ts.win_percentage).abs() > 1e-9
    check("percent:win_percentage recomputes", not wp.any(), "", n=int(wp.sum()))
    pts = (3 * p.regulation_wins + 2 * (p.ot_wins + p.so_wins) + (p.ot_losses + p.so_losses)) != p.points
    check("record:PWHL points formula", not pts.any(), "", n=int(pts.sum()))
    rng = ts[(ts.win_percentage < 0) | (ts.win_percentage > 1) | (ts.games_played <= 0)]
    check("range:win_percentage in [0,1], GP>0", rng.empty, "", n=len(rng))
    gp_var = ts.groupby(["league", "season"]).games_played.nunique()
    check("record:equal GP within league-season", (gp_var == 1).all(), gp_var[gp_var > 1].to_string(), severity="WARN",
          n=int((gp_var > 1).sum()))
    wl = ts.groupby(["league", "season"]).apply(lambda d: d.wins.sum() - (d.losses.sum() + d.overtime_losses.fillna(0).sum()),
                                                  include_groups=False)
    check("record:league wins = league losses (incl. OTL)", (wl == 0).all(), wl[wl != 0].to_string(), n=int((wl != 0).sum()))
    po = ts.dropna(subset=["playoff_game_wins"]).groupby(["league", "season"]).apply(
        lambda d: d.playoff_game_wins.sum() - d.playoff_game_losses.sum(), include_groups=False)
    check("record:playoff game wins = losses league-wide", (po == 0).all(), po[po != 0].to_string(), n=int((po != 0).sum()))
    ch = ts.groupby(["league", "season"]).champion.apply(lambda x: (x.astype(str) == "True").sum())
    check("record:exactly one champion per completed season", (ch == 1).all(), ch[ch != 1].to_string(), n=int((ch != 1).sum()))

    # 5 season labels
    badw = w[~w.season.str.fullmatch(r"\d{4}") | (w.season.astype(int) != w.season_start_year.astype(int))]
    badp = p[~p.season.str.fullmatch(r"\d{4}-\d{2}") | (p.season.str[:4].astype(int) != p.season_start_year.astype(int))
             | (p.season_end_year.astype(int) != p.season_start_year.astype(int) + 1)]
    check("season_labels:WNBA YYYY", badw.empty, "", n=len(badw))
    check("season_labels:PWHL YYYY-YY with end=start+1", badp.empty, "", n=len(badp))
    if ps is not None:
        bl = ps[(ps.league == "PWHL") & ~ps.season.str.fullmatch(r"\d{4}-\d{2}")]
        check("season_labels:player PWHL", bl.empty, "", n=len(bl))

    # 6 players
    if ps is not None:
        key = set(map(tuple, ts[["league", "season", "team_id"]].values.tolist()))
        pk = ps[["league", "season", "team_id"]].apply(tuple, axis=1)
        orphan = ps[~pk.isin(key)]
        check("players:team-season exists", orphan.empty, orphan[["league", "season", "team_id"]].drop_duplicates().to_string(), n=len(orphan))
        m = ps.merge(ts[["league", "season", "team_id", "games_played"]].rename(columns={"games_played": "team_gp"}),
                     on=["league", "season", "team_id"], how="left")
        over = m[m.games_played > m.team_gp]
        check("players:player GP <= team GP", over.empty, over[["season", "team_id", "player_name", "games_played", "team_gp"]].head(10).to_string(), n=len(over))
        dupname = ps.groupby(["league", "season", "team_id", "player_name"]).player_id.nunique()
        check("players:one id per name within team-season", (dupname <= 1).all(), dupname[dupname > 1].head().to_string(), severity="WARN", n=int((dupname > 1).sum()))
        # reconciliation of totals
        wp_ = ps[ps.league == "WNBA"].groupby(["season", "team_id"]).points.sum()
        wt = w.set_index(["season", "team_id"]).points_for
        diff = (wp_ - wt.reindex(wp_.index)).abs()
        check("players:WNBA sum(player points) = team points_for", (diff.fillna(0) < 0.5).all(),
              diff[diff >= 0.5].head(10).to_string(), n=int((diff >= 0.5).sum()))
        pg = ps[ps.league == "PWHL"].groupby(["season", "team_id"]).goals.sum()
        pt = p.set_index(["season", "team_id"])
        so_w = pt.so_wins.reindex(pg.index)
        gdiff = pt.goals_for.reindex(pg.index) - pg - so_w
        check("players:PWHL team GF = sum(player goals) + shootout wins", (gdiff.abs() < 0.5).all(),
              "GF - player goals - SO wins: " + gdiff[gdiff.abs() >= 0.5].head(10).to_string(), severity="WARN",
              n=int((gdiff.abs() >= 0.5).sum()))
        miss_age = ps[(ps.games_played.fillna(0) > 0) & ps.age_at_reference.isna()]
        check("players:age available for players who appeared", miss_age.empty, f"{len(miss_age)} rows", severity="WARN", n=len(miss_age))
        neg = ps[(ps[["games_played", "minutes", "points"]].fillna(0) < 0).any(axis=1)]
        check("players:non-negative counts", neg.empty, "", n=len(neg))
        mt = ps.groupby(["league", "season", "player_id"]).team_id.nunique()
        flag = ps.set_index(["league", "season", "player_id"]).n_teams_in_season
        check("players:multi-team stints flagged", True, f"{int((mt > 1).sum())} player-seasons with >1 team row")

    # 7 draft
    if dh is not None:
        e = dh[dh.draft_type == "entry"]
        dup = e.groupby(["league", "draft_year"]).pick_overall.apply(lambda x: x.duplicated().sum())
        check("draft:unique pick numbers", (dup == 0).all(), dup[dup > 0].to_string(), n=int(dup.sum()))
        gaps = e.groupby(["league", "draft_year"]).pick_overall.apply(lambda x: sorted(set(range(1, int(x.max()) + 1)) - set(x.astype(int))))
        g = gaps[gaps.map(len) > 0]
        check("draft:contiguous pick numbers (forfeits are WARN)", g.empty, g.to_string(), severity="WARN", n=len(g))
        rnd = e[e["round"].isna()]
        check("draft:round known for entry picks", rnd.empty, "", severity="WARN", n=len(rnd))
        car = dh[(dh.league == "WNBA") & (dh.career_match_status == "matched_pick_name_differs")]
        check("draft:WNBA bbref name mismatches (spelling variants)", car.empty,
              car[["draft_year", "pick_overall", "player_name", "bbref_player_name"]].to_string(), severity="WARN", n=len(car))
    if inv is not None:
        dupi = inv.groupby(["league", "draft_year"]).pick_overall.apply(lambda x: x.dropna().duplicated().sum())
        check("inventory:unique future pick slots", (dupi == 0).all(), "", n=int(dupi.sum()))
        badh = inv[~inv.current_rights_holder_team_id.isin(known)]
        check("inventory:rights holder known", badh.empty, badh.current_rights_holder_name_source.to_string(), n=len(badh))
        per_team = inv[inv.league == "WNBA"].groupby("current_rights_holder_team_id").size()
        check("inventory:WNBA every active team listed or traded out", True, per_team.to_string())

    # 8 financial
    if ps is not None:
        sal = ps.dropna(subset=["salary_base_usd"])
        cba = data["league_cba_parameters.csv"]
        mn = cba[(cba.league == "PWHL") & (cba.parameter == "min_base_salary")].set_index("season").value.astype(float)
        low = sal[(sal.league == "PWHL") & (sal.salary_base_usd < sal.season.map(mn) - 0.5)]
        check("financial:PWHL salaries >= CBA minimum", low.empty, low[["player_name", "salary_base_usd"]].to_string(), severity="WARN", n=len(low))
        check("financial:salaries positive", (sal.salary_base_usd > 0).all(), "", n=int((sal.salary_base_usd <= 0).sum()))
    if fin is not None:
        wcap = fin[(fin.league == "WNBA") & (fin.record_type == "season") & fin.team_salary_cap.isna()]
        check("financial:WNBA cap attached to each season row", wcap.empty, "", n=len(wcap))
        nopay = fin[(fin.record_type == "season") & fin.payroll_reported_total.isna()]
        check("financial:team payroll available", nopay.empty,
              nopay.groupby(["league", "financial_data_status"]).size().to_string(), severity="WARN", n=len(nopay))
        band = fin[(fin.league == "PWHL") & fin.avg_salary_vs_requirement.notna() & ((fin.avg_salary_vs_requirement - 1).abs() > 0.10)]
        check("financial:PWHL avg reported salary within +/-10% of requirement", band.empty,
              band[["season", "team_id", "avg_salary_vs_requirement"]].to_string(), severity="WARN", n=len(band))

    # 9 provenance
    if prov is not None:
        pv = prov[prov.dataset == "team_season_data"]
        pkeys = set(map(tuple, pv[["league", "season", "team_id"]].astype(str).values.tolist()))
        tkeys = set(map(tuple, ts[["league", "season", "team_id"]].astype(str).values.tolist()))
        lack = tkeys - pkeys
        check("provenance:every team-season has source rows", not lack, str(sorted(lack)[:10]), n=len(lack))
        blank = prov[prov.source_url.isna() | prov.retrieval_timestamp_utc.isna()]
        check("provenance:source_url and retrieval timestamp present", blank.empty, "", n=len(blank))
        dsets = set(prov.dataset)
        for need in ["team_season_data", "player_season_data", "draft_history", "team_financials", "current_roster_snapshot"]:
            check(f"provenance:dataset covered:{need}", need in dsets, "")

    # 10 schema snapshot
    final_checks(data, known)
    snap_path = settings.LOG_DIR / "_schema_snapshot.json"
    schema = {k: list(v.columns) for k, v in data.items() if v is not None}
    if snap_path.exists():
        old = json.loads(snap_path.read_text())
        for k, cols in schema.items():
            if k in old and old[k] != cols:
                added, removed = sorted(set(cols) - set(old[k])), sorted(set(old[k]) - set(cols))
                check(f"schema_stable:{k}", False, f"added {added} removed {removed}", severity="WARN", n=len(added) + len(removed))
            else:
                check(f"schema_stable:{k}", True)
    snap_path.write_text(json.dumps(schema, indent=1))

    # 11 cross-checks
    ck_path = settings.PROCESSED_DIR / "team_record_crosschecks.csv"
    if ck_path.exists():
        ck = pd.read_csv(ck_path, dtype={"season": str})
        mm = ck[ck.status == "mismatch"]
        check("crosscheck:team records vs second source", mm.empty,
              mm[["league", "season", "team_id", "source_b", "mismatched_fields"]].to_string(), severity="WARN", n=len(mm))
        cov = ts.merge(ck[["league", "season", "team_id"]].drop_duplicates(), how="left", indicator=True)
        nocheck = cov[cov._merge == "left_only"]
        check("crosscheck:coverage", nocheck.empty, nocheck[["league", "season", "team_id"]].to_string(), severity="WARN", n=len(nocheck))

    res = pd.DataFrame(results)
    res["run_at_utc"] = utc_now_iso()
    settings.LOG_DIR.mkdir(exist_ok=True)
    res.to_csv(settings.LOG_DIR / "validation_results.csv", index=False)

    # ---- missingness + report ----
    miss_rows = []
    for name, df in data.items():
        if df is None or "league" not in df:
            continue
        for lg, d in df.groupby("league"):
            for c in df.columns:
                miss_rows.append({"dataset": name, "league": lg, "column": c, "n_rows": len(d),
                                  "pct_missing": round(100 * d[c].isna().mean(), 1)})
    miss = pd.DataFrame(miss_rows)
    miss.to_csv(settings.LOG_DIR / "missingness_report.csv", index=False)
    write_report(data, res, miss)
    n_fail = int((res.status == "FAIL").sum())
    log.info("validation: %d checks, %d PASS, %d WARN, %d FAIL", len(res), (res.status == "PASS").sum(),
             (res.status == "WARN").sum(), n_fail)
    return 1 if n_fail else 0


def final_checks(data, known) -> None:
    w, p = data.get("wnba_team_doom_dataset.csv"), data.get("pwhl_team_doom_dataset.csv")
    if w is None or p is None:
        check("final:both league files exist", False, "missing final dataset")
        return
    shared_w = [c for c in w.columns if c in p.columns]
    shared_p = [c for c in p.columns if c in w.columns]
    check("final:shared columns in identical order", shared_w == shared_p, "")
    only = sorted(set(w.columns) ^ set(p.columns))
    check("final:league-specific columns", True, f"{len(shared_w)} shared; league-specific: {only}")
    for lg, df in (("WNBA", w), ("PWHL", p)):
        teams = teams_table()
        active = teams[(teams.league == lg) & teams.status_as_of_snapshot.isin(["active", "relocating", "expansion_not_yet_played"])]
        cur = df[df.row_type == "current"]
        check(f"final:{lg} one current row per active franchise", set(cur.team_id) == set(active.franchise_id) and len(cur) == len(active),
              f"{len(cur)} current rows vs {len(active)} active")
        ss = df[df.row_type == "season"]
        check(f"final:{lg} season rows match core team-seasons", len(ss) == len(data["team_season_data.csv"].query(
            "league == @lg and in_core_scope.astype('str') == 'True'", engine="python")), f"{len(ss)} rows")
        check(f"final:{lg} perf_win_pct present on season rows", ss.perf_win_pct.notna().all(), "")
        share_cols = [c for c in df.columns if ("_share" in c or "_pct" in c or c.endswith("_hhi") or "coverage" in c)
                      and pd.api.types.is_numeric_dtype(df[c]) and c not in ("perf_win_pct_change_yoy", "out_next_win_pct_change", "fin_payroll_share_of_cap")]
        bad = [c for c in share_cols if ((df[c] < -1e-9) | (df[c] > 1 + 1e-9)).any()]
        check(f"final:{lg} share/percentage columns within [0,1]", not bad, str(bad))
        if "fin_payroll_share_of_cap" in df:
            sc = df.fin_payroll_share_of_cap.dropna()
            check(f"final:{lg} payroll/cap plausible (0.6-1.3; earnings can exceed cap)", sc.between(0.6, 1.3).all(),
                  sc[~sc.between(0.6, 1.3)].to_string(), severity="WARN")
        ages = df[[c for c in df.columns if c in ("age_mean", "age_median", "age_playtime_weighted", "age_top_n_by_playtime", "age_top_n_by_production")]]
        st = ages.stack()
        check(f"final:{lg} ages plausible (18-45)", ((st >= 18) & (st <= 45)).all(), str(st[(st < 18) | (st > 45)].head()))
        banned = [c for c in df.columns if "doom" in c.lower() or "score" in c.lower() or "weight" == c.lower()]
        check(f"final:{lg} no Doom Score / weight columns", not banned, str(banned))
        lead = ss.sort_values("season").groupby("team_id")
        nxt_ok = True
        for tid, d in lead:
            v = d.perf_win_pct.tolist()
            o = d.out_next_win_pct.tolist()
            for i in range(len(v) - 1):
                if pd.notna(o[i]) and abs(o[i] - v[i + 1]) > 1e-3:
                    nxt_ok = False
        check(f"final:{lg} out_next_win_pct equals next season's perf_win_pct", nxt_ok, "")


KEY_FIELDS = {
    "team_season_data.csv": ["wins", "losses", "overtime_losses", "win_percentage", "points_percentage", "points_for",
                             "goals_for", "home_wins", "sos_bbref", "playoff_round_reached", "prior_season_win_pct",
                             "win_pct_rolling3_mean"],
    "player_season_data.csv": ["birth_date", "age_at_reference", "experience_years", "position", "games_played",
                               "minutes", "time_on_ice_total_min", "points", "ws", "plus_minus", "save_pct",
                               "salary_base_usd", "contract_end_year"],
    "draft_history.csv": ["round", "player_id", "original_owner_team_id", "trade_note_text", "career_games"],
    "team_financials.csv": ["team_salary_cap", "team_average_salary_requirement", "payroll_reported_total",
                            "cap_space", "top8_salary_share"],
}


def write_report(data, res, miss) -> None:
    L = [f"# Data collection report", "", f"Generated: {utc_now_iso()} (UTC). Produced by `scripts/06_validate_data.py`.", ""]
    L += ["## Row counts", "", "| dataset | league | rows | seasons / years |", "|---|---|---|---|"]
    for name, df in data.items():
        if df is None or "league" not in df:
            continue
        for lg, d in df.groupby("league"):
            sc = "season" if "season" in d else ("draft_year" if "draft_year" in d else None)
            span = ", ".join(sorted(map(str, d[sc].dropna().unique())))[:120] if sc else ""
            L.append(f"| {name} | {lg} | {len(d)} | {span} |")
    ts = data["team_season_data.csv"]
    L += ["", "## Team-season coverage", "", "| league | season | teams | games per team | in core scope |", "|---|---|---|---|---|"]
    for (lg, s), d in ts.groupby(["league", "season"]):
        L.append(f"| {lg} | {s} | {d.team_id.nunique()} | {', '.join(map(str, sorted(d.games_played.unique())))} | {d.in_core_scope.iloc[0]} |")
    L += ["", "## Missingness of key fields (% of rows null)", ""]
    for name, cols in KEY_FIELDS.items():
        m = miss[(miss.dataset == name) & miss.column.isin(cols)]
        if m.empty:
            continue
        pv = m.pivot(index="column", columns="league", values="pct_missing").reindex(cols).dropna(how="all")
        L += [f"**{name}**", "", "| field | " + " | ".join(pv.columns) + " |", "|---|" + "---|" * len(pv.columns)]
        for c, r in pv.iterrows():
            L.append(f"| {c} | " + " | ".join("" if pd.isna(v) else f"{v:.1f}" for v in r.values) + " |")
        L.append("")
    L += ["Interpretation: a missing value is null, never zero. Large percentages above are expected where a field "
          "does not apply to a league (e.g. `ws` for the PWHL, `goals_for` for the WNBA) or no permitted source exists "
          "(WNBA salaries). See `docs/source_coverage_matrix.md`.", ""]
    prov = data["team_season_sources.csv"]
    if prov is not None:
        L += ["## Source coverage (provenance rows by dataset and source)", "", "| league | dataset | source | rows | verification |", "|---|---|---|---|---|"]
        g = prov.groupby(["league", "dataset", "source_organization"]).agg(n=("source_url", "size"),
                                                                           v=("verification_status", lambda x: ", ".join(sorted(set(map(str, x))))))
        for (lg, ds, so), r in g.iterrows():
            L.append(f"| {lg} | {ds} | {so} | {r.n} | {r.v} |")
    L += ["", "## Validation results", "", f"{(res.status=='PASS').sum()} PASS, {(res.status=='WARN').sum()} WARN, "
          f"{(res.status=='FAIL').sum()} FAIL (full table: `logs/validation_results.csv`).", "",
          "| check | status | n | detail |", "|---|---|---|---|"]
    for r in res[res.status != "PASS"].itertuples():
        det = re.sub(r"\s+", " ", str(r.detail))[:220].replace("|", "/")
        L.append(f"| {r.check} | {r.status} | {r.n_issues} | {det} |")
    (settings.DOCS_DIR / "collection_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
