# Source coverage matrix

Status as of 2026-11-19. Sources were checked directly before any collector was written
(HTTP status, robots.txt, terms notices). ✅ collected · 🟡 partial / secondary · ❌ not collected (reason given).

## Sources investigated

| source | URL | access check | used? | why / why not |
|---|---|---|---|---|
| Basketball-Reference (Sports Reference) | basketball-reference.com/wnba/ | 200; robots allows `/wnba/` (disallows gamelogs/splits); crawl-delay 3 s | ✅ | WNBA standings, ratings, SOS, rosters, player totals/advanced, playoffs, draft careers. Requests spaced ≥ 4 s and cached. |
| ESPN public site API | site.api.espn.com/apis/v2/sports/basketball/wnba/standings | 200 JSON | ✅ | home/road splits, seeds, independent W/L + points cross-check |
| stats.wnba.com (official) | stats.wnba.com/stats/… | connection times out for scripted clients | ❌ | anti-bot protection; not bypassed |
| WNBA.com news | wnba.com/news/… | 200 | ✅ (manual) | 2026 CBA terms (cap, max/min salaries, roster rules) transcribed into `config/cba_parameters.csv` |
| Her Hoop Stats | herhoopstats.com/salary-cap-sheet/… | robots.txt: `User-agent: * Disallow: /` | ❌ (scripted) | robots disallows generic crawlers; one page viewed manually to confirm the 2025 cap. Salary data can be supplied via the manual-import template if your access terms allow it |
| Spotrac | spotrac.com/wnba/… | HTTP 403 to scripted client | ❌ | access denied; not bypassed |
| PWHL HockeyTech stats feed | lscluster.hockeytech.com/feed/… | the key in the URL is a client key embedded in thepwhl.com, not one issued to this project | ❌ (direct) | not used directly; the published fastRhockey dataset (built from this feed) is used instead |
| sportsdataverse fastRhockey-pwhl-data | github.com/sportsdataverse/fastRhockey-pwhl-data | 200; MIT licence | ✅ | PWHL schedules/results, rosters (birth dates, positions), per-game player/goalie box scores incl. TOI |
| PWHLPA Player Salary Guide | pwhlpa.com/salary-guide (+ PDF) | 200; site notice: no duplication/redistribution | ✅ | official 2025-26 base salaries. Raw PDF kept in git-ignored cache; see README "Redistribution" |
| Wikipedia (MediaWiki API) | en.wikipedia.org/w/api.php | 200; CC BY-SA | 🟡 | draft order/ownership & trade footnotes, PWHL standings cross-check, current rosters, PWHL contract terms. Crowd-edited → every row stores the revision permalink and is marked `secondary_unverified` |
| Front Office Sports / Daily Faceoff / Just Women's Sports / Boardroom / Winsidr | various | 200 | 🟡 (manual) | CBA parameters not published in an official machine-readable form; each value cites its article |

## Field coverage

| dataset / field group | WNBA source | WNBA seasons | PWHL source | PWHL seasons | availability & limitations |
|---|---|---|---|---|---|
| W, L, GP, win % | BBRef (✓ ESPN) | 2019–2026 | fastRhockey games (✓ Wikipedia) | 2023-24 → 2025-26 | ✅ all team-seasons cross-checked; 0 W/L mismatches |
| OTL / RW / OTW / SOW, standings points, points % | n/a | | calculated from game status | all | ✅ matches Wikipedia standings exactly |
| points/goals for & against | BBRef (✓ ESPN) | all | game scores | all | ✅ 4 WNBA team-seasons differ from ESPN by 1–2 points (logged) |
| home / away records | ESPN | all | calculated | all | ✅ |
| strength of schedule / ratings | BBRef SOS, SRS, MOV, ORtg/DRtg, pace | all | — | — | ❌ PWHL: no defensible published SOS; not computed |
| playoffs (series, games, champion) | BBRef playoff table | all | fastRhockey playoff games | all | ✅ |
| lag features (prior season, YoY, 3-season) | calculated | 2020–2026 have priors | calculated | priors from 2024-25; 3-season only 2025-26 | ✅ |
| rosters, position, birth date, height | BBRef team rosters (+ player pages when omitted) | 2021–2026 | fastRhockey rosters | all | ✅ (height/weight WNBA only) |
| experience | BBRef "Yrs" | 2021–2026 | prior PWHL seasons (calculated) | all | 🟡 PWHL excludes pre-PWHL pro leagues |
| participation (GP, GS, MIN / TOI) | BBRef totals | 2021–2026 | per-game box scores | all | ✅ |
| box-score production | BBRef totals | 2021–2026 | box scores (G, A, P, SOG, hits, blocks, PIM, +/-, FO) | all | ✅ |
| advanced / impact | BBRef PER, TS%, USG%, ORtg/DRtg, Win Shares | 2021–2026 | — | — | ❌ PWHL: no credible public GAR/xG impact metric collected (goalie SV%, GAA computed) |
| player salary | none permitted (manual import hook) | — | PWHLPA guide | 2025-26 only | ❌ WNBA; 🟡 PWHL single season, base salary only |
| contract term / expiry / FA status | none | — | Wikipedia transaction tables | signings since 2025 offseason | ❌ WNBA; 🟡 PWHL lower-bound counts |
| draft selections | Wikipedia (✓ BBRef pick+name) | 2016–2026 | Wikipedia | 2023–2026 | ✅ |
| original owner vs. selecting team, trade notes | Wikipedia "(from X)" + footnotes | 2016–2026 | Wikipedia | 2024–2026 (no traded picks recorded for 2023) | 🟡 secondary source, verbatim notes kept |
| expansion drafts / signing windows | Wikipedia | 2024 (GSV), 2026 (POR, TOR) | Wikipedia | 2025 (SEA, VAN), 2026 (4 teams) | ✅ |
| draftee career outcomes | BBRef career totals | 2016–2026 drafts | project player data | 2023–2025 drafts | ✅ raw stats only; no composite outcome defined |
| future pick inventory | Wikipedia 2027 draft (post-lottery order) | 2027 | traded picks only | none found | 🟡 WNBA next draft only; ❌ 2028+; PWHL not available |
| salary cap / CBA parameters | WNBA.com (2026), press (2021–2025) | 2021–2026 | press / PWHLPA | 2023-24 → 2026-27 | 🟡 some years `calculated_unverified` (3% escalation) |
| team payroll, cap space, concentration | — | — | aggregated PWHLPA | 2025-26 | ❌ WNBA; 🟡 PWHL single season (77–93% of roster covered) |
| current roster snapshot | Wikipedia roster templates | Nov 2026 | Wikipedia team articles | 2026-27 preseason | 🟡 dated, crowd-edited; WNBA reflects end-of-season rosters |
| organisational events (coach/GM changes, ownership) | — | — | — | — | ❌ not yet collected (optional/secondary in the brief; Wikipedia season pages have "Coaching changes" / "Front office changes" tables that could be added) |
