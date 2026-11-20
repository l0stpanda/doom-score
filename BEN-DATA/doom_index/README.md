# WNBA + PWHL Team Doom Index — data collection

Data-collection phase of a project that builds a comparable, evidence-based measure of how precarious each
professional women's basketball (WNBA) and hockey (PWHL) team's long-term outlook is.
**This phase collects, organises, validates and documents data only.** It does not train models, choose
weights, or compute a Doom Score.

* Snapshot date of the current data: **2026-11-19**.
* WNBA: seasons **2021–2026** (plus 2019–2020 team records as context for lag features). The 2026 season is complete
  (Golden State won the title on 2026-10-31).
* PWHL: **2023-24 (inaugural), 2024-25, 2025-26**. The 2026-27 season has not started (12 teams; first
  regular-season game 2026-12-04 per the league's stats feed, Dec 5 per press). Current rosters, contracts and
  expansion-team information for 2026-27 are in the snapshot tables.

## Final outputs

**Start here:** [`data/final/`](data/final/README.md). It holds two analysis-ready CSVs, one per league, with the same
columns (league-specific concepts excepted):

* `data/final/wnba_team_doom_dataset.csv`: 76 WNBA team-seasons (2021–2026) + 15 current-roster rows (2027)
* `data/final/pwhl_team_doom_dataset.csv`: 20 PWHL team-seasons (2023-24 → 2025-26) + 12 current-roster rows (2026-27)

Column prefixes separate performance (`perf_`, which includes the Y-axis win %), next-season outcomes (`out_`) and
candidate structural features (`age_`, `exp_`, `conc_`, `qual_`, `cont_`, `avail_`, `draft_`, `fin_`, `ctx_`).
Everything else in `data/` is upstream: the normalised tables the final files are built from, plus the raw cache.

## Quick start

```bash
pip install -r requirements.txt
python scripts/run_all.py            # 01 -> 06, uses the raw cache in data/raw/
python scripts/run_all.py --refresh  # re-download every source (old raw copies are archived)
```

Each script can also be run alone, e.g. `python scripts/01_collect_team_data.py --league PWHL`.
A full run from an empty cache takes roughly 10–12 minutes (Basketball-Reference requests are spaced ≥ 4 s apart);
a cached re-run takes under a minute. Re-runs **upsert** on primary keys, so they never append duplicate rows.

## Pipeline

| script | collects / builds | main outputs |
|---|---|---|
| `01_collect_team_data.py` | records, scoring, home/away, BBRef ratings & SOS, playoffs, lag features; cross-checks (ESPN for WNBA, Wikipedia standings for PWHL) | `team_season_data.csv`, `processed/team_record_crosschecks.csv` |
| `02_collect_player_data.py` | player-team-season stints: bio, age, experience, participation, production, advanced metrics, PWHLPA salaries; dated current rosters | `player_season_data.csv`, `processed/current_roster_snapshot.csv` |
| `03_collect_draft_data.py` | entry + expansion drafts, original owner vs. selecting team, trade notes, career outcomes, next-draft pick inventory | `draft_history.csv`, `processed/draft_pick_inventory.csv` |
| `04_collect_financial_data.py` | CBA parameters, team payroll aggregates where salaries exist, PWHL contract terms | `team_financials.csv`, `processed/contract_transactions.csv`, `processed/league_cba_parameters.csv` |
| `05_build_final_datasets.py` | the two final per-league CSVs (season rows + current-roster rows). **No score / weights** | `data/final/*.csv`, `data/final/feature_params.json` |
| `06_validate_data.py` | ~90 data-quality checks (incl. final-file parity, ranges, outcome alignment), missingness, collection report | `logs/validation_results.csv`, `logs/missingness_report.csv`, `docs/collection_report.md` |

Every collected value is traceable via `data/exports/team_season_sources.csv` (source URL, retrieval timestamp,
source update date, direct vs. calculated, calculation definition, verification status). Each script's docstring lists exactly
what it collects, sources, formulas and limitations.

## Documentation

* [`docs/data_dictionary.md`](docs/data_dictionary.md) — every field: definition, units, grain, source, calculation.
* [`docs/source_coverage_matrix.md`](docs/source_coverage_matrix.md) — which source covers which field and season, and what is missing and why.
* [`docs/collection_report.md`](docs/collection_report.md) — generated: row counts, season coverage, missingness, source coverage, validation warnings.
* `config/teams.csv`, `config/team_aliases.csv`, `config/player_name_aliases.csv` — stable IDs and documented name mappings.
* `config/cba_parameters.csv` — salary-cap / CBA values, each with its own source and verification status.

## Key definitions

* **Win percentage vs. points percentage.** `win_percentage = wins / games_played` in both leagues (PWHL wins include
  OT/SO wins). PWHL `points_percentage = points / (3 × games_played)` with 3-2-1-0 standings points. They are stored
  separately and must not be treated as interchangeable.
* **Age** = decimal years on the league-season's first regular-season game date (`age_at_reference`); the source's own
  integer age is kept as `age_source`.
* **Stints.** Traded players have one row per team with that team's games only.
* **Missing ≠ zero.** Nulls are never filled with zeros or imputed. Status columns explain why a value is missing.

## Known gaps (see the coverage matrix for detail)

1. **WNBA salaries cover 2021–2023 only.** They come from a CC BY 4.0 academic dataset on Mendeley Data that republishes
   Spotrac's player salary rankings for 2018–2023. These are cash earnings, prorated for short contracts, not cap hits.
   **WNBA 2024–2026 salaries and all WNBA contract terms are still missing:** Her Hoop Stats' robots.txt disallows
   generic crawlers, Spotrac returns 403 to scripts, and stats.wnba.com blocks scripted clients. None of these were
   bypassed. If you have legitimate access, fill `data/raw/manual/wnba_player_contracts.csv` from the template
   (instructions in `data/raw/manual/README.md`) and re-run 02–06.
2. **PWHL salaries cover 2025-26 only** (PWHLPA base salaries as of 2026-04-12; 77–93% of each team's players are listed).
   PWHL contract lengths come from Wikipedia transaction tables and cover signings since the 2025 offseason, so expiring-contract counts are lower bounds.
3. **Future draft picks:** WNBA 2027 order only; 2028+ not collected. No PWHL 2027 pick has been traded and no 2027
   draft page exists, so PWHL inventory is unknown rather than assumed.
4. **WNBA "current" rosters** (Wikipedia templates, November) still largely reflect end-of-2026 rosters before 2027
   free agency under the new CBA.
5. **No PWHL impact metric** (GAR/xG) or strength-of-schedule measure was collected.
6. Organisational events (coach/GM changes, ownership) are not yet collected (optional in the brief).

## Redistribution and terms

* `data/raw/` is git-ignored. It is a local cache of source responses, some of which carry redistribution limits.
* The **PWHLPA** salary guide states that its content may not be duplicated or redistributed. Salary columns in
  `player_season_data.csv` / `team_financials.csv` are for this course project; check with the PWHLPA before publishing them.
* Basketball-Reference data is © Sports Reference LLC. Requests are throttled per its published crawl limits. Do not
  republish bulk extracts.
* WNBA 2021–2023 salaries: Sitthiyot, T. (2026), "Annual salaries of athletes from 10 professional sports (2014–2023)",
  Mendeley Data, v1, doi:10.17632/38wkcb4pwb.1, licensed CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). The dataset credits Spotrac as its source. Changes made here: team codes
  mapped to franchise ids, names matched to Basketball-Reference players, and values aggregated to team payrolls.
* Wikipedia content is CC BY-SA. fastRhockey PWHL data is MIT-licensed and derived from official PWHL statistics
  ("Official statistics provided by Professional Women's Hockey League").

## Directory layout

```text
doom_index/
├── README.md, requirements.txt, .gitignore
├── config/        settings.py, teams.csv, team_aliases.csv, player_name_aliases.csv, cba_parameters.csv
├── scripts/       01_…06_ collectors, run_all.py, lib/ (http cache, table parsers, store, sources, salaries)
├── data/raw/      cached raw responses + .meta.json sidecars (git-ignored); raw/manual/ for optional user files
├── data/processed/ side tables read by 05/06 (roster snapshot, contracts, pick inventory, CBA parameters, cross-checks)
├── data/exports/  the five normalised tables required by the brief (team, player, draft, financial, sources)
├── data/final/    ★ the two analysis-ready per-league CSVs + README (column dictionary)
├── docs/          data dictionary, coverage matrix, generated collection report
└── logs/          run logs, validation_results.csv
```
