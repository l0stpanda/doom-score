"""03 - Collect draft history, pick ownership/transactions, career outcomes and future pick inventory.

WHAT IT COLLECTS
    * draft_history.csv: one row per draft selection (entry drafts and
      expansion drafts), with the team that made the selection, the original
      owner of the pick, trade annotations, and raw career production.
    * draft_pick_inventory.csv: known FUTURE picks (next draft) with original
      owner vs. current rights holder and any trade/condition notes.
    * draft_pick_transactions.csv: draft-pick assets parsed from trade tables
      (PWHL) - raw text preserved.

LEAGUES / YEARS
    WNBA entry drafts 2016-2026 (+ 2027 as future inventory); WNBA expansion
         drafts 2024 (Golden State) and 2026 (Portland, Toronto).
    PWHL entry drafts 2023-2026; PWHL expansion processes 2025 (Seattle,
         Vancouver) and 2026 (Detroit, Hamilton, San Jose, Vegas).

SOURCES
    Wikipedia draft articles ("{YYYY} WNBA draft", "{YYYY} PWHL Draft",
      "{YYYY} WNBA expansion draft") via the MediaWiki API - pick order, team,
      "(from X)" ownership annotations and footnoted trade details. Each row
      stores the article's permanent revision URL.
    Basketball-Reference draft pages /wnba/draft/{YYYY}.html - player id and
      career WNBA totals (seasons, games, MP/G, PTS/G, TRB/G, AST/G, WS, WS/40).
    PWHL career outcomes are computed from this project's player_season_data.csv
      (regular-season games, goals, assists, points, TOI across PWHL seasons).

FIELDS / DERIVED
    pick_in_round          = rank of pick_overall within (draft, round)
    original_owner_team_id = team named in "(from X)" annotation, else the selecting team
    pick_traded_before_draft = original_owner_team_id != selecting_team_id
    rights_traded_after_selection_to = team in "(traded to Y)" annotation
    career_* (WNBA)        = Basketball-Reference career totals as of retrieval date
    career_* (PWHL)        = sums over collected PWHL seasons (2023-24..2025-26)
    No composite "career outcome" score is defined at this stage.

KNOWN LIMITATIONS
    * Ownership annotations and trade notes come from a crowd-edited source;
      they are stored verbatim alongside parsed fields.
    * Pick acquisition is only "own" vs "trade" (+ note text); compensation /
      forfeited picks are flagged only when the note text says so.
    * Future-pick inventory beyond the next draft is NOT collected (no
      reliable public table); PWHL 2027 picks only appear when a recorded trade
      mentions them - teams' remaining own picks are NOT assumed.
    * PWHL career matching is by normalised name (documented aliases) and is
      limited to PWHL games; pre-PWHL careers are not covered.
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
from lib.sources import bbref_page, wiki_page
from lib.store import record_provenance, upsert_csv
from lib.tables import bbref_rows, bbref_tables, clean_cell, wikitable_grid

SCRIPT = "03_collect_draft_data.py"
log = setup_logging("03_collect_draft_data")

ROUND_WORDS = {w: i + 1 for i, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split())}
ORDINALS = {w: i + 1 for i, w in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth".split())}


def round_from_heading(text: str | None):
    if not text:
        return None
    t = text.lower()
    m = re.search(r"round\s+(\d+)", t) or re.search(r"(\d+)(?:st|nd|rd|th)\s+round", t)
    if m:
        return int(m.group(1))
    for w, n in ROUND_WORDS.items():
        if re.search(rf"round\s+{w}\b", t):
            return n
    for w, n in ORDINALS.items():
        if re.search(rf"\b{w}\s+round", t):
            return n
    return None


def notes_for(cell, soup) -> list[str]:
    """Return text of explanatory footnotes (not bibliographic citations) linked from a cell."""
    out = []
    for a in cell.find_all("a", href=True):
        if not a["href"].startswith("#cite_note"):
            continue
        li = soup.find(id=a["href"][1:])
        if li is None:
            continue
        # Explanatory notes use letter labels ([a], [b]) or "Trade n"; numeric labels are citations.
        label = a.get_text(strip=True)
        is_note = bool(re.fullmatch(r"\[?\s*[a-z]{1,2}\s*\]?", label) or re.search(r"trade", label, re.I))
        if is_note:
            txt = clean_cell(li.get_text(" ", strip=True)).lstrip("^ ").strip()
            txt = re.sub(r"^(?:[a-z]\s+)+(?=[A-Z0-9])", "", txt)  # drop back-link letters 'a b 
            out.append(txt)
    return out


def parse_team_cell(text: str):
    """'Minnesota Lynx (from Chicago, traded to X)' -> (selector, original, traded_to, raw_paren)."""
    t = clean_cell(text)
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", t)
    if not m:
        return t.strip(), None, None, None
    team, paren = m.group(1).strip(), m.group(2)
    orig = traded = None
    for part in [p.strip() for p in re.split(r",|;", paren)]:
        fm = re.match(r"from\s+(.+?)(?:\s+via\s+.+)?$", part, re.I)
        tm = re.match(r"(?:rights\s+)?traded\s+to\s+(.+)$", part, re.I)
        if fm:
            orig = fm.group(1).strip()
        elif tm:
            traded = tm.group(1).strip()
    return team, orig, traded, paren


def clean_player(text: str):
    t = clean_cell(text)
    traded = None
    m = re.search(r"\((?:rights\s+)?traded\s+to\s+([^)]+)\)", t, re.I)
    if m:
        traded = m.group(1).strip()
        t = t.replace(m.group(0), "")
    pos = None
    pm = re.search(r"\(\s*([A-Z]{1,2}(?:/[A-Z]{1,2})?)\s*\)", t)
    if pm:
        pos = pm.group(1)
        t = t.replace(pm.group(0), "")
    t = re.sub(r"[*#^+!†‡]", "", t)
    t = re.sub(r"\s+x$", "", t.strip())  # trailing key marker used on some draft pages
    return re.sub(r"\s+", " ", t).strip(), pos, traded


# ---------------------------------------------------------------------------
# Generic Wikipedia draft table parser
# ---------------------------------------------------------------------------
def parse_selection_tables(page, league: str, draft_year: int, draft_type: str, default_team: str | None = None) -> list[dict]:
    rows = []
    soup = page.soup
    for tb in soup.find_all("table", class_="wikitable"):
        grid = wikitable_grid(tb)
        if not grid:
            continue
        hdr = [clean_cell(c.get_text(" ", strip=True)) if c is not None else "" for c in grid[0]]
        low = [h.lower() for h in hdr]
        pick_col = next((i for i, h in enumerate(low) if h in ("pick", "#", "no.", "number", "overall")), None)
        player_col = next((i for i, h in enumerate(low) if h == "player"), None)
        team_col = next((i for i, h in enumerate(low) if h in ("team", "pwhl team", "wnba team")), None)
        if pick_col is None or player_col is None or (team_col is None and default_team is None):
            continue
        rnd_col = next((i for i, h in enumerate(low) if h in ("rnd.", "round", "rnd")), None)
        nat_col = next((i for i, h in enumerate(low) if h.startswith("nationality")), None)
        sch_col = next((i for i, h in enumerate(low) if h.startswith("school")), None)
        pos_col = next((i for i, h in enumerate(low) if h in ("position", "pos.", "pos")), None)
        prev_col = next((i for i, h in enumerate(low) if h in ("former team", "previous team", "team drafted from")), None)
        heading = tb.find_previous(["h2", "h3", "h4"])
        heading_txt = heading.get_text(" ", strip=True) if heading else None
        rnd_heading = round_from_heading(heading_txt)
        for r in grid[1:]:
            if len(r) < len(hdr):
                continue
            pick = to_num(clean_cell(r[pick_col].get_text(" ", strip=True)))
            if pick is None:
                continue
            player, pos_in_name, traded_after = clean_player(r[player_col].get_text(" ", strip=True))
            team_txt = r[team_col].get_text(" ", strip=True) if team_col is not None else default_team
            sel, orig, traded_to, paren = parse_team_cell(team_txt)
            notes = (notes_for(r[team_col], soup) if team_col is not None else []) + notes_for(r[player_col], soup)
            rnd = to_num(clean_cell(r[rnd_col].get_text(" ", strip=True))) if rnd_col is not None else rnd_heading
            rec = {"league": league, "draft_year": draft_year, "draft_type": draft_type,
                   "draft_name": page.title, "draft_section": heading_txt,
                   "round": int(rnd) if rnd else None, "round_source": "column" if rnd_col is not None else ("heading" if rnd_heading else None),
                   "pick_overall": int(pick), "player_name": player or None,
                   "position": (clean_cell(r[pos_col].get_text(" ", strip=True)) if pos_col is not None else None) or pos_in_name,
                   "nationality": clean_cell(r[nat_col].get_text(" ", strip=True)) if nat_col is not None else None,
                   "school_or_club": clean_cell(r[sch_col].get_text(" ", strip=True)) if sch_col is not None else None,
                   "selecting_team_name_source": sel,
                   "selecting_team_id": resolve_team(league, sel),
                   "original_owner_name_source": orig,
                   "original_owner_team_id": resolve_team(league, orig) if orig else resolve_team(league, sel),
                   "rights_traded_after_selection_to": traded_after or traded_to,
                   "rights_traded_after_selection_to_id": resolve_team(league, traded_after or traded_to) if (traded_after or traded_to) else None,
                   "previous_team_name_source": clean_cell(r[prev_col].get_text(" ", strip=True)) if prev_col is not None else None,
                   "team_cell_raw": clean_cell(team_txt), "trade_note_text": " || ".join(notes) or None,
                   "source_url": page.permalink, "source_revision_id": page.revid,
                   "retrieved_at_utc": page.retrieved_at_utc}
            rows.append(rec)
    return rows


def parse_side_by_side(page, league: str, draft_year: int, draft_type: str, heading_filter: re.Pattern) -> list[dict]:
    """Tables laid out as Team A | Team B | ... with Player / Former team sub-columns."""
    out = []
    for tb in page.soup.find_all("table", class_="wikitable"):
        heading = tb.find_previous(["h2", "h3", "h4"])
        htxt = heading.get_text(" ", strip=True) if heading else ""
        grid = wikitable_grid(tb)
        if len(grid) < 3:
            continue
        top = [clean_cell(c.get_text(" ", strip=True)) if c is not None else "" for c in grid[0]]
        sub = [clean_cell(c.get_text(" ", strip=True)) if c is not None else "" for c in grid[1]]
        team_ids = [resolve_team(league, t) for t in top]
        has_pairs = sum(1 for s in sub if s.lower() == "player") >= 2 or (
            sum(1 for t in team_ids if t) >= 2 and sub and sub[0] and resolve_team(league, sub[0]) is None and "Player" not in top)
        if not (heading_filter.search(htxt) or heading_filter.search(" ".join(top))):
            continue
        if sum(1 for t in team_ids if t) < 2:
            continue
        data_rows = grid[2:] if any(s.lower() in ("player", "former team") for s in sub) else grid[1:]
        for k, r in enumerate(data_rows):
            for ci, tid in enumerate(team_ids):
                if not tid or ci >= len(r):
                    continue
                label = sub[ci].lower() if ci < len(sub) else "player"
                if label not in ("player", "") and label != top[ci].lower():
                    continue
                if ci > 0 and team_ids[ci - 1] == tid:   # second column of the same team (former team)
                    continue
                player, pos, _ = clean_player(r[ci].get_text(" ", strip=True))
                if not player:
                    continue
                prev = clean_cell(r[ci + 1].get_text(" ", strip=True)) if ci + 1 < len(r) and ci + 1 < len(team_ids) and team_ids[ci + 1] == tid else None
                out.append({"league": league, "draft_year": draft_year, "draft_type": draft_type, "draft_name": page.title,
                            "draft_section": htxt, "round": None, "pick_overall": None, "selection_seq": k + 1,
                            "player_name": player, "position": pos, "selecting_team_name_source": top[ci],
                            "selecting_team_id": tid, "original_owner_team_id": tid,
                            "previous_team_name_source": prev, "source_url": page.permalink,
                            "source_revision_id": page.revid, "retrieved_at_utc": page.retrieved_at_utc})
    return out


# ---------------------------------------------------------------------------
# Career outcomes
# ---------------------------------------------------------------------------
def wnba_bbref_careers(year: int, refresh: bool) -> tuple[pd.DataFrame, str, str]:
    res = bbref_page(f"/wnba/draft/{year}.html", refresh, allow_404=True)
    if res is None:
        return pd.DataFrame(), None, None
    T = bbref_tables(res.text)
    t = T.get("stats")
    if t is None:
        return pd.DataFrame(), res.url, res.retrieved_at_utc
    recs = []
    for r in bbref_rows(t):
        pick = to_num(r.get("pick_overall"))
        if pick is None:
            continue
        m = re.search(r"/wnba/players/./([a-z0-9]+)\.html", r.get("player_href") or "")
        recs.append({"pick_overall": int(pick), "bbref_player_name": r.get("player"),
                     "bbref_player_id": m.group(1) if m else None, "bbref_draft_team": r.get("team"),
                     "career_seasons": to_num(r.get("seasons")), "career_games": to_num(r.get("g")),
                     "career_minutes_per_game": to_num(r.get("mp_per_g")), "career_points_per_game": to_num(r.get("pts_per_g")),
                     "career_rebounds_per_game": to_num(r.get("trb_per_g")), "career_assists_per_game": to_num(r.get("ast_per_g")),
                     "career_win_shares": to_num(r.get("ws")), "career_ws_per_40": to_num(r.get("ws_per_40"))})
    return pd.DataFrame(recs), res.url, res.retrieved_at_utc


def pwhl_careers(players: pd.DataFrame) -> pd.DataFrame:
    p = players[players.league == "PWHL"].copy()
    p["name_key"] = [player_key("PWHL", n) for n in p.player_name]
    g = p.groupby("name_key").agg(
        pwhl_player_id=("player_id", lambda x: x.iloc[0] if x.nunique() == 1 else None),
        career_seasons=("season", lambda x: x[p.loc[x.index, "games_played"] > 0].nunique()),
        career_games=("games_played", "sum"), career_goals=("goals", "sum"), career_assists=("assists", "sum"),
        career_points=("points", "sum"), career_toi_total_min=("time_on_ice_total_min", "sum"),
        career_goalie_saves=("saves", "sum"), career_goalie_shots_against=("shots_against", "sum"),
        teams_played_for=("team_id", lambda x: ";".join(sorted(set(x.dropna())))))
    return g.reset_index()


# ---------------------------------------------------------------------------
# PWHL trade tables -> pick transactions
# ---------------------------------------------------------------------------
PICK_RE = re.compile(r"(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|\d+(?:st|nd|rd|th))[\s-]+round pick\s*[–-]\s*(\d{4}) PWHL Draft(?:\s*\(([^)]*)\))?", re.I)


def pwhl_trade_picks(page, season_label: str) -> list[dict]:
    out = []
    if page is None:
        return out
    h = page.soup.find(id="Trades")
    if h is None:
        return out
    tb = h.find_parent().find_next("table")
    grid = wikitable_grid(tb)
    last_date = None
    for r in grid[1:]:
        cells = [clean_cell(c.get_text("\n", strip=True)) if c is not None else "" for c in r]
        if not cells:
            continue
        if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$", cells[0]):
            last_date, parts = cells[0], cells[1:]
        else:
            parts = cells
        sides = [p for p in parts if p.startswith("To ")]
        teams_in_trade = []
        for sd in sides:
            m = re.match(r"To (.+?)(?:\n|$)", sd)
            teams_in_trade.append(m.group(1).strip() if m else None)
        for sd, recv in zip(sides, teams_in_trade):
            others = [t for t in teams_in_trade if t != recv]
            for pm in PICK_RE.finditer(sd.replace("\n", " ")):
                rnd_txt = pm.group(1).lower()
                rnd = ORDINALS.get(rnd_txt) or to_num(re.sub(r"\D", "", rnd_txt))
                note = pm.group(3)
                pick_no = to_num(re.search(r"#\s*(\d+)", note).group(1)) if note and re.search(r"#\s*(\d+)", note) else None
                out.append({"league": "PWHL", "season_of_transaction": season_label, "transaction_date": last_date,
                            "draft_year": int(pm.group(2)), "round": int(rnd) if rnd else None, "pick_overall": pick_no,
                            "pick_note": note, "receiving_team_name_source": recv,
                            "receiving_team_id": resolve_team("PWHL", recv),
                            "sending_team_name_source": others[0] if len(others) == 1 else ";".join(o for o in others if o),
                            "sending_team_id": resolve_team("PWHL", others[0]) if len(others) == 1 else None,
                            "trade_text": " | ".join(sides).replace("\n", " "),
                            "source_url": page.permalink, "retrieved_at_utc": page.retrieved_at_utc})
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    args = base_argparser(__doc__.splitlines()[0]).parse_args()
    leagues = ["WNBA", "PWHL"] if args.league == "both" else [args.league]
    hist, inv, ptx, prov = [], [], [], []
    players_path = settings.EXPORTS_DIR / "player_season_data.csv"
    players = pd.read_csv(players_path, dtype={"season": str}, low_memory=False) if players_path.exists() else pd.DataFrame()

    if "WNBA" in leagues:
        for year in settings.WNBA_DRAFT_YEARS + [settings.WNBA_NEXT_DRAFT_YEAR]:
            page = wiki_page(f"{year} WNBA draft", args.refresh, current=(year >= settings.WNBA_NEXT_DRAFT_YEAR))
            if page is None:
                continue
            rows = parse_selection_tables(page, "WNBA", year, "entry")
            log.info("WNBA %s draft: %d selections parsed", year, len(rows))
            if year >= settings.WNBA_NEXT_DRAFT_YEAR:
                for r in rows:
                    inv.append({"league": "WNBA", "draft_year": year, "round": r["round"], "pick_overall": r["pick_overall"],
                                "pick_slot_status": "assigned_per_source_revision",
                                "original_owner_team_id": r["original_owner_team_id"],
                                "original_owner_name_source": r["original_owner_name_source"] or r["selecting_team_name_source"],
                                "current_rights_holder_team_id": r["selecting_team_id"],
                                "current_rights_holder_name_source": r["selecting_team_name_source"],
                                "is_traded": r["original_owner_team_id"] != r["selecting_team_id"],
                                "conditional_or_protected_flag": bool(r["trade_note_text"] and re.search(r"protect|condition|swap", r["trade_note_text"], re.I)),
                                "trade_note_text": r["trade_note_text"], "team_cell_raw": r["team_cell_raw"],
                                "source_url": r["source_url"], "source_revision_id": r["source_revision_id"],
                                "snapshot_date": r["retrieved_at_utc"][:10]})
                prov.append({"league": "WNBA", "team_id": "", "season": str(year), "dataset": "draft_pick_inventory",
                             "variables": "pick order; original owner; current rights holder; trade notes",
                             "source_organization": "Wikipedia (crowd-edited)", "source_url": page.permalink,
                             "retrieval_timestamp_utc": page.retrieved_at_utc, "value_origin": "direct",
                             "verification_status": "secondary_unverified",
                             "quality_notes": "Future draft order as shown on the article revision; verify against WNBA.com before relying on it."})
                continue
            car, burl, bret = wnba_bbref_careers(year, args.refresh)
            if not car.empty:
                cmap = car.set_index("pick_overall")
                for r in rows:
                    c = cmap.loc[r["pick_overall"]] if r["pick_overall"] in cmap.index else None
                    if c is None:
                        r["career_match_status"] = "no_bbref_row"
                        continue
                    r.update({k: c[k] for k in car.columns if k != "pick_overall"})
                    r["player_id"] = c["bbref_player_id"]
                    same = player_key("WNBA", c["bbref_player_name"]) == player_key("WNBA", r["player_name"])
                    r["career_match_status"] = "matched_pick_and_name" if same else "matched_pick_name_differs"
                    r["career_stats_source_url"] = burl
                    r["career_stats_as_of"] = bret
            hist += rows
            prov.append({"league": "WNBA", "team_id": "", "season": str(year), "dataset": "draft_history",
                         "variables": "round;pick;player;team;original owner;trade notes", "source_organization": "Wikipedia (crowd-edited)",
                         "source_url": page.permalink, "retrieval_timestamp_utc": page.retrieved_at_utc,
                         "value_origin": "direct", "verification_status": "cross_checked_pick_and_name_against_bbref" if not car.empty else "secondary_unverified"})
            if burl:
                prov.append({"league": "WNBA", "team_id": "", "season": str(year), "dataset": "draft_history",
                             "variables": "career_* (seasons, games, per-game, win shares)",
                             "source_organization": "Sports Reference LLC (Basketball-Reference)", "source_url": burl,
                             "retrieval_timestamp_utc": bret, "value_origin": "direct",
                             "quality_notes": "Career totals as of retrieval; change as careers continue.",
                             "verification_status": "single_source"})
        for year, title, default in ((2024, "2024 WNBA expansion draft", "Golden State Valkyries"),
                                     (2026, "2026 WNBA expansion draft", None)):
            page = wiki_page(title, args.refresh)
            if page is None:
                continue
            rows = parse_selection_tables(page, "WNBA", year, "expansion", default_team=default)
            for r in rows:
                r["original_owner_team_id"] = resolve_team("WNBA", r.get("previous_team_name_source"))
                r["acquisition_note"] = "expansion draft: player selected from previous team's unprotected list"
            log.info("%s: %d selections", title, len(rows))
            hist += rows
            prov.append({"league": "WNBA", "team_id": "", "season": str(year), "dataset": "draft_history",
                         "variables": "expansion draft selections", "source_organization": "Wikipedia (crowd-edited)",
                         "source_url": page.permalink, "retrieval_timestamp_utc": page.retrieved_at_utc,
                         "value_origin": "direct", "verification_status": "secondary_unverified"})

    if "PWHL" in leagues:
        careers = pwhl_careers(players) if not players.empty else pd.DataFrame()
        n_teams = {2023: 6, 2024: 6, 2025: 8, 2026: 12}
        for year in settings.PWHL_DRAFT_YEARS:
            page = wiki_page(f"{year} PWHL Draft", args.refresh)
            if page is None:
                continue
            rows = parse_selection_tables(page, "PWHL", year, "entry")
            exp_rows = [r for r in rows if re.search(r"expansion", r["draft_section"] or "", re.I)]
            for r in rows:
                if r in exp_rows:
                    r["draft_type"] = "expansion"
                    r["original_owner_team_id"] = resolve_team("PWHL", r.get("previous_team_name_source"))
                elif r["round"] is None and r["pick_overall"]:
                    r["round"] = int((r["pick_overall"] - 1) // n_teams[year] + 1)
                    r["round_source"] = f"inferred_from_pick_and_{n_teams[year]}_teams"
            side = parse_side_by_side(page, "PWHL", year, "expansion_signing_or_selection",
                                      re.compile(r"signed players|expansion", re.I))
            for r in side:
                r["original_owner_team_id"] = resolve_team("PWHL", r.get("previous_team_name_source"))
            log.info("PWHL %s draft: %d entry/expansion rows, %d side-by-side expansion rows", year, len(rows), len(side))
            hist += rows + side
            prov.append({"league": "PWHL", "team_id": "", "season": str(year), "dataset": "draft_history",
                         "variables": "round;pick;player;team;original owner;expansion selections/signings",
                         "source_organization": "Wikipedia (crowd-edited)", "source_url": page.permalink,
                         "retrieval_timestamp_utc": page.retrieved_at_utc, "value_origin": "direct",
                         "verification_status": "secondary_unverified"})
        for s in settings.PWHL_SEASONS + [settings.PWHL_UPCOMING_SEASON]:
            page = wiki_page(s["wikipedia_page"], args.refresh, current=s["season"] == settings.PWHL_UPCOMING_SEASON["season"])
            ptx += pwhl_trade_picks(page, s["season"])
        nxt = max(settings.PWHL_DRAFT_YEARS) + 1
        nxt_page = wiki_page(f"{nxt} PWHL Draft", args.refresh, current=True)
        if nxt_page is None:
            log.info("no %s PWHL Draft article; future PWHL inventory limited to traded picks", nxt)
        for t in ptx:
            if t["draft_year"] >= nxt:
                inv.append({"league": "PWHL", "draft_year": t["draft_year"], "round": t["round"], "pick_overall": t["pick_overall"],
                            "pick_slot_status": "unknown_not_yet_determined",
                            "original_owner_team_id": t["sending_team_id"], "original_owner_name_source": t["sending_team_name_source"],
                            "original_owner_basis": "assumed to be the sending team's own pick unless trade text says otherwise",
                            "current_rights_holder_team_id": t["receiving_team_id"],
                            "current_rights_holder_name_source": t["receiving_team_name_source"], "is_traded": True,
                            "conditional_or_protected_flag": bool(re.search(r"protect|condition", t["trade_text"], re.I)),
                            "trade_note_text": t["trade_text"], "source_url": t["source_url"],
                            "snapshot_date": t["retrieved_at_utc"][:10]})
        if not careers.empty:
            cmap = careers.set_index("name_key")
            last_completed_end = max(s["end_year"] for s in settings.PWHL_SEASONS)
            for r in hist:
                if r["league"] != "PWHL":
                    continue
                k = player_key("PWHL", r["player_name"])
                if r["draft_year"] >= last_completed_end and r["draft_type"] == "entry":
                    r["career_match_status"] = "drafted_after_last_completed_season"
                    continue
                if k in cmap.index:
                    c = cmap.loc[k]
                    r.update({col: c[col] for col in careers.columns if col not in ("name_key", "pwhl_player_id")})
                    r["player_id"] = c["pwhl_player_id"]
                    r["career_match_status"] = "matched_by_name"
                    r["career_stats_source_url"] = "derived: data/exports/player_season_data.csv (PWHL regular season)"
                else:
                    r["career_match_status"] = "no_pwhl_games_found"

    df = pd.DataFrame(hist)
    if not df.empty:
        if "selection_seq" not in df:
            df["selection_seq"] = np.nan
        df["selection_key"] = [f"{t}-{int(p)}" if pd.notna(p) else f"{t}-{tm}-{int(s)}"
                               for t, p, tm, s in zip(df.draft_type, df.pick_overall, df.selecting_team_id, df.selection_seq.fillna(0))]
        df = df.drop_duplicates(["league", "draft_year", "selection_key"], keep="first")
        df["pick_in_round"] = df.groupby(["league", "draft_year", "draft_type", "round"])["pick_overall"].rank(method="first")
        traded = (df.original_owner_team_id.fillna("?") != df.selecting_team_id.fillna("?"))
        is_entry = df.draft_type == "entry"
        df["pick_traded_before_draft"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
        df.loc[is_entry, "pick_traded_before_draft"] = traded[is_entry]
        tr = df.pick_traded_before_draft.fillna(False).astype(bool)
        df["acquisition_method"] = np.where(~is_entry, df.draft_type, np.where(tr, "trade", "own"))
        df.loc[is_entry & df.trade_note_text.fillna("").str.contains("compensat", case=False), "acquisition_method"] = "compensation_or_trade_see_note"
        df["traded_from_team_id"] = df.original_owner_team_id.where(tr)
        df["traded_to_team_id"] = df.selecting_team_id.where(tr)
        first = ["league", "draft_year", "draft_type", "draft_name", "selection_key", "round", "round_source",
                 "pick_overall", "pick_in_round", "player_name", "player_id", "position", "nationality", "school_or_club",
                 "selecting_team_id", "selecting_team_name_source", "original_owner_team_id", "original_owner_name_source",
                 "pick_traded_before_draft", "acquisition_method", "traded_from_team_id", "traded_to_team_id",
                 "rights_traded_after_selection_to", "rights_traded_after_selection_to_id", "previous_team_name_source",
                 "trade_note_text", "team_cell_raw"]
        df = df[[c for c in first if c in df] + [c for c in df.columns if c not in first]]
        unresolved = df[df.selecting_team_id.isna()]
        if len(unresolved):
            log.warning("%d selections with unresolved team names: %s", len(unresolved),
                        unresolved.selecting_team_name_source.unique()[:10])
        upsert_csv(df, settings.EXPORTS_DIR / "draft_history.csv", ["league", "draft_year", "selection_key"],
                   replace_scope={"league": leagues})
    if inv:
        idf = pd.DataFrame(inv)
        idf["inventory_key"] = [f"{y}-{r}-{p if pd.notna(p) else 'na'}-{h}-{o}" for y, r, p, h, o in
                                zip(idf.draft_year, idf["round"], idf.pick_overall, idf.current_rights_holder_team_id, idf.original_owner_team_id)]
        idf = idf.drop_duplicates(["league", "inventory_key"])
        upsert_csv(idf, settings.EXPORTS_DIR / "draft_pick_inventory.csv", ["league", "inventory_key"], replace_scope={"league": leagues})
    if ptx:
        pdf = pd.DataFrame(ptx)
        pdf["tx_key"] = [f"{d}-{y}-{r}-{rc}-{i}" for i, (d, y, r, rc) in enumerate(zip(pdf.transaction_date, pdf.draft_year, pdf["round"], pdf.receiving_team_id))]
        upsert_csv(pdf, settings.PROCESSED_DIR / "draft_pick_transactions.csv", ["league", "tx_key"], replace_scope={"league": ["PWHL"]})
    record_provenance(prov, SCRIPT)
    log.info("done: %d draft rows, %d future-pick rows, %d pick transactions", len(df), len(inv), len(ptx))


if __name__ == "__main__":
    main()
