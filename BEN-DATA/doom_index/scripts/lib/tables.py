"""HTML table parsing helpers.

* ``bbref_tables`` / ``bbref_rows``: Sports-Reference pages put many tables
  inside HTML comments; cells carry stable ``data-stat`` attributes that we use
  as column names (more robust than visible headers).
* ``wikitable_grid``: expands ``rowspan``/``colspan`` in Wikipedia tables into
  a rectangular grid so that each row has one value per column.
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup, Comment, Tag


# ---------------------------------------------------------------------------
# Sports-Reference
# ---------------------------------------------------------------------------
def bbref_tables(html: str) -> dict[str, Tag]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, Tag] = {}
    for t in soup.find_all("table"):
        if t.get("id"):
            out[t["id"]] = t
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        if "<table" in c:
            for t in BeautifulSoup(str(c), "lxml").find_all("table"):
                if t.get("id"):
                    out.setdefault(t["id"], t)
    return out


def bbref_rows(table: Tag, keep_links: tuple[str, ...] = ("player", "team", "team_name")) -> list[dict]:
    """Return tbody rows as dicts keyed by ``data-stat``.

    Header/separator rows (class ``thead``/``over_header``) are skipped but a
    ``_section`` key carries the most recent separator text (used for draft
    rounds). For keys in ``keep_links`` the href is stored as ``<key>_href``.
    """
    body = table.find("tbody") or table
    rows: list[dict] = []
    section: Optional[str] = None
    for tr in body.find_all("tr", recursive=False):
        classes = tr.get("class") or []
        if "thead" in classes or "over_header" in classes:
            section = tr.get_text(" ", strip=True)
            continue
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        rec: dict = {"_section": section}
        for c in cells:
            key = c.get("data-stat")
            if not key or key == "DUMMY":
                continue
            rec[key] = c.get_text(" ", strip=True)
            if key in keep_links:
                a = c.find("a")
                rec[f"{key}_href"] = a["href"] if a and a.has_attr("href") else None
            if c.has_attr("csk"):
                rec[f"{key}_csk"] = c["csk"]
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------
_FOOTNOTE_RE = re.compile(r"\[\s*[a-z0-9 ]{1,12}\s*\]", re.I)


def clean_cell(text: str) -> str:
    """Strip footnote markers like '[ a ]' / '[1]' and normalise whitespace."""
    text = _FOOTNOTE_RE.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


def wikitable_grid(table: Tag) -> list[list[Tag]]:
    """Expand a table into a grid of cell Tags honouring rowspan/colspan."""
    grid: list[list[Optional[Tag]]] = []
    pending: dict[tuple[int, int], Tag] = {}
    for r_idx, tr in enumerate(table.find_all("tr")):
        row: list[Optional[Tag]] = []
        col = 0
        cells = tr.find_all(["th", "td"], recursive=False)
        ci = 0
        while ci < len(cells) or (r_idx, col) in pending:
            if (r_idx, col) in pending:
                row.append(pending.pop((r_idx, col)))
                col += 1
                continue
            cell = cells[ci]
            ci += 1
            try:
                rs = int(cell.get("rowspan", 1) or 1)
                cs = int(cell.get("colspan", 1) or 1)
            except ValueError:
                rs, cs = 1, 1
            for k in range(cs):
                row.append(cell)
                for dr in range(1, rs):
                    pending[(r_idx + dr, col + k)] = cell
            col += cs
        grid.append(row)
    return grid  # type: ignore[return-value]


def grid_text(grid: list[list[Tag]]) -> list[list[str]]:
    return [[clean_cell(c.get_text(" ", strip=True)) if c is not None else "" for c in row] for row in grid]


def find_header_row(rows: list[list[str]], required: tuple[str, ...]) -> Optional[int]:
    for i, r in enumerate(rows[:6]):
        low = [x.lower() for x in r]
        if all(any(req.lower() == x or x.startswith(req.lower()) for x in low) for req in required):
            return i
    return None
