"""Central configuration for the WNBA + PWHL Team Doom Index data collection.

Everything that controls *what* is collected (leagues, seasons, sources,
throttling) lives here so the collection scripts stay declarative and
reproducible. Nothing in this file encodes a Doom Score weight or a
feature-importance assumption.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # untouched downloads / API responses (cache)
PROCESSED_DIR = DATA_DIR / "processed"  # parsed, source-specific intermediate tables
EXPORTS_DIR = DATA_DIR / "exports"      # the five normalised tables required by the brief
FINAL_DIR = DATA_DIR / "final"          # the two analysis-ready CSVs (one per league)
MANUAL_DIR = RAW_DIR / "manual"         # optional user-supplied files (see README)
LOG_DIR = ROOT / "logs"
DOCS_DIR = ROOT / "docs"

TEAMS_CSV = CONFIG_DIR / "teams.csv"
TEAM_ALIASES_CSV = CONFIG_DIR / "team_aliases.csv"
CBA_PARAMETERS_CSV = CONFIG_DIR / "cba_parameters.csv"

# ---------------------------------------------------------------------------
# HTTP behaviour
# ---------------------------------------------------------------------------
# Generic, non-identifying client name (no personal details are sent).
USER_AGENT = "doom-index-research/0.1 (academic sports data collection; python-requests)"
REQUEST_TIMEOUT = 45
MAX_RETRIES = 4
BACKOFF_SECONDS = 5.0
# Minimum seconds between requests, per source. Sports Reference publishes a
# crawl-delay of 3s and a 20 requests/minute limit, so we stay above both.
THROTTLE_SECONDS = {
    "bbref": 4.0,
    "espn": 1.0,
    "wikipedia": 2.5,
    "github": 0.5,
    "fastrhockey": 0.5,
    "pwhlpa": 2.0,
    "mendeley": 2.0,
    "default": 2.0,
}
# Cached raw responses are reused unless older than this (None = reuse forever
# until --refresh is passed). Completed seasons do not change, so the default is
# to reuse; "current" snapshot sources get a shorter max age.
CACHE_MAX_AGE_DAYS_HISTORICAL = None
CACHE_MAX_AGE_DAYS_CURRENT = 7

# ---------------------------------------------------------------------------
# Leagues and seasons
# ---------------------------------------------------------------------------
# WNBA seasons are single calendar years: season label "2024" means the 2024
# regular season + playoffs (May-October 2024).
WNBA_CORE_SEASONS = [2021, 2022, 2023, 2024, 2025, 2026]
# Context seasons are collected for TEAM records only, so that lagged features
# (prior-season win %, 3-season rolling averages) exist for 2021. They are
# flagged in_core_scope = False in every export.
WNBA_CONTEXT_SEASONS = [2019, 2020]
WNBA_LATEST_COMPLETED_SEASON = 2026

# Draft history years. Older drafts are included so that career-outcome
# measures exist for picks whose careers are largely complete; the 2027 draft
# is the next (future) draft and is handled as pick inventory.
WNBA_DRAFT_YEARS = list(range(2016, 2027))
WNBA_NEXT_DRAFT_YEAR = 2027

# PWHL seasons span two calendar years. Season label convention used in all
# exports: "YYYY-YY" with season_start_year = first calendar year in the label.
# The inaugural season is labelled "2023-24" (the league itself branded it the
# "2024 season"; its first regular-season game was 2024-01-01). The source
# label is retained in `source_season_label`.
# fastrhockey_season = the season END year used by the sportsdataverse files.
PWHL_SEASONS = [
    {"season": "2023-24", "start_year": 2023, "end_year": 2024, "fastrhockey_season": 2024,
     "source_season_label": "2024 Regular Season / 2024 Playoffs",
     "wikipedia_page": "2024 PWHL season", "status": "completed"},
    {"season": "2024-25", "start_year": 2024, "end_year": 2025, "fastrhockey_season": 2025,
     "source_season_label": "2024-25 Regular Season / 2025 Playoffs",
     "wikipedia_page": "2024–25 PWHL season", "status": "completed"},
    {"season": "2025-26", "start_year": 2025, "end_year": 2026, "fastrhockey_season": 2026,
     "source_season_label": "2025-26 Regular Season / 2026 Playoffs",
     "wikipedia_page": "2025–26 PWHL season", "status": "completed"},
]
PWHL_UPCOMING_SEASON = {"season": "2026-27", "start_year": 2026, "end_year": 2027,
                        "wikipedia_page": "2026–27 PWHL season", "status": "not_started"}
PWHL_LATEST_COMPLETED_SEASON = "2025-26"
PWHL_DRAFT_YEARS = [2023, 2024, 2025, 2026]

# PWHL standings points system (CBA / league rules since inaugural season):
# 3 points regulation win, 2 points overtime/shootout win, 1 point OT/SO loss.
PWHL_POINTS = {"reg_win": 3, "ot_so_win": 2, "ot_so_loss": 1, "reg_loss": 0}

# ---------------------------------------------------------------------------
# Source endpoints
# ---------------------------------------------------------------------------
BBREF_BASE = "https://www.basketball-reference.com"
ESPN_WNBA_STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
FASTRHOCKEY_RAW_BASE = "https://raw.githubusercontent.com/sportsdataverse/fastRhockey-pwhl-data/main/pwhl"
FASTRHOCKEY_REPO_URL = "https://github.com/sportsdataverse/fastRhockey-pwhl-data"
PWHLPA_SALARY_PAGE = "https://www.pwhlpa.com/salary-guide"

# Age convention: age in decimal years on the first regular-season game date of
# the league-season (computed from the collected schedule). Integer source ages
# (e.g. Basketball-Reference's season age) are kept separately.
AGE_REFERENCE_CONVENTION = "first_regular_season_game_date"
