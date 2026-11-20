# MLB + NHL doom dataset: guide

*Files: **`data/processed/mlb_nhl_model_slim.csv`** (1,454 rows × 27 columns, the table to model from) and the full `data/processed/mlb_nhl_team_seasons.csv` (1,454 rows × 104 columns, a superset). All numbers come from `docs/make_doc_stats.py`. D-numbers refer to `DECISIONS.md`.*

## 1. Model table (slim): start here

`mlb_nhl_model_slim.csv` has the same rows as the full table and 27 of its columns: identifiers and the season-t record, **one `_lpct` feature per concept**, two flags, and the labels. Columns were **chosen by concept, not by correlation with the label** (D61). Where a concept has several candidate columns, the one listed in `FEATURE_CROSSWALK.md` is used. `SLIM_SELECTION.md` lists all 104 full-table columns as kept or dropped, with a reason for each. The other 77 columns are under [Extended columns](#4-extended-columns-full-table-only) below.

`_lpct` = within-league-season percentile, 0 = lowest value that season, 100 = highest (same formula as `win_pct_percentile`, D59). Use these when stacking MLB and NHL: raw units differ. Missing values are left missing: `spending_lpct` is empty for every NHL row (D57), `underlying_quality_lpct` for NHL 2005–07, `gm_tenure_lpct` where the GM is vacant or unknown, `ot_losses` for MLB.

| Column | Group | Definition | Built from | Coverage |
|---|---|---|---|---|
| `league` | id | `MLB` or `NHL`. | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `season_start_year` | id | Calendar year the season starts (NHL `2017` = 2017–18). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `franchise_id` | id | Lowercase-hyphenated *current* franchise name, constant through moves and renames (D03, D05, D06). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `team` | id | Franchise's current (2026) name, the same for every year. | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `wins` | id | Regular-season wins (source: league standings API). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `losses` | id | Regular-season losses; NHL: regulation losses only. | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `ot_losses` | id | NHL overtime + shootout losses. | — | MLB 0%; NHL 100% (2005–2025) |
| `games` | id | Games played (MLB W+L+T; NHL W+L+OTL). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `win_pct` | id | (wins + 0.5 × ties) / games. NHL: equals points % (D07). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `margin_per_game_lpct` | feature | Within league-season percentile (0–100): (scored - allowed) / games | `margin_per_game` ← MLB `point_diff_per_game` / NHL `point_diff_per_game` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `luck_lpct` | feature | Within league-season percentile (0–100): win_pct - Pythagorean win% | `luck` ← MLB `luck` / NHL `luck` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `underlying_quality_lpct` | feature | Within league-season percentile (0–100): Quality beyond W-L record | `underlying_quality` ← MLB `pythag_win_pct` / NHL `corsi_pct` | MLB 100% (2000–2026); NHL 86% (2008–2025) |
| `roster_age_weighted_lpct` | feature | Within league-season percentile (0–100): Playing-time-weighted roster age | `roster_age_weighted` ← MLB `age_weighted` / NHL `age_weighted` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `star_concentration_lpct` | feature | Within league-season percentile (0–100): Top-3 players' share of team production | `star_concentration` ← MLB `top3_concentration` / NHL `top3_concentration` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `draft_capital_lpct` | feature | Within league-season percentile (0–100): Picks in rounds 1-2 of the year-t draft | `draft_capital` ← MLB `draft_picks_rd1_2` / NHL `draft_picks_rd1_2` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `gm_tenure_lpct` | feature | Within league-season percentile (0–100): GM tenure at the prediction moment | `gm_tenure` ← MLB `personnel_lead_tenure_years` / NHL `personnel_lead_tenure_years` | MLB 94% (2000–2026); NHL 100% (2005–2025) |
| `coach_tenure_lpct` | feature | Within league-season percentile (0–100): Manager/head-coach tenure at end of regular season | `coach_tenure` ← MLB `coach_tenure_years` / NHL `coach_tenure_years` | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `spending_lpct` | feature | Within league-season percentile (0–100): Payroll relative to league-season mean | `spending` ← MLB `payroll_rel_league_mean` / NHL **unavailable** | MLB 100% (2000–2026); NHL 0% |
| `win_pct_percentile` | feature | Within league-season: (average rank − 1)/(n − 1) × 100 of win_pct; worst 0, best 100 (D10). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `win_pct_trailing_3_seasons` | feature | Mean win_pct of the franchise's last 3 played seasons incl. t (min 1; D08, D09). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `short_season` | flag | True for MLB 2020 and NHL 2012–13, 2019–20, 2020–21 (D14). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `seasons_of_history` | flag | Number of franchise seasons available up to t (history fetched from 1997 MLB / 2002 NHL). | — | MLB 100% (2000–2026); NHL 100% (2005–2025) |
| `y_doom_3yr` | label | 100 − mean(y_pct_t1, y_pct_t2, y_pct_t3); NaN unless all three exist (D11). | — | MLB 89% (2000–2023); NHL 85% (2005–2022) |
| `y_doomed_bottom25` | label | y_doom_3yr ≥ 75 (binary). | — | MLB 89% (2000–2023); NHL 85% (2005–2022) |
| `y_pct_t1` | label | win_pct_percentile in season t+1. | — | MLB 96% (2000–2025); NHL 95% (2005–2024) |
| `y_pct_t2` | label | win_pct_percentile in season t+2. | — | MLB 93% (2000–2024); NHL 90% (2005–2023) |
| `y_pct_t3` | label | win_pct_percentile in season t+3. | — | MLB 89% (2000–2023); NHL 85% (2005–2022) |

### Slim column details

**`league`**  
- Definition: `MLB` or `NHL`.
- Plain English: Which league the row belongs to.
- Why it might relate to doom: Not a predictor; use it to group or stratify.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `MLB`, `NHL`

**`season_start_year`**  
- Definition: Calendar year the season starts (NHL `2017` = 2017–18).
- Plain English: The season this row describes.
- Why it might relate to doom: Not a predictor; defines time order for train/test splits.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 2,000 / 2,014 / 2,026

**`franchise_id`**  
- Definition: Lowercase-hyphenated *current* franchise name, constant through moves and renames (D03, D05, D06).
- Plain English: A stable ID for the club across its history.
- Why it might relate to doom: Not a predictor; use it to follow a club over time.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `arizona-diamondbacks`, `athletics`

**`team`**  
- Definition: Franchise's current (2026) name, the same for every year.
- Plain English: The club's name today.
- Why it might relate to doom: Not a predictor.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `Arizona Diamondbacks`, `Athletics`

**`wins`**  
- Definition: Regular-season wins (source: league standings API).
- Plain English: Games won.
- Why it might relate to doom: Better teams now tend to stay better (persistence).
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 15 / 63.00 / 116

**`losses`**  
- Definition: Regular-season losses; NHL: regulation losses only.
- Plain English: Games lost (in hockey, losses in normal time).
- Why it might relate to doom: Mirror of wins.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 7 / 65.00 / 121

**`ot_losses`**  
- Definition: NHL overtime + shootout losses.
- Plain English: Hockey games lost after the normal 60 minutes.
- Why it might relate to doom: Close losses; partly luck.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 9.00 / 20.00

**`games`**  
- Definition: Games played (MLB W+L+T; NHL W+L+OTL).
- Plain English: How many games the team played.
- Why it might relate to doom: Flags short seasons.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 48 / 162.0 / 163

**`win_pct`**  
- Definition: (wins + 0.5 × ties) / games. NHL: equals points % (D07).
- Plain English: Share of games won, with half credit for ties / overtime losses.
- Why it might relate to doom: Current quality; the strongest single predictor.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.253 / 0.531 / 0.823

**`margin_per_game_lpct`**  
- Definition: Within league-season percentile of `margin_per_game`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `margin_per_game` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`luck_lpct`**  
- Definition: Within league-season percentile of `luck`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `luck` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`underlying_quality_lpct`**  
- Definition: Within league-season percentile of `underlying_quality`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `underlying_quality` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 86% (2008–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`roster_age_weighted_lpct`**  
- Definition: Within league-season percentile of `roster_age_weighted`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `roster_age_weighted` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`star_concentration_lpct`**  
- Definition: Within league-season percentile of `star_concentration`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `star_concentration` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`draft_capital_lpct`**  
- Definition: Within league-season percentile of `draft_capital`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `draft_capital` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 48.28 / 100.0

**`gm_tenure_lpct`**  
- Definition: Within league-season percentile of `gm_tenure`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `gm_tenure` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 94% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`coach_tenure_lpct`**  
- Definition: Within league-season percentile of `coach_tenure`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `coach_tenure` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`spending_lpct`**  
- Definition: Within league-season percentile of `spending`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `spending` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`win_pct_percentile`**  
- Definition: Within league-season: (average rank − 1)/(n − 1) × 100 of win_pct; worst 0, best 100 (D10).
- Plain English: Where the team finished relative to the rest of its league that year.
- Why it might relate to doom: Current standing; the doom label is built from future values of this.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`win_pct_trailing_3_seasons`**  
- Definition: Mean win_pct of the franchise's last 3 played seasons incl. t (min 1; D08, D09).
- Plain English: Average record over the last three seasons.
- Why it might relate to doom: Smooths one-season noise.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.323 / 0.525 / 0.715

**`short_season`**  
- Definition: True for MLB 2020 and NHL 2012–13, 2019–20, 2020–21 (D14).
- Plain English: Seasons cut short (lockout or pandemic).
- Why it might relate to doom: Records from short seasons are noisier.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): share True = 8.4%

**`seasons_of_history`**  
- Definition: Number of franchise seasons available up to t (history fetched from 1997 MLB / 2002 NHL).
- Plain English: How much past data exists for this club.
- Why it might relate to doom: Low values = less reliable trailing features (expansion teams).
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 1 / 15.00 / 30

### Labels: never use these as features

These columns describe seasons *t+1* to *t+3*. Using any of them, or anything computed from them, as a model input is leakage.

**`y_doom_3yr`**  
- Definition: 100 − mean(y_pct_t1, y_pct_t2, y_pct_t3); NaN unless all three exist (D11).
- Plain English: The doom score: higher = worse finishes over the next three seasons.
- Why it might relate to doom: **The target.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 89% (2000–2023); NHL 85% (2005–2022)
- Typical range (min / median / max): 1.15 / 48.85 / 100.0

**`y_doomed_bottom25`**  
- Definition: y_doom_3yr ≥ 75 (binary).
- Plain English: Whether the team averaged a bottom-quarter finish over the next three seasons.
- Why it might relate to doom: **Binary target.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 89% (2000–2023); NHL 85% (2005–2022)
- Typical range (min / median / max): share True = 18.1%

**`y_pct_t1`**  
- Definition: win_pct_percentile in season t+1.
- Plain English: Standing next season.
- Why it might relate to doom: **Label.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 96% (2000–2025); NHL 95% (2005–2024)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`y_pct_t2`**  
- Definition: win_pct_percentile in season t+2.
- Plain English: Standing two seasons ahead.
- Why it might relate to doom: **Label.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 93% (2000–2024); NHL 90% (2005–2023)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`y_pct_t3`**  
- Definition: win_pct_percentile in season t+3.
- Plain English: Standing three seasons ahead.
- Why it might relate to doom: **Label.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 89% (2000–2023); NHL 85% (2005–2022)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

## 2. Quick start

**One row = one team in one season *t*.** Key columns:
- `league`, `season_start_year`, `franchise_id`: identify the row (NHL `2017` = the 2017–18 season).
- `win_pct_percentile`: where the team finished in its league that season.
- The nine concept features, as `_lpct` columns (e.g. `roster_age_weighted_lpct`, `spending_lpct`); see section 1.
- Labels: `y_doom_3yr` (0–100, higher = more doomed) and `y_doomed_bottom25` (yes/no).

**Reading a percentile.** Within one league and season, teams are ranked by record; the worst gets 0, the best 100, everyone else in between (ties share an average rank). A 75 means the team finished ahead of about three quarters of the league. Because it is relative, percentiles are comparable across leagues and years even though records are not.

**Worked example: high doom.** Houston Astros (MLB), season 2010:

| Season | Percentile |
|---|---|
| 2010 (now, 76–86) | 27.6 |
| 2011 | 0.0 |
| 2012 | 0.0 |
| 2013 | 0.0 |

Average of the next three: 0.0 → doom = 100 − 0.0 = **100.0** (stored `y_doom_3yr` = 100.0; `y_doomed_bottom25` = True).

**Worked example: low doom.** Los Angeles Dodgers (MLB), season 2019:

| Season | Percentile |
|---|---|
| 2019 (now, 106–56) | 96.6 |
| 2020 | 100.0 |
| 2021 | 96.6 |
| 2022 | 100.0 |

Average of the next three: 98.9 → doom = 100 − 98.9 = **1.1** (stored `y_doom_3yr` = 1.1; `y_doomed_bottom25` = False).

Labels exist only for seasons with three played follow-up seasons: MLB through 2023, NHL through 2022–23.

## 3. Sports primer

### MLB (baseball)

**Season.** 30 teams each play a 162-game regular season (median `games` = 162), from spring to early fall, followed by playoffs ending with the World Series in October/November. The 2020 season was cut by the pandemic (58–60 games per team in the data).

**Standings.** Teams are ranked by wins and losses. Ties are rare (games are normally played until someone wins); 12 team-seasons here include one.

**GM vs manager.** The *general manager* (GM) builds the roster: trades, free-agent signings, the draft. Some clubs place a "president of baseball operations" above the GM; this dataset uses the GM (D36). The *manager* is the in-game boss who sets lineups and makes game decisions (the equivalent of a head coach).

**Draft.** Each summer teams select amateur players (high school and college). The draft is long (`draft_rounds_in_year` ranges 8–52 round labels here, counting bonus rounds), and drafted players usually take years to reach the major leagues.

**Payroll and the luxury tax.** MLB has no salary cap. Teams that spend above a threshold pay a *Competitive Balance Tax* ("luxury tax") on the excess. The threshold in this data runs from $117.0M (2003) to $244.0M (2026); there was no tax in 2000–02. "Opening Day payroll" is the salary total of the roster when the season starts.

**Plate appearances and batters faced.** A *plate appearance* (PA) is one completed turn at bat by a hitter. *Batters faced* (BF) counts the hitters a pitcher pitched to. PA + BF is used as a measure of how much a player played.

### NHL (hockey)

**Season.** 30–32 teams (expansion: Vegas 2017, Seattle 2021) each play 82 regular-season games (median `games` = 82), October to April, then playoffs ending with the Stanley Cup final in June. Shortened seasons: 2012–13 (lockout), 2019–20 and 2020–21 (pandemic).

**Standings, overtime losses and points %.** A win earns 2 points. A game tied after 60 minutes goes to overtime and then a shootout. The loser of an overtime or shootout game is credited with an *overtime loss* (OTL) and still earns 1 point; a regulation loss earns 0. *Points %* = points / (2 × games). In this dataset `win_pct` equals points % because OTLs are stored in `ties` and get half credit (D07).

**GM vs head coach.** The GM builds the roster; the *head coach* runs practices and games.

**Draft.** Each June teams pick junior and amateur players; every NHL draft in this data has 7 rounds. Worse teams generally pick earlier.

**Salary cap.** The NHL has a hard cap: each team's total *cap hit* (average annual salary of its contracts) must stay under an upper limit, $39.0M in 2005–06 rising to $104.0M in 2026–27 (2012–13 shows the pro-rated $60.0M). Team cap hits are not in this dataset.

**Time on ice.** *Time on ice* (TOI) is how long a player was on the ice; it is the hockey measure of playing time here.

**Corsi, expected goals and PDO.** *Corsi %* is the team's share of all shot attempts (shots, misses, blocked shots) in its games; teams that control the puck tend to win later. *Expected goals %* (xG %) weights each shot by how likely a shot like it is to score (from a model), then takes the team's share. *PDO* is 5-on-5 shooting % plus save %; it averages about 1.000 and extreme values usually do not last, so it is read as a luck gauge.

## 4. Extended columns (full table only)

The 77 columns below are in `mlb_nhl_team_seasons.csv` but not in the slim table: raw concept aliases (league units), league source columns, alternatives, audit columns and the duplicate label. Grouped by concept in the order of `FEATURE_CROSSWALK.md`, then the remaining columns. "Coverage" is the share of rows that are non-missing, per league. "Typical range" is min / median / max over all rows.

### Playing-time weight

**`playing_time_weight`**  
- Definition: Text: `PA+BF` (MLB) or `TOI` (NHL) (D58).
- Plain English: Which measure of playing time the roster features are weighted by.
- Why it might relate to doom: Descriptor only.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `PA+BF`, `TOI`

**`team_pa`**  
- Definition: Sum of player plate appearances; equals the official team total (D46).
- Plain English: Total turns at bat by the team's hitters.
- Why it might relate to doom: Audit; the weight behind MLB roster features.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 2,011 / 6,172 / 6,537

**`team_bf`**  
- Definition: Sum of batters faced by the team's pitchers; equals the official total.
- Plain English: Total batters the team's pitchers faced.
- Why it might relate to doom: Audit.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 1,989 / 6,172 / 6,559

**`skater_gp_sum`**  
- Definition: Sum of skater games played (≈18 per team game).
- Plain English: Total skater appearances.
- Why it might relate to doom: Audit.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 100% (2005–2025)
- Typical range (min / median / max): 863.0 / 1,476 / 1,477

**`goalie_gp_sum`**  
- Definition: Sum of goalie games played.
- Plain English: Total goalie appearances.
- Why it might relate to doom: Audit.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 100% (2005–2025)
- Typical range (min / median / max): 49.00 / 87.00 / 97.00

**`roster_players_used`**  
- Definition: Players with playing time for the team in t.
- Plain English: How many different players the team used.
- Why it might relate to doom: Lots of players can signal injuries or churn.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 26 / 42.00 / 71

**`age_weight_coverage`**  
- Definition: Share of playing time with a known birthdate.
- Plain English: Data-quality check for the age features.
- Why it might relate to doom: Audit only.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 100.0%

### roster_age_weighted

**`roster_age_weighted`**  
- Definition: **Shared concept.** Copy of MLB `age_weighted` / NHL `age_weighted` (D58).
- Plain English: Average age of the team, counting players by how much they played.
- Why it might relate to doom: Old rosters may decline; young ones may improve.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 25.41 / 28.63 / 33.73

**`age_weighted`**  
- Definition: Playing-time-weighted mean age; age on MLB Jun 30 of t / NHL Feb 1 of t+1; weights MLB PA+BF, NHL TOI per team stint (D45).
- Plain English: Average age of the team, counting players by how much they played.
- Why it might relate to doom: Old rosters may decline; young ones may improve.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 25.41 / 28.63 / 33.73

**`age_weighted_hitters`**  
- Definition: MLB PA-weighted age.
- Plain English: Average age of the hitters.
- Why it might relate to doom: Ageing bats.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 25.32 / 28.96 / 34.50

**`age_weighted_pitchers`**  
- Definition: MLB batters-faced-weighted age.
- Plain English: Average age of the pitchers.
- Why it might relate to doom: Ageing arms.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 25.70 / 28.83 / 34.61

### vet_share

**`vet_share`**  
- Definition: **Shared concept.** Copy of MLB `share_production_age32plus` / NHL `share_production_age32plus` (D58).
- Plain English: How much of the playing time went to veterans aged 32 or older.
- Why it might relate to doom: Veteran-heavy teams may fall off as players age.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 0.203 / 0.643

**`vet_share_lpct`**  
- Definition: Within league-season percentile of `vet_share`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `vet_share` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`share_production_age32plus`**  
- Definition: Share of playing time (MLB PA+BF; NHL TOI) from players aged 32+.
- Plain English: How much of the playing time went to veterans aged 32 or older.
- Why it might relate to doom: Veteran-heavy teams may fall off as players age.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 0.203 / 0.643

**`share_points_age32plus`**  
- Definition: NHL share of skater points from players aged 32+.
- Plain English: How much of the scoring came from veterans.
- Why it might relate to doom: Same idea, measured on scoring.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 0.172 / 0.571

### vet_share_lq

**`vet_share_lq`**  
- Definition: Share of team playing time from players at or above vet_age_cut_lq (D60).
- Plain English: How much playing time went to the league's oldest quarter of players.
- Why it might relate to doom: Like vet_share, but the age cutoff adapts to each league and season.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 0.244 / 0.640

**`vet_share_lq_lpct`**  
- Definition: Within league-season percentile of `vet_share_lq`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `vet_share_lq` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`vet_age_cut_lq`**  
- Definition: League-season playing-time-weighted 75th-percentile age (D60).
- Plain English: The age above which a player is in the oldest quarter of that league-season.
- Why it might relate to doom: Defines vet_share_lq.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 30.54 / 31.39 / 32.44

### star_concentration

**`star_concentration`**  
- Definition: **Shared concept.** Copy of MLB `top3_concentration` / NHL `top3_concentration` (D58).
- Plain English: How much the team depends on its three biggest contributors.
- Why it might relate to doom: Star-dependent teams are fragile if a star leaves or ages.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.129 / 0.221 / 0.480

**`top3_concentration`**  
- Definition: MLB: top-3 players' share of PA+BF. NHL: top-3 skaters' share of skater points (D45).
- Plain English: How much the team depends on its three biggest contributors.
- Why it might relate to doom: Star-dependent teams are fragile if a star leaves or ages.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.129 / 0.221 / 0.480

### margin_per_game

**`margin_per_game`**  
- Definition: **Shared concept.** Copy of MLB `point_diff_per_game` / NHL `point_diff_per_game` (D58).
- Plain English: Average winning (or losing) margin per game.
- Why it might relate to doom: Margin predicts future records better than wins do.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): -2.62 / 0.028 / 2.27

**`point_diff_per_game`**  
- Definition: (runs or goals scored − allowed) / games.
- Plain English: Average winning (or losing) margin per game.
- Why it might relate to doom: Margin predicts future records better than wins do.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): -2.62 / 0.028 / 2.27

**`scored_per_game`**  
- Definition: Runs/goals scored per game.
- Plain English: Offence.
- Why it might relate to doom: Component of margin.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 1.83 / 3.94 / 6.04

**`allowed_per_game`**  
- Definition: Runs/goals allowed per game.
- Plain English: Defence and pitching/goaltending.
- Why it might relate to doom: Component of margin.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 1.89 / 3.89 / 6.30

### luck

**`luck`**  
- Definition: win_pct − pythag_win_pct.
- Plain English: How many more (or fewer) wins the team got than its margin suggests.
- Why it might relate to doom: Lucky teams tend to regress; unlucky teams to rebound.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): -0.083 / 0.023 / 0.149

### underlying_quality

**`underlying_quality`**  
- Definition: **Shared concept.** Copy of MLB `pythag_win_pct` / NHL `corsi_pct` (D58).
- Plain English: MLB: The record a team 'should' have had given its scoring margin. NHL: Share of all shot attempts in the team's games that the team took.
- Why it might relate to doom: Estimate of true quality.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 86% (2008–2025)
- Typical range (min / median / max): 0.272 / 0.500 / 0.715

**`pythag_win_pct`**  
- Definition: Pythagorean win %: RS^k/(RS^k+RA^k), k = 1.83 MLB, 2.0 NHL (D13).
- Plain English: The record a team 'should' have had given its scoring margin.
- Why it might relate to doom: Estimate of true quality.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.223 / 0.504 / 0.750

**`corsi_pct`**  
- Definition: NHL shot-attempt share, all situations (MoneyPuck; D48).
- Plain English: Share of all shot attempts in the team's games that the team took.
- Why it might relate to doom: Measures puck control; predictive of future results.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 86% (2008–2025)
- Typical range (min / median / max): 0.380 / 0.500 / 0.600

**`xgoals_pct`**  
- Definition: NHL expected-goals share, all situations (MoneyPuck; **soft leakage, D54**).
- Plain English: Share of shot *quality* the team generated.
- Why it might relate to doom: Strongest single NHL signal, but see the leakage note.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 86% (2008–2025)
- Typical range (min / median / max): 0.400 / 0.500 / 0.600

**`pdo_5v5`**  
- Definition: NHL 5-on-5 shooting % + save %: GF/SOGF + 1 − GA/SOGA (D48).
- Plain English: A luck gauge: shooting plus goaltending percentages, ≈1.000 on average.
- Why it might relate to doom: Extreme values tend to return to 1.000.
- Known: End of season t (before the prediction moment)
- Leagues: NHL · Coverage: MLB 0%; NHL 86% (2008–2025)
- Typical range (min / median / max): 0.963 / 1.000 / 1.04

**`underlying_source`**  
- Definition: MoneyPuck CSV URL.
- Plain English: Where the hockey metrics came from.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: NHL · Coverage: MLB 0%; NHL 86% (2008–2025)
- Typical range (min / median / max): e.g. `https://moneypuck.com/moneypuck/playerData/seasonSummary/2021/regular/teams.csv`, `https://moneypuck.com/moneypuck/playerData/seasonSummary/2022/regular/teams.csv`

### draft_capital

**`draft_capital`**  
- Definition: **Shared concept.** Copy of MLB `draft_picks_rd1_2` / NHL `draft_picks_rd1_2` (D58).
- Plain English: How many high-value early picks the team made.
- Why it might relate to doom: Early picks are the ones most likely to become good players.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 2.00 / 11.00

**`draft_picks_rd1_2`**  
- Definition: Picks in rounds 1–2 (MLB incl. supplemental 1st, Competitive Balance Round A, PPI; D21).
- Plain English: How many high-value early picks the team made.
- Why it might relate to doom: Early picks are the ones most likely to become good players.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0 / 2.00 / 11

**`draft_picks_used`**  
- Definition: Picks the team made in the year-t draft (D18, D19).
- Plain English: How many new prospects the team drafted that year.
- Why it might relate to doom: More picks = more future talent (in theory).
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 2 / 20.00 / 59

**`draft_picks_used_pctile`**  
- Definition: Within league-season percentile of draft_picks_used (D20).
- Plain English: Number of picks relative to other teams that year.
- Why it might relate to doom: Comparable across draft-length changes.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 51.72 / 100.0

**`draft_first_pick_number`**  
- Definition: Team's earliest overall pick in the year-t draft.
- Plain English: Where the team picked first (1 = the first pick of the whole draft).
- Why it might relate to doom: Bad teams pick early; also a measure of incoming talent.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 1 / 16.00 / 193

**`draft_rounds_in_year`**  
- Definition: Distinct round labels in that year's draft.
- Plain English: How long the draft was that year.
- Why it might relate to doom: Context: MLB changed draft length.
- Known: Draft held in year t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 7 / 24.00 / 52

**`draft_source`**  
- Definition: API URL for the draft data.
- Plain English: Where the draft data came from.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `https://api-web.nhle.com/v1/draft/picks/2021/all`, `https://api-web.nhle.com/v1/draft/picks/2022/all`

### gm_tenure

**`gm_tenure`**  
- Definition: **Shared concept.** Copy of MLB `personnel_lead_tenure_years` / NHL `personnel_lead_tenure_years` (D58).
- Plain English: How long the person running the roster has been in charge.
- Why it might relate to doom: New GMs often rebuild; long tenures can mean stability or stagnation.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 94% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 3.86 / 27.84

**`personnel_lead_tenure_years`**  
- Definition: Years the current GM has held the job at the prediction moment; GM only (D30, D36).
- Plain English: How long the person running the roster has been in charge.
- Why it might relate to doom: New GMs often rebuild; long tenures can mean stability or stagnation.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 94% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.000 / 3.86 / 27.84

**`personnel_lead_changed_past_year`**  
- Definition: 1 if the GM at the moment differs from 365 days earlier (VACANT counts as a state). MLB 2026 is always 0 (D43).
- Plain English: Whether the team changed its GM in the last year.
- Why it might relate to doom: A new GM can signal a rebuild.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 95% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 15.0%

**`personnel_lead_name`**  
- Definition: GM at the prediction moment (NaN if vacant or unknown).
- Plain English: Who the GM was.
- Why it might relate to doom: Not a numeric feature.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 94% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `Brian Cashman`, `Ken Holland`

**`personnel_lead_vacant`**  
- Definition: 1 if the source shows no one held the GM title (D42).
- Plain English: The team had no GM at that moment.
- Why it might relate to doom: Vacancies often follow upheaval.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 96% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 1.2%

**`personnel_lead_gap_carried`**  
- Definition: 1 if the previous GM was carried across a short gap caused by year-only dates (D30, D37).
- Plain English: Data-quality flag for the GM columns.
- Why it might relate to doom: Audit; treat these rows as less certain.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 96% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 1.9%

**`personnel_lead_tenure_left_censored`**  
- Definition: GM tenure reaches the start of the available history (≤1999), so the true tenure may be longer.
- Plain English: Tenure may be undercounted.
- Why it might relate to doom: Audit.
- Known: At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)
- Leagues: MLB, NHL · Coverage: MLB 96% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): share True = 15.4%

### coach_tenure

**`coach_tenure`**  
- Definition: **Shared concept.** Copy of MLB `coach_tenure_years` / NHL `coach_tenure_years` (D58).
- Plain English: How long the current manager/coach has been in charge.
- Why it might relate to doom: Coaching changes often follow bad seasons.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.500 / 2.00 / 20.50

**`coach_tenure_years`**  
- Definition: Consecutive seasons as season-end manager/head coach incl. t; a first season taken over mid-season counts 0.5 (D24).
- Plain English: How long the current manager/coach has been in charge.
- Why it might relate to doom: Coaching changes often follow bad seasons.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.500 / 2.00 / 20.50

**`coach_name`**  
- Definition: Manager/head coach at the end of regular season t.
- Plain English: Who ran the team in games.
- Why it might relate to doom: Not a numeric feature.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `Bruce Bochy`, `Terry Francona`

**`coach_changed_during_regular_season`**  
- Definition: 1 if more than one manager/coach ran the team during regular season t; later changes are not captured (D26).
- Plain English: Whether the coach was replaced during the season.
- Why it might relate to doom: Mid-season firings signal trouble.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 11.8%

**`coach_tenure_left_censored`**  
- Definition: Tenure streak reaches the start of the coach history.
- Plain English: Tenure may be undercounted.
- Why it might relate to doom: Audit.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): share True = 2.8%

**`manager_resolved_by_fallback`**  
- Definition: MLB: season-end manager chosen by the interim rule (D27).
- Plain English: Data-quality flag (manager on leave, interim finished).
- Why it might relate to doom: Audit.
- Known: Last regular-season game of t
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 0.3%

### spending

**`spending`**  
- Definition: **Shared concept.** Copy of MLB `payroll_rel_league_mean` (NHL: unavailable) (D58).
- Plain English: Spending relative to the average team that year (1.0 = average).
- Why it might relate to doom: Same as payroll but comparable across years.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 0.193 / 0.948 / 2.85

**`spending_available`**  
- Definition: 1 = spending observed (MLB); 0 = unavailable (NHL) (D57).
- Plain English: Whether this league has a spending measure.
- Why it might relate to doom: Descriptor.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 55.7%

**`payroll_rel_league_mean`**  
- Definition: Payroll / league mean payroll that season (D57).
- Plain English: Spending relative to the average team that year (1.0 = average).
- Why it might relate to doom: Same as payroll but comparable across years.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 0.193 / 0.948 / 2.85

**`payroll_opening_day_usd`**  
- Definition: MLB Opening Day payroll, USD (Cot's Baseball Contracts; D53). 2020 pro-rated to 60 games.
- Plain English: How much the team was paying its players at the start of the season.
- Why it might relate to doom: Money buys talent; also signals owner commitment.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 14,998,500 / 93,500,017 / 354,705,231

**`payroll_rank`**  
- Definition: Within-season payroll rank, 1 = highest, recomputed from values (D53).
- Plain English: Where the team ranked in spending.
- Why it might relate to doom: Same idea, ordinal.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): 1.00 / 15.50 / 30.00

**`cbt_threshold_usd`**  
- Definition: MLB luxury-tax (Competitive Balance Tax) threshold, USD; none 2000–02 (D50).
- Plain English: The payroll level above which MLB teams pay a tax.
- Why it might relate to doom: Context for payroll_pct_of_cbt.
- Known: Descriptive / fixed
- Leagues: MLB · Coverage: MLB 89% (2003–2026); NHL 0%
- Typical range (min / median / max): 117,000,000 / 189,000,000 / 244,000,000

**`payroll_pct_of_cbt`**  
- Definition: payroll_opening_day_usd / cbt_threshold_usd.
- Plain English: Payroll as a share of the luxury-tax line.
- Why it might relate to doom: Teams near the line spend like contenders.
- Known: Opening Day of season t
- Leagues: MLB · Coverage: MLB 89% (2003–2026); NHL 0%
- Typical range (min / median / max): 0.110 / 0.573 / 1.63

**`cap_space_pct`**  
- Definition: Teammate schema column; **empty for both leagues** (D57).
- Plain English: Would be unused room under the salary cap.
- Why it might relate to doom: Unavailable; use `spending` for MLB.
- Known: Descriptive / fixed
- Leagues: none (empty) · Coverage: MLB 0%; NHL 0%
- Typical range (min / median / max): — (empty)

**`cap_upper_limit_usd`**  
- Definition: NHL salary cap upper limit, USD (Wikipedia; D51).
- Plain English: The most an NHL team may spend on player salaries that season.
- Why it might relate to doom: Context only (same for every team in a season).
- Known: Descriptive / fixed
- Leagues: NHL · Coverage: MLB 0%; NHL 100% (2005–2025)
- Typical range (min / median / max): 39,000,000 / 71,400,000 / 95,500,000

**`team_cap_hit_usd`**  
- Definition: NHL team cap hit. **Empty by decision** (D52, D57).
- Plain English: Would be the team's total salary-cap charge.
- Why it might relate to doom: Unavailable.
- Known: Descriptive / fixed
- Leagues: none (empty) · Coverage: MLB 0%; NHL 0%
- Typical range (min / median / max): — (empty)

**`payroll_source`**  
- Definition: Cot's page for the payroll.
- Plain English: Where the payroll came from.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): e.g. `https://legacy.baseballprospectus.com/compensation/cots/…/arizona-diamondbacks/`, `https://legacy.baseballprospectus.com/compensation/cots/…/athletics/`

### market

**`market`**  
- Definition: **Shared concept.** Copy of MLB `attendance_per_game` (NHL: unavailable) (D58).
- Plain English: How many fans came to home games.
- Why it might relate to doom: Market size and demand; partly a result of winning.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 96% (2000–2026); NHL 0%
- Typical range (min / median / max): 7,934 / 29,476 / 52,729

**`market_lpct`**  
- Definition: Within league-season percentile of `market`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).
- Plain English: `market` expressed as 0–100 relative to the other teams in the same league and season.
- Why it might relate to doom: Use this version when stacking leagues: raw units differ.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 96% (2000–2026); NHL 0%
- Typical range (min / median / max): 0.000 / 50.00 / 100.0

**`market_available`**  
- Definition: 1 = market proxy observed (MLB); 0 = unavailable (NHL).
- Plain English: Whether this league has a market measure.
- Why it might relate to doom: Descriptor.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0/1; share 1 = 55.7%

**`attendance_per_game`**  
- Definition: MLB average home attendance per game; 2020 NaN (D25). NHL not collected.
- Plain English: How many fans came to home games.
- Why it might relate to doom: Market size and demand; partly a result of winning.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 96% (2000–2026); NHL 0%
- Typical range (min / median / max): 7,934 / 29,476 / 52,729

**`attendance_rank`**  
- Definition: Within-season rank of attendance_per_game, 1 = highest.
- Plain English: Where the team ranked in attendance.
- Why it might relate to doom: Same idea, ordinal.
- Known: End of season t (before the prediction moment)
- Leagues: MLB · Coverage: MLB 96% (2000–2026); NHL 0%
- Typical range (min / median / max): 1.00 / 15.50 / 30.00

**`attendance_restricted`**  
- Definition: True for MLB 2020 and 2021 (COVID limits).
- Plain English: Seasons when attendance was limited.
- Why it might relate to doom: Flag for unusual attendance.
- Known: Descriptive / fixed
- Leagues: MLB · Coverage: MLB 100% (2000–2026); NHL 0%
- Typical range (min / median / max): share True = 7.4%

### Identifiers and standings (not in the crosswalk)

**`team_name_then`**  
- Definition: Name the source used that season (e.g. `Expos`).
- Plain English: What the club was called that year.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `Athletics`, `Braves`

**`team_id`**  
- Definition: Source team ID (MLB or NHL API).
- Plain English: The league's own internal team number.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 1 / 111.0 / 158

**`ties`**  
- Definition: MLB: tie games. **NHL: overtime/shootout losses** (+ true ties in 2002–04), so that win_pct equals NHL points % (D07).
- Plain English: In MLB, games that ended level. In the NHL, games lost after regulation, which still earn a point.
- Why it might relate to doom: Part of the record; see the NHL gotcha.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0 / 0.000 / 20

**`win_pct_raw`**  
- Definition: wins / games (no credit for ties/OTL).
- Plain English: Plain share of games won.
- Why it might relate to doom: Alternative to win_pct for the NHL.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): 0.232 / 0.506 / 0.793

**`standings_source`**  
- Definition: API URL for the standings row.
- Plain English: Where the record came from.
- Why it might relate to doom: Audit only.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): e.g. `https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId=20212022 and gameTypeId=2`, `https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId=20222023 and gameTypeId=2`

### Trajectory and context (not in the crosswalk)

**`win_pct_change_1yr`**  
- Definition: win_pct(t) − win_pct(previous played season).
- Plain English: How much the record changed from last season.
- Why it might relate to doom: Big jumps often partly reverse.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): -0.274 / 0.000 / 0.299

**`win_pct_slope_3yr`**  
- Definition: OLS slope of win_pct over the last 3 played seasons (needs ≥2).
- Plain English: Whether the team has been trending up or down.
- Why it might relate to doom: Trend may continue or reverse.
- Known: End of season t (before the prediction moment)
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): -0.180 / -0.000 / 0.244

**`expansion_first_3_seasons`**  
- Definition: True for Vegas 2017–19 and Seattle 2021–23.
- Plain English: A brand-new team's first three seasons.
- Why it might relate to doom: New teams follow unusual roster rules.
- Known: Descriptive / fixed
- Leagues: MLB, NHL · Coverage: MLB 100% (2000–2026); NHL 100% (2005–2025)
- Typical range (min / median / max): share True = 0.4%


### Extended labels: never use these as features

**`observed_doom_next_3_seasons`**  
- Definition: Identical to `y_doom_3yr`; name required by the teammate's schema.
- Plain English: The doom score (label).
- Why it might relate to doom: **Label, never a feature.**
- Known: Seasons t+1 to t+3 (the future) — label
- Leagues: MLB, NHL · Coverage: MLB 89% (2000–2023); NHL 85% (2005–2022)
- Typical range (min / median / max): 1.15 / 48.85 / 100.0


## 5. Gotchas

- **NHL `ties` holds overtime losses.** For NHL rows from 2005 on, `ties` equals `ot_losses` in 100.0% of rows. Example: Boston Bruins 2022–23 went 65–12–5 (W–L–OTL), so `ties` = 5 and `win_pct` = 0.823 (points %), while `win_pct_raw` = 0.793.
- **Short seasons.** MLB 2020: 58–60 games, NHL 2012–13: 48–48 games, NHL 2019–20: 68–71 games, NHL 2020–21: 56–56 games. Use `short_season` to flag or down-weight them; counts such as wins are not comparable to full seasons.
- **Relocations and renames.** `franchise_id` follows the club, not the city. Clubs with more than one name in the data:
  - `arizona-diamondbacks` (MLB): Diamondbacks → D-backs
  - `cleveland-guardians` (MLB): Indians → Guardians
  - `tampa-bay-rays` (MLB): Devil Rays → Rays
  - `washington-nationals` (MLB): Expos → Nationals
  - `utah-mammoth` (NHL): Phoenix Coyotes → Arizona Coyotes → Utah Hockey Club → Utah Mammoth
  - `winnipeg-jets` (NHL): Atlanta Thrashers → Winnipeg Jets

  The Thrashers → Jets mapping comes from the NHL's own franchise IDs (D05); Coyotes → Utah is a manual mapping (D06). Some moves do not appear as a name change in the source: the Athletics (Oakland → Sacramento, `athletics`) and the Marlins (Florida → Miami, `miami-marlins`) keep the same short name, so see D03 for the full MLB mapping.
- **Vacant vs missing personnel.** `personnel_lead_vacant` = 1 (15 MLB, 2 NHL rows) means the source shows no GM; `gm_tenure` is empty on purpose. A missing GM with vacant = 0 (36 MLB, 0 NHL rows) means the data could not be found. Do not treat the two the same.
- **MLB 2020.** Attendance is NaN for all 30 teams (no fans; D25). Payroll is pro-rated to 60 games: median Opening Day payroll $56.3M in 2020 vs $123.0M in 2019. Use `payroll_rel_league_mean` / `spending`, which compare teams within a season.
- **Expansion teams.** `seattle-kraken` first season 2021 (seasons_of_history starts at 1); `vegas-golden-knights` first season 2017 (seasons_of_history starts at 1). Their trailing features use fewer seasons; `seasons_of_history` tells you how many.
- **MLB 2026 GM changes are always 0** (year-only dates fall after the moment; D43). MLB 2026 is unlabelled.

## 6. Which features look predictive (exploratory)

From `reports/phase4.md` / `phase4_correlations.csv`. These are **exploratory correlations on labelled rows, not model results**. "Partial" is the Spearman correlation with `y_doom_3yr` after removing what `win_pct_percentile` already explains (D55). Negative means a higher value goes with *less* doom. Current standing alone has Spearman -0.45 (MLB) and -0.50 (NHL) with doom.

| League | Feature | n | Spearman | Partial (ctrl. percentile) |
|---|---|---|---|---|
| MLB | `point_diff_per_game` | 720 | -0.47 | -0.15 |
| MLB | `pythag_win_pct` | 720 | -0.46 | -0.14 |
| MLB | `attendance_rank` | 690 | +0.30 | +0.12 |
| MLB | `personnel_lead_tenure_left_censored` | 694 | -0.17 | -0.11 |
| MLB | `luck` | 720 | -0.06 | +0.11 |
| MLB | `age_weighted_hitters` | 720 | -0.03 | +0.10 |
| NHL | `xgoals_pct` | 458 | -0.55 | -0.30 |
| NHL | `point_diff_per_game` | 548 | -0.54 | -0.23 |
| NHL | `corsi_pct` | 458 | -0.45 | -0.23 |
| NHL | `pythag_win_pct` | 548 | -0.54 | -0.23 |
| NHL | `win_pct_trailing_3_seasons` | 548 | -0.48 | -0.17 |
| NHL | `luck` | 548 | -0.01 | +0.17 |

Reading: after controlling for current standing, the clearest signals are NHL shot-based quality (expected goals, with its leakage caveat, and Corsi), scoring margin and Pythagorean win % in both leagues, and luck (lucky teams tend to slip). MLB payroll adds little beyond standing (partial -0.08). Some entries are data-quality flags (e.g. `personnel_lead_tenure_left_censored`, which marks long tenures cut off by the start of the history); treat them as artifacts, not signals. The correlations were computed before the shared concept columns were added, so they use the league column names (e.g. `point_diff_per_game` = `margin_per_game`).
