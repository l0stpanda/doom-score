"""Polite, cached, retrying HTTP fetcher.

Every response is written unchanged to ``data/raw/<source>/`` together with a
``.meta.json`` sidecar recording the URL, query parameters, HTTP status,
retrieval timestamp (UTC), ``Last-Modified`` header (when the server sends it)
and a SHA-256 of the body. Re-runs reuse the cached body unless it is older
than ``max_age_days`` or ``refresh=True``; when a cached file is refreshed the
previous copy is moved to ``_archive/`` instead of being overwritten.

This module never sends credentials, cookies or personal details and does not
attempt to evade access controls: a 401/403 is logged and surfaced as a
failure so the caller can record the source as inaccessible.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import settings

log = logging.getLogger(__name__)

_last_request_at: dict[str, float] = {}


class FetchError(RuntimeError):
    """Raised when a resource cannot be retrieved (after retries) or access is denied."""


@dataclass
class FetchResult:
    url: str
    content: bytes
    retrieved_at_utc: str
    from_cache: bool
    status: int
    path: Path
    last_modified: Optional[str] = None

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content.decode("utf-8"))


def _safe_name(key: str) -> str:
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")
    return key[:150] or "resource"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Fetcher:
    def __init__(self, source: str, refresh: bool = False, max_age_days: Optional[float] = None):
        self.source = source
        self.refresh = refresh
        self.max_age_days = max_age_days
        self.cache_dir = settings.RAW_DIR / source
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = settings.THROTTLE_SECONDS.get(source, settings.THROTTLE_SECONDS["default"])
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.USER_AGENT, "Accept-Encoding": "gzip, deflate"})

    # -- cache helpers -------------------------------------------------------
    def _paths(self, cache_key: str, ext: str) -> tuple[Path, Path]:
        name = _safe_name(cache_key)
        body = self.cache_dir / f"{name}.{ext}"
        meta = self.cache_dir / f"{name}.{ext}.meta.json"
        return body, meta

    def _cache_valid(self, body: Path, meta: Path) -> bool:
        if self.refresh or not body.exists() or not meta.exists():
            return False
        if self.max_age_days is None:
            return True
        age_days = (time.time() - body.stat().st_mtime) / 86400
        return age_days <= self.max_age_days

    def _archive(self, body: Path, meta: Path) -> None:
        if not body.exists():
            return
        stamp = datetime.fromtimestamp(body.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        arch = self.cache_dir / "_archive"
        arch.mkdir(exist_ok=True)
        shutil.move(str(body), str(arch / f"{stamp}__{body.name}"))
        if meta.exists():
            shutil.move(str(meta), str(arch / f"{stamp}__{meta.name}"))

    def _throttle(self) -> None:
        last = _last_request_at.get(self.source)
        if last is not None:
            wait = self.min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        _last_request_at[self.source] = time.monotonic()

    # -- public API ----------------------------------------------------------
    def get(self, url: str, params: Optional[dict] = None, cache_key: Optional[str] = None,
            ext: str = "html", allow_404: bool = False) -> Optional[FetchResult]:
        """Fetch ``url`` (with optional query ``params``) using the raw cache.

        Returns ``None`` for a 404 when ``allow_404`` is set; raises
        :class:`FetchError` for access denials and exhausted retries.
        """
        if cache_key is None:
            digest = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:12]
            cache_key = f"{url.rstrip('/').split('/')[-1]}_{digest}"
        body_path, meta_path = self._paths(cache_key, ext)

        if self._cache_valid(body_path, meta_path):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("status") == 404:
                return None
            return FetchResult(url=meta["url"], content=body_path.read_bytes(),
                               retrieved_at_utc=meta["retrieved_at_utc"], from_cache=True,
                               status=meta["status"], path=body_path,
                               last_modified=meta.get("last_modified"))

        last_exc: Optional[Exception] = None
        for attempt in range(1, settings.MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=settings.REQUEST_TIMEOUT)
            except requests.RequestException as exc:  # network error -> retry
                last_exc = exc
                log.warning("[%s] attempt %d network error for %s: %s", self.source, attempt, url, exc)
                time.sleep(settings.BACKOFF_SECONDS * attempt)
                continue

            if resp.status_code in (401, 403):
                raise FetchError(f"Access denied ({resp.status_code}) for {resp.url}; not retrying or bypassing.")
            if resp.status_code == 404:
                if allow_404:
                    self._write(body_path, meta_path, resp, b"")
                    log.info("[%s] 404 (recorded) %s", self.source, resp.url)
                    return None
                raise FetchError(f"404 Not Found: {resp.url}")
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else settings.BACKOFF_SECONDS * attempt * 2
                log.warning("[%s] HTTP %d for %s; waiting %.0fs", self.source, resp.status_code, resp.url, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            retrieved = self._write(body_path, meta_path, resp, resp.content)
            log.info("[%s] fetched %s (%d bytes)", self.source, resp.url, len(resp.content))
            return FetchResult(url=resp.url, content=resp.content, retrieved_at_utc=retrieved,
                               from_cache=False, status=resp.status_code, path=body_path,
                               last_modified=resp.headers.get("Last-Modified"))
        raise FetchError(f"Failed to fetch {url} after {settings.MAX_RETRIES} attempts: {last_exc}")

    def _write(self, body_path: Path, meta_path: Path, resp: requests.Response, content: bytes) -> str:
        self._archive(body_path, meta_path)
        retrieved = utc_now_iso()
        body_path.write_bytes(content)
        meta = {
            "url": resp.url,
            "status": resp.status_code,
            "retrieved_at_utc": retrieved,
            "last_modified": resp.headers.get("Last-Modified"),
            "content_type": resp.headers.get("Content-Type"),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source": self.source,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return retrieved
