"""CSV persistence: idempotent upserts and the provenance (audit) table."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from config import settings

log = logging.getLogger(__name__)

PROVENANCE_PATH = settings.EXPORTS_DIR / "team_season_sources.csv"
PROVENANCE_COLUMNS = [
    "league", "team_id", "season", "dataset", "variables", "source_organization", "source_url",
    "retrieval_timestamp_utc", "source_update_date", "value_origin", "calculation_definition",
    "quality_notes", "verification_status", "collected_by_script",
]
PROVENANCE_KEYS = ["league", "team_id", "season", "dataset", "variables", "source_url"]


def upsert_csv(df: pd.DataFrame, path: Path, keys: list[str], replace_scope: Optional[dict] = None) -> pd.DataFrame:
    """Write ``df`` to ``path`` replacing existing rows with the same ``keys``.

    ``replace_scope`` (column -> value or list of values) drops *all* existing
    rows in that scope before merging, so that records which disappeared at the
    source do not linger (e.g. re-collecting one league's seasons).
    Raises if ``df`` itself contains duplicate keys.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dupes = df.duplicated(keys, keep=False)
    if dupes.any():
        sample = df.loc[dupes, keys].head(10).to_string()
        raise ValueError(f"Duplicate primary keys in new data for {path.name}:\n{sample}")
    if path.exists() and path.stat().st_size > 0:
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        if replace_scope:
            mask = pd.Series(True, index=old.index)
            for col, val in replace_scope.items():
                vals = val if isinstance(val, (list, tuple, set)) else [val]
                mask &= old[col].isin([str(v) for v in vals]) if col in old else False
            old = old[~mask]
        new_keys = set(map(tuple, df[keys].astype(str).values.tolist()))
        if len(old):
            old_keys = old[keys].astype(str).apply(tuple, axis=1)
            old = old[~old_keys.isin(new_keys)]
        combined = pd.concat([old, df.astype(object)], ignore_index=True, sort=False)
        # keep column order: new df's columns first, then any legacy columns
        cols = list(df.columns) + [c for c in combined.columns if c not in df.columns]
        combined = combined[cols]
    else:
        combined = df
    combined = combined.sort_values(keys, kind="stable").reset_index(drop=True)
    combined.to_csv(path, index=False)
    log.info("wrote %s (%d rows)", path, len(combined))
    return combined


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("wrote %s (%d rows)", path, len(df))


def record_provenance(rows: Iterable[dict], script: str) -> None:
    rows = list(rows)
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["collected_by_script"] = script
    for c in PROVENANCE_COLUMNS:
        if c not in df:
            df[c] = None
    df = df[PROVENANCE_COLUMNS].fillna("")
    df = df.drop_duplicates(PROVENANCE_KEYS, keep="last")
    upsert_csv(df, PROVENANCE_PATH, PROVENANCE_KEYS)
