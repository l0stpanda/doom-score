# Phase 2: draft, front office, attendance (revised after review)

**Output:** `data/processed/mlb_nhl_core_phase2.csv` (1,454 × 52; Phase 1 file unchanged) · `front_office_spans.csv` (716 spans) · `data/manual/front_office_template.csv`, `front_office_unresolved_people.csv`, `baseball_ops_president_template.csv` (optional) · `reports/phase2_coverage.csv`, `phase2_checks.csv`, `phase2_verification.csv`
**Code:** `src/fetch_phase2.py`, `fetch_wiki_batch.py`, `fetch_wiki_people.py`, `phase2_api_features.py`, `parse_front_office.py`, `parse_people.py`, `build_phase2.py`

## Sources
| Source | Result |
|---|---|
| MLB Stats API (draft, coaches, seasons, attendance), NHL `api-web` draft | ok |
| Wikipedia lists | BLOCKED (429) after 21 of 98 pages. One approved retry: 2 requests, 77/77 pages |
| Wikipedia individual articles (Braves/Orioles/Reds GMs) | 1 batched request, 44/44 pages, no 429 |

## Coverage (% non-missing)
| Column | MLB 2000–2026 | NHL 2005–2025 |
|---|---|---|
| draft columns (4) | 100 | 100 |
| personnel_lead_tenure_years / changed_past_year | 94.7 / 93.6 | 100 / 100 |
| coach_tenure_years / coach_changed_during_regular_season | 100 | 100 |
| attendance_per_game / rank | 96.3 (2020 NaN) | not fetched |

Template (`front_office_template.csv`), MLB GM seasons only:
- **Reds 2009–26:** Dick Williams and Nick Krall are unresolved, so Jocketty's end is unknown.
- **Marlins (11 seasons) and Red Sox (4):** some of these are real GM vacancies (Red Sox 2018), the rest list gaps.
- **Dodgers 2020–22:** no GM in the list.
- **Six single-season gaps** on other teams.

## Review items
1. **Year convention:** the lists use **mostly calendar years** (hire/departure), not seasons, so the conservative shift stays. Evidence (D39):
   - Zaidi/Dodgers "2014–2018" (hired Nov 2014), Dombrowski/Phillies "2020-present" (Dec 2020) and Fuld/Phillies "2020–2024" all give the hire year.
   - Only Zaidi/Giants "2019–2024" (Nov 2018) gives the first season.
   - Epstein/Cubs and Friedman/Dodgers have no dated entries.
   - Across 85 consecutive MLB GM handovers, 59 share the boundary year (calendar style) and 26 step by one.
   - Year-only spans: 195 of 716 (MLB 152 of 174).
2. **personnel_lead = GM only** in both leagues (D36). The president template is optional. I also capped gap-carrying at 400 days, so long vacancies stay missing instead of carrying a departed GM (D37). Carried rows: MLB 40, NHL 6.
3. **Individual articles:** the Braves chain is complete with source sentences. The Orioles miss 2007, and the Reds miss 2009 onward. 31 unresolved people are listed with reasons (D38). The **8 NHL coach seasons came from parser bugs**, not missing data. The worst was "to" matching inside "October", which silently dropped every term starting in October. Fixing it recovered 14 spans, including 12 GMs (D40). NHL coaches are now 100% without individual articles.
4. **Source verification:** **not done in the first pass.** Done now: 5 random spans (seed 2026) vs cached source = **5/5 match**.

| Span | Parsed | Source |
|---|---|---|
| MLB LAD GM Dan Evans | 2001-12-31 → 2004-12-31 (year) | "Dan Evans ‖ 2001–2004" |
| NHL ANA coach Dallas Eakins | seasons 2019–2022 | "hired June 17, 2019 … until April 14, 2023" |
| NHL WSH coach Peter Laviolette | seasons 2020–2022 | "On September 15, 2020 … named head coach" |
| NHL DAL coach Rick Bowness | in-season 2019 → 2021 | season links 2019–2021 |
| NHL PHI coach Rick Tocchet | 2025-05-14 → open (day) | "May 14, 2025 – present" |

## Checks
5/5 PASS: Giants 2023 ≠ Melvin; Phillies 2022 change = 1 (Thomson); MLB 2020 attendance NaN; unique keys; draft timing. Manager fallback rows: 4.

Phase 2 complete. Stopped for review before Phase 3.
