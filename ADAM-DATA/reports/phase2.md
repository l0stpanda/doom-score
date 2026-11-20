# Phase 2: draft, front office, attendance

**Output:** `data/processed/mlb_nhl_core_phase2.csv` (1,454 rows × 54 cols; Phase 1 file unchanged) · `data/processed/front_office_spans.csv` (688 spans) · `data/manual/front_office_template.csv`, `baseball_ops_president_template.csv` · `reports/phase2_coverage.csv`, `phase2_checks.csv`, `phase2_build_log.txt`
**Code:** `src/fetch_phase2.py`, `src/fetch_wiki_batch.py`, `src/phase2_api_features.py`, `src/parse_front_office.py`, `src/build_phase2.py`

## Source probes
| Source | Result |
|---|---|
| MLB Stats API: draft, coaches (season + date), seasons, attendance | ok (1,110 manager-season calls + 127 season-end calls) |
| NHL `api-web` draft picks | ok |
| Wikipedia | **BLOCKED (HTTP 429) after 21 of 98 pages.** After your approval: one retry via the Action API, 2 batched requests → 77/77 pages, no 429 |

## Coverage (% non-missing, first–last season)
| Column | MLB | NHL |
|---|---|---|
| draft_picks_used / _rd1_2 / _first_pick_number / _pctile | 100% 2000–2026 | 100% 2005–2025 |
| personnel_lead_tenure_years | 90.0% 2000–2026 | 100% 2005–2025 |
| personnel_lead_changed_past_year | 89.8% | 100% |
| coach_tenure_years, coach_changed_during_regular_season | 100% | 98.8% |
| attendance_per_game, attendance_rank | 96.3% (2020 = NaN) | not fetched (spec: MLB only) |

**Gaps → manual templates:**
- **MLB GM pages without years** (Braves, Orioles, Reds; 27 seasons each) can't be parsed.
- **NHL coach gaps:** 8 team-seasons (PHI 3, TOR 4, WPG 1).
- **Baseball-ops presidents:** dated spans exist for only 5 of 30 MLB teams, so the other 25 fall back to the GM. Cubs/Epstein and Dodgers/Friedman are known misses (see D31).

## Your five requests
1. **Date precision:** every span stores `date_precision`. **189 of 688 spans are year-only** (MLB 146 of 156). These are placed after that year's season and its prediction moment (MLB Dec 31, NHL Jul 1). This makes October hires show up one season late, and 88 lead-seasons carry the previous person through a year-only gap (`personnel_lead_gap_carried`).
2. **Personnel lead:** the MLB lead is the baseball-ops president/CBO when one is active, otherwise the GM. Business presidents are ignored. NHL = GM. MLB rows: 688 GM, 41 president. Logged as D31.
3. **Manager checks:** 2023 Giants = Kapler, not Melvin (**PASS**). 2022 Phillies `coach_changed_during_regular_season` = 1, ending with Thomson (**PASS**).
   - **List order:** the season list is **not chronological** (in 108 resolved cases, the season-end manager was listed last 60×, first 43×). The season-end manager therefore comes from the season-end date query, never from list order.
   - **Fallback:** **4 rows** have `manager_resolved_by_fallback` = 1 (BOS 2015, CLE 2021, CWS 2022, LAA 2025). In each, the titled manager was on leave and the interim finished the season.
   - **Rename:** the flag is now `coach_changed_during_regular_season`. Changes after the last regular-season game aren't captured (D26).
4. **Draft:** added `draft_picks_used_pctile` and `draft_rounds_in_year`. MLB distinct round labels went from 51 (2000) to 8 (2020) to 26 (2026). `draft_picks_rd1_2` includes Competitive Balance Round A (D21).
5. **Attendance:** MLB 2020 attendance = NaN (the API returns 0), and `attendance_restricted` = True for 2020 and 2021.

## Checks
All 5 PASS: Giants 2023; Phillies 2022; MLB 2020 attendance NaN; one row per key; draft timing. My own spot checks also agree (Montgomery/Sweeney, Sutter replacing Stevens, Bowman, Cheveldayoff, Tourigny's tenure continuing from Arizona to Utah, the Daniels GM→president switch).

## Leakage notes
- The NHL draft for season t uses only the June t draft.
- Personnel leads are taken at the prediction moment (MLB Nov 15 t, NHL Jun 15 t+1).
- Coach and manager values are as of the last regular-season game.
- All Wikipedia spans are marked `needs_verification`.

Phase 2 complete. Stopped for review before Phase 3.
