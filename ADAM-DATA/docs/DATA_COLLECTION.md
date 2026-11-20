# How the MLB + NHL doom dataset was built

*For groupmates. All numbers below are computed by `docs/make_doc_stats.py` from the files in this repo. D-numbers refer to rows in `DECISIONS.md`.*

## 1. Goal

The dataset is for predicting which teams will be bad over the next few years. One row is one **team-season**: one club in one league in one season *t*. There are 1,454 rows: 810 for **MLB** (Major League Baseball, 2000–2026) and 644 for the **NHL** (National Hockey League, 2005–26). The NHL season starts in the fall and ends the next spring, so "NHL 2005" means the 2005–06 season.

**Doom score.** For each team-season we take the team's **league percentile** (where it finished relative to the other teams that year: 0 = worst record, 100 = best) in each of the next three seasons, average those three numbers, and subtract from 100: `y_doom_3yr = 100 − mean(percentile in t+1, t+2, t+3)`. Higher means more doomed. A team that finishes last three years running scores 100; a team that finishes first three years running scores 0. The score exists only when all three future seasons have been played, so the last three seasons of each league (MLB 2024–2026, NHL 2023–2025) have no label. Labelled rows: 720 MLB, 548 NHL. A binary version, `y_doomed_bottom25` (doom ≥ 75), is true for 17.9% of labelled MLB rows and 18.4% of NHL rows.

## 2. Avoiding look-ahead (leakage)

**Leakage** means a feature contains information that would not have been available when the prediction is made. A model trained with leaked features looks great on past seasons and fails on new ones.

**Prediction moment** (D29): the point in time at which we pretend to make the prediction for season *t*.
- MLB: **November 15 of year t**, just after the World Series (MLB's championship) ends.
- NHL: **June 15 of year t+1**, after the Stanley Cup final and before the June draft.

Rules every feature follows (from the build prompt and D08, D28, D59):
- It uses only information from season *t* or earlier, knowable by the prediction moment.
- Rolling and trailing features look only backwards; there is no back-filling and no imputation from later seasons.
- "Tenure" features are measured *as of the prediction moment*, never as total tenure.
- No scaling or model fitting across years. Percentile features (`_lpct`) are computed within a single league-season.
- Label columns start with `y_` (plus `observed_doom_next_3_seasons`), and no feature is derived from them.

Why it matters: we will train on past seasons and test on later ones. If a feature secretly encodes what happened next, the test score is meaningless.

**Concrete example (D18).** The NHL holds its draft (the yearly selection of new young players) every June. For NHL season *t*, the June draft of year *t+1* happens *after* the June 15 prediction moment, and the draft order itself is set by season *t*'s results. Attaching that draft to season *t* would leak. So `draft_picks_used` and the other draft columns for NHL season *t* use only the June draft of year *t*, held before season *t* began. Example from the data: Edmonton Oilers 2010–11 has `draft_first_pick_number` = 1, which is that June 2010 draft. A second example: MLB year-end and luxury-tax payrolls are published after the prediction moment, so only the Opening Day payroll is used (D53).

## 3. Sources

| Source | What it provided | Years in this dataset | Access | Blocked / dropped and why |
|---|---|---|---|---|
| MLB Stats API (`statsapi.mlb.com`) | Standings, draft, managers, attendance, player stints, birthdates, official team totals | 2000–2026 (history from 1997; managers from 1990) | Public JSON API, cached | — |
| NHL stats REST (`api.nhle.com`) | Standings, franchise map, skater/goalie stints, birthdates | 2005–2025 (history 2002–04) | Public JSON API, cached | Team "percentages" report probed but not needed (D48) |
| NHL `api-web.nhle.com` | Draft picks; birthdates for players missing from the bios report | 2005–2025 | Public JSON API | — |
| Wikipedia | GM and head-coach history (team lists; individual articles for Braves/Orioles/Reds GMs); NHL salary cap by season | GM/coach spans from 1999; cap 2005–2026 | MediaWiki Action API, batched, descriptive User-Agent | Rate-limited (HTTP 429) once; one approved, throttled retry succeeded (D17). All rows `needs_verification` |
| Cot's Baseball Contracts (Baseball Prospectus) | MLB Opening Day payroll; luxury-tax thresholds | payroll 2000–2026; tax 2003–2026 | Public web pages | Its printed payroll ranks contradict its own values → recomputed (D53) |
| Lahman database mirror | MLB salaries, cross-check only | 2000–2016 | CSV | First mirror returned 404; a second mirror worked |
| MoneyPuck | NHL Corsi, expected goals, PDO | 2008–2025 | Public CSV | Starts in 2008, so NHL 2005–07 are empty (D48) |
| Spotrac | (would have been payroll / cap hits) | — | — | **Blocked** (HTTP 403) (D52) |
| PuckPedia | (NHL cap hits) | — | — | **Blocked** (anti-bot page) (D52) |
| CapWages | (NHL cap hits) | — | — | Reachable but only covers 2025-26 onward (D52) |
| Sports-Reference, FanGraphs | — | — | — | Not used by rule: they block automated access |

## 4. Phase by phase

Commits on the `adam` branch:

| Commit | Date | Message |
|---|---|---|
| `d0fc8e8` | 2026-11-16 | init |
| `9ed9508` | 2026-11-19 | ADAM-DATA Phase 1: MLB+NHL core team-season table, labels, checks |
| `37a1301` | 2026-11-19 | ADAM-DATA Phase 2: draft, managers/coaches, front-office spans, MLB attendance |
| `a38c6e6` | 2026-11-19 | ADAM-DATA Phase 2 review: GM-only lead, parser fixes, GM articles, source verification |
| `1aea70b` | 2026-11-19 | ADAM-DATA Phase 2 review 3: Giants/Rays season-based, vacancy flag, tenure and GM-change checks, parser fixes |
| `25028eb` | 2026-11-19 | ADAM-DATA Phase 3: roster age/composition by stint, MoneyPuck underlying metrics |
| `06fa235` | 2026-11-19 | ADAM-DATA Phase 4: MLB payroll (Cot's), CBT/cap tables, final stacked table, data dictionary, correlation review |
| `9c0379c` | 2026-11-19 | ADAM-DATA: feature crosswalk (shared concept aliases, _lpct, vet_share_lq), spending decision |

**Phase 1: core table and labels.**
- Built standings, percentiles, trailing features, cheap extras (Pythagorean win %, luck, trend) and the labels from the two league APIs.
- Mapped relocated and renamed clubs to one `franchise_id` each, e.g. the Thrashers → Jets and Coyotes → Utah (D05, D06).
- NHL overtime losses are stored in `ties` so that win % equals the NHL's official points % (D07).
- Checks: 9 of 11 passed. The two literal failures are expected and explained: 12 MLB rows have a tie game (W+L+T = G holds everywhere), and tied best/worst records keep a percentile endpoint off exactly 0/100 (the tie-aware version passes).

**Phase 2: draft, front office, attendance.**
- Draft counts from the league APIs. MLB draft length changed a lot (D20 notes 40+ rounds before 2020 and 5 regular rounds in 2020; the data shows 8 round labels for 2020 once bonus rounds are counted), so a within-season percentile was added (D20).
- Managers (MLB) from the API. The API's season list of managers turned out *not* to be in chronological order, so the season-end manager comes from a date query (D23); 4 rows needed an interim fallback rule (D27).
- GMs and NHL coaches parsed from Wikipedia. Problems found and fixed:
  - Wikipedia rate-limited the fetch; one approved, throttled retry succeeded (D17).
  - The date-range separator "to" matched inside "Oc**to**ber", silently dropping every term starting in October; fixing it recovered 14 spans (D40).
  - Achievement bullets such as "Won Presidents' Trophy" were read as people; a tenure-consistency check caught them (D44).
  - Many MLB pages give only years; a rule places year-only changes after that season so they never leak into it (D28, D39).
- Checks: 7 of 8 pass outright. The remaining item is a flag, not a failure: MLB 2026 shows 0 GM changes because every 2026 change in the sources has only a year (D43). A 5-row random source verification matched 5/5 (D41).

**Phase 3: roster age and composition.**
- Player-level playing time and birthdates from the league APIs; age-weighted roster features, veteran share and star concentration (D45).
- **Traded players** are counted by their stint with each team. The MLB query silently dropped players traded *away* in recent seasons; 29 team-seasons were repaired from per-player year-by-year stats, and player totals now equal official team totals for every MLB team-season (D46). NHL stints use a per-franchise filter (D47).
- NHL Corsi, expected goals and PDO from MoneyPuck (D48).
- Checks: 11 of 11 passed.

**Phase 4: money and final table.**
- MLB Opening Day payroll from Cot's for every team-season, cross-checked against Lahman (2000–16: r = 0.986, median difference 0.27%) (D53). Cot's printed ranks contradicted its own dollar values in most seasons, so ranks are recomputed.
- Luxury-tax thresholds (D50) and the NHL salary cap (D51) typed from cited sources, one citation per row.
- NHL team cap hits were unavailable (Spotrac blocked, PuckPedia anti-bot, CapWages no history); NHL spending is marked unavailable by decision (D52, D57).
- Final table with the teammate's 19 core columns first, the data dictionary, and a correlation review.
- Checks: 8 of 8 passed. Afterwards the feature crosswalk added shared concept columns (9 of 9 checks passed).

## 5. The ten decisions that matter most for using the data

1. **D29** — Prediction moment is MLB Nov 15 of *t*, NHL Jun 15 of *t+1*; every feature respects it.
2. **D07** — NHL `ties` holds overtime losses so `win_pct` equals NHL points %.
3. **D06** — The Arizona/Phoenix Coyotes and Utah are one franchise, `utah-mammoth`.
4. **D12** — Output rows are MLB 2000–2026 and NHL 2005–2025; earlier seasons were used only to build trailing features.
5. **D28 / D39** — Year-only Wikipedia dates are placed after that season (except Giants and Rays pages, read as seasons in charge); this makes MLB GM changes appear up to a season late.
6. **D36** — The front-office lead is the GM in both leagues (not a president of baseball operations).
7. **D42** — `personnel_lead_vacant` = 1 means the source shows *no GM*, which is different from missing data.
8. **D26** — Coaching changes after the last regular-season game are not captured.
9. **D54** — MoneyPuck expected goals carries soft leakage; Corsi and PDO do not.
10. **D59** — Use the `_lpct` (within league-season percentile) columns when stacking leagues; raw units differ.

## 6. Known limitations

- **Coverage gaps.** NHL Corsi / expected goals / PDO exist only from 2008 (86.0% of NHL rows). MLB GM is unknown (neither named nor vacant) for 36 team-seasons, mostly the Reds after 2008 (`data/manual/front_office_template.csv`, 8 rows). NHL attendance was not collected.
- **Soft leakage.** MoneyPuck's expected-goals model is trained on all seasons, including those after *t* (D54). Separately, all sources were downloaded in 2026-11-19 (git log), so season statistics reflect each source's current values. Any later stat corrections are therefore included; this effect was not measured.
- **Short seasons.** MLB 2020 (58–60 games), NHL 2012–13 (48–48 games), NHL 2019–20 (68–71 games), NHL 2020–21 (56–56 games). Records and counts from these seasons are noisier (`short_season`).
- **Front-office dates.** 160 of 682 GM/coach spans have year-only dates (153 of the 175 MLB spans). These changes are placed after that year's season, so they can show up a season late (D28). 24 MLB and 3 NHL rows carry the previous GM across a short date gap (`personnel_lead_gap_carried`).
- **Vacancies.** 15 MLB and 2 NHL rows have no GM according to the source (`personnel_lead_vacant` = 1); their tenure is empty by design.
- **NHL spending unavailable.** No historical team cap hits; `spending`, `cap_space_pct` and `team_cap_hit_usd` are empty for the NHL (D57).
- **MLB 2026 GM flags.** `personnel_lead_changed_past_year` sums to 0 for MLB 2026 because all 2026 changes are year-only (D43). That season has no label.
- **Unverified percentile formula.** The teammate's NBA/NFL file was not in the repo, so the percentile formula has not been cross-checked against it (D15).

## 7. How to reproduce

```
ADAM-DATA/
  src/            fetch_*.py (download + cache), build_*.py (build), make_data_dictionary.py
  data/raw/       API/web cache (git-ignored; created by the fetch scripts)
  data/processed/ mlb_nhl_core.csv (phase 1) → _phase2 → _phase3 → mlb_nhl_team_seasons.csv (final)
  data/manual/    hand-typed tables with citations + templates for missing data
  reports/        phase reports, check results, logs
  docs/           these docs + make_doc_stats.py
```

Requires Python 3 with `requests`, `pandas`, `numpy`, `matplotlib`. On Windows set `PYTHONUTF8=1`. Run from `ADAM-DATA/`:

```
# 1) download (network; cached, safe to re-run)
python src/fetch_phase1.py
python src/fetch_phase2.py
python src/fetch_wiki_batch.py        # Wikipedia pages missing after a rate limit
python src/fetch_wiki_people.py       # Braves/Orioles/Reds GM articles
python src/fetch_phase3.py mlb
python src/fetch_phase3.py mlb_repair
python src/fetch_phase3.py nhl
python src/fetch_phase3.py nhl_births
python src/fetch_phase3.py mp
python src/fetch_phase4.py
# 2) build (offline, from the cache)
python src/build_phase1.py
python src/build_phase2.py
python src/build_phase3.py
python src/build_phase4.py
python src/build_crosswalk.py
python src/make_data_dictionary.py
# 3) docs
python docs/make_doc_stats.py
```

Note: the NHL salary-cap page was fetched with a one-off batched request (`data/raw/wikipedia_money/NHL_salary_cap.json`); `fetch_phase4.py` requests a page title that does not exist. Unclear how to refetch it with the scripts alone; see D51.

## 8. What the NBA/NFL side needs to match

See `FEATURE_CROSSWALK.md`. Use the same 19 core columns (in order) and fill the shared concept columns plus their `_lpct` versions. Every NBA and NFL entry is still **TBD**: playing-time weight, roster_age_weighted, vet_share, vet_share_lq, star_concentration, margin_per_game, luck, underlying_quality, draft_capital, gm_tenure, coach_tenure, spending, market. The `_lpct` formula is the same as `win_pct_percentile`: (average rank − 1)/(n − 1) × 100 within league-season, over non-missing values.
