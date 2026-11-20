"""04 - Collect salary-cap parameters, team payroll aggregates and contract-term information.

WHAT IT COLLECTS
    * team_financials.csv - one row per team per season (record_type='season')
      plus one dated row per team for the upcoming PWHL season / current WNBA
      offseason (record_type='current_snapshot'). League CBA parameters are
      attached to every row; team payroll aggregates are filled ONLY where
      player-level salaries exist.
    * contract_transactions.csv - PWHL signings / extensions with contract
      term, parsed from Wikipedia season articles (secondary source), with the
      inferred contract season span.
    * cba_parameters copy (data/exports/league_cba_parameters.csv).

LEAGUES / SEASONS
    WNBA 2021-2026 seasons + current snapshot; PWHL 2023-24..2025-26 + 2026-27 snapshot.

SOURCES
    config/cba_parameters.csv - hand-transcribed league parameters, each row
        with its own source URL and verification_status (official /
        secondary_source / calculated_unverified).
    player_season_data.csv (from script 02) - PWHLPA 2025-26 base salaries;
        optional WNBA manual contract import.
    Wikipedia "2025-26 PWHL season", "2026-27 PWHL season" (Draft signings, Free
        agency, Contract extensions tables) - contract term in years.

FIELD DEFINITIONS (all amounts USD; measure stated in *_measure columns)
    payroll_reported_total      = sum of reported player base salaries for the team-season
    n_players_salary_reported   = players with a reported salary
    n_players_on_team           = players with a row for the team-season (appeared or under contract)
    salary_coverage_share       = n_players_salary_reported / n_players_on_team
    payroll_avg / median / max  = over reported salaries
    top5_salary_share (WNBA)    = sum of 5 largest salaries / payroll_reported_total
    top8_salary_share (PWHL)    = sum of 8 largest salaries / payroll_reported_total
    pct_of_cap_committed (WNBA) = payroll_reported_total / team_salary_cap
    cap_space (WNBA)            = team_salary_cap - payroll_reported_total
    avg_salary_vs_requirement (PWHL) = payroll_avg / team_average_salary_requirement
    contract_first_season       = season beginning in the signing year if signed May-Nov
                                  (offseason), else the season in progress at signing
    contract_last_season        = contract_first_season + term_years - 1
    n_known_contracts_expiring_after_<season> = players whose inferred
                                  contract_last_season == that season (known contracts only)

KNOWN LIMITATIONS
    * WNBA team payroll / cap space / expiring contracts: NOT collected (no
      permitted automated source; see README "WNBA salary data"). Fields are null
      with financial_data_status explaining why.
    * PWHL salaries exist for 2025-26 only, base salary only, as of 2026-04-12,
      and exclude players not listed by the PWHLPA.
    * PWHL contract terms cover only transactions recorded on Wikipedia since the
      2025 offseason; contracts signed earlier (e.g. inaugural 3-year deals) are
      unknown -> counts are lower bounds and flagged with coverage fields.
    * The PWHL CBA has no hard cap; the team-average requirement (+/-10%) is the
      binding constraint, so "cap space" is not defined for the PWHL.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: F401

import numpy as np
import pandas as pd

from config import settings
from lib.common import base_argparser, player_key, resolve_team, setup_logging, teams_table, to_num
from lib.http import utc_now_iso
from lib.sources import wiki_page
from lib.store import record_provenance, upsert_csv, write_csv
from lib.tables import clean_cell, grid_text, wikitable_grid

SCRIPT = "04_collect_financial_data.py"
log = setup_logging("04_collect_financial_data")

TERM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def parse_term(raw: str):
    t = (raw or "").lower()
    m = re.search(r"(\d+|one|two|three|four|five|six)[\s-]+years?", t)
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else TERM_WORDS[v]
    if re.search(r"rest of (the )?season|remainder", t):
        return 0  # covers only the season in progress
    return None


def season_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[2:]}"


def pwhl_contract_transactions(refresh: bool) -> tuple[pd.DataFrame, list[dict]]:
    rows, prov = [], []
    for s in [x for x in settings.PWHL_SEASONS if x["start_year"] >= 2025] + [settings.PWHL_UPCOMING_SEASON]:
        page = wiki_page(s["wikipedia_page"], refresh, current=s["season"] == settings.PWHL_UPCOMING_SEASON["season"])
        if page is None:
            continue
        n0 = len(rows)
        for tb in page.soup.find_all("table", class_="wikitable"):
            h = tb.find_previous(["h2", "h3", "h4"])
            section = h.get_text(" ", strip=True) if h else ""
            if not re.search(r"free agency|contract extension|draft", section, re.I):
                continue
            txt = grid_text(wikitable_grid(tb))
            if not txt:
                continue
            hdr = txt[0]
            if "Player" not in hdr or not any(c.startswith("Term") for c in hdr):
                continue
            term_col = next(c for c in hdr if c.startswith("Term"))
            team_col = "New team" if "New team" in hdr else "Team"
            for r in txt[1:]:
                if len(r) != len(hdr):
                    continue
                d = dict(zip(hdr, r))
                date = pd.to_datetime(re.sub(r"\[.*?\]", "", d.get("Date", "")).strip(), errors="coerce")
                term_raw = d.get(term_col, "")
                yrs = parse_term(term_raw)
                ttype = ("termination" if re.search(r"terminat|release|mutual", term_raw, re.I) else
                         "reserve_contract" if re.search(r"reserve", term_raw, re.I) else
                         "draft_signing" if section.lower().startswith("draft") else
                         "free_agent_signing" if "free" in section.lower() else
                         "extension_term_remaining" if term_col == "Term remaining" else "extension")
                if pd.notna(date):
                    first_start = date.year if date.month >= 5 else date.year - 1
                else:
                    first_start = s["start_year"]
                if ttype == "extension" and pd.notna(date) and date.month < 5:
                    # in-season extension: term starts the following season
                    first_start = date.year
                rows.append({"league": "PWHL", "article_season": s["season"], "section": section,
                             "transaction_type": ttype, "transaction_date": date.date().isoformat() if pd.notna(date) else None,
                             "player_name": d.get("Player"), "team_name_source": d.get(team_col),
                             "team_id": resolve_team("PWHL", d.get(team_col)),
                             "previous_team_name_source": d.get("Previous team"),
                             "draft_detail": d.get("Draft"), "term_raw": term_raw, "term_years": yrs,
                             "contract_first_season": season_label(first_start) if yrs is not None and ttype != "termination" else None,
                             "contract_last_season": season_label(first_start + max(yrs, 1) - 1) if yrs is not None and ttype != "termination" else None,
                             "season_span_inference": "May-Nov signing -> starts that autumn; Dec-Apr signing -> season in progress (extensions: next season)",
                             "source_url": page.permalink, "source_revision_id": page.revid,
                             "retrieved_at_utc": page.retrieved_at_utc})
        log.info("%s: %d contract transactions", s["wikipedia_page"], len(rows) - n0)
        prov.append({"league": "PWHL", "team_id": "", "season": s["season"], "dataset": "contract_transactions",
                     "variables": "transaction date; player; team; term", "source_organization": "Wikipedia (crowd-edited)",
                     "source_url": page.permalink, "retrieval_timestamp_utc": page.retrieved_at_utc,
                     "value_origin": "direct",
                     "calculation_definition": "contract_first/last_season inferred from date + term (see script docstring)",
                     "verification_status": "secondary_unverified"})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["player_key"] = [player_key("PWHL", n) for n in df.player_name]
        df["tx_key"] = (df.transaction_date.fillna("") + "|" + df.player_key + "|" + df.team_id.fillna("") + "|" + df.transaction_type)
        df = df.drop_duplicates("tx_key", keep="last")
    return df, prov


def payroll_aggregates(players: pd.DataFrame, top_n: int) -> pd.DataFrame:
    rows = []
    for (lg, ssn, tid), d in players.groupby(["league", "season", "team_id"]):
        sal = d.salary_base_usd.dropna().sort_values(ascending=False)
        n_team = d.player_id.nunique()
        rec = {"league": lg, "season": ssn, "team_id": tid, "n_players_on_team": n_team,
               "n_players_salary_reported": len(sal)}
        if len(sal):
            tot = sal.sum()
            rec.update({"payroll_reported_total": tot, "payroll_avg": sal.mean(), "payroll_median": sal.median(),
                        "payroll_max": sal.max(), "payroll_min": sal.min(),
                        f"top{top_n}_salary_share": sal.head(top_n).sum() / tot if len(sal) >= top_n else np.nan,
                        "salary_coverage_share": len(sal) / n_team,
                        "salary_measure": d.salary_measure.dropna().iloc[0] if d.salary_measure.notna().any() else None,
                        "salary_source": d.salary_source.dropna().iloc[0] if d.salary_source.notna().any() else None,
                        "salary_as_of": d.salary_as_of.dropna().iloc[0] if d.salary_as_of.notna().any() else None})
        rows.append(rec)
    return pd.DataFrame(rows)


def cba_lookup(cba: pd.DataFrame, league: str, season: str, param: str):
    m = cba[(cba.league == league) & (cba.season == season) & (cba.parameter == param)]
    if m.empty:
        return None, None, None
    r = m.iloc[0]
    return float(r.value), r.verification_status, r.cba_regime


def main() -> None:
    args = base_argparser(__doc__.splitlines()[0]).parse_args()
    leagues = ["WNBA", "PWHL"] if args.league == "both" else [args.league]
    cba = pd.read_csv(settings.CBA_PARAMETERS_CSV, dtype=str)
    write_csv(cba, settings.EXPORTS_DIR / "league_cba_parameters.csv")
    ts = pd.read_csv(settings.EXPORTS_DIR / "team_season_data.csv", dtype={"season": str})
    players = pd.read_csv(settings.EXPORTS_DIR / "player_season_data.csv", dtype={"season": str}, low_memory=False)
    prov = []
    snap_date = utc_now_iso()[:10]
    out = []

    for lg in leagues:
        t = ts[ts.league == lg][["league", "season", "team_id", "team_name", "in_core_scope"]]
        if lg == "WNBA":
            t = t[t.in_core_scope.astype(str) == "True"]
        p = players[players.league == lg]
        agg = payroll_aggregates(p, 5 if lg == "WNBA" else 8)
        f = t.merge(agg, on=["league", "season", "team_id"], how="left")
        f["record_type"] = "season"
        f["snapshot_date"] = None
        out.append(f)

    df = pd.concat(out, ignore_index=True)
    # attach CBA parameters
    for i, r in df.iterrows():
        if r.league == "WNBA":
            cap, vs, regime = cba_lookup(cba, "WNBA", r.season, "team_salary_cap")
            df.at[i, "team_salary_cap"], df.at[i, "cap_value_verification"], df.at[i, "cba_regime"] = cap, vs, regime
            df.at[i, "cap_measure"] = "hard cap on total team salary (WNBA CBA)" if cap else None
        else:
            req, vs, regime = cba_lookup(cba, "PWHL", r.season, "team_average_salary_requirement")
            mn, _, _ = cba_lookup(cba, "PWHL", r.season, "min_base_salary")
            df.at[i, "team_average_salary_requirement"], df.at[i, "cap_value_verification"] = req, vs
            df.at[i, "cba_regime"], df.at[i, "league_min_salary"] = regime, mn
            df.at[i, "cap_measure"] = "no hard cap; team average base salary must be within +/-10% of requirement" if req else None
    is_w = df.league == "WNBA"
    df.loc[is_w, "pct_of_cap_committed"] = df.loc[is_w, "payroll_reported_total"] / df.loc[is_w, "team_salary_cap"]
    df.loc[is_w, "cap_space"] = df.loc[is_w, "team_salary_cap"] - df.loc[is_w, "payroll_reported_total"]
    df.loc[~is_w, "avg_salary_vs_requirement"] = df.loc[~is_w, "payroll_avg"] / df.loc[~is_w, "team_average_salary_requirement"]
    df["financial_data_status"] = np.where(
        df.n_players_salary_reported.fillna(0) > 0, "player_salaries_reported",
        np.where(df.league == "WNBA", "not_collected_no_permitted_automated_source", "not_reported_by_source_for_season"))
    for i in df.index[(df.league == "WNBA") & (df.financial_data_status != "player_salaries_reported")]:
        df.at[i, "pct_of_cap_committed"] = np.nan
        df.at[i, "cap_space"] = np.nan

    # ---- PWHL contract transactions and upcoming-season snapshot ----
    snaps = []
    if "PWHL" in leagues:
        ct, cprov = pwhl_contract_transactions(args.refresh)
        prov += cprov
        if not ct.empty:
            upsert_csv(ct, settings.EXPORTS_DIR / "contract_transactions.csv", ["league", "tx_key"], replace_scope={"league": ["PWHL"]})
            up = settings.PWHL_UPCOMING_SEASON["season"]
            valid = ct[ct.transaction_type != "termination"].dropna(subset=["contract_last_season"])
            latest = valid.sort_values("transaction_date").groupby("player_key").tail(1)  # most recent deal per player
            cur_teams = teams_table()
            cur_teams = cur_teams[(cur_teams.league == "PWHL") & cur_teams.status_as_of_snapshot.isin(["active", "expansion_not_yet_played"])]
            req, vs, regime = cba_lookup(cba, "PWHL", up, "team_average_salary_requirement")
            mn, _, _ = cba_lookup(cba, "PWHL", up, "min_base_salary")
            ros, _, _ = cba_lookup(cba, "PWHL", up, "roster_size")
            snap_p = settings.EXPORTS_DIR / "current_roster_snapshot.csv"
            roster = pd.read_csv(snap_p, dtype=str) if snap_p.exists() else pd.DataFrame()
            if not roster.empty:
                roster = roster[roster.league == "PWHL"].copy()
                roster["player_key"] = [player_key("PWHL", n) for n in roster.player_name]
            by_player = latest.set_index("player_key")
            for tm in cur_teams.itertuples():
                if roster.empty:
                    # fall back to the team named in the transaction
                    d = latest[latest.team_id == tm.franchise_id]
                    n_roster, basis = None, "transaction_team"
                else:
                    keys = roster[roster.snapshot_team_id == tm.franchise_id].player_key
                    d = by_player.loc[by_player.index.intersection(keys)].reset_index()
                    n_roster, basis = len(keys), "current_roster_snapshot_membership"
                covering = d[d.contract_last_season >= up]
                snaps.append({"league": "PWHL", "season": up, "team_id": tm.franchise_id, "team_name": tm.current_team_name,
                              "record_type": "current_snapshot", "snapshot_date": snap_date, "cba_regime": regime,
                              "team_average_salary_requirement": req, "league_min_salary": mn, "roster_size_rule": ros,
                              "cap_value_verification": vs,
                              "cap_measure": "no hard cap; team average base salary must be within +/-10% of requirement",
                              "snapshot_roster_n": n_roster, "contract_team_basis": basis,
                              "n_known_contracts_covering_upcoming_season": len(covering),
                              "known_contract_share_of_roster": len(covering) / n_roster if n_roster else np.nan,
                              f"n_known_contracts_expiring_after_{up}": int((covering.contract_last_season == up).sum()),
                              "n_known_contracts_multi_year_beyond_upcoming": int((covering.contract_last_season > up).sum()),
                              "known_contract_coverage_note": "Counts include only roster players with a 2025+ signing/extension recorded on Wikipedia; contracts signed earlier are unknown.",
                              "financial_data_status": "contract_terms_partial_secondary_source"})
    wnba_snap = []
    if "WNBA" in leagues:
        cap, vs, regime = cba_lookup(cba, "WNBA", str(settings.WNBA_LATEST_COMPLETED_SEASON), "team_salary_cap")
        cur_teams = teams_table()
        cur_teams = cur_teams[(cur_teams.league == "WNBA") & cur_teams.status_as_of_snapshot.isin(["active", "relocating"])]
        for tm in cur_teams.itertuples():
            wnba_snap.append({"league": "WNBA", "season": f"offseason_after_{settings.WNBA_LATEST_COMPLETED_SEASON}",
                              "team_id": tm.franchise_id, "team_name": tm.current_team_name, "record_type": "current_snapshot",
                              "snapshot_date": snap_date, "cba_regime": regime,
                              "team_salary_cap": None, "cap_value_verification": None,
                              "cap_measure": "2027 cap not yet published (revenue-linked under 2026 CBA); latest published cap is the 2026 figure in league_cba_parameters.csv",
                              "financial_data_status": "not_collected_no_permitted_automated_source"})
    allf = pd.concat([df, pd.DataFrame(snaps), pd.DataFrame(wnba_snap)], ignore_index=True)
    first = ["league", "season", "record_type", "snapshot_date", "team_id", "team_name", "financial_data_status",
             "cba_regime", "cap_measure", "team_salary_cap", "team_average_salary_requirement", "league_min_salary",
             "cap_value_verification", "payroll_reported_total", "salary_measure", "salary_source", "salary_as_of",
             "n_players_on_team", "n_players_salary_reported", "salary_coverage_share", "payroll_avg", "payroll_median",
             "payroll_max", "payroll_min", "top5_salary_share", "top8_salary_share", "pct_of_cap_committed", "cap_space",
             "avg_salary_vs_requirement"]
    for c in first:
        if c not in allf:
            allf[c] = np.nan
    allf = allf[first + [c for c in allf.columns if c not in first and c != "in_core_scope"]]
    upsert_csv(allf, settings.EXPORTS_DIR / "team_financials.csv", ["league", "season", "record_type", "team_id"],
               replace_scope={"league": leagues})
    for r in allf.itertuples():
        if r.financial_data_status == "player_salaries_reported":
            prov.append({"league": r.league, "team_id": r.team_id, "season": r.season, "dataset": "team_financials",
                         "variables": "payroll_reported_total;payroll_avg;payroll_median;payroll_max;top-N share;coverage",
                         "source_organization": r.salary_source, "source_url": "derived from player_season_data.csv salary_base_usd",
                         "retrieval_timestamp_utc": utc_now_iso(), "source_update_date": r.salary_as_of,
                         "value_origin": "calculated", "calculation_definition": "aggregates of reported base salaries (see script docstring)",
                         "verification_status": "official_players_association"})
        if pd.notna(r.team_salary_cap) or pd.notna(r.team_average_salary_requirement):
            prov.append({"league": r.league, "team_id": r.team_id, "season": r.season, "dataset": "team_financials",
                         "variables": "team_salary_cap / team_average_salary_requirement / league_min_salary",
                         "source_organization": "config/cba_parameters.csv (see per-row source_url)",
                         "source_url": "config/cba_parameters.csv", "retrieval_timestamp_utc": utc_now_iso(),
                         "value_origin": "direct" if r.cap_value_verification in ("official", "secondary_source") else "calculated",
                         "verification_status": r.cap_value_verification})
    record_provenance(prov, SCRIPT)
    log.info("done: %d financial rows", len(allf))


if __name__ == "__main__":
    main()
