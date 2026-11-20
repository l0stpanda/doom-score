"""02 - Collect player-team-season rosters, characteristics, participation, production and contract fields.

WHAT IT COLLECTS
    One row per player per team per season (a "stint"). A player who changed
    teams mid-season has one row per team containing only the games played for
    that team; season totals across teams are never copied onto a team row.
    Also writes a dated CURRENT roster snapshot for each league.

LEAGUES / SEASONS
    WNBA  2021-2026 regular season (+ a few playoff totals columns).
    PWHL  2023-24, 2024-25, 2025-26 regular season (+ playoff totals columns).
    Current snapshot: Wikipedia current-roster tables for all active WNBA and
    PWHL franchises (incl. 2026-27 PWHL expansion teams), dated by retrieval
    timestamp and Wikipedia revision id.

OUTPUTS
    data/exports/player_season_data.csv       (key: league, season, team_id, player_id)
    data/processed/current_roster_snapshot.csv  (key: league, snapshot_team_id, player_name)
    data/exports/team_season_sources.csv      (provenance rows, upserted)

SOURCES
    WNBA  Basketball-Reference team-season pages /wnba/teams/{CODE}/{YYYY}.html
            tables roster, totals, advanced, playoffs_totals.
          Optional manual contract file data/raw/manual/wnba_player_contracts.csv (see README).
    PWHL  sportsdataverse fastRhockey-pwhl-data: rosters_{Y}, player_box_{Y}, schedules_{Y}
            (per-game box scores from the league's HockeyTech feed, MIT licence).
          PWHLPA Player Salary Guide 2025-26 (base salary only, as of 2026-04-12).
    Snapshot  Wikipedia "Template:<Team> roster" (WNBA) and the "Current roster"
            section of each PWHL team article.

FIELDS (selection; full list in docs/data_dictionary.md)
    identifiers: league, season, team_id, team_name, player_id, player_name, position, position_group
    characteristics: birth_date, age_at_reference (decimal years on the league-season's
        first regular-season game date), age_source (integer age published by source),
        experience_years (WNBA: Basketball-Reference prior WNBA seasons, 'R'->0;
        PWHL: prior PWHL seasons with >=1 game, computed), height_in, weight_lb
    participation: games_played, games_started, minutes / time_on_ice totals and per game
    WNBA production: pts, trb, orb, drb, ast, stl, blk, tov, pf, fg/fga/fg_pct, fg3*, fg2*, ft*,
        per, ts_pct, usg_pct, ows, dws, ws, ws_per_40, off_rtg, def_rtg
    PWHL production: goals, assists, points, shots, hits, blocked_shots, pim, plus_minus,
        faceoffs; goalies saves, shots_against, goals_against, save_pct, gaa
    contract: salary_base_usd, salary_measure, salary_source, salary_as_of, contract_data_status

DERIVED FORMULAS
    age_at_reference  = (reference_date - birth_date).days / 365.2425
    minutes_per_game  = minutes / games_played
    toi_per_game      = time_on_ice_total_min / games_played (skaters: games dressed)
    save_pct          = saves / shots_against ; gaa = goals_against * 60 / goalie TOI minutes
    multi_team_season = player has >1 team row in the same league-season

KNOWN LIMITATIONS
    * WNBA salaries/contract terms are NOT collected automatically (see lib/salaries.py).
    * PWHL salaries exist only for 2025-26 and only for players listed by the PWHLPA
      (mid-season signings may be missing). Earlier seasons: contract_data_status = not_reported.
    * PWHL plus/minus is retained as published but is a noisy, context-dependent stat.
    * PWHL goalie wins/losses (decisions) are not in the collected files.
    * PWHL prior professional experience outside the PWHL (PHF, PWHPA, Europe) is not collected.
    * Wikipedia roster snapshots are crowd-edited; they are dated, carry a revision id,
      and are kept separate from the historical player table.
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
from lib.common import (age_on, base_argparser, flip_last_first, franchise_by_bbref, franchise_by_source_id, player_key,
                        norm_name, resolve_team, setup_logging, teams_table, to_num)
from lib.http import utc_now_iso
from lib.salaries import pwhlpa_salaries, wnba_manual_contracts, wnba_mendeley_salaries
from lib.sources import bbref_page, fastrhockey_commit, fastrhockey_parquet, wiki_page
from lib.store import record_provenance, upsert_csv
from lib.tables import bbref_rows, bbref_tables, clean_cell, grid_text, wikitable_grid

SCRIPT = "02_collect_player_data.py"
log = setup_logging("02_collect_player_data")
KEYS = ["league", "season", "team_id", "player_id"]


def team_seasons() -> pd.DataFrame:
    p = settings.EXPORTS_DIR / "team_season_data.csv"
    if not p.exists():
        raise SystemExit("team_season_data.csv not found - run 01_collect_team_data.py first")
    return pd.read_csv(p, dtype={"season": str})


def _pid(href):
    m = re.search(r"/wnba/players/./([a-z0-9]+)\.html", href or "")
    return m.group(1) if m else None


def _height_in(s):
    m = re.match(r"^(\d)-(\d{1,2})$", s or "")
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


WNBA_TOTAL_FIELDS = ["g", "gs", "mp", "fg", "fga", "fg_pct", "fg3", "fg3a", "fg3_pct", "fg2", "fg2a", "fg2_pct",
                     "ft", "fta", "ft_pct", "orb", "drb", "trb", "ast", "stl", "blk", "tov", "pf", "pts"]
WNBA_ADV_FIELDS = ["per", "ts_pct", "efg_pct", "usg_pct", "orb_pct", "drb_pct", "trb_pct", "ast_pct", "stl_pct",
                   "blk_pct", "tov_pct", "off_rtg", "def_rtg", "ows", "dws", "ws", "ws_per_40"]


# ===========================================================================
# Salary attachment (shared by both leagues)
# ===========================================================================
def attach_salaries(df: pd.DataFrame, sal: pd.DataFrame, league: str, status: str, measure: str, source: str,
                    source_url: str, as_of: str, unlisted_status: str) -> tuple[pd.DataFrame, int]:
    """Attach player-season salaries (columns season, team_id, name_key, player_name, salary_base_usd)
    to the stint rows of ``df`` for the seasons present in ``sal``.

    Match order: (season, team, name) -> that team's stint; else (season, name) unique -> the
    player's main stint that season (most games; method 'name_only_team_differs', because a
    source may list one team per player-season); else a contract-only row at the listed team
    (roster_status 'under_contract_no_appearance_for_team'). Stints in covered seasons with no
    listed salary get ``unlisted_status``.
    """
    df = df.copy()
    df["name_key"] = [player_key(league, n) for n in df["player_name"]]
    for c in ("salary_base_usd", "salary_match_method", "salary_measure", "salary_source", "salary_source_url", "salary_as_of"):
        if c not in df:
            df[c] = np.nan
        df[c] = df[c].astype(object) if c != "salary_base_usd" else pd.to_numeric(df[c], errors="coerce")
    cov = df.season.isin(set(sal.season)) & (df.league == league)
    df.loc[cov, "contract_data_status"] = unlisted_status
    stints = df[cov]
    by_team = {(r.season, r.team_id, r.name_key): i for i, r in stints.iterrows()}
    main_idx = {}
    for k, g in stints.assign(_g=stints.games_played.fillna(0)).sort_values("_g", ascending=False).groupby(["season", "name_key"]):
        if g.player_id.nunique() == 1:
            main_idx[k] = g.index[0]
    add = []
    for r in sal.itertuples():
        i = by_team.get((r.season, r.team_id, r.name_key))
        method = "team+name"
        if i is None:
            i = main_idx.get((r.season, r.name_key))
            method = "name_only_team_differs"
        if i is not None:
            if pd.isna(df.at[i, "salary_base_usd"]):
                df.at[i, "salary_base_usd"] = r.salary_base_usd
                df.at[i, "salary_match_method"] = method
            else:  # second listing for the same stint: sum and flag
                df.at[i, "salary_base_usd"] += r.salary_base_usd
                df.at[i, "salary_match_method"] = "summed_multiple_listings"
            df.at[i, "contract_data_status"] = status
            continue
        y0 = int(str(r.season)[:4])
        add.append({"league": league, "season": r.season, "season_start_year": y0,
                    "season_end_year": y0 + (1 if league == "PWHL" else 0), "team_id": r.team_id,
                    "player_id": f"salary-only-{r.name_key.replace(' ', '-')}",
                    "player_id_source": f"{source} name key (no stats match)", "player_name": r.player_name,
                    "games_played": 0, "games_started": 0, "roster_status": "under_contract_no_appearance_for_team",
                    "salary_base_usd": r.salary_base_usd, "salary_match_method": "unmatched_contract_only_row",
                    "contract_data_status": status})
    if add:
        df = pd.concat([df, pd.DataFrame(add)], ignore_index=True)
    rep = df.contract_data_status == status
    df.loc[rep, "salary_measure"] = measure
    df.loc[rep, "salary_source"] = source
    df.loc[rep, "salary_source_url"] = source_url
    df.loc[rep, "salary_as_of"] = as_of
    log.info("%s salaries (%s): %d listed, %d stint rows with salary, %d contract-only rows", league, source, len(sal),
             int(rep.sum()) - len(add), len(add))
    return df.drop(columns=["name_key"]), len(add)


# ===========================================================================
# WNBA
# ===========================================================================
def fill_wnba_bio(df: pd.DataFrame, refresh: bool) -> tuple[pd.DataFrame, list[dict]]:
    """Fill birth_date / experience for stints missing from a team's roster table.

    Team roster tables can omit players who left mid-season. Birth date is a
    player constant, so it is taken (1) from the same player's other
    Basketball-Reference team rows, else (2) from the player's own
    Basketball-Reference page. Experience for that season is taken from the
    player's other team row in the SAME season, else computed from the player
    page as the number of distinct earlier WNBA seasons played.
    """
    prov = []
    df["bio_fill_method"] = np.where(df.birth_date.notna(), "team_roster_table", None)
    bd = df.dropna(subset=["birth_date"]).groupby("player_id").birth_date.first()
    need = df.birth_date.isna() & df.player_id.isin(bd.index)
    df.loc[need, "birth_date"] = df.loc[need, "player_id"].map(bd)
    df.loc[need, "bio_fill_method"] = "birth_date_from_other_team_row"
    pos = df.dropna(subset=["position"]).sort_values("season").groupby("player_id").position.last()
    need_p = df.position.isna() & df.player_id.isin(pos.index)
    df.loc[need_p, "position"] = df.loc[need_p, "player_id"].map(pos)
    df["position_source"] = np.where(need_p, "other_team_row_same_player_latest", np.where(df.position.notna(), "team_roster_table", None))
    same_exp = df.dropna(subset=["experience_years"]).groupby(["season", "player_id"]).experience_years.first()
    need_e = df.experience_years.isna()
    df.loc[need_e, "experience_years"] = [same_exp.get((s, p)) for s, p in zip(df.loc[need_e, "season"], df.loc[need_e, "player_id"])]
    todo = df[df.birth_date.isna() | df.experience_years.isna()].player_id.unique()
    for pid in todo:
        res = bbref_page(f"/wnba/players/{pid[0]}/{pid}.html", refresh, allow_404=True)
        if res is None:
            continue
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, "lxml")
        span = soup.find(attrs={"data-birth": True})
        birth = span["data-birth"] if span else None
        T = bbref_tables(res.text)
        seasons = set()
        for tid in ("per_game0", "per_game", "totals0", "totals"):
            if tid in T:
                for x in bbref_rows(T[tid]):
                    y = re.match(r"^(\d{4})", x.get("year") or x.get("year_id") or x.get("season") or "")
                    if y:
                        seasons.add(int(y.group(1)))
                break
        for i in df.index[df.player_id == pid]:
            if pd.isna(df.at[i, "birth_date"]) and birth:
                df.at[i, "birth_date"] = birth
                df.at[i, "bio_fill_method"] = "birth_date_from_player_page"
            if pd.isna(df.at[i, "experience_years"]) and seasons:
                df.at[i, "experience_years"] = sum(1 for y in seasons if y < int(df.at[i, "season"]))
                df.at[i, "experience_years_raw"] = "computed_from_player_page_seasons"
        prov.append({"league": "WNBA", "team_id": "", "season": "", "dataset": "player_season_data",
                     "variables": f"birth_date;experience_years for {pid}", "source_organization": "Sports Reference LLC (Basketball-Reference)",
                     "source_url": res.url, "retrieval_timestamp_utc": res.retrieved_at_utc, "value_origin": "direct",
                     "quality_notes": "Used only where the team roster table omitted the player.", "verification_status": "single_source"})
    # recompute ages for filled rows
    for i in df.index[df.bio_fill_method.fillna("").str.startswith("birth_date_from")]:
        ref = df.at[i, "age_reference_date"]
        df.at[i, "age_at_reference"] = age_on(pd.to_datetime(df.at[i, "birth_date"]).date(), pd.to_datetime(ref).date() if ref else None)
    log.info("WNBA bio fill: %d rows still missing birth_date", df.birth_date.isna().sum())
    return df, prov


def collect_wnba(ts: pd.DataFrame, refresh: bool) -> tuple[pd.DataFrame, list[dict]]:
    rows, prov = [], []
    w = ts[ts.league == "WNBA"]
    w = w[w.season.astype(int).isin(settings.WNBA_CORE_SEASONS)]
    for r in w.sort_values(["season", "team_id"]).itertuples():
        season, code = int(r.season), r.team_abbr_source
        res = bbref_page(f"/wnba/teams/{code}/{season}.html", refresh)
        T = bbref_tables(res.text)
        ref_date = pd.to_datetime(r.first_regular_season_game_date).date() if isinstance(r.first_regular_season_game_date, str) else None
        players: dict[str, dict] = {}

        def rec(pid, name):
            return players.setdefault(pid, {"league": "WNBA", "season": str(season), "season_start_year": season,
                                            "season_end_year": season, "team_id": r.team_id, "team_name": r.team_name,
                                            "player_id": pid, "player_id_source": "basketball-reference",
                                            "player_name": name})

        for x in bbref_rows(T["roster"]) if "roster" in T else []:
            pid = _pid(x.get("player_href"))
            if not pid:
                continue
            p = rec(pid, x["player"])
            bd = pd.to_datetime(x.get("birth_date"), format="%B %d, %Y", errors="coerce")
            exp_raw = x.get("exp")
            p.update({"jersey_number": x.get("number"), "position": x.get("pos"), "height_raw": x.get("height"),
                      "height_in": _height_in(x.get("height")), "weight_lb": to_num(x.get("weight")),
                      "birth_date": bd.date().isoformat() if pd.notna(bd) else None,
                      "experience_years_raw": exp_raw,
                      "experience_years": 0 if exp_raw == "R" else to_num(exp_raw),
                      "college_or_prior": x.get("college"), "on_season_roster_table": True})
        for tid, fields, prefix in (("totals", WNBA_TOTAL_FIELDS, ""), ("advanced", WNBA_ADV_FIELDS, "")):
            if tid not in T:
                continue
            for x in bbref_rows(T[tid]):
                pid = _pid(x.get("player_href"))
                if not pid:
                    continue
                p = rec(pid, x["player"])
                p["age_source"] = to_num(x.get("wnba_age"))
                for f in fields:
                    p[prefix + f] = to_num(x.get(f))
        if "playoffs_totals" in T:
            for x in bbref_rows(T["playoffs_totals"]):
                pid = _pid(x.get("player_href"))
                if pid:
                    p = rec(pid, x["player"])
                    p.update({"playoff_g": to_num(x.get("g")), "playoff_mp": to_num(x.get("mp")),
                              "playoff_pts": to_num(x.get("pts"))})
        for p in players.values():
            bd = pd.to_datetime(p.get("birth_date")).date() if p.get("birth_date") else None
            p["age_reference_date"] = ref_date.isoformat() if ref_date else None
            p["age_at_reference"] = age_on(bd, ref_date)
        rows += list(players.values())
        base = {"league": "WNBA", "team_id": r.team_id, "season": str(season), "dataset": "player_season_data",
                "source_organization": "Sports Reference LLC (Basketball-Reference)", "source_url": res.url,
                "retrieval_timestamp_utc": res.retrieved_at_utc, "verification_status": "single_source"}
        prov.append({**base, "variables": "roster: position;height;weight;birth_date;experience;college", "value_origin": "direct"})
        prov.append({**base, "variables": "totals;advanced (PER, WS, ratings);playoff totals", "value_origin": "direct",
                     "quality_notes": "Team-specific stint stats from the team page; advanced metrics are Basketball-Reference definitions."})
        prov.append({**base, "variables": "age_at_reference", "value_origin": "calculated",
                     "calculation_definition": "(first regular-season game date - birth_date) in years / 365.2425"})
    df = pd.DataFrame(rows)
    # "(DC)" suffix = developmental contract (2026 CBA developmental roster spots)
    df["developmental_contract"] = df["player_name"].str.contains(r"\(DC\)", regex=True)
    df["player_name"] = df["player_name"].str.replace(r"\s*\(DC\)\s*", "", regex=True).str.strip()
    df, fill_prov = fill_wnba_bio(df, refresh)
    prov += fill_prov
    df = df.rename(columns={"g": "games_played", "gs": "games_started", "mp": "minutes", "trb": "rebounds",
                            "ast": "assists", "stl": "steals", "blk": "blocks", "tov": "turnovers", "pts": "points"})
    df["minutes_per_game"] = df["minutes"] / df["games_played"]
    df["points_per_game"] = df["points"] / df["games_played"]
    df["roster_status"] = np.where(df["games_played"].fillna(0) > 0, "appeared", "rostered_no_appearance")
    df["position_group"] = df["position"].map(lambda p: None if not isinstance(p, str) else
                                              ("G" if p.startswith("G") else "F" if p.startswith("F") else "C" if p.startswith("C") else None))

    # salaries: Spotrac player earnings via the CC BY 4.0 Mendeley dataset (2018-2023)
    df["contract_data_status"] = "not_collected_no_permitted_automated_source"
    try:
        sal, meta = wnba_mendeley_salaries(refresh)
        sal = sal[sal.season.isin(set(df.season))]
        df, _ = attach_salaries(df, sal, "WNBA", status="reported_spotrac_via_mendeley",
                                measure="annual salary earnings per Spotrac player rankings (prorated for partial-season/hardship contracts)",
                                source="Spotrac via Mendeley Data (CC BY 4.0)", source_url=meta["doi_url"], as_of=meta["as_of"],
                                unlisted_status="not_listed_in_source")
        for ssn, tid in sal[["season", "team_id"]].drop_duplicates().itertuples(index=False):
            prov.append({"league": "WNBA", "team_id": tid, "season": ssn, "dataset": "player_season_data",
                         "variables": "salary_base_usd",
                         "source_organization": "Spotrac (via Mendeley Data dataset 38wkcb4pwb v1, CC BY 4.0)",
                         "source_url": meta["file_url"], "retrieval_timestamp_utc": meta["retrieved"],
                         "source_update_date": meta["as_of"], "value_origin": "direct",
                         "quality_notes": "Annual earnings as listed by Spotrac (accessed by the dataset authors 2024-04-28); one team per player-season.",
                         "verification_status": "secondary_source"})
    except Exception as exc:
        log.error("WNBA Mendeley salary dataset unavailable: %s", exc)
    # optional manual file (e.g. 2024+ salaries from a source you are licensed to use)
    manual = wnba_manual_contracts()
    if manual is not None:
        m = manual.rename(columns={"salary_usd": "salary_base_usd"})
        for ssn, g in m.groupby("season"):
            g = g.assign(name_key=[player_key("WNBA", n) for n in g.player_name])
            df, _ = attach_salaries(df, g, "WNBA", status="manual_import", measure=g.salary_measure.iloc[0],
                                    source=g.source_organization.iloc[0], source_url=g.source_url.iloc[0],
                                    as_of=g.source_as_of_date.iloc[0], unlisted_status="not_listed_in_source")
    return df, prov


# ===========================================================================
# PWHL
# ===========================================================================
SKATER_SUM = ["goals", "assists", "points", "shots", "hits", "blocked_shots", "penalty_minutes", "plus_minus",
              "faceoff_attempts", "faceoff_wins", "faceoff_losses"]


def collect_pwhl(ts: pd.DataFrame, refresh: bool) -> tuple[pd.DataFrame, list[dict]]:
    commit = fastrhockey_commit(refresh)
    frames, prov = [], []
    first_dates = (ts[ts.league == "PWHL"].groupby("season").first_regular_season_game_date.min().to_dict())
    for s in settings.PWHL_SEASONS:
        y = s["fastrhockey_season"]
        sched, _ = fastrhockey_parquet("schedules", y, refresh)
        box, bres = fastrhockey_parquet("player_box", y, refresh)
        ros, rres = fastrhockey_parquet("rosters", y, refresh)
        box = box.merge(sched[["game_id", "game_type"]], on="game_id", how="left")
        box["is_goalie"] = (box["player_type"] == "goalie") | (box["position"] == "G")
        box["played"] = np.where(box.is_goalie, box["time_on_ice"].fillna(0) > 0, True)
        out = []
        for (pid, tid), d in box.groupby(["player_id", "team_id"]):
            reg = d[d.game_type == "regular"]
            po = d[d.game_type != "regular"]
            goalie = bool(d.is_goalie.any())
            rec = {"source_player_id": pid, "source_team_id": tid,
                   "first_name": d.first_name.iloc[0], "last_name": d.last_name.iloc[0],
                   "box_position": d.position.mode().iloc[0] if len(d.position.mode()) else None,
                   "is_goalie": goalie,
                   "games_dressed": len(reg), "games_played": int(reg.played.sum()),
                   "games_started": int(reg.starting.sum()),
                   "time_on_ice_total_min": reg.time_on_ice.sum(min_count=1),
                   "toi_games_with_data": int(reg.time_on_ice.notna().sum())}
            for c in SKATER_SUM:
                rec[c] = reg[c].sum(min_count=1) if c in reg else None
            if goalie:
                for c in ("saves", "goals_against", "shots_against"):
                    rec[c] = reg[c].sum(min_count=1)
            rec.update({"playoff_games_dressed": len(po), "playoff_games_played": int(po.played.sum()),
                        "playoff_goals": po.goals.sum(min_count=1), "playoff_assists": po.assists.sum(min_count=1),
                        "playoff_points": po.points.sum(min_count=1),
                        "playoff_time_on_ice_total_min": po.time_on_ice.sum(min_count=1)})
            out.append(rec)
        agg = pd.DataFrame(out)
        r = ros.drop_duplicates(["team_id", "player_id"]).rename(columns={"player_id": "source_player_id", "team_id": "source_team_id"})
        agg = agg.merge(r[["source_player_id", "source_team_id", "position", "birth_date", "jersey_number", "team"]],
                        on=["source_player_id", "source_team_id"], how="outer")
        agg["league"] = "PWHL"
        agg["season"] = s["season"]
        agg["season_start_year"], agg["season_end_year"] = s["start_year"], s["end_year"]
        agg["team_id"] = agg["source_team_id"].map(lambda x: franchise_by_source_id("PWHL", x))
        agg["player_id"] = "pwhl-" + agg["source_player_id"].astype(int).astype(str)
        agg["player_id_source"] = "PWHL/HockeyTech player_id (via fastRhockey)"
        names = box.drop_duplicates("player_id").set_index("player_id")[["first_name", "last_name"]]
        agg["first_name"] = agg["first_name"].fillna(agg.source_player_id.map(names.first_name))
        agg["last_name"] = agg["last_name"].fillna(agg.source_player_id.map(names.last_name))
        agg["player_name"] = (agg.first_name.fillna("") + " " + agg.last_name.fillna("")).str.strip()
        agg["position"] = agg["position"].fillna(agg["box_position"])
        agg["team_name"] = agg.groupby("team_id")["team"].transform(lambda x: x.dropna().iloc[0] if x.notna().any() else None)
        ref = pd.to_datetime(first_dates.get(s["season"])).date() if first_dates.get(s["season"]) else None
        agg["age_reference_date"] = ref.isoformat() if ref else None
        agg["age_at_reference"] = [age_on(pd.to_datetime(b).date() if isinstance(b, str) and b else None, ref) for b in agg.birth_date]
        frames.append(agg)
        commit_note = f"fastRhockey data repo commit {commit.get('sha')} ({commit.get('date')})"
        for tid in agg.team_id.dropna().unique():
            base = {"league": "PWHL", "team_id": tid, "season": s["season"], "dataset": "player_season_data",
                    "source_organization": "sportsdataverse fastRhockey-pwhl-data (from PWHL/HockeyTech official stats)",
                    "retrieval_timestamp_utc": bres.retrieved_at_utc, "source_update_date": commit.get("date"),
                    "verification_status": "single_source"}
            prov.append({**base, "variables": "games_played;games_dressed;time_on_ice;goals;assists;points;shots;hits;blocked_shots;pim;plus_minus;faceoffs;goalie saves/GA/SA",
                         "source_url": bres.url, "value_origin": "calculated",
                         "calculation_definition": "Sums of per-game player box scores for regular-season games (schedule game_type == 'regular'), grouped by player_id and team_id.",
                         "quality_notes": commit_note})
            prov.append({**base, "variables": "position;birth_date;jersey_number", "source_url": rres.url, "value_origin": "direct",
                         "quality_notes": commit_note})
    df = pd.concat(frames, ignore_index=True)
    for c in ["games_dressed", "games_played", "games_started"]:
        df[c] = df[c].fillna(0)
    df["roster_status"] = np.where(df["games_dressed"] > 0, "appeared", "rostered_no_appearance")
    df["position_group"] = df["position"].map(lambda p: None if not isinstance(p, str) else
                                              ("G" if p == "G" else "D" if p in ("D", "LD", "RD") else "F"))
    df["toi_per_game"] = df["time_on_ice_total_min"] / df["games_played"].replace(0, np.nan)
    df.loc[df.toi_games_with_data.fillna(0) < df.games_played, "toi_note"] = "TOI missing for some games"
    df["save_pct"] = df["saves"] / df["shots_against"].replace(0, np.nan)
    df["gaa"] = df["goals_against"] * 60 / df["time_on_ice_total_min"].where(df.is_goalie == True).replace(0, np.nan)
    df["points_per_game"] = df["points"] / df["games_played"].replace(0, np.nan)
    # PWHL experience: number of earlier PWHL seasons in which the player appeared
    order = {s["season"]: i for i, s in enumerate(settings.PWHL_SEASONS)}
    seasons_played = df[df.games_played > 0].groupby("player_id")["season"].apply(lambda x: sorted(set(x), key=order.get))
    df["experience_years"] = [sum(1 for x in seasons_played.get(p, []) if order[x] < order[s]) for p, s in zip(df.player_id, df.season)]
    df["experience_definition"] = "prior PWHL seasons with >=1 regular-season game (excludes PHF/PWHPA/other leagues)"
    df = df.drop(columns=["team", "box_position"])

    # salaries (PWHLPA, 2025-26)
    df["contract_data_status"] = "not_reported"
    try:
        sal, meta = pwhlpa_salaries(refresh)
        df, _ = attach_salaries(df, sal, "PWHL", status="reported_pwhlpa",
                                measure="base salary (excludes bonuses, incentives, housing)",
                                source="PWHLPA Player Salary Guide", source_url=meta["url"], as_of=meta["as_of"],
                                unlisted_status="not_listed_in_pwhlpa_guide")
        for tid in sal.team_id.dropna().unique():
            prov.append({"league": "PWHL", "team_id": tid, "season": sal.season.iloc[0], "dataset": "player_season_data",
                         "variables": "salary_base_usd", "source_organization": "PWHL Players' Association (PWHLPA)",
                         "source_url": meta["url"], "retrieval_timestamp_utc": meta["retrieved"],
                         "source_update_date": meta["as_of"], "value_origin": "direct",
                         "quality_notes": "Base salary only; players under contract at publication; PWHLPA site restricts redistribution.",
                         "verification_status": "official_players_association"})
    except Exception as exc:
        log.error("PWHLPA salary guide unavailable: %s", exc)
    return df, prov


# ===========================================================================
# Current roster snapshot (Wikipedia)
# ===========================================================================
def _wnba_template_rows(page) -> list[dict]:
    out = []
    for tb in page.soup.find_all("table"):
        txt = grid_text(wikitable_grid(tb))
        if not txt or "Pos." not in txt[0] or "Name" not in txt[0]:
            continue
        hdr = txt[0]
        for r in txt[1:]:
            if len(r) != len(hdr) or r == hdr:
                continue
            d = dict(zip(hdr, r))
            if not d.get("Name"):
                continue
            name = re.sub(r"\s*\((?:C|DP|FA|S|TE|IN|DE|RFA|UFA|[A-Z]{1,3})\)\s*", " ", d["Name"]).strip()
            out.append({"player_name_source": d["Name"], "player_name": flip_last_first(name), "position": d.get("Pos."),
                        "jersey_number": d.get("No."), "birth_date": d.get("DOB"), "height_raw": d.get("Height"),
                        "experience_years_raw": d.get("Yrs"), "college_or_prior": d.get("From")})
        if out:
            break
    return out


def _pwhl_article_rows(page) -> list[dict]:
    h = page.soup.find(id=re.compile(r"^Current_roster"))
    if h is None:
        return []
    tb = h.find_parent().find_next("table")
    txt = grid_text(wikitable_grid(tb))
    hdr_i = next((i for i, r in enumerate(txt) if "Player" in r and "Pos" in r), None)
    if hdr_i is None:
        return []
    hdr = txt[hdr_i]
    out = []
    for r in txt[hdr_i + 1:]:
        if len(r) != len(hdr) or r == hdr:
            continue
        d = dict(zip(hdr, r))
        if not d.get("Player"):
            continue
        name = re.sub(r"\s*\((?:C|A)\)\s*", " ", d["Player"]).strip()
        out.append({"player_name_source": d["Player"], "player_name": name, "position": d.get("Pos"),
                    "jersey_number": d.get("No."), "age_integer_source": to_num(d.get("Age")),
                    "acquired_year": d.get("Acquired"), "shoots_catches": d.get("S / G") or d.get("S/G")})
    return out


def collect_snapshot(players: pd.DataFrame, refresh: bool) -> tuple[pd.DataFrame, list[dict]]:
    teams = teams_table()
    teams = teams[teams.status_as_of_snapshot.isin(["active", "relocating", "expansion_not_yet_played"])]
    rows, prov = [], []
    snap_date = utc_now_iso()[:10]
    for t in teams.itertuples():
        page, items = None, []
        if t.league == "WNBA":
            cands = [f"Template:{t.current_team_name} roster"]
            if t.franchise_id == "WNBA-CON":
                cands = ["Template:Houston Comets roster"] + cands
            for title in cands:
                page = wiki_page(title, refresh, current=True)
                items = _wnba_template_rows(page) if page else []
                if items:
                    break
        else:
            for title in (t.current_team_name, t.current_team_name.replace("é", "e")):
                page = wiki_page(title, refresh, current=True)
                items = _pwhl_article_rows(page) if page else []
                if items:
                    break
        if not items:
            log.warning("no current roster found for %s", t.franchise_id)
            continue
        for it in items:
            it.update({"league": t.league, "snapshot_team_id": t.franchise_id, "snapshot_team_name": t.current_team_name,
                       "snapshot_date": snap_date, "source_title": page.title, "source_revision_id": page.revid,
                       "source_url": page.permalink, "retrieved_at_utc": page.retrieved_at_utc})
            rows.append(it)
        prov.append({"league": t.league, "team_id": t.franchise_id, "season": f"snapshot_{snap_date}",
                     "dataset": "current_roster_snapshot", "variables": "current roster (names, position, age/DOB, experience/acquired)",
                     "source_organization": "Wikipedia (crowd-edited)", "source_url": page.permalink,
                     "retrieval_timestamp_utc": page.retrieved_at_utc, "value_origin": "direct",
                     "quality_notes": "Secondary, crowd-edited source; reflects page state at the revision id; verify before treating as official.",
                     "verification_status": "secondary_unverified"})
    df = pd.DataFrame(rows)
    if df.empty:
        return df, prov
    df["birth_date"] = pd.to_datetime(df.get("birth_date"), errors="coerce").dt.date.astype("string")
    df["age_at_snapshot"] = [age_on(pd.to_datetime(b).date() if isinstance(b, str) and b not in ("", "<NA>") else None,
                                    pd.to_datetime(snap_date).date()) for b in df["birth_date"]]
    df["experience_years"] = df.get("experience_years_raw").map(lambda x: 0 if x == "R" else to_num(x)) if "experience_years_raw" in df else None
    # link to historical player ids by normalised name within league (unique matches only)
    df["name_key"] = [player_key(lg, n) for lg, n in zip(df.league, df.player_name)]
    pl = players.copy()
    pl["name_key"] = [player_key(lg, n) for lg, n in zip(pl.league, pl.player_name)]
    ids = pl.groupby(["league", "name_key"]).player_id.agg(lambda x: x.iloc[0] if x.nunique() == 1 else None)
    df["player_id"] = [ids.get((lg, k)) for lg, k in zip(df.league, df.name_key)]
    df["player_id_match"] = np.where(df.player_id.notna(), "unique_name_match", "no_historical_match_or_ambiguous")
    # birth date: from the snapshot page if shown (WNBA), else from the matched historical record
    hist_bd = pl.dropna(subset=["birth_date"]).groupby("player_id").birth_date.first()
    df["birth_date_source"] = np.where(df.birth_date.notna() & (df.birth_date != "<NA>"), "snapshot_page", None)
    fill = df.birth_date_source.isna() & df.player_id.isin(hist_bd.index)
    df.loc[fill, "birth_date"] = df.loc[fill, "player_id"].map(hist_bd)
    df.loc[fill, "birth_date_source"] = "historical_player_record"
    df["age_at_snapshot"] = [age_on(pd.to_datetime(b).date() if isinstance(b, str) and b not in ("", "<NA>") else None,
                                    pd.to_datetime(snap_date).date()) for b in df["birth_date"]]
    # flag whether the player's most recent historical team equals the snapshot team
    last = pl.sort_values("season_start_year").groupby("player_id").tail(1).set_index("player_id")
    df["last_historical_team_id"] = df.player_id.map(last.team_id)
    df["last_historical_season"] = df.player_id.map(last.season)
    df = df.drop(columns=["name_key"])
    df = df.drop_duplicates(["league", "snapshot_team_id", "player_name"])
    return df, prov


COLS_FIRST = ["league", "season", "season_start_year", "season_end_year", "team_id", "team_name", "player_id",
              "player_id_source", "player_name", "first_name", "last_name", "position", "position_group", "jersey_number",
              "roster_status", "multi_team_season", "n_teams_in_season", "birth_date", "age_reference_date",
              "age_at_reference", "age_source", "experience_years", "experience_years_raw", "experience_definition",
              "height_raw", "height_in", "weight_lb", "college_or_prior", "is_goalie", "games_played", "games_dressed",
              "games_started", "minutes", "minutes_per_game", "time_on_ice_total_min", "toi_per_game",
              "toi_games_with_data", "toi_note", "points", "points_per_game", "rebounds", "orb", "drb", "assists",
              "steals", "blocks", "turnovers", "pf", "fg", "fga", "fg_pct", "fg3", "fg3a", "fg3_pct", "fg2", "fg2a",
              "fg2_pct", "ft", "fta", "ft_pct", "per", "ts_pct", "efg_pct", "usg_pct", "orb_pct", "drb_pct", "trb_pct",
              "ast_pct", "stl_pct", "blk_pct", "tov_pct", "off_rtg", "def_rtg", "ows", "dws", "ws", "ws_per_40",
              "goals", "shots", "hits", "blocked_shots", "penalty_minutes", "plus_minus", "faceoff_attempts",
              "faceoff_wins", "faceoff_losses", "saves", "shots_against", "goals_against", "save_pct", "gaa",
              "playoff_g", "playoff_mp", "playoff_pts", "playoff_games_dressed", "playoff_games_played",
              "playoff_goals", "playoff_assists", "playoff_points", "playoff_time_on_ice_total_min",
              "contract_data_status", "salary_base_usd", "salary_measure", "salary_source", "salary_source_url",
              "salary_as_of", "salary_match_method", "contract_start_year", "contract_end_year", "contract_type",
              "guaranteed_usd", "free_agent_status_next", "source_player_id", "source_team_id"]


def main() -> None:
    ap = base_argparser(__doc__.splitlines()[0])
    ap.add_argument("--skip-snapshot", action="store_true")
    args = ap.parse_args()
    ts = team_seasons()
    frames, prov = [], []
    leagues = ["WNBA", "PWHL"] if args.league == "both" else [args.league]
    if "WNBA" in leagues:
        d, p = collect_wnba(ts, args.refresh); frames.append(d); prov += p
    if "PWHL" in leagues:
        d, p = collect_pwhl(ts, args.refresh); frames.append(d); prov += p
    df = pd.concat(frames, ignore_index=True)
    n_teams = df[df.games_played.fillna(0) > 0].groupby(["league", "season", "player_id"]).team_id.nunique()
    df["n_teams_in_season"] = [n_teams.get((a, b, c), 0) for a, b, c in zip(df.league, df.season, df.player_id)]
    df["multi_team_season"] = df["n_teams_in_season"] > 1
    for c in COLS_FIRST:
        if c not in df:
            df[c] = np.nan
    df = df[COLS_FIRST + [c for c in df.columns if c not in COLS_FIRST]]
    out = upsert_csv(df, settings.EXPORTS_DIR / "player_season_data.csv", KEYS, replace_scope={"league": leagues})
    if not args.skip_snapshot:
        allp = pd.read_csv(settings.EXPORTS_DIR / "player_season_data.csv", dtype={"season": str}, low_memory=False)
        snap, sp = collect_snapshot(allp, args.refresh)
        prov += sp
        if not snap.empty:
            upsert_csv(snap, settings.PROCESSED_DIR / "current_roster_snapshot.csv",
                       ["league", "snapshot_team_id", "player_name"], replace_scope={"league": leagues})
    record_provenance(prov, SCRIPT)
    log.info("done: %d player-team-season rows", len(df))


if __name__ == "__main__":
    main()
