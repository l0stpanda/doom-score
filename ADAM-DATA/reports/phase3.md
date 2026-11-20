# Phase 3: roster age and composition

**Output:** `data/processed/mlb_nhl_core_phase3.csv` (1,454 × 69; Phase 2 file unchanged) · `reports/phase3_coverage.csv`, `phase3_checks.csv`, `phase3_build_log.txt`
**Code:** `src/fetch_phase3.py` (mlb · mlb_repair · nhl · nhl_births · mp), `src/build_phase3.py`

## Source probes
| Source | Result |
|---|---|
| MLB Stats API: player season stats by `teamId`, `/people`, `/teams/stats`, fullSeason rosters, yearByYear | ok (1,620 stint calls + 75 people batches + 54 team totals + 29 rosters + 1 repair batch) |
| NHL stats REST: skater/goalie summary by `franchiseId`, bios (paged); api-web player landing | ok (~1,330 + ~230 + 27 calls) |
| MoneyPuck team season CSV | ok, 2008–2025 (18 calls) |
| NHL REST team "percentages" | ok on probe, not needed (fallback) |

Nothing was blocked.

## Coverage (% non-missing, first–last season)
| Column | MLB | NHL |
|---|---|---|
| age_weighted, share_production_age32plus, top3_concentration | 100% 2000–2026 | 100% 2005–2025 |
| age_weighted_hitters / _pitchers | 100% | — |
| share_points_age32plus | — | 100% |
| xgoals_pct, corsi_pct, pdo_5v5 | — | 86% 2008–2025 (MoneyPuck starts 2008) |

## Checks (11/11 PASS)
- Every team-season has roster features; birthdates cover 100% of playing time.
- **Traded players are split by stint** (Ramirez 2010: LAD 232 + CWS 88 PA).
- **MLB player PA and BF sum exactly to official team totals for all 810 team-seasons.** The first run failed this: the `teamId` query drops players traded away in recent seasons (2025 Twins were 1,400 PA short). Repaired from yearByYear splits (D46).
- NHL skater games per team game: 17.77–18.01 (18 dressed). Goalie GP ≥ team games.
- League means: age_weighted MLB 29.0, NHL 28.2. Corsi/xG mean 0.500, PDO 1.000. Shares in [0, 1]. Unique keys.

**Sanity:**
- **Oldest:** 2005 Yankees (33.7) and 2005–07 Red Wings (32.4–32.7).
- **Youngest:** 2006 Marlins (25.7) and 2020 Rangers (25.4).
- **top3_concentration means:** MLB 0.19 (share of playing time), NHL 0.31 (share of points).

## Spearman vs y_doom_3yr (review only)
| | age_weighted | share 32+ | top3 | corsi | xG% | PDO |
|---|---|---|---|---|---|---|
| MLB | −0.12 | −0.10 | −0.08 | | | |
| NHL | +0.04 | +0.06 | −0.23 | −0.45 | −0.55 | −0.28 |

Older MLB rosters are slightly *less* doomed. They're usually good teams, so this is likely confounded with current quality. NHL xG% is the strongest single signal so far.

## Decisions
D45 (definitions and weights), D46 (MLB stint repair), D47 (NHL stints and birthdates), D48 (MoneyPuck), D49 (output file). Leakage: all features use season-t stints only; ages are on fixed in-season dates.

Phase 3 complete. Stopped for review before Phase 4.
