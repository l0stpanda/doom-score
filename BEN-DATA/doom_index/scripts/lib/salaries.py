"""Player-level salary sources.

PWHL   PWHLPA Player Salary Guide (official players' association disclosure).
       Base salary only, excludes bonuses/incentives; "accurate as of April 12,
       2026"; covers players under contract at publication. The PDF link is
       discovered from https://www.pwhlpa.com/salary-guide each run.
       The PWHLPA site states that its content may not be duplicated or
       redistributed; the raw PDF is therefore kept only in the local raw cache
       (git-ignored) and salary values should not be republished outside the
       course project without checking with the PWHLPA.

WNBA   2018-2023: "Annual salaries of athletes from 10 professional sports
       (2014-2023)", T. Sitthiyot, Mendeley Data (2026), doi:10.17632/38wkcb4pwb.1, CC BY 4.0. The
       WNBA sheets reproduce Spotrac's player salary rankings (accessed by the
       dataset authors 2024-04-28): one row per player-season with name, team
       code, position and annual salary earnings (prorated for partial-season /
       hardship contracts). Downloaded via the public Mendeley Data API.
       2024+: no permitted automated source. Her Hoop Stats' robots.txt disallows
       generic crawlers and Spotrac returns HTTP 403 to scripted clients, so
       neither is scraped. A user may supply
       ``data/raw/manual/wnba_player_contracts.csv`` (schema in README) compiled
       from a source they are licensed to use; it is ingested with its own provenance.
"""
from __future__ import annotations

import io
import logging
import re
from typing import Optional

import pandas as pd

from config import settings
from lib.common import norm_name, player_key, resolve_team
from lib.sources import fetcher

log = logging.getLogger(__name__)

PWHLPA_AS_OF = "2026-04-12"
PWHLPA_SEASON = "2025-26"

WNBA_MANUAL_CONTRACTS = settings.MANUAL_DIR / "wnba_player_contracts.csv"
WNBA_MANUAL_COLUMNS = ["season", "team", "player_name", "salary_usd", "salary_measure", "contract_start_year",
                       "contract_end_year", "contract_type", "guaranteed_usd", "free_agent_status_next",
                       "source_organization", "source_url", "source_as_of_date"]


def pwhlpa_salaries(refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    import pdfplumber  # local import: only needed for this source

    f = fetcher("pwhlpa", refresh, settings.CACHE_MAX_AGE_DAYS_CURRENT)
    page = f.get(settings.PWHLPA_SALARY_PAGE, cache_key="salary_guide_page", ext="html")
    links = sorted(set(re.findall(r"https?://[^\"'\s<>]+PlayerSalaries[^\"'\s<>]*\.pdf", page.text)))
    if not links:
        raise RuntimeError("PWHLPA salary guide PDF link not found on page")
    pdf_url = links[-1]
    m = re.search(r"(\d{4})-(\d{4})", pdf_url)
    label = f"{m.group(1)}-{m.group(2)[2:]}" if m else PWHLPA_SEASON
    res = f.get(pdf_url, cache_key=f"PlayerSalaries_{label}", ext="pdf")
    rows = []
    with pdfplumber.open(io.BytesIO(res.content)) as pdf:
        for p in pdf.pages:
            for tb in p.extract_tables():
                for r in tb:
                    if not r or r[0] is None or r[0].strip().lower() == "first name":
                        continue
                    first, last, team, sal = (x.strip() if x else "" for x in r[:4])
                    rows.append({"first_name": first, "last_name": last, "player_name": f"{first} {last}".strip(),
                                 "team_source": team, "salary_base_usd": float(sal.replace(",", "")) if sal else None})
    df = pd.DataFrame(rows)
    df["league"] = "PWHL"
    df["season"] = label
    df["team_id"] = df["team_source"].map(lambda t: resolve_team("PWHL", t))
    df["name_key"] = [player_key(lg, n) for lg, n in zip(df["league"], df["player_name"])]
    meta = {"url": pdf_url, "page_url": page.url, "retrieved": res.retrieved_at_utc, "as_of": PWHLPA_AS_OF}
    log.info("PWHLPA salary guide: %d players (%s)", len(df), label)
    if df["team_id"].isna().any():
        log.warning("unmapped PWHLPA teams: %s", df.loc[df.team_id.isna(), "team_source"].unique())
    return df, meta


def wnba_manual_contracts() -> Optional[pd.DataFrame]:
    if not WNBA_MANUAL_CONTRACTS.exists():
        return None
    df = pd.read_csv(WNBA_MANUAL_CONTRACTS, dtype=str)
    missing = [c for c in WNBA_MANUAL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{WNBA_MANUAL_CONTRACTS} missing columns: {missing}")
    df["team_id"] = df["team"].map(lambda t: resolve_team("WNBA", t))
    df["name_key"] = [player_key(lg, n) for lg, n in zip(df["league"], df["player_name"])]
    df["salary_usd"] = pd.to_numeric(df["salary_usd"], errors="coerce")
    df["guaranteed_usd"] = pd.to_numeric(df["guaranteed_usd"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# WNBA: Spotrac rankings via Mendeley Data (CC BY 4.0)
# ---------------------------------------------------------------------------
MENDELEY_DATASET = "38wkcb4pwb"
MENDELEY_DOI_URL = "https://doi.org/10.17632/38wkcb4pwb.1"
MENDELEY_AS_OF = "2024-04-28 (Spotrac access date stated by the dataset)"
# Spotrac team codes in the workbook -> Basketball-Reference codes used by config/teams.csv
SPOTRAC_TO_BBREF = {"LA": "LAS", "LV": "LVA", "NY": "NYL", "PHX": "PHO"}


def wnba_mendeley_salaries(refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    from lib.common import franchise_by_bbref

    f = fetcher("mendeley", refresh)
    meta_res = f.get(f"https://data.mendeley.com/public-api/datasets/{MENDELEY_DATASET}",
                     cache_key=f"dataset_{MENDELEY_DATASET}", ext="json")
    meta = meta_res.json()
    lic = (meta.get("data_licence") or {}).get("short_name")
    if lic != "CC BY 4.0":
        raise RuntimeError(f"unexpected licence on Mendeley dataset: {lic}")
    xfile = next(x for x in meta["files"] if x["filename"].lower().endswith(".xlsx"))
    url = xfile["content_details"]["download_url"]
    res = f.get(url, cache_key=f"dataset_{MENDELEY_DATASET}_v{meta.get('version')}", ext="xlsx")
    book = pd.ExcelFile(io.BytesIO(res.content))
    rows = []
    for sh in book.sheet_names:
        m = re.fullmatch(r"WNBA(\d{2})", sh)
        if not m:
            continue
        season = str(2000 + int(m.group(1)))
        d = book.parse(sh, header=None, skiprows=1)
        d = d.iloc[:, :4]
        d.columns = ["rank", "player_name", "team_pos", "salary"]
        d = d.dropna(subset=["player_name", "salary"])
        for r in d.itertuples():
            team_code, _, pos = str(r.team_pos).partition(",")
            code = SPOTRAC_TO_BBREF.get(team_code.strip(), team_code.strip())
            rows.append({"league": "WNBA", "season": season, "player_name": str(r.player_name).strip(),
                         "team_code_source": team_code.strip(), "position_source": pos.strip(),
                         "team_id": franchise_by_bbref(code), "salary_base_usd": float(r.salary)})
    df = pd.DataFrame(rows)
    if df.team_id.isna().any():
        log.warning("unmapped Spotrac team codes: %s", sorted(df.loc[df.team_id.isna(), "team_code_source"].unique()))
    df["name_key"] = [player_key("WNBA", n) for n in df.player_name]
    log.info("Mendeley/Spotrac WNBA salaries: %d player-seasons (%s)", len(df), ", ".join(sorted(df.season.unique())))
    return df, {"doi_url": MENDELEY_DOI_URL, "file_url": url, "retrieved": res.retrieved_at_utc, "as_of": MENDELEY_AS_OF}
