# Decisions log — MLB + NHL Doom data build

| ID | Decision | Alternatives | Why | Needs review (Y/N) |
|---|---|---|---|---|
| D01 | Put all work (`src/`, `data/`, `reports/`, this file) under `ADAM-DATA/`; removed `ADAM-DATA/dummy.txt` | Repo root | The repo has one folder per teammate; the readme says to delete dummy.txt once real files exist | N |
| D02 | Root `.gitignore` excludes `ADAM-DATA/data/raw/` | Commit raw JSON | Per ground rules; raw files can be rebuilt with `src/fetch_phase1.py` | N |
| D03 | MLB franchise = MLB Stats API team ID; `team` = the 2026 name for that ID | Hand-made name map | IDs checked: identical every season 1998–2026 (1997 is the 28-team subset). Expos→`washington-nationals`, Oakland/Sacramento→`athletics`, Indians→`cleveland-guardians`, Florida→`miami-marlins` | N |
| D04 | MLB `ties` = `leagueRecord.ties` (12 team-seasons have 1 tie); `games` = API gamesPlayed = W+L+T | Drop ties | Matches the teammate's `win_pct` formula; the "W+L=G" check fails only on these 12 rows | N |
| D05 | NHL franchise = NHL `franchiseId`; Thrashers (team 11) and Jets (52) already share franchise 35 → `winnipeg-jets` | Manual map | The NHL API links them itself | Y |
| D06 | Manual override: Phoenix/Arizona Coyotes franchise 28 → Utah franchise 40, `utah-mammoth` | Treat Utah as a new team (the NHL does) | Instructions ask for one continuous id; the roster and hockey operations moved together | Y |
| D07 | NHL `ties` = OTL (+ real ties in 2002–03/2003–04); added `ot_losses`, `win_pct_raw = W/GP` | `ties` = 0 | Makes `win_pct` equal NHL points %: max abs diff vs API pointPct is 1e-5 | Y |
| D08 | Trailing/diff/slope features use the franchise's previous *played* seasons, so NHL 2005 looks back to 2003, 2002 | Treat 2004 as missing → NaN | 2004–05 was cancelled; no information is lost | Y |
| D09 | `win_pct_trailing_3_seasons` uses min 1 season; `win_pct_slope_3yr` (OLS over t-2..t) needs ≥2; added `seasons_of_history` | Require all 3 seasons | Keeps expansion teams (VGK, SEA) in the data; the count column shows when there is less history | Y |
| D10 | Percentile uses average rank; when the top or bottom team is tied, the endpoints are not exactly 0/100 (11 league-season endpoints) | min/max rank | The spec says "average rank"; this is the consequence | N |
| D11 | Labels = percentile in the franchise's next 3 played seasons; `y_doomed_bottom25` is NA when `y_doom_3yr` is NA | — | Per spec | N |
| D12 | Output rows: MLB 2000–2026, NHL 2005–2025; history-only seasons (MLB 1997–99, NHL 2002–03) are dropped after feature build | Keep them | Spec: fetched only for trailing features | N |
| D13 | Pythag uses runs/goals as the API reports them (NHL GF includes shootout-decider goals) | Strip SO goals | Not available from this endpoint; small effect | Y |
| D14 | `short_season` flags MLB 2020 and NHL 2012, 2019, 2020 (start years) | — | Per spec | N |
| D15 | Teammate file `doom_nba_nfl_team_seasons_enriched.csv` is not in the repo → percentile formula not cross-checked against it | — | Must be checked once that file exists | Y |
| D16 | Extra columns kept for audit: `team_name_then`, `team_id` (source team ID) | Drop them | Helps review relocations; not features | N |
