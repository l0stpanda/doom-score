# Phase 1: core table and labels

**Output:** `data/processed/mlb_nhl_core.csv` (1,454 rows) · `reports/phase1.png` · `reports/phase1_checks.csv`
**Code:** `src/fetch_phase1.py` (cached download), `src/build_phase1.py` (build + checks)

## Source probes
| Source | Result |
|---|---|
| statsapi.mlb.com standings (1997–2026, 30 calls) | ok |
| statsapi.mlb.com teams (2026, for current names) | ok |
| api.nhle.com team/summary (2002–03, 2003–04, 2005–06…2025–26, 23 calls) | ok |
| api.nhle.com team, franchise | ok |

Nothing was blocked.

## Row counts
| League | Seasons | Rows | Rows with a label |
|---|---|---|---|
| MLB | 2000–2026 | 810 | 720 (2000–2023) |
| NHL | 2005–06 … 2025–26 | 644 | 548 (2005–2022) |

## Checks
| Check | Result |
|---|---|
| One row per league-season-franchise | PASS |
| Team counts: MLB 30; NHL 30 → 31 (2017) → 32 (2021) | PASS |
| MLB W+L = G | FAIL, but expected: 12 team-seasons have 1 tie. **W+L+T = G: PASS** |
| NHL W+L+OTL = GP | PASS |
| League-wide run/goal differential = 0 | PASS (exactly 0 every season) |
| Percentiles span 0–100 | FAIL, but expected: 11 endpoints are tied best/worst records under average rank (e.g. 98.3). **Tie-aware check: PASS** |
| 2001 Mariners 116–46 | PASS |
| 2022–23 Bruins 65–12–5 | PASS |
| Labels NaN only in each league's last 3 seasons | PASS (186 NaN rows) |
| NHL `win_pct` = API points % | max diff 1e-5 |
| MLB team IDs constant through relocations | PASS (1998–2026) |

Sanity: corr(`win_pct_percentile`, `y_doom_3yr`) = −0.46 (MLB), −0.50 (NHL). Bottom-25 doom rate is 17.9% (MLB) and 18.4% (NHL).

## Most / least doomed (`y_doom_3yr`)
| League | Season | Team | W–L | Pctile t | Doom |
|---|---|---|---|---|---|
| MLB | 2010 | Houston Astros | 76–86 | 27.6 | 100.0 |
| MLB | 2023 | Colorado Rockies | 59–103 | 6.9 | 98.9 |
| NHL | 2008 | Edmonton Oilers | 38–35 | 31.0 | 98.9 |
| NHL | 2016 | Ottawa Senators | 44–28 | 62.1 | 97.8 |
| MLB | 2000 | Tampa Bay Rays | 69–92 | 17.2 | 97.7 |
| MLB | 2019 | Los Angeles Dodgers | 106–56 | 96.6 | 1.1 |
| MLB | 2001 | New York Yankees | 95–65 | 93.1 | 2.3 |
| MLB | 2018 | Los Angeles Dodgers | 92–71 | 79.3 | 2.3 |
| MLB | 2021 | Los Angeles Dodgers | 106–56 | 96.6 | 2.3 |
| NHL | 2006 | San Jose Sharks | 51–26 | 82.8 | 2.3 |

These match known history (the 2011–13 Astros teardown, the post-2017 Senators collapse, the Dodgers' dynasty).

## Decisions made (full table in `DECISIONS.md`)
- Files are under `ADAM-DATA/` (team repo layout). `dummy.txt` was removed.
- MLB: the API team ID is the franchise key. `team`/`franchise_id` use the 2026 name.
- NHL: Thrashers→Jets were already linked by the NHL API. **Coyotes→Utah was mapped by hand to `utah-mammoth` (needs review).**
- NHL `ties` = OTL (+ real ties pre-lockout), so `win_pct` = points %. Added `ot_losses` and `win_pct_raw`.
- Trailing features skip the cancelled 2004–05 season. Expansion teams use the history they have (`seasons_of_history` column).
- **The teammate's NBA/NFL file is not in the repo, so the percentile formula is not cross-checked yet.**

Phase 1 complete. Stopped for review before Phase 2.
