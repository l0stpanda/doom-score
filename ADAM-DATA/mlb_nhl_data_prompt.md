# MLB + NHL Doom data build — run ONE phase at a time

How to use: tell Claude Code **"Read this file and do Phase 1 only."** Each phase is meant to be short (≈10–15 min). It must end with a short report, a commit, and a **stop**. I review the report before starting the next phase.

---

## Ground rules (apply to every phase)

**Goal of the whole build.** Produce one model-ready table: one row per MLB/NHL team-season *t*. Features may use only information knowable at the end of season *t*. The label comes from seasons *t+1..t+3*. The core columns must match my teammate's NBA/NFL file, so all four leagues can be stacked into a single table.

**Speed and visibility.**
- Before any bulk download, **probe each source with one request** and print the result (ok / blocked / error).
- If a source returns 403, 429, a captcha, or a Cloudflare page, or fails twice: mark it BLOCKED in the report and move on. Do not retry in loops, spoof headers, or try to get around blocks.
- **Do not use Sports-Reference (Baseball/Hockey-Reference) or FanGraphs.** They block automated access.
- Print a one-line status after every step. Write partial output files as soon as they exist, not only at the end.
- Cache every raw response under `data/raw/<source>/` and never re-download something that's already cached. Add `data/raw/` to `.gitignore`.
- Keep the code simple: plain scripts in `src/` using `requests` and `pandas`. No frameworks, no elaborate test suites.
- At the end of each phase:
  - write `reports/phaseN.md`, at most one page
  - append any decisions to `DECISIONS.md`
  - commit on the current branch (don't push)
  - print the report and **stop**

**DECISIONS.md format.** One row per decision, in a table:
`| ID | Decision | Alternatives | Why | Needs review (Y/N) |`
Log every nontrivial choice. Keep each row short.

**Leakage rules.**
- **Prediction moment for season t:** the end of season *t*'s playoffs.
  - MLB season t: ~November of year t.
  - NHL season t, which starts in fall of year t (2017 = 2017–18): ~mid-June of year t+1, before that June's draft.
- Every feature must be knowable by that moment.
- Trailing or rolling features use seasons ≤ t only. No back-fill, and no imputation that looks at later seasons.
- Tenure-type features are measured as of the prediction moment, never as total tenure.
- No scaling or model fitting across years in this stage.
- Label columns start with `y_`, and no feature may be derived from them.

**Seasons.**
- MLB: 2000 through the latest completed season (2026). Also fetch 1997–1999, used only to build trailing features.
- NHL: 2005–06 through 2025–26. Also fetch 2002–03 and 2003–04 for trailing features. 2004–05 was cancelled. Exclude the in-progress 2026–27 season.

**Teammate's schema.** Core columns, in this exact order:

`league, season_start_year, franchise_id, team, wins, losses, ties, games, win_pct, point_diff_per_game, win_pct_percentile, win_pct_trailing_3_seasons, observed_doom_next_3_seasons, draft_picks_used, cap_space_pct, personnel_lead_tenure_years, personnel_lead_changed_past_year, standings_source, draft_source`

Definitions:
- `win_pct = (wins + 0.5·ties) / games`
- `win_pct_percentile` = within league-season, `(average rank ascending − 1)/(n − 1) × 100`. Worst team = 0, best = 100.
- `win_pct_trailing_3_seasons` = mean of seasons t−2, t−1, t (it includes t).
- `team` = the franchise's **current** name for every year.
- `franchise_id` = lowercase-hyphenated current name, kept the same through relocations and renames (e.g. `athletics`, `washington-nationals` for the Expos years, `winnipeg-jets` for the Atlanta Thrashers years, `cleveland-guardians`).
- If the teammate's file (`doom_nba_nfl_team_seasons_enriched.csv`) is in the repo, reproduce one of its percentiles to confirm the formula.

---

## Phase 1: core table and labels (the minimum viable dataset)

**Sources (official league APIs, no key needed):**
- MLB: `https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={YYYY}&standingsTypes=regularSeason`, one call per season. It returns W, L, runs scored and allowed. MLB team IDs stay the same for a franchise across relocations; confirm this.
- NHL: `https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId={YYYYYYYY} and gameTypeId=2`, one call per season. It returns GP, W, L, OTL, GF, GA, and points %. Use `https://api.nhle.com/stats/rest/en/team` and `.../franchise` to map team IDs to franchises.
  - The Thrashers→Jets and Coyotes→Utah IDs differ. Map them by hand to one continuous `franchise_id` each, and log both mappings as needing review.

**Build:**
1. All core columns:
   - Leave `draft_picks_used`, `cap_space_pct` and the `personnel_*` columns empty for now.
   - `standings_source` = the API URL.
2. NHL choices (log them):
   - add an `ot_losses` column
   - fill `ties` with the OTL count, so that `win_pct` equals NHL points %
   - add `win_pct_raw = W/GP`
3. Labels:
   - `y_pct_t1`, `y_pct_t2`, `y_pct_t3` = the team's `win_pct_percentile` in each of the next three seasons.
   - `y_doom_3yr = 100 − mean(y_pct_t1..t3)`. NaN unless all three exist.
   - `y_doomed_bottom25 = y_doom_3yr ≥ 75`.
   - `observed_doom_next_3_seasons = y_doom_3yr`.
4. Cheap extra features (all from season t or earlier):
   - runs/goals for and against per game
   - Pythagorean win% (MLB exponent 1.83; NHL 2.0) and `luck = win_pct − pythag`
   - `win_pct_change_1yr`
   - `win_pct_slope_3yr`
   - `short_season` flag: MLB 2020; NHL 2012–13, 2019–20, 2020–21
   - `expansion_first_3_seasons` flag: Vegas from 2017, Seattle from 2021
5. Validation. Print pass/fail for each check:
   - one row per league-season-franchise
   - team counts: MLB 30; NHL 30, then 31 from 2017, then 32 from 2021
   - MLB: W+L = G. NHL: W+L+OTL = GP
   - league-wide run/goal differential ≈ 0 each season
   - percentiles span 0–100 within each league-season
   - spot checks: 2001 Mariners 116–46; 2022–23 Bruins 65–12–5
   - labels are NaN only in each league's last 3 seasons

**Output:**
- `data/processed/mlb_nhl_core.csv`
- `reports/phase1.png`: scatter of `win_pct_percentile` (x) vs `y_doom_3yr` (y), colored by league
- `reports/phase1.md`, containing:
  - row counts by league
  - check results
  - decisions made
  - the 5 most-doomed and 5 least-doomed team-seasons, as a sanity check
  - the source probe results

**Stop.**

---

## Phase 2: draft, front office, attendance

**Sources (probe first):**
- MLB draft: `https://statsapi.mlb.com/api/v1/draft/{YYYY}`. Season t's July draft is allowed.
- NHL draft: `https://api-web.nhle.com/v1/draft/picks/{YYYY}/all`. Only the draft held in June of year t (before season t) is allowed. The June t+1 draft is after the prediction moment.
- MLB managers: `https://statsapi.mlb.com/api/v1/teams/{id}/coaches?season={YYYY}`.
- NHL coaches and GMs for both leagues: Wikipedia pages listing each team's GMs and head coaches. Fetch the pages and build `data/processed/front_office_spans.csv` with columns `franchise_id, role, person, start_date, end_date, source_url`.
- MLB attendance: try the MLB Stats API first; skip if unavailable.

**Build:**
- `draft_picks_used` (total), `draft_picks_rd1_2`, `draft_first_pick_number`.
- `personnel_lead_tenure_years` (GM / top executive, as of the prediction moment) and `personnel_lead_changed_past_year`. Do the same for the manager/head coach: `coach_tenure_years`, `coach_changed_in_season`.
- `attendance_per_game` and `attendance_rank`, if a source is available.

**Report:** coverage by column (% non-missing, first–last season), anything BLOCKED, and decisions. Mark rows from Wikipedia as `needs_verification` in the spans file.

Commit. **Stop.**

---

## Phase 3: roster age and composition (player-level, official APIs)

**Sources (probe first):**
- MLB: season player stats and birthdates from the MLB Stats API, e.g. `/api/v1/stats?stats=season&group=hitting|pitching&season={YYYY}&playerPool=ALL&limit=...` plus `/api/v1/people?personIds=...`.
- NHL: `https://api.nhle.com/stats/rest/en/skater/summary` and `.../goalie/summary` per season, plus bios for birthdates.

**Build (team-season level):**
- `age_weighted`: weighted by plate appearances + batters faced (MLB), or by time on ice/games (NHL). Age is measured on a fixed date: MLB June 30 of year t; NHL Feb 1 of year t+1.
- `share_production_age32plus`: the share of PA/BF (MLB) or points/TOI (NHL) coming from players aged 32+.
- `top3_concentration`: the share of team production from its top 3 players.
- Assign traded players to each team by their stint with that team, not by their season total.

**NHL underlying metrics:** probe MoneyPuck's team season CSV downloads (~2008 onward) for xGoals%, Corsi% and PDO. If blocked, try the NHL stats REST team "percentages" reports. If both fail, skip and log it.

**Report** in the same format. Commit. **Stop.**

---

## Phase 4: money (best effort)

- Static tables: the MLB luxury-tax (CBT) threshold and the NHL salary-cap ceiling for each season. These are small enough to type by hand; cite a source for each row.
- MLB payroll: Lahman `Salaries` (≤2016), from a mirror that downloads in bulk. After 2016, try Spotrac or Cot's Contracts. Build `payroll_pct_of_cbt`.
- NHL cap hit: try PuckPedia, CapWages or Spotrac. Fill `cap_space_pct = (ceiling − team cap hit)/ceiling`.
- If the money sites are BLOCKED, **don't fight them**. Instead, write `data/manual/payroll_template.csv` (franchise_id, season, payroll, source_url) with the missing rows, so a person can fill it in, and say so in the report.

**Report and finish:**
- `DATA_DICTIONARY.md`: for each column, its definition, source, as-of timing, coverage, and leakage note.
- Final `data/processed/mlb_nhl_team_seasons.csv`: core columns first, in the teammate's order.
- A Spearman correlation table of features vs `y_doom_3yr` per league. This is for review only.

Commit. **Stop.**
