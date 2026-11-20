# Feature crosswalk (shared concepts across leagues)

Shared concept columns sit right after the 19 core columns in `data/processed/mlb_nhl_team_seasons.csv`. Each concept is an **alias** (copy) of a league-specific column, so the NBA/NFL files can fill the same names. `<concept>_lpct` = within-league-season percentile, (average rank − 1)/(n − 1) × 100 over non-missing values, the same formula as `win_pct_percentile` (0 = lowest, 100 = highest). Use `_lpct` when stacking leagues, because raw scales differ (runs vs goals, PA+BF vs TOI, dollars vs none).

| Concept | Definition | MLB column | NHL column | NBA | NFL | Coverage MLB / NHL | Notes |
|---|---|---|---|---|---|---|---|
| playing-time weight (`playing_time_weight`) | Weight used for roster aggregates | PA + batters faced per team stint | time on ice per team stint | TBD (e.g. minutes) | TBD (e.g. snaps) | 100% / 100% | Text column naming the basis |
| `roster_age_weighted` | Playing-time-weighted roster age | `age_weighted` | `age_weighted` | TBD | TBD | 100% / 100% | Age on MLB Jun 30 t / NHL Feb 1 t+1 |
| `vet_share` | Share of playing time from players aged 32+ | `share_production_age32plus` | `share_production_age32plus` | TBD | TBD | 100% / 100% | Fixed age cut |
| `vet_share_lq` | Share of playing time from the league-season's oldest quartile (playing-time-weighted age q75) | `vet_share_lq` | `vet_share_lq` | TBD | TBD | 100% / 100% | Cut adapts per league-season |
| `star_concentration` | Top-3 players' share of team production | `top3_concentration` | `top3_concentration` | TBD | TBD | 100% / 100% | MLB: share of PA+BF; NHL: share of skater points |
| `margin_per_game` | (scored - allowed) / games | `point_diff_per_game` | `point_diff_per_game` | TBD | TBD | 100% / 100% | Runs vs goals |
| `luck` | win_pct - Pythagorean win% | `luck` | `luck` | TBD | TBD | 100% / 100% | Exponent 1.83 MLB, 2.0 NHL |
| `underlying_quality` | Quality beyond W-L record | `pythag_win_pct` | `corsi_pct` | TBD | TBD | 100% / 86% | MLB: Pythagorean win% (run-based, overlaps margin); NHL: Corsi% 2008+ (no model). Alternative NHL: xgoals_pct (stronger, soft leakage D54) |
| `draft_capital` | Picks in rounds 1-2 of the year-t draft | `draft_picks_rd1_2` | `draft_picks_rd1_2` | TBD | TBD | 100% / 100% | MLB incl. supplemental 1st, CB-A, PPI. Alternative: draft_first_pick_number |
| `gm_tenure` | GM tenure at the prediction moment | `personnel_lead_tenure_years` | `personnel_lead_tenure_years` | TBD | TBD | 94% / 100% | NaN when vacant (personnel_lead_vacant = 1) |
| `coach_tenure` | Manager/head-coach tenure at end of regular season | `coach_tenure_years` | `coach_tenure_years` | TBD | TBD | 100% / 100% | Mid-season first season = 0.5 |
| `spending` | Payroll relative to league-season mean | `payroll_rel_league_mean` | **unavailable** | TBD | TBD | 100% / 0% | MLB: Cot's Opening Day payroll / league mean. NHL: unavailable (spending_available = 0) |
| `market` | Market / demand proxy | `attendance_per_game` | **unavailable** | TBD | TBD | 96% / 0% | MLB: home attendance per game (partly endogenous to winning; 2020 NaN). NHL: unavailable |

Flags: `spending_available`, `market_available` (1 = MLB, 0 = NHL). `vet_age_cut_lq` stores the league-season age cut used by `vet_share_lq` (MLB 30.9–32.4, NHL 30.5–32.2 years).

Decisions: D57 (spending), D58 (concept choices), D59 (_lpct), D60 (vet_share_lq). NBA/NFL columns are TBD for the teammate to fill.
