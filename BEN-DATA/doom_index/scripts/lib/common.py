"""Logging, CLI, name normalisation and team-ID resolution shared by all scripts."""
from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from typing import Optional

import pandas as pd

from config import settings


def setup_logging(script_name: str) -> logging.Logger:
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout),
                logging.FileHandler(settings.LOG_DIR / f"{script_name}_{stamp}.log", encoding="utf-8")]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)
    for noisy in ("urllib3", "pdfminer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(script_name)


def base_argparser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--refresh", action="store_true",
                   help="Ignore the raw cache and re-download every source (old copies are archived).")
    p.add_argument("--league", choices=["WNBA", "PWHL", "both"], default="both")
    return p


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------
def strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def norm_name(s: Optional[str]) -> str:
    """Lower-case, accent-free, punctuation-free key used for *matching only*."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = strip_accents(str(s)).lower()
    s = re.sub(r"\(.*?\)", " ", s)          # drop parentheticals e.g. '(C)' captain marks
    s = re.sub(r"[*#†‡^]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", " ", s)
    s = re.sub(r"[^a-z ]", " ", s.replace("-", " ").replace("'", "").replace("’", "").replace("`", ""))
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _player_alias_map() -> dict[tuple[str, str], str]:
    p = settings.CONFIG_DIR / "player_name_aliases.csv"
    if not p.exists():
        return {}
    al = pd.read_csv(p, dtype=str, keep_default_na=False)
    return {(r.league, norm_name(r.alias_name)): norm_name(r.canonical_name) for r in al.itertuples()}


def player_key(league: str, name: Optional[str]) -> str:
    """Normalised player-name key with documented alias substitution (config/player_name_aliases.csv)."""
    k = norm_name(name)
    return _player_alias_map().get((league, k), k)


def flip_last_first(s: str) -> str:
    """'Cooke, Zia' -> 'Zia Cooke'."""
    if "," in s:
        last, first = [x.strip() for x in s.split(",", 1)]
        return f"{first} {last}"
    return s


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def teams_table() -> pd.DataFrame:
    return pd.read_csv(settings.TEAMS_CSV, dtype=str, keep_default_na=False)


@lru_cache(maxsize=1)
def _alias_map() -> dict[tuple[str, str], str]:
    al = pd.read_csv(settings.TEAM_ALIASES_CSV, dtype=str, keep_default_na=False)
    out: dict[tuple[str, str], str] = {}
    for r in al.itertuples():
        out[(r.league, norm_name(r.alias))] = r.franchise_id
    for r in teams_table().itertuples():
        out[(r.league, norm_name(r.current_team_name))] = r.franchise_id
        out.setdefault((r.league, norm_name(r.abbr)), r.franchise_id)
    return out


def resolve_team(league: str, name: Optional[str]) -> Optional[str]:
    """Map a team name / city / alias to a stable franchise_id (or None)."""
    if not name:
        return None
    key = norm_name(str(name).replace("*", ""))
    amap = _alias_map()
    if (league, key) in amap:
        return amap[(league, key)]
    # tolerate trailing qualifiers like 'Las Vegas Aces (from Seattle)'
    key2 = norm_name(re.split(r"[(\[]", str(name))[0])
    return amap.get((league, key2))


def franchise_by_bbref(code: str) -> Optional[str]:
    t = teams_table()
    m = t[(t.league == "WNBA") & (t.bbref_code == code)]
    return m.franchise_id.iloc[0] if len(m) else None


def franchise_by_source_id(league: str, source_team_id) -> Optional[str]:
    t = teams_table()
    m = t[(t.league == league) & (t.source_team_id == str(source_team_id))]
    return m.franchise_id.iloc[0] if len(m) else None


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def to_num(x):
    """Convert source strings like '.422', '+9.4', '1,234', '' to float/None."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return None if pd.isna(x) else x
    s = str(x).strip().replace(",", "").replace("$", "").replace("−", "-").replace("–", "-")
    if s in ("", "-", "—", "N/A", "n/a"):
        return None
    if s.startswith("+"):
        s = s[1:]
    try:
        return float(s)
    except ValueError:
        return None


def age_on(birth: Optional[date], ref: Optional[date]) -> Optional[float]:
    if birth is None or ref is None or pd.isna(birth) or pd.isna(ref):
        return None
    return round((pd.Timestamp(ref) - pd.Timestamp(birth)).days / 365.2425, 3)


def wnba_season_meta(season: int) -> dict:
    return {
        "league": "WNBA",
        "season": str(season),
        "season_start_year": season,
        "season_end_year": season,
        "in_core_scope": season in settings.WNBA_CORE_SEASONS,
    }


def pwhl_season_meta(s: dict) -> dict:
    return {
        "league": "PWHL",
        "season": s["season"],
        "season_start_year": s["start_year"],
        "season_end_year": s["end_year"],
        "in_core_scope": True,
    }
