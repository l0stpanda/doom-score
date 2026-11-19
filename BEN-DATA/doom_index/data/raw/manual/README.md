# Manual source files (optional)

Scripts read these files **only if present**. They exist for data that has no
permitted automated source.

## `wnba_player_contracts.csv`

WNBA player salaries / contract terms. Her Hoop Stats disallows generic crawlers
(robots.txt) and Spotrac returns HTTP 403 to scripted clients, so the pipeline
does not scrape either. If you have legitimate access (e.g. a Her Hoop Stats
subscription whose terms allow this use, or figures transcribed from official
team/league announcements), copy `wnba_player_contracts.template.csv` to
`wnba_player_contracts.csv` and fill one row per player-team-season:

| column | meaning |
|---|---|
| season | WNBA season year, e.g. `2026` |
| team | team name or city (resolved via `config/team_aliases.csv`) |
| player_name | as printed by the source (matched with documented name normalisation) |
| salary_usd | amount in USD |
| salary_measure | e.g. `base salary`, `cap hit`, `guaranteed` - do not mix measures without saying so |
| contract_start_year / contract_end_year | seasons covered |
| contract_type | e.g. rookie scale, veteran, developmental, hardship |
| guaranteed_usd | guaranteed portion, if known |
| free_agent_status_next | e.g. UFA / RFA / reserved / core-designated |
| source_organization, source_url, source_as_of_date | provenance for the row |

Then re-run `02`, `04`, `05`, `06`. Matched rows get `contract_data_status = manual_import`.
