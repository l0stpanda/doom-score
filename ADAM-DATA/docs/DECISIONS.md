# Decisions

The 30 decisions that shaped the final product, one line each with the reason. IDs match the full logs (D = model,
M = map), so an ID cited in the code or docs that isn't here is in the full logs listed at the end.

## Doom score and model

| ID | Decision | Why |
|---|---|---|
| D07, D10 | Standing = within-league-season percentile of win % (worst 0, best 100); NHL win % = points % (OT/SO losses count half) | One scale across leagues and eras, ties handled the same way everywhere |
| D11 | Doom = 100 − mean standing over the franchise's next three **played** seasons; no label unless all three exist | Measures a sustained bad stretch, not one bad year |
| D29 | Prediction moment: MLB Nov 15 of t, NHL Jun 15 of t+1; every feature must be known by then | No information from the future leaks into a prediction |
| D03, D05, D06 | One franchise id through moves and renames | A team's history stays one series through relocations |
| D59 | Features are within-league-season percentiles (`_lpct`) | Leagues and eras share one scale; no league-specific units |
| D61, D63 | Features chosen by concept, not by correlation with the outcome; near-duplicates (MLB Pythagorean %) dropped | Avoids fitting noise in small samples |
| D64 | Walk-forward backtest: season T predicted by a model trained only on seasons ≤ T−3 | Matches what was knowable at the time (labels lag three seasons) |
| D72 | Model differences judged by a moving-block bootstrap over test seasons (blocks of 3) | Seasons are correlated; plain resampling would overstate certainty |
| D76 | The simplest model within noise of the best: **MLB = standings only (B1), NHL = elastic net on 13 features** | Extra features must earn their place out of sample |
| D86 | Six pre-registered MLB features did not beat standings beyond noise; BaseRuns margin is future work | Pre-registration keeps the MLB search honest |
| D54, D79 | NHL expected goals not used (the provider's xG model saw future seasons); Corsi used instead | Soft leakage would inflate backtest results |
| D80, D88 | 80% intervals by split conformal from earlier seasons' walk-forward errors; 3-year paths from per-horizon models, shifted to average to the headline doom | Honest coverage (82% MLB, 85% NHL); paths consistent with the score |
| D99, D100 | `p_doom75` = chance doom ends ≥ 75; bands Low < 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50% | A plain-language risk level next to a wide interval |
| D92 | Live seasons (MLB 2024–26, NHL 2023–25) use models refit on all earlier labelled seasons | Uses all data for current predictions; flagged as not strictly out of sample |

## Doom Map and dashboard

| ID | Decision | Why |
|---|---|---|
| M57 | Scope: the four men's leagues (MLB, NHL, NBA, NFL), listed in `map/inputs/leagues.csv` with real/demo status, backtest flag and model note | Shared calendar and geography; WNBA/PWHL can follow the same path later |
| M50 | The map's only model input is per-team scores in `map/inputs/scores/` (required: league, season_start_year, franchise_id, doom_pred) | Adding a league = one file; the map doesn't depend on any one model |
| M51 | Optional score columns are per league; whatever needs a missing column is hidden for that league only | A sparse file never breaks the page |
| M02 | Map season Y = every league's season starting in calendar year Y (NHL/NBA Y–Y+1) | Same key as the data; no reshuffling |
| M03, M14 | Location = city of the venue with most home games that season (temporary homes count); a located team with no score is "too new to score", shown but left out of averages | The map shows where teams actually played |
| M52 | Team registry for all four leagues (NBA/NFL 2000–2026, teammates' franchise ids), relocations checked on official league/team pages | Teammates send scores only; locations, names and logos are ours |
| M08 | 23 fan regions built from counties/census divisions by nearest fan-identity anchor within allowed states/provinces; fixed across seasons | Fan identity rather than census lines, with recognisable borders; rules are data, so reviewable |
| M16, M17 | Colour = z of doom within league-season, then leagues side by side | Leagues comparable; caveat: it makes MLB look as certain as NHL |
| M18–M20 | σ = 100 mi blending and the opacity cutoffs and colour-scale ends are derived by rule from the teams, and re-derived when a league is added | No hand-tuned constants; `--freeze-params` keeps them when wanted |
| M21, M24 | Colour-blind-safe blue → gold → crimson ramp (OKLCh) by default, green–red as an option; grey = no teams nearby | Readable for colour-blind users in light and dark mode |
| M27, M28 | Regions ranked by an empirical-Bayes shrunk average; verdict words from tertiles of raw averages; "most differences are within chance" shown | Regions with few teams would otherwise swing to the extremes |
| M45 | One dashboard page: map, projected-standing scatter and team panel share season, leagues, mode and team, mirrored in the URL | Select a team once and see it everywhere; links restore the view |
| M54 | `map/add_scores.py` validates, matches team names (ids, names, abbreviations, by season), stops on unmatched names or uncovered seasons, then rebuilds | A wrong silent match would put a team in the wrong city |
| M58 | "This season shows: … (no …)" banner when a selected league has no scores; default season = latest with the most leagues | One rule for any mix of leagues and seasons |
| M59–M61 | Demo mode: fake NBA/NFL scores on real standings, labelled everywhere (banner, Demo tags), never read by a normal build and blocked from commits | Lets people try four leagues now without fake numbers passing as results |
| M49 | The build uses the committed region shapes; raw boundary files are only needed to change regions | Runs on any machine with no large downloads |

## Full logs

- Model decisions D01–D108, with alternatives: `git show adam-full-pipeline:ADAM-DATA/DECISIONS.md`
- Map decisions M01–M62, with alternatives and checks: `git show adam-map-full:ADAM-DATA/docs/MAP_DECISIONS.md`
- Phase reports and screenshots: tags `adam-full-pipeline` (model) and `adam-map-full` (map), under `ADAM-DATA/reports/`.
