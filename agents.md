# Agent Brief: WNBA + PWHL Team Doom Index

## Project overview

Build a data-first sports analytics project that develops a comparable,
evidence-based way to assess how precarious the future outlook of
professional women's sports teams is.

The project covers: - **WNBA:** seasons 2021--2026. - **PWHL:** from its
inaugural 2023--24 season onward, through the latest available data. -
**Current snapshot:** use the latest completed season for performance,
plus the latest available roster, contract, draft, and financial
information. As of the project brief date (2026-11-16), the 2026 WNBA
season is complete; the PWHL 2026--27 season has not yet begun and is
scheduled to begin in December 2026. Verify these dates and statuses
from authoritative sources before relying on them.

The intended final visualization is a scatter plot: - **X-axis:** Team
Doom Score (higher = more concerning long-term outlook). - **Y-axis:**
Current win percentage. - Current win percentage must remain
conceptually separate from the Doom Score. Do not include current win
percentage as a component of the score if it is also plotted on the
Y-axis.

The project ultimately has two goals: 1. Rank teams by their current
doom / long-term franchise outlook. 2. Explore whether historical team
characteristics can help predict future performance.

## Critical scope boundary: data collection only

At this stage, focus **only on data collection, data organization, data
quality, and transparent feature construction**.

Do not: - Train machine-learning models. - Choose Doom Score weights. -
Calculate a final Doom Score. - Decide in advance which features are
most important. - Build the final visualization yet. - Present
speculative or unavailable values as facts.

The modeling phase is intentionally exploratory. Historical data should
help investigate which features are meaningful, which are redundant, and
which have predictive value. Preserve raw variables so alternative
definitions and models can be tested later.

## Data design

Use modular, reproducible Python collection scripts and CSV outputs.
Prefer a normalized structure with separate team-, player-, draft-, and
financial-level data. Preserve raw/source fields as well as calculated
fields.

### 1. `team_season_data.csv`

**Grain:** one row per team per season.

Collect, where available:

**Identifiers** - `league` (WNBA or PWHL) - `team_name` - `team_id` or
stable franchise/team identifier - `season` - `season_start_year` -
`season_end_year`

**Record and performance** - `wins` - `losses` - `ties` (if
applicable) - `overtime_losses` (if applicable) - `games_played` -
`win_percentage` (wins / games played; retain the exact definition) -
`points` / standings points (where applicable) - `points_percentage`
(especially relevant for hockey; retain separately from win
percentage) - `points_for` - `points_against` - `point_differential` -
`goals_for` and `goals_against` for hockey, where available - home and
away records, if reliably available - strength-of-schedule measure, only
if a defensible source or calculation is available

**Historical performance** - playoff qualification / appearance -
playoff wins and losses - championship / title result - prior-season win
percentage - year-over-year change in win percentage - rolling
multi-season performance (e.g. three-season average), only when enough
prior seasons exist

Do not silently equate WNBA win percentage with PWHL points percentage.
Store the underlying record and both relevant percentage measures where
possible.

### 2. `player_season_data.csv`

**Grain:** one row per player per team per season. If a player changes
teams during a season, preserve team-specific stints or document a
consistent approach; do not duplicate a season total as if it were a
team-specific statistic.

**Identifiers** - `league` - `season` - `player_name` - stable
`player_id` where available - `team_name` - `team_id` - `position`

**Player characteristics** - age (document the age reference date /
calculation convention) - years of professional experience, where
available - height and other basic roster characteristics only if
consistently sourced and useful

**Roster / participation** - roster status - games played - games
started, where available - minutes played / average minutes for
basketball - time on ice / average time on ice for hockey, where
available - games dressed / appearances, where available

**WNBA performance** - points - rebounds - assists - steals - blocks -
turnovers - shooting percentages and attempts (FG%, 3P%, FT%, where
available) - minutes - advanced metrics such as BPM, Win Shares, or
other reputable impact metrics, if source coverage and definitions are
documented

**PWHL performance** - goals - assists - points - shots - plus/minus
(retain with caveat) - goalie-specific statistics where applicable (save
percentage, goals-against average, goals saved above expected, etc.,
where available) - time on ice and other advanced metrics where
available - GAR or other impact metrics only when a credible source
provides them

**Contract information** - salary / cap hit / base salary, as
appropriate to the league and CBA - contract start and end dates, where
available - contract status - guaranteed compensation, where available -
free-agent status (RFA/UFA or league equivalent), where available

Do not assume a field exists just because it is listed here. Record
missingness and source limitations explicitly.

### 3. `draft_history.csv`

**Grain:** one row per draft selection / pick.

Collect: - league - draft year - draft name / event - round - overall
pick number - pick number within round - player selected - player ID, if
available - position - original drafting team - team that ultimately
held / exercised the pick, if different - pick acquisition method
(original, trade, compensation, etc.) where known - whether the pick was
traded - traded-to / traded-from team and transaction details, where
available - player career games / appearances - career production
statistics appropriate to the league - a transparent, reproducible
career-outcome measure only if later defined and justified

Also collect **future draft-pick inventory** by team and draft year: -
picks owned - round and expected pick slot, if known - original owner -
current rights holder - whether conditional / protected - trade source
and destination, if known

Do not assume a team's original pick is still owned by that team.
Distinguish original ownership from current rights ownership. Do not
fabricate future pick positions when they are unknown.

### 4. `team_financials.csv`

**Grain:** one row per team per season (and, where useful, a dated
snapshot for current financial information).

Collect, when publicly available and comparable: - league - team -
season / snapshot date - league salary cap - team salary commitments /
cap hit - cap space - percentage of cap committed - guaranteed salary /
compensation - total base salaries - average salary - salary
concentration (e.g. top-five players' share of team payroll), if the
underlying player salaries are sufficiently complete - expiring salary /
commitments - number of expiring contracts - number of players with
RFA/UFA or equivalent status - future-year commitments - relevant CBA /
salary-cap regime identifier or notes

Financial definitions differ between leagues and may change over time.
Preserve the source's terminology and document whether each amount is
base salary, cap hit, guaranteed compensation, or another measure. Do
not compare unlike measures as though they were equivalent.

### 5. `team_season_sources.csv` (provenance / audit table)

Record source-level provenance for collected values or groups of
values: - league - team (if applicable) - season - dataset / variable
name - source organization - source URL - retrieval timestamp - source
publication / update date, if available - whether the value is directly
sourced or calculated - calculation definition, if applicable -
missing-data / quality notes - confidence or verification status, if a
clear rubric is defined

Cite and preserve source URLs in the data. Prefer official league, team,
players' association, and CBA sources; use reputable specialist
databases when official data are unavailable. Cross-check important
values when possible.

## Additional features to consider collecting

These are candidate variables, not predetermined Doom Score components:

**Roster age and composition** - average roster age - median roster
age - average age of top contributors (define contribution using a
transparent metric) - average age of top five players (WNBA) / top eight
players (PWHL), if appropriate - percentage of roster under 25 -
percentage over 30 - average professional experience - roster size -
number of young players with meaningful playing time

**Roster quality / concentration** - total and minutes-weighted player
production - number of above-average contributors (only after defining
the comparison population) - production of top players - share of team
production generated by the top players - dependence on one or a few
high-usage / high-minute players - availability / games missed, if
reliable

**Contracts and retention** - expiring contracts - free-agent counts by
type - salary committed to expiring players - future salary
commitments - player retention / turnover between seasons

**Organizational stability (optional / secondary)** - head coach
changes - general manager changes - ownership / relocation / expansion
context - major roster rebuilds - player departures and acquisitions

Organizational variables may be harder to quantify consistently. Collect
only verifiable events, with dates and sources, and keep them separate
from core quantitative data.

## Candidate project structure

Use a clear structure such as:

``` text
doom_index/
├── README.md
├── requirements.txt
├── config/
│   └── settings.py
├── scripts/
│   ├── 01_collect_team_data.py
│   ├── 02_collect_player_data.py
│   ├── 03_collect_draft_data.py
│   ├── 04_collect_financial_data.py
│   ├── 05_build_team_features.py
│   └── 06_validate_data.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── exports/
└── logs/
```

Expected primary CSV exports: - `team_season_data.csv` -
`player_season_data.csv` - `draft_history.csv` - `team_financials.csv` -
`team_season_sources.csv`

Keep raw downloads / API responses where licensing and source terms
permit. Do not overwrite raw data with transformed data.

## Script responsibilities

### `01_collect_team_data.py`

Collect historical and latest team standings / results, records,
scoring, point differential, playoff results, and related team-season
facts for both leagues.

### `02_collect_player_data.py`

Collect season rosters, player identifiers, ages, positions,
participation, performance statistics, and available contract fields.
Handle players changing teams carefully.

### `03_collect_draft_data.py`

Collect historical draft selections and future pick ownership /
transactions. Preserve original drafting team and current rights holder
separately.

### `04_collect_financial_data.py`

Collect salary caps, team commitments, cap room, player salaries,
contract terms, and free-agent / expiring-contract information where
reliable.

### `05_build_team_features.py`

Join / aggregate player, draft, and financial records into
team-season-level derived features, such as average age, age
distribution, roster experience, player-production summaries, and
draft-pick counts. This script may calculate descriptive features, but
**must not calculate a Doom Score or assign feature weights**.

### `06_validate_data.py`

Run data-quality checks: - duplicate primary keys - missing team-season
observations - inconsistent team names / IDs - impossible or
inconsistent records - percentage calculations - mismatched season
labels - players assigned to incorrect teams or duplicated incorrectly -
invalid draft pick ownership - missing / suspicious financial values -
source and retrieval metadata - schema consistency across repeated runs

## Data collection and engineering standards

1.  **Make scripts transparent.** Each script must begin with a clear
    docstring describing:

    -   exactly what it collects
    -   leagues and seasons covered
    -   output file(s)
    -   source websites / APIs
    -   fields collected
    -   derived fields and formulas
    -   known limitations

2.  **Document every field.** Maintain a data dictionary
    (e.g. `README.md` or `data_dictionary.md`) with field name,
    definition, units, grain, source, and calculation method.

3.  **Use stable identifiers.** Team names can change; maintain stable
    team / franchise IDs where possible and a documented name-alias
    mapping. Do the same for players.

4.  **Preserve season semantics.** Explicitly define season labels,
    especially for PWHL seasons such as `2023-24`. Do not confuse
    calendar year with season year.

5.  **Preserve raw and derived values.** Store wins and games played as
    well as win percentage; store source values as well as calculated
    cap space or roster aggregates.

6.  **Handle missing data honestly.** Use null / empty values rather
    than fabricated values or unjustified zeroes. Distinguish "not
    applicable," "not reported," and "not yet available" where feasible.

7.  **Do not silently impute.** No statistical imputation during
    collection. Missing-data handling belongs in later analysis and must
    be documented.

8.  **Make collection reproducible and incremental.** Rerunning scripts
    should update or upsert records using defined keys, not append
    duplicate rows. Include request throttling, retries, caching where
    appropriate, and useful logs.

9.  **Respect source terms and access limits.** Prefer official APIs /
    downloadable data. Do not bypass paywalls, authentication, or
    anti-bot protections. If a source is inaccessible, document it and
    identify a legitimate alternative.

10. **Verify freshness.** Store retrieval timestamps and source update
    dates. For "current" data, identify the snapshot date.

11. **Avoid false precision.** If historical salary, contract, or
    advanced-stat coverage is incomplete, make that visible. Do not
    imply a complete historical series where only partial information
    exists.

12. **Separate league-specific definitions.** WNBA and PWHL have
    different roster, salary, schedule, and standings structures. Keep
    raw league-specific variables and definitions, then create carefully
    documented comparable features only where justified.

## Sources to investigate

Start with authoritative and specialist sources, verifying URLs and
coverage before coding:

**WNBA** - Official WNBA standings, schedules, rosters, transactions,
and draft records. - Her Hoop Stats for salary / cap information and
basketball statistics, subject to availability and access. -
Basketball-Reference or other reputable statistical archives for
historical player / team statistics, where permitted. - Official CBA and
players' association materials for salary-cap and contract definitions.

**PWHL** - Official PWHL standings, schedules, rosters, transactions,
and draft records. - PWHLPA materials for salary and contract
information, where publicly available. - PWHLStats or other reputable
hockey statistical databases for historical player / team statistics. -
Official league and players' association materials for CBA and
salary-cap definitions.

Do not assume that any one source covers every requested field or
season. Build a source-coverage matrix before implementing each
collector. Verify all source links and data access methods directly.

## Historical analysis intent (for later, not now)

The historical dataset should eventually support questions such as: - Do
older rosters tend to decline, or does the age of top contributors
matter more than average age? - Does draft capital relate to future
performance? - Does salary-cap flexibility relate to improvement? - Does
player-production concentration make a team fragile? - Do expiring
contracts predict roster decline or improvement? - Are point
differential and win percentage telling different stories? - Which
features predict future win percentage over one, two, or three seasons?

These are research questions, not assumptions. Do not bake answers into
the data collection scripts.

## Current visualization intent (for later)

The eventual scatter plot places: - X = Doom Score. - Y = current win
percentage.

The Doom Score should represent structural / forward-looking risk, not
simply restate current performance. The exact score definition and
feature weights will be explored after data collection and historical
exploratory analysis.

## Immediate execution plan

1.  Inspect the project directory and existing code before creating or
    changing files.
2.  Create the project structure and a clear README / data dictionary.
3.  Build a source-coverage matrix listing each desired field, source,
    seasons covered, availability, and limitations.
4.  Implement and test team standings collection first.
5.  Implement player / roster collection next.
6.  Add draft history and future pick ownership.
7.  Add salary and contract data, clearly marking gaps.
8.  Build team-level descriptive features from the raw player and team
    datasets.
9.  Run validation and produce a concise collection report showing row
    counts, season coverage, missingness, and source coverage by league.
10. Do not proceed to modeling or Doom Score construction until
    explicitly asked.

## Definition of done for the data-collection phase

The phase is complete when: - The scripts run reproducibly. - Each
script clearly states exactly what it collects. - The CSV schemas and
data dictionary are documented. - WNBA 2021--2026 and PWHL inaugural
season onward are covered to the extent data are publicly available. -
Current roster / financial snapshots are dated. - Missing and
unavailable fields are explicitly reported. - Duplicate and consistency
checks pass or produce documented warnings. - Sources are traceable for
all collected values. - No Doom Score weights, final score, or
predictive model have been introduced.
