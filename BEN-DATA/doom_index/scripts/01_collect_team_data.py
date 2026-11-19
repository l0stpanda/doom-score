"""01 - Collect team-season records, scoring, playoff results and lag features.

WHAT IT COLLECTS
    One row per team per season with regular-season record, scoring, home/away
    splits, source-published strength-of-schedule / rating measures (WNBA),
    playoff results, and historical-performance lags.

LEAGUES / SEASONS
    WNBA  core seasons 2021-2026 + context seasons 2019-2020 (flagged
          in_core_scope=False; collected only so 2021 has lag features).
    PWHL  2023-24 (inaugural), 2024-25, 2025-26. The 2026-27 season had not
          started at the snapshot date (first regular-season game 2026-12-04 per
          the league's stats feed; Daily Faceoff reports 2026-12-05), so it has
          no rows here.

OUTPUTS
    data/exports/team_season_data.csv            (key: league, season, team_id)
    data/processed/playoff_series.csv            (key: league, season, round_number, team_a_id, team_b_id)
    data/processed/pwhl_games.csv                (key: league, season, game_id)
    data/processed/team_record_crosschecks.csv   (source-vs-source comparisons)
    data/exports/team_season_sources.csv         (provenance rows, upserted)

SOURCES
    WNBA  Basketball-Reference season pages  https://www.basketball-reference.com/wnba/years/{YYYY}.html
            tables: standings_e / standings_w (conference standings),
            advanced-team (age, MOV, SOS, SRS, ratings, pace), totals-team /
            totals-opponent (points), all_playoffs (series results).
          ESPN public standings API  https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings?season=YYYY
            home/road records, playoff seed, and an independent W/L + points cross-check.
    PWHL  sportsdataverse fastRhockey PWHL data (MIT licence; derived from the
            league's official HockeyTech stats feed)
            https://github.com/sportsdataverse/fastRhockey-pwhl-data
            files: schedules/pwhl_schedule_{end_year}.parquet, game_info_{end_year}.parquet
          Wikipedia season articles (standings table) used ONLY as a cross-check.

FIELDS / DERIVED FORMULAS
    win_percentage           = wins / games_played (all wins incl. OT/SO wins in PWHL)
    points (PWHL)            = 3*regulation_wins + 2*(ot_wins+so_wins) + 1*(ot_losses+so_losses)
    points_percentage (PWHL) = points / (3 * games_played)
    point_differential       = points_for - points_against (WNBA)
    goal_differential        = goals_for - goals_against (PWHL; GF/GA include
                               the +1 credited to shootout winners as in the source final score)
    prior_season_win_pct     = franchise win_percentage in the immediately preceding league season
    win_pct_change_yoy       = win_percentage - prior_season_win_pct
    win_pct_rolling3_mean    = mean of win_percentage over seasons t, t-1, t-2 (all three required)
    win_pct_3season_pooled   = sum(wins) / sum(games_played) over t, t-1, t-2 (all three required)
    (the same lag set is produced for points_percentage in the PWHL)
    playoff_* fields          = derived from series results (games won/lost from series scores)

KNOWN LIMITATIONS
    * WNBA strength of schedule is Basketball-Reference's SOS (rating-based,
      points per game relative to average); PWHL has no SOS measure collected.
    * Schedule lengths differ (WNBA 40-44 games; PWHL 24-30), so percentages
      have different sampling noise.
    * 2020 WNBA season was a shortened 22-game "bubble" season (context only).
    * ESPN home/road splits are taken as published; missing if ESPN lacks a season.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: F401  (sets sys.path for config)

import numpy as np
import pandas as pd

from config import settings
from lib.common import (base_argparser, franchise_by_bbref, franchise_by_source_id, pwhl_season_meta,
                        resolve_team, setup_logging, to_num, wnba_season_meta)
from lib.sources import bbref_page, espn_wnba_standings, fastrhockey_commit, fastrhockey_parquet, wiki_page
from lib.store import record_provenance, upsert_csv, write_csv
from lib.tables import bbref_rows, bbref_tables, find_header_row, grid_text, wikitable_grid

SCRIPT = "01_collect_team_data.py"
log = setup_logging("01_collect_team_data")

TEAM_KEYS = ["league", "season", "team_id"]


# ===========================================================================
# WNBA
# ===========================================================================
def _team_code(href: str | None) -> str | None:
    m = re.search(r"/wnba/teams/([A-Z]{3})/", href or "")
    return m.group(1) if m else None


def parse_wnba_playoffs(tables: dict, season: int) -> list[dict]:
    t = tables.get("all_playoffs")
    if t is None:
        return []
    out = []
    for tr in t.find_all("tr"):
        tds = tr.find_all(["td", "th"], recursive=False)
        if len(tds) < 2:
            continue
        label = tds[0].get_text(" ", strip=True)
        txt = tds[1].get_text(" ", strip=True)
        m = re.match(r"(.+?) over (.+?) \((\d+)-(\d+)\)", txt)
        if not m:
            continue
        links = [a["href"] for a in tds[1].find_all("a") if a.has_attr("href")]
        codes = [_team_code(h) for h in links if _team_code(h)]
        win_id = franchise_by_bbref(codes[0]) if len(codes) > 0 else resolve_team("WNBA", m.group(1))
        lose_id = franchise_by_bbref(codes[1]) if len(codes) > 1 else resolve_team("WNBA", m.group(2))
        out.append({"league": "WNBA", "season": str(season), "round_label": label,
                    "winner_id": win_id, "loser_id": lose_id, "winner_name": m.group(1), "loser_name": m.group(2),
                    "winner_games": int(m.group(3)), "loser_games": int(m.group(4))})
    # BBRef lists the final first; assign round_number by reversing the round order.
    labels = []
    for r in out:
        if r["round_label"] not in labels:
            labels.append(r["round_label"])
    order = {lab: len(labels) - i for i, lab in enumerate(labels)}
    for r in out:
        r["round_number"] = order[r["round_label"]]
        r["is_final"] = r["round_number"] == max(order.values())
    return out


def collect_wnba_season(season: int, refresh: bool) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    path = f"/wnba/years/{season}.html"
    res = bbref_page(path, refresh)
    tables = bbref_tables(res.text)
    url = res.url
    teams: dict[str, dict] = {}

    def row_for(code: str, name: str) -> dict:
        fid = franchise_by_bbref(code)
        if fid is None:
            raise ValueError(f"Unknown BBRef team code {code} ({name}) in {season}")
        return teams.setdefault(fid, {**wnba_season_meta(season), "team_id": fid,
                                      "team_name": name.replace("*", "").strip(), "team_abbr_source": code})

    # Conference standings (record, per-game scoring, playoff asterisk)
    for conf_id, conf in (("standings_e", "Eastern"), ("standings_w", "Western")):
        t = tables.get(conf_id)
        if t is None:
            continue
        for r in bbref_rows(t, keep_links=("team_name",)):
            code = _team_code(r.get("team_name_href"))
            if not code:
                continue
            rec = row_for(code, r["team_name"])
            rec["conference"] = conf
            rec["playoff_qualified"] = r["team_name"].strip().endswith("*")
            rec["bbref_wins"] = to_num(r.get("wins"))
            rec["bbref_losses"] = to_num(r.get("losses"))
            rec["bbref_points_for_per_game"] = to_num(r.get("pts_per_g"))
            rec["bbref_points_against_per_game"] = to_num(r.get("opp_pts_per_g"))

    adv = tables.get("advanced-team")
    if adv is not None:
        for r in bbref_rows(adv):
            code = _team_code(r.get("team_href"))
            if not code:
                continue
            rec = row_for(code, r["team"])
            rec.setdefault("playoff_qualified", r["team"].strip().endswith("*"))
            rec["bbref_wins"] = rec.get("bbref_wins") or to_num(r.get("wins"))
            rec["bbref_losses"] = rec.get("bbref_losses") or to_num(r.get("losses"))
            for src, dst in [("age", "team_avg_age_bbref"), ("wins_pyth", "pythag_wins_bbref"),
                             ("losses_pyth", "pythag_losses_bbref"), ("mov", "mov_bbref"), ("sos", "sos_bbref"),
                             ("srs", "srs_bbref"), ("off_rtg", "off_rtg_bbref"), ("def_rtg", "def_rtg_bbref"),
                             ("net_rtg", "net_rtg_bbref"), ("pace", "pace_bbref")]:
                rec[dst] = to_num(r.get(src))
            rec["arena_name"] = r.get("arena_name")

    for tid, prefix in (("totals-team", ""), ("totals-opponent", "opp_")):
        t = tables.get(tid)
        if t is None:
            continue
        for r in bbref_rows(t):
            code = _team_code(r.get("team_href"))
            if not code:
                continue
            rec = row_for(code, r["team"])
            if prefix == "":
                rec["games_played"] = to_num(r.get("g"))
                rec["points_for"] = to_num(r.get("pts"))
            else:
                rec["points_against"] = to_num(r.get("opp_pts", r.get("pts")))

    series = parse_wnba_playoffs(tables, season)

    # Schedule page: first / last regular-season game dates (age reference date).
    first_game = last_game = None
    try:
        sres = bbref_page(f"/wnba/years/{season}_games.html", refresh)
        st = bbref_tables(sres.text).get("schedule")
        if st is not None:
            srows = [r for r in bbref_rows(st) if r.get("date_game")]
            reg = [r for r in srows if not (r.get("_section") or "").lower().startswith("playoff")]
            dates = pd.to_datetime([r["date_game"] for r in reg], format="%a, %b %d, %Y", errors="coerce").dropna()
            if len(dates):
                first_game, last_game = dates.min().date().isoformat(), dates.max().date().isoformat()
    except Exception as exc:
        log.warning("schedule page unavailable for %s: %s", season, exc)
    for rec in teams.values():
        rec["first_regular_season_game_date"] = first_game
        rec["last_regular_season_game_date"] = last_game

    # ESPN: home/road + cross-check
    checks: list[dict] = []
    espn_url = None
    espn_retrieved = None
    try:
        er = espn_wnba_standings(season, refresh)
        espn_url, espn_retrieved = er.url, er.retrieved_at_utc
        data = er.json()
        for child in data.get("children", []):
            for e in child.get("standings", {}).get("entries", []):
                fid = resolve_team("WNBA", e["team"].get("displayName"))
                if fid is None or fid not in teams:
                    log.warning("ESPN team %s not matched for %s", e["team"].get("displayName"), season)
                    continue
                stats = {s.get("name") or s.get("type"): s for s in e.get("stats", [])}
                rec = teams[fid]
                for nm, dst in (("Home", "home"), ("Road", "away")):
                    s = stats.get(nm) or stats.get(nm.lower())
                    if s and re.match(r"^\d+-\d+$", s.get("summary") or s.get("displayValue") or ""):
                        w, l = (s.get("summary") or s.get("displayValue")).split("-")
                        rec[f"{dst}_wins"], rec[f"{dst}_losses"] = int(w), int(l)
                seed = stats.get("playoffSeed", {}).get("value")
                rec["playoff_seed_espn"] = seed if seed and seed > 0 else None
                ew, el = stats.get("wins", {}).get("value"), stats.get("losses", {}).get("value")
                epf, epa = stats.get("pointsFor", {}).get("value"), stats.get("pointsAgainst", {}).get("value")
                checks.append({"league": "WNBA", "season": str(season), "team_id": fid,
                               "source_a": "Basketball-Reference", "source_b": "ESPN",
                               "wins_a": rec.get("bbref_wins"), "wins_b": ew,
                               "losses_a": rec.get("bbref_losses"), "losses_b": el,
                               "scored_a": rec.get("points_for"), "scored_b": epf,
                               "allowed_a": rec.get("points_against"), "allowed_b": epa})
    except Exception as exc:  # ESPN is a secondary source; record and continue
        log.warning("ESPN standings unavailable for %s: %s", season, exc)

    rows = []
    for rec in teams.values():
        rec["wins"] = rec.pop("bbref_wins", None)
        rec["losses"] = rec.pop("bbref_losses", None)
        if rec.get("games_played") is None and rec.get("wins") is not None:
            rec["games_played"] = rec["wins"] + rec["losses"]
        rows.append(rec)

    prov = []
    for rec in rows:
        base = {"league": "WNBA", "team_id": rec["team_id"], "season": str(season), "dataset": "team_season_data",
                "source_organization": "Sports Reference LLC (Basketball-Reference)", "source_url": url,
                "retrieval_timestamp_utc": res.retrieved_at_utc, "value_origin": "direct",
                "verification_status": "cross_checked_against_espn" if espn_url else "single_source"}
        prov.append({**base, "variables": "wins;losses;games_played;points_for;points_against;conference;playoff_qualified"})
        prov.append({**base, "variables": "team_avg_age_bbref;pythag_wins_bbref;pythag_losses_bbref;mov_bbref;sos_bbref;srs_bbref;off_rtg_bbref;def_rtg_bbref;net_rtg_bbref;pace_bbref;arena_name",
                     "quality_notes": "Source-defined metrics; see Basketball-Reference glossary. SOS/SRS are rating-based (points per game vs. average).",
                     "verification_status": "single_source"})
        prov.append({**base, "variables": "playoff_series_won;playoff_series_lost;playoff_game_wins;playoff_game_losses;playoff_round_reached;champion;finalist",
                     "value_origin": "calculated", "calculation_definition": "Aggregated from the season page Playoff Series table (series winner, loser and series score).",
                     "verification_status": "single_source"})
        if espn_url:
            prov.append({"league": "WNBA", "team_id": rec["team_id"], "season": str(season), "dataset": "team_season_data",
                         "variables": "home_wins;home_losses;away_wins;away_losses;playoff_seed_espn",
                         "source_organization": "ESPN (public site API)", "source_url": espn_url,
                         "retrieval_timestamp_utc": espn_retrieved, "value_origin": "direct",
                         "quality_notes": "Unofficial public API; used for splits and as a W/L cross-check.",
                         "verification_status": "single_source"})
    return rows, series, checks, prov


# ===========================================================================
# PWHL
# ===========================================================================
def build_pwhl_games(s: dict, refresh: bool) -> tuple[pd.DataFrame, str, str]:
    sched, res = fastrhockey_parquet("schedules", s["fastrhockey_season"], refresh)
    info, _ = fastrhockey_parquet("game_info", s["fastrhockey_season"], refresh)
    g = sched[["game_id", "game_type", "game_status", "home_team_id", "away_team_id", "home_score", "away_score"]].copy()
    g = g.merge(info[["game_id", "game_date_iso", "game_status", "has_shootout", "attendance", "game_venue"]]
                .rename(columns={"game_status": "info_status"}), on="game_id", how="left")
    g["home_score"] = pd.to_numeric(g["home_score"], errors="coerce")
    g["away_score"] = pd.to_numeric(g["away_score"], errors="coerce")
    st = g["game_status"].fillna("").str.upper()
    g["decided_in"] = np.where(st.str.contains("SO") | (g["has_shootout"] == 1), "SO",
                               np.where(st.str.contains("OT"), "OT", "REG"))
    g["is_final"] = st.str.startswith("FINAL")
    g["game_date"] = pd.to_datetime(g["game_date_iso"].str[:10], errors="coerce")
    g.insert(0, "league", "PWHL")
    g.insert(1, "season", s["season"])
    g["home_team_id"] = g["home_team_id"].map(lambda x: franchise_by_source_id("PWHL", x))
    g["away_team_id"] = g["away_team_id"].map(lambda x: franchise_by_source_id("PWHL", x))
    if g[["home_team_id", "away_team_id"]].isna().any().any():
        raise ValueError(f"Unmapped PWHL team ids in {s['season']}")
    return g, res.url, res.retrieved_at_utc


def pwhl_team_rows(g: pd.DataFrame, s: dict) -> list[dict]:
    reg = g[(g.game_type == "regular") & g.is_final]
    long = []
    for side, opp in (("home", "away"), ("away", "home")):
        d = pd.DataFrame({"team_id": reg[f"{side}_team_id"], "gf": reg[f"{side}_score"], "ga": reg[f"{opp}_score"],
                          "decided_in": reg["decided_in"], "venue_side": side, "game_date": reg["game_date"]})
        long.append(d)
    L = pd.concat(long)
    L["win"] = L.gf > L.ga
    rows = []
    for tid, d in L.groupby("team_id"):
        rw = int(((d.decided_in == "REG") & d.win).sum())
        otw = int(((d.decided_in == "OT") & d.win).sum())
        sow = int(((d.decided_in == "SO") & d.win).sum())
        rl = int(((d.decided_in == "REG") & ~d.win).sum())
        otl = int(((d.decided_in == "OT") & ~d.win).sum())
        sol = int(((d.decided_in == "SO") & ~d.win).sum())
        gp = len(d)
        pts = (settings.PWHL_POINTS["reg_win"] * rw + settings.PWHL_POINTS["ot_so_win"] * (otw + sow)
               + settings.PWHL_POINTS["ot_so_loss"] * (otl + sol))
        h, a = d[d.venue_side == "home"], d[d.venue_side == "away"]
        rec = {**pwhl_season_meta(s), "team_id": tid, "games_played": gp,
               "wins": rw + otw + sow, "losses": rl, "overtime_losses": otl + sol,
               "regulation_wins": rw, "ot_wins": otw, "so_wins": sow, "ot_losses": otl, "so_losses": sol,
               "points": pts, "goals_for": int(d.gf.sum()), "goals_against": int(d.ga.sum()),
               "home_wins": int(h.win.sum()), "home_losses": int(((h.decided_in == "REG") & ~h.win).sum()),
               "home_overtime_losses": int(((h.decided_in != "REG") & ~h.win).sum()),
               "away_wins": int(a.win.sum()), "away_losses": int(((a.decided_in == "REG") & ~a.win).sum()),
               "away_overtime_losses": int(((a.decided_in != "REG") & ~a.win).sum()),
               "first_regular_season_game_date": d.game_date.min().date().isoformat(),
               "last_regular_season_game_date": d.game_date.max().date().isoformat(),
               "source_season_label": s["source_season_label"]}
        rows.append(rec)
    return rows


def series_from_games(g: pd.DataFrame, league: str, season: str) -> list[dict]:
    p = g[(g.game_type != "regular") & g.is_final].copy()
    if p.empty:
        return []
    p["pair"] = p.apply(lambda r: tuple(sorted([r.home_team_id, r.away_team_id])), axis=1)
    p["winner"] = np.where(p.home_score > p.away_score, p.home_team_id, p.away_team_id)
    out = []
    for pair, d in p.groupby("pair"):
        wins = d.winner.value_counts()
        a, b = pair
        wa, wb = int(wins.get(a, 0)), int(wins.get(b, 0))
        win, lose = (a, b) if wa > wb else (b, a)
        out.append({"league": league, "season": season, "winner_id": win, "loser_id": lose,
                    "winner_games": max(wa, wb), "loser_games": min(wa, wb), "start_date": d.game_date.min()})
    # round number = position of the series in each team's own playoff sequence
    for r in out:
        seq_w = sorted([x["start_date"] for x in out if r["winner_id"] in (x["winner_id"], x["loser_id"])])
        r["round_number"] = seq_w.index(r["start_date"]) + 1
    max_round = max(r["round_number"] for r in out)
    for r in out:
        r["is_final"] = r["round_number"] == max_round
        r["round_label"] = "Final" if r["is_final"] else ("Semifinal" if r["round_number"] == max_round - 1 else f"Round {r['round_number']}")
        r["start_date"] = r["start_date"].date().isoformat()
    return out


def pwhl_wiki_crosscheck(s: dict, rows: list[dict], refresh: bool) -> tuple[list[dict], dict | None]:
    page = wiki_page(s["wikipedia_page"], refresh)
    if page is None:
        return [], None
    checks = []
    by_id = {r["team_id"]: r for r in rows}
    for tb in page.soup.find_all("table", class_="wikitable"):
        txt = grid_text(wikitable_grid(tb))
        h = find_header_row(txt, ("Pos", "Team", "Pld", "W", "OTW", "OTL", "L", "GF", "GA"))
        if h is None:
            continue
        cols = txt[h]
        for r in txt[h + 1:]:
            if len(r) < len(cols):
                continue
            rec = dict(zip(cols, r))
            team_name = re.sub(r"\s*\((?:[A-Z]|[a-z])\)\s*$", "", rec.get("Team v t e", rec.get("Team", ""))).replace("v t e", "").strip()
            team_name = re.sub(r"\s*\([A-Za-z]\)", "", team_name).strip()
            fid = resolve_team("PWHL", team_name)
            if fid not in by_id:
                continue
            ours = by_id[fid]
            checks.append({"league": "PWHL", "season": s["season"], "team_id": fid,
                           "source_a": "fastRhockey (HockeyTech-derived), calculated", "source_b": f"Wikipedia rev {page.revid}",
                           "wins_a": ours["regulation_wins"], "wins_b": to_num(rec.get("W")),
                           "otw_a": ours["ot_wins"] + ours["so_wins"], "otw_b": to_num(rec.get("OTW")),
                           "otl_a": ours["overtime_losses"], "otl_b": to_num(rec.get("OTL")),
                           "losses_a": ours["losses"], "losses_b": to_num(rec.get("L")),
                           "scored_a": ours["goals_for"], "scored_b": to_num(rec.get("GF")),
                           "allowed_a": ours["goals_against"], "allowed_b": to_num(rec.get("GA")),
                           "points_a": ours["points"], "points_b": to_num(re.sub(r"\D", "", rec.get("Pts", "")))})
        break  # first standings table is the overall standings
    return checks, {"url": page.permalink, "retrieved": page.retrieved_at_utc}


# ===========================================================================
# Shared post-processing
# ===========================================================================
def add_playoff_fields(df: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    if series.empty:
        return df
    recs = []
    for (lg, ssn), d in series.groupby(["league", "season"]):
        teams = set(d.winner_id) | set(d.loser_id)
        for t in teams:
            w = d[d.winner_id == t]
            l = d[d.loser_id == t]
            recs.append({"league": lg, "season": ssn, "team_id": t,
                         "playoff_appearance": True,
                         "playoff_series_won": len(w), "playoff_series_lost": len(l),
                         "playoff_game_wins": int(w.winner_games.sum() + l.loser_games.sum()),
                         "playoff_game_losses": int(w.loser_games.sum() + l.winner_games.sum()),
                         "playoff_round_reached": int(pd.concat([w.round_number, l.round_number]).max()),
                         "playoff_round_reached_label": pd.concat([w, l]).sort_values("round_number").round_label.iloc[-1],
                         "finalist": bool(pd.concat([w, l]).is_final.any()),
                         "champion": bool(w.is_final.any())})
    pf = pd.DataFrame(recs)
    df = df.merge(pf, on=["league", "season", "team_id"], how="left")
    # Teams in a completed season with no series did not appear in the playoffs.
    seasons_with_series = set(map(tuple, series[["league", "season"]].drop_duplicates().values.tolist()))
    in_scope = df[["league", "season"]].apply(tuple, axis=1).isin(seasons_with_series)
    for c, v in (("playoff_appearance", False), ("playoff_series_won", 0), ("playoff_series_lost", 0),
                 ("playoff_game_wins", 0), ("playoff_game_losses", 0), ("playoff_round_reached", 0),
                 ("finalist", False), ("champion", False)):
        df.loc[in_scope & df[c].isna(), c] = v
    df.loc[in_scope & df["playoff_round_reached_label"].isna(), "playoff_round_reached_label"] = "did_not_qualify"
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_order"] = df["season_start_year"].astype(int)
    out = []
    for lg, d in df.groupby("league"):
        seasons = sorted(d["_order"].unique())
        idx = {y: i for i, y in enumerate(seasons)}
        d = d.copy()
        d["_si"] = d["_order"].map(idx)
        for tid, t in d.groupby("team_id"):
            t = t.sort_values("_si").copy()
            by_si = t.set_index("_si")
            for metric in (["win_percentage"] + (["points_percentage"] if lg == "PWHL" else [])):
                prior, roll, pooled = [], [], []
                for si in t["_si"]:
                    p1 = by_si[metric].get(si - 1)
                    prior.append(p1)
                    window = [si, si - 1, si - 2]
                    if all(w in by_si.index for w in window):
                        roll.append(float(np.mean([by_si[metric][w] for w in window])))
                        if metric == "win_percentage":
                            pooled.append(float(sum(by_si["wins"][w] for w in window) / sum(by_si["games_played"][w] for w in window)))
                        else:
                            pooled.append(float(sum(by_si["points"][w] for w in window) / sum(3 * by_si["games_played"][w] for w in window)))
                    else:
                        roll.append(None)
                        pooled.append(None)
                base = metric.replace("_percentage", "_pct")
                t[f"prior_season_{base}"] = prior
                t[f"{base}_change_yoy"] = t[metric] - pd.to_numeric(pd.Series(prior, index=t.index), errors="coerce")
                t[f"{base}_rolling3_mean"] = roll
                t[f"{base}_3season_pooled"] = pooled
            diff_col = "point_differential_per_game" if lg == "WNBA" else "goal_differential_per_game"
            t[f"prior_season_{diff_col}"] = [by_si[diff_col].get(si - 1) for si in t["_si"]]
            out.append(t)
    res = pd.concat(out).drop(columns=["_order", "_si"])
    return res


COLUMN_ORDER = [
    "league", "season", "season_start_year", "season_end_year", "in_core_scope", "source_season_label",
    "team_id", "team_name", "team_abbr_source", "conference",
    "games_played", "wins", "losses", "ties", "overtime_losses", "regulation_wins", "ot_wins", "so_wins",
    "ot_losses", "so_losses", "win_percentage", "win_percentage_definition", "points", "points_percentage",
    "points_for", "points_against", "point_differential", "points_for_per_game", "points_against_per_game",
    "point_differential_per_game", "goals_for", "goals_against", "goal_differential", "goal_differential_per_game",
    "home_wins", "home_losses", "home_overtime_losses", "away_wins", "away_losses", "away_overtime_losses",
    "mov_bbref", "sos_bbref", "srs_bbref", "pythag_wins_bbref", "pythag_losses_bbref", "off_rtg_bbref",
    "def_rtg_bbref", "net_rtg_bbref", "pace_bbref", "team_avg_age_bbref", "arena_name",
    "playoff_qualified", "playoff_seed_espn", "playoff_appearance", "playoff_series_won", "playoff_series_lost",
    "playoff_game_wins", "playoff_game_losses", "playoff_round_reached", "playoff_round_reached_label",
    "finalist", "champion",
    "prior_season_win_pct", "win_pct_change_yoy", "win_pct_rolling3_mean", "win_pct_3season_pooled",
    "prior_season_points_pct", "points_pct_change_yoy", "points_pct_rolling3_mean", "points_pct_3season_pooled",
    "prior_season_point_differential_per_game", "prior_season_goal_differential_per_game",
    "first_regular_season_game_date", "last_regular_season_game_date",
]


def main() -> None:
    args = base_argparser(__doc__.splitlines()[0]).parse_args()
    team_rows, series_rows, checks, prov = [], [], [], []
    games_frames = []
    leagues = ["WNBA", "PWHL"] if args.league == "both" else [args.league]

    if "WNBA" in leagues:
        for season in settings.WNBA_CONTEXT_SEASONS + settings.WNBA_CORE_SEASONS:
            log.info("WNBA %s", season)
            r, s, c, p = collect_wnba_season(season, args.refresh)
            team_rows += r; series_rows += s; checks += c; prov += p

    if "PWHL" in leagues:
        commit = fastrhockey_commit(args.refresh)
        for s in settings.PWHL_SEASONS:
            log.info("PWHL %s", s["season"])
            g, url, retrieved = build_pwhl_games(s, args.refresh)
            games_frames.append(g)
            rows = pwhl_team_rows(g, s)
            names = {}
            team_box, _ = fastrhockey_parquet("team_box", s["fastrhockey_season"], args.refresh)
            for r_ in team_box[["team_id", "team", "team_abbr"]].drop_duplicates().itertuples():
                names[franchise_by_source_id("PWHL", r_.team_id)] = (r_.team, r_.team_abbr)
            for r in rows:
                r["team_name"], r["team_abbr_source"] = names.get(r["team_id"], (None, None))
            team_rows += rows
            series_rows += series_from_games(g, "PWHL", s["season"])
            c, wiki = pwhl_wiki_crosscheck(s, rows, args.refresh)
            checks += c
            for r in rows:
                base = {"league": "PWHL", "team_id": r["team_id"], "season": s["season"], "dataset": "team_season_data",
                        "source_organization": "sportsdataverse fastRhockey-pwhl-data (from PWHL/HockeyTech official stats)",
                        "source_url": url, "retrieval_timestamp_utc": retrieved,
                        "source_update_date": commit.get("date"),
                        "verification_status": "cross_checked_against_wikipedia" if wiki else "single_source"}
                prov.append({**base, "variables": "games_played;wins;losses;overtime_losses;regulation_wins;ot_wins;so_wins;ot_losses;so_losses;goals_for;goals_against;home_*;away_*",
                             "value_origin": "calculated",
                             "calculation_definition": "Aggregated from final regular-season game results (game_type == 'regular'); OT/SO from game_status / has_shootout.",
                             "quality_notes": f"fastRhockey data repo commit {commit.get('sha')}"})
                prov.append({**base, "variables": "points;points_percentage;win_percentage", "value_origin": "calculated",
                             "calculation_definition": "points = 3*RW + 2*(OTW+SOW) + 1*(OTL+SOL); points_percentage = points/(3*GP); win_percentage = (RW+OTW+SOW)/GP"})
                prov.append({**base, "variables": "playoff_*;champion;finalist", "value_origin": "calculated",
                             "calculation_definition": "Series reconstructed from playoff games (game_type == 'playoffs'): pair of teams, wins per team; round = order of series in each team's playoff run."})

    df = pd.DataFrame(team_rows)
    for c in ("points_for", "points_against", "points", "goals_for", "goals_against", "games_played", "wins"):
        if c not in df:
            df[c] = np.nan
    # ---- derived fields common to both leagues ---------------------------
    df["win_percentage"] = df["wins"] / df["games_played"]
    df["win_percentage_definition"] = np.where(
        df.league == "WNBA", "wins / games_played (regular season; no ties or overtime losses in basketball standings)",
        "(regulation + OT + SO wins) / games_played (regular season); OT/SO losses count as games played, not wins")
    is_w = df.league == "WNBA"
    df.loc[is_w, "point_differential"] = df.loc[is_w, "points_for"] - df.loc[is_w, "points_against"]
    for c in ("points_for", "points_against", "point_differential"):
        df.loc[is_w, f"{c}_per_game"] = df.loc[is_w, c] / df.loc[is_w, "games_played"]
    is_p = ~is_w
    if is_p.any():
        df.loc[is_p, "points_percentage"] = df.loc[is_p, "points"] / (3 * df.loc[is_p, "games_played"])
        df.loc[is_p, "goal_differential"] = df.loc[is_p, "goals_for"] - df.loc[is_p, "goals_against"]
        df.loc[is_p, "goal_differential_per_game"] = df.loc[is_p, "goal_differential"] / df.loc[is_p, "games_played"]
    if "goal_differential_per_game" not in df:
        df["goal_differential_per_game"] = np.nan
    if "point_differential_per_game" not in df:
        df["point_differential_per_game"] = np.nan
    df["ties"] = np.nan  # not applicable in either league (see data dictionary)
    series = pd.DataFrame(series_rows)
    df = add_playoff_fields(df, series)
    df = add_lag_features(df)
    for c in COLUMN_ORDER:
        if c not in df:
            df[c] = np.nan
    extra = [c for c in df.columns if c not in COLUMN_ORDER]
    df = df[COLUMN_ORDER + extra]

    scope = {"league": leagues}
    upsert_csv(df, settings.EXPORTS_DIR / "team_season_data.csv", TEAM_KEYS, replace_scope=scope)
    if not series.empty:
        series = series.rename(columns={"winner_id": "team_a_id", "loser_id": "team_b_id"})
        series["team_a_is_winner"] = True
        upsert_csv(series, settings.PROCESSED_DIR / "playoff_series.csv",
                   ["league", "season", "round_number", "team_a_id", "team_b_id"], replace_scope=scope)
    if games_frames:
        games = pd.concat(games_frames)
        upsert_csv(games, settings.PROCESSED_DIR / "pwhl_games.csv", ["league", "season", "game_id"])
    if checks:
        ck = pd.DataFrame(checks)
        diffs = []
        metrics = [c[:-2] for c in ck.columns if c.endswith("_a") and c != "source_a" and f"{c[:-2]}_b" in ck.columns]
        for _, r in ck.iterrows():
            bad = [m for m in metrics if pd.notna(r[f"{m}_a"]) and pd.notna(r[f"{m}_b"])
                   and abs(float(r[f"{m}_a"]) - float(r[f"{m}_b"])) > 1e-9]
            diffs.append(";".join(bad))
        ck["mismatched_fields"] = diffs
        ck["status"] = np.where(ck["mismatched_fields"] == "", "match", "mismatch")
        upsert_csv(ck, settings.PROCESSED_DIR / "team_record_crosschecks.csv", ["league", "season", "team_id", "source_b"],
                   replace_scope=scope)
        n_bad = (ck.status == "mismatch").sum()
        log.info("cross-checks: %d rows, %d mismatches", len(ck), n_bad)
    record_provenance(prov, SCRIPT)
    log.info("done: %d team-season rows", len(df))


if __name__ == "__main__":
    main()
