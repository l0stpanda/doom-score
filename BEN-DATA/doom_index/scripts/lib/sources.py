"""Source-specific fetch helpers (one function per upstream resource type)."""
from __future__ import annotations

import io
import json
import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import quote

import pandas as pd
from bs4 import BeautifulSoup

from config import settings
from lib.http import Fetcher, FetchResult

log = logging.getLogger(__name__)

_fetchers: dict[tuple, Fetcher] = {}


def fetcher(source: str, refresh: bool = False, max_age_days: Optional[float] = None) -> Fetcher:
    key = (source, refresh, max_age_days)
    if key not in _fetchers:
        _fetchers[key] = Fetcher(source, refresh=refresh, max_age_days=max_age_days)
    return _fetchers[key]


# ---------------------------------------------------------------------------
# Basketball-Reference (Sports Reference LLC)
# ---------------------------------------------------------------------------
def bbref_page(path: str, refresh: bool = False, allow_404: bool = False) -> Optional[FetchResult]:
    url = settings.BBREF_BASE + path
    key = path.strip("/").replace("/", "__").replace(".html", "")
    return fetcher("bbref", refresh).get(url, cache_key=key, ext="html", allow_404=allow_404)


# ---------------------------------------------------------------------------
# ESPN public site API
# ---------------------------------------------------------------------------
def espn_wnba_standings(season: int, refresh: bool = False) -> FetchResult:
    return fetcher("espn", refresh).get(settings.ESPN_WNBA_STANDINGS, params={"season": season},
                                        cache_key=f"wnba_standings_{season}", ext="json")


# ---------------------------------------------------------------------------
# Wikipedia (MediaWiki action API, CC BY-SA content)
# ---------------------------------------------------------------------------
class WikiPage:
    def __init__(self, title: str, html: str, revid: int, retrieved_at_utc: str):
        self.title = title
        self.html = html
        self.revid = revid
        self.retrieved_at_utc = retrieved_at_utc
        self.soup = BeautifulSoup(html, "lxml")

    @property
    def permalink(self) -> str:
        return f"https://en.wikipedia.org/w/index.php?title={quote(self.title.replace(' ', '_'))}&oldid={self.revid}"


def wiki_page(title: str, refresh: bool = False, current: bool = False) -> Optional[WikiPage]:
    """Fetch the parsed HTML of a Wikipedia page. ``current`` pages expire after a week."""
    max_age = settings.CACHE_MAX_AGE_DAYS_CURRENT if current else None
    f = fetcher("wikipedia", refresh, max_age)
    res = f.get(settings.WIKIPEDIA_API,
                params={"action": "parse", "page": title, "prop": "text|revid", "format": "json",
                        "redirects": "1", "formatversion": "2"},
                cache_key=f"parse_{title}", ext="json")
    data = res.json()
    if "error" in data:
        log.warning("Wikipedia page %r unavailable: %s", title, data["error"].get("info"))
        return None
    p = data["parse"]
    return WikiPage(p["title"], p["text"], p["revid"], res.retrieved_at_utc)


# ---------------------------------------------------------------------------
# sportsdataverse fastRhockey PWHL data (MIT licence, GitHub)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def fastrhockey_commit(refresh: bool = False) -> dict:
    """Latest commit on the data repo, used as the source update date."""
    f = fetcher("github", refresh, settings.CACHE_MAX_AGE_DAYS_CURRENT)
    res = f.get("https://api.github.com/repos/sportsdataverse/fastRhockey-pwhl-data/commits/main",
                cache_key="fastrhockey_pwhl_data_commit_main", ext="json")
    d = res.json()
    return {"sha": d.get("sha"), "date": (d.get("commit") or {}).get("committer", {}).get("date"),
            "retrieved_at_utc": res.retrieved_at_utc}


def fastrhockey_parquet(dataset: str, season: int, refresh: bool = False) -> tuple[pd.DataFrame, FetchResult]:
    """Download one season file, e.g. dataset='skater_box' season=2026 (= 2025-26)."""
    names = {"schedules": f"schedules/parquet/pwhl_schedule_{season}.parquet"}
    rel = names.get(dataset, f"{dataset}/parquet/{dataset}_{season}.parquet")
    url = f"{settings.FASTRHOCKEY_RAW_BASE}/{rel}"
    res = fetcher("fastrhockey", refresh).get(url, cache_key=f"{dataset}_{season}", ext="parquet")
    return pd.read_parquet(io.BytesIO(res.content)), res
