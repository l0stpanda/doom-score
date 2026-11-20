"""Regenerate the two groupmate docs (DATA_COLLECTION.md, DATASET_GUIDE.md) and doc_stats.json.

Every number quoted in the docs is computed here from files in the repo:
data/processed/*.csv, data/manual/*.csv, reports/*_checks.csv, reports/phase4_correlations.csv,
reports/phase4_payroll_crosscheck.json and the git log. Prose comes from DECISIONS.md, reports/phase1-4.md,
DATA_DICTIONARY.md and FEATURE_CROSSWALK.md (D-numbers cited inline).

Run from the repo root or anywhere:  PYTHONUTF8=1 python ADAM-DATA/docs/make_doc_stats.py
It does not change any data or code."""
import json, os, subprocess
import numpy as np
import pandas as pd

DOCS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DOCS)                      # ADAM-DATA
P = lambda *a: os.path.join(ROOT, *a)

df = pd.read_csv(P("data", "processed", "mlb_nhl_team_seasons.csv"))
spans = pd.read_csv(P("data", "processed", "front_office_spans.csv"))
cbt = pd.read_csv(P("data", "manual", "mlb_cbt_threshold.csv"))
cap = pd.read_csv(P("data", "manual", "nhl_salary_cap.csv"))
tmpl = pd.read_csv(P("data", "manual", "payroll_template.csv"))
fo_tmpl = pd.read_csv(P("data", "manual", "front_office_template.csv"))
corr = pd.read_csv(P("reports", "phase4_correlations.csv"))
xcheck = json.load(open(P("reports", "phase4_payroll_crosscheck.json")))
checks = {k: pd.read_csv(P("reports", f"{k}_checks.csv")) for k in ("phase1", "phase2", "phase3", "phase4", "crosswalk")}
gitlog = subprocess.run(["git", "-C", ROOT, "log", "--format=%h|%ad|%s", "--date=short"], capture_output=True,
                        text=True).stdout.strip().splitlines()

M, N = df[df.league == "MLB"], df[df.league == "NHL"]
lab = df[df.y_doom_3yr.notna()]
S = {}  # all numbers, saved to doc_stats.json


def fmt(v, nd=None):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    a = abs(v)
    if nd is None:
        nd = 0 if a >= 1000 else 1 if a >= 100 else 2 if a >= 1 else 3
    return f"{v:,.{nd}f}"


def season_label(lg, y):
    return f"{y}" if lg == "MLB" else f"{y}–{str(y + 1)[2:]}"


# ---------------- core counts ----------------
S["rows"] = len(df)
S["cols"] = df.shape[1]
for lg, g in (("MLB", M), ("NHL", N)):
    S[f"{lg}_rows"] = len(g)
    S[f"{lg}_first"], S[f"{lg}_last"] = int(g.season_start_year.min()), int(g.season_start_year.max())
    S[f"{lg}_seasons"] = g.season_start_year.nunique()
    S[f"{lg}_franchises"] = g.franchise_id.nunique()
    S[f"{lg}_labelled"] = int(g.y_doom_3yr.notna().sum())
    S[f"{lg}_label_last"] = int(g[g.y_doom_3yr.notna()].season_start_year.max())
    S[f"{lg}_bottom25_rate"] = round(float(g.y_doomed_bottom25.dropna().astype(float).mean()) * 100, 1)
    S[f"{lg}_games_median"] = int(g.games.median())
    S[f"{lg}_teams_per_season"] = sorted(g.groupby("season_start_year").size().unique().tolist())
S["NHL_team_count_changes"] = {int(y): int(n) for y, n in N.groupby("season_start_year").size().items()
                               if y == N.season_start_year.min() or n != N[N.season_start_year == y - 1].shape[0]}
S["doom_median"] = round(float(lab.y_doom_3yr.median()), 1)

# short seasons
S["short"] = {f"{lg} {season_label(lg, y)}": (int(g.games.min()), int(g.games.max()))
              for (lg, y), g in df[df.short_season.astype(str) == "True"].groupby(["league", "season_start_year"])}

# worked examples (highest and lowest doom among labelled rows)
def example(row):
    pcts = [row.y_pct_t1, row.y_pct_t2, row.y_pct_t3]
    return dict(league=row.league, season=season_label(row.league, row.season_start_year), team=row.team,
                wins=int(row.wins), losses=int(row.losses), pct_now=round(row.win_pct_percentile, 1),
                next3=[round(p, 1) for p in pcts], mean_next3=round(float(np.mean(pcts)), 1),
                doom=round(row.y_doom_3yr, 1), recomputed=round(100 - float(np.mean(pcts)), 1),
                bottom25=bool(row.y_doomed_bottom25), next_seasons=[season_label(row.league, row.season_start_year + k)
                                                                    for k in (1, 2, 3)])
S["ex_high"] = example(lab.sort_values(["y_doom_3yr", "season_start_year"], ascending=[False, True]).iloc[0])
S["ex_low"] = example(lab.sort_values(["y_doom_3yr", "season_start_year"]).iloc[0])

# NHL ties = OTL
n05 = N[N.season_start_year >= 2005]
S["nhl_ties_equal_otl_share"] = round(float((n05.ties == n05.ot_losses).mean()) * 100, 1)
ex_t = N[(N.franchise_id == "boston-bruins") & (N.season_start_year == 2022)].iloc[0]
S["ex_ties"] = dict(team=ex_t.team, season=season_label("NHL", 2022), w=int(ex_t.wins), l=int(ex_t.losses),
                    otl=int(ex_t.ot_losses), ties=int(ex_t.ties), gp=int(ex_t.games), win_pct=round(ex_t.win_pct, 3),
                    win_pct_raw=round(ex_t.win_pct_raw, 3))
S["mlb_tie_rows"] = int((M.ties > 0).sum())

# relocations / renames
reloc = df.groupby(["league", "franchise_id"]).team_name_then.apply(lambda s: list(dict.fromkeys(s)))
S["renames"] = {f"{lg}|{fid}": names for (lg, fid), names in reloc.items() if len(names) > 1}
S["expansion"] = {fid: (int(g.season_start_year.min()), int(g.seasons_of_history.min()))
                  for fid, g in N[N.franchise_id.isin(["vegas-golden-knights", "seattle-kraken"])].groupby("franchise_id")}

# front office
S["spans_total"] = len(spans)
S["spans_by_precision"] = spans.date_precision.value_counts().to_dict()
S["spans_year_only_mlb"] = int(((spans.league == "MLB") & (spans.date_precision == "year")).sum())
S["spans_mlb"] = int((spans.league == "MLB").sum())
for lg, g in (("MLB", M), ("NHL", N)):
    S[f"{lg}_vacant"] = int((g.personnel_lead_vacant == 1).sum())
    S[f"{lg}_gm_unknown"] = int((g.personnel_lead_name.isna() & (g.personnel_lead_vacant != 1)).sum())
    S[f"{lg}_gap_carried"] = int(g.personnel_lead_gap_carried.fillna(0).sum())
    S[f"{lg}_gm_cov"] = round(float(g.personnel_lead_tenure_years.notna().mean()) * 100, 1)
S["fallback_rows"] = int(M.manager_resolved_by_fallback.fillna(0).sum())
S["mlb_2026_gm_changes"] = int(M[M.season_start_year == 2026].personnel_lead_changed_past_year.sum())
S["fo_template_rows"] = len(fo_tmpl)
S["fo_template_teams"] = fo_tmpl.franchise_id.tolist()

# money
S["cbt_first"], S["cbt_last"] = (int(cbt.dropna(subset=["cbt_threshold_usd"]).season.min()),
                                 int(cbt.dropna(subset=["cbt_threshold_usd"]).season.max()))
S["cbt_min_m"], S["cbt_max_m"] = cbt.cbt_threshold_usd.min() / 1e6, cbt.cbt_threshold_usd.max() / 1e6
S["cap_first"], S["cap_last"] = int(cap.season_start_year.min()), int(cap.season_start_year.max())
S["cap_min_m"], S["cap_max_m"] = cap.cap_upper_limit_usd.min() / 1e6, cap.cap_upper_limit_usd.max() / 1e6
S["cap_2012_m"] = float(cap[cap.season_start_year == 2012].cap_upper_limit_usd.iloc[0]) / 1e6
S["pay_2019_median_m"] = float(M[M.season_start_year == 2019].payroll_opening_day_usd.median()) / 1e6
S["pay_2020_median_m"] = float(M[M.season_start_year == 2020].payroll_opening_day_usd.median()) / 1e6
S["att_2020_nan"] = int(M[M.season_start_year == 2020].attendance_per_game.isna().sum())
S["nhl_template_rows"] = int((tmpl.league == "NHL").sum())
S["xcheck"] = {k: float(v) for k, v in xcheck.items()}
S["draft_rounds"] = {lg: (int(g.draft_rounds_in_year.min()), int(g.draft_rounds_in_year.max()))
                     for lg, g in (("MLB", M), ("NHL", N)) if g.draft_rounds_in_year.notna().any()}
S["mlb_draft_rounds_2020"] = int(M[M.season_start_year == 2020].draft_rounds_in_year.iloc[0])

# leakage example: NHL draft timing
ex_d = N[(N.franchise_id == "edmonton-oilers") & (N.season_start_year == 2010)].iloc[0]
S["ex_draft"] = dict(team=ex_d.team, season=season_label("NHL", 2010), first_pick=int(ex_d.draft_first_pick_number),
                     picks=int(ex_d.draft_picks_used))

# NHL underlying coverage
S["nhl_mp_cov"] = round(float(N.corsi_pct.notna().mean()) * 100, 1)
S["nhl_mp_first"] = int(N[N.corsi_pct.notna()].season_start_year.min())

# checks per phase
S["checks"] = {k: (int(v["pass"].astype(str).eq("True").sum()), len(v)) for k, v in checks.items()}
S["phase1_fails"] = checks["phase1"][checks["phase1"]["pass"].astype(str) != "True"].check.tolist()
S["phase2_nonpass"] = checks["phase2"][checks["phase2"]["pass"].astype(str) != "True"].check.tolist()

# git log
S["git"] = [l.split("|", 2) for l in gitlog]
S["download_dates"] = sorted({d for _, d, m in S["git"] if "Phase" in m or "crosswalk" in m})

# correlations: top partials per league
top = {}
for lg, g in corr.groupby("league"):
    g = g.dropna(subset=["partial_spearman_ctrl_win_pct_percentile"])
    g = g.reindex(g.partial_spearman_ctrl_win_pct_percentile.abs().sort_values(ascending=False).index)
    top[lg] = g.head(8)[["feature", "n", "spearman", "partial_spearman_ctrl_win_pct_percentile"]].values.tolist()
S["corr_top"] = top
S["corr_n"] = {lg: int(g.n.max()) for lg, g in corr.groupby("league")}
cp = corr.set_index(["league", "feature"])
S["corr_payroll_mlb"] = float(cp.loc[("MLB", "payroll_rel_league_mean"), "partial_spearman_ctrl_win_pct_percentile"])
S["corr_wpp"] = {lg: float(cp.loc[(lg, "win_pct_percentile"), "spearman"]) for lg in ("MLB", "NHL")}

# ---------------- per-column metadata ----------------
E = "End of season t (before the prediction moment)"
PM = "At the prediction moment (MLB Nov 15 of t; NHL Jun 15 of t+1)"
OD = "Opening Day of season t"
DR = "Draft held in year t (before the prediction moment)"
RS = "Last regular-season game of t"
FX = "Descriptive / fixed"
LB = "Seasons t+1 to t+3 (the future) — label"

META = {
 # identifiers & standings
 "league": ("`MLB` or `NHL`.", "Which league the row belongs to.", "Not a predictor; use it to group or stratify.", FX),
 "season_start_year": ("Calendar year the season starts (NHL `2017` = 2017–18).", "The season this row describes.", "Not a predictor; defines time order for train/test splits.", FX),
 "franchise_id": ("Lowercase-hyphenated *current* franchise name, constant through moves and renames (D03, D05, D06).", "A stable ID for the club across its history.", "Not a predictor; use it to follow a club over time.", FX),
 "team": ("Franchise's current (2026) name, the same for every year.", "The club's name today.", "Not a predictor.", FX),
 "team_name_then": ("Name the source used that season (e.g. `Expos`).", "What the club was called that year.", "Audit only.", FX),
 "team_id": ("Source team ID (MLB or NHL API).", "The league's own internal team number.", "Audit only.", FX),
 "wins": ("Regular-season wins (source: league standings API).", "Games won.", "Better teams now tend to stay better (persistence).", E),
 "losses": ("Regular-season losses; NHL: regulation losses only.", "Games lost (in hockey, losses in normal time).", "Mirror of wins.", E),
 "ties": ("MLB: tie games. **NHL: overtime/shootout losses** (+ true ties in 2002–04), so that win_pct equals NHL points % (D07).", "In MLB, games that ended level. In the NHL, games lost after regulation, which still earn a point.", "Part of the record; see the NHL gotcha.", E),
 "ot_losses": ("NHL overtime + shootout losses.", "Hockey games lost after the normal 60 minutes.", "Close losses; partly luck.", E),
 "games": ("Games played (MLB W+L+T; NHL W+L+OTL).", "How many games the team played.", "Flags short seasons.", E),
 "win_pct": ("(wins + 0.5 × ties) / games. NHL: equals points % (D07).", "Share of games won, with half credit for ties / overtime losses.", "Current quality; the strongest single predictor.", E),
 "win_pct_raw": ("wins / games (no credit for ties/OTL).", "Plain share of games won.", "Alternative to win_pct for the NHL.", E),
 "win_pct_percentile": ("Within league-season: (average rank − 1)/(n − 1) × 100 of win_pct; worst 0, best 100 (D10).", "Where the team finished relative to the rest of its league that year.", "Current standing; the doom label is built from future values of this.", E),
 "standings_source": ("API URL for the standings row.", "Where the record came from.", "Audit only.", FX),
 # trajectory
 "win_pct_trailing_3_seasons": ("Mean win_pct of the franchise's last 3 played seasons incl. t (min 1; D08, D09).", "Average record over the last three seasons.", "Smooths one-season noise.", E),
 "win_pct_change_1yr": ("win_pct(t) − win_pct(previous played season).", "How much the record changed from last season.", "Big jumps often partly reverse.", E),
 "win_pct_slope_3yr": ("OLS slope of win_pct over the last 3 played seasons (needs ≥2).", "Whether the team has been trending up or down.", "Trend may continue or reverse.", E),
 "seasons_of_history": ("Number of franchise seasons available up to t (history fetched from 1997 MLB / 2002 NHL).", "How much past data exists for this club.", "Low values = less reliable trailing features (expansion teams).", E),
 "short_season": ("True for MLB 2020 and NHL 2012–13, 2019–20, 2020–21 (D14).", "Seasons cut short (lockout or pandemic).", "Records from short seasons are noisier.", FX),
 "expansion_first_3_seasons": ("True for Vegas 2017–19 and Seattle 2021–23.", "A brand-new team's first three seasons.", "New teams follow unusual roster rules.", FX),
 # playing time / audit
 "playing_time_weight": ("Text: `PA+BF` (MLB) or `TOI` (NHL) (D58).", "Which measure of playing time the roster features are weighted by.", "Descriptor only.", FX),
 "team_pa": ("Sum of player plate appearances; equals the official team total (D46).", "Total turns at bat by the team's hitters.", "Audit; the weight behind MLB roster features.", E),
 "team_bf": ("Sum of batters faced by the team's pitchers; equals the official total.", "Total batters the team's pitchers faced.", "Audit.", E),
 "skater_gp_sum": ("Sum of skater games played (≈18 per team game).", "Total skater appearances.", "Audit.", E),
 "goalie_gp_sum": ("Sum of goalie games played.", "Total goalie appearances.", "Audit.", E),
 "roster_players_used": ("Players with playing time for the team in t.", "How many different players the team used.", "Lots of players can signal injuries or churn.", E),
 "age_weight_coverage": ("Share of playing time with a known birthdate.", "Data-quality check for the age features.", "Audit only.", E),
 # age
 "age_weighted": ("Playing-time-weighted mean age; age on MLB Jun 30 of t / NHL Feb 1 of t+1; weights MLB PA+BF, NHL TOI per team stint (D45).", "Average age of the team, counting players by how much they played.", "Old rosters may decline; young ones may improve.", E),
 "age_weighted_hitters": ("MLB PA-weighted age.", "Average age of the hitters.", "Ageing bats.", E),
 "age_weighted_pitchers": ("MLB batters-faced-weighted age.", "Average age of the pitchers.", "Ageing arms.", E),
 "share_production_age32plus": ("Share of playing time (MLB PA+BF; NHL TOI) from players aged 32+.", "How much of the playing time went to veterans aged 32 or older.", "Veteran-heavy teams may fall off as players age.", E),
 "share_points_age32plus": ("NHL share of skater points from players aged 32+.", "How much of the scoring came from veterans.", "Same idea, measured on scoring.", E),
 "vet_age_cut_lq": ("League-season playing-time-weighted 75th-percentile age (D60).", "The age above which a player is in the oldest quarter of that league-season.", "Defines vet_share_lq.", E),
 "vet_share_lq": ("Share of team playing time from players at or above vet_age_cut_lq (D60).", "How much playing time went to the league's oldest quarter of players.", "Like vet_share, but the age cutoff adapts to each league and season.", E),
 "top3_concentration": ("MLB: top-3 players' share of PA+BF. NHL: top-3 skaters' share of skater points (D45).", "How much the team depends on its three biggest contributors.", "Star-dependent teams are fragile if a star leaves or ages.", E),
 # margin / luck / underlying
 "point_diff_per_game": ("(runs or goals scored − allowed) / games.", "Average winning (or losing) margin per game.", "Margin predicts future records better than wins do.", E),
 "scored_per_game": ("Runs/goals scored per game.", "Offence.", "Component of margin.", E),
 "allowed_per_game": ("Runs/goals allowed per game.", "Defence and pitching/goaltending.", "Component of margin.", E),
 "pythag_win_pct": ("Pythagorean win %: RS^k/(RS^k+RA^k), k = 1.83 MLB, 2.0 NHL (D13).", "The record a team 'should' have had given its scoring margin.", "Estimate of true quality.", E),
 "luck": ("win_pct − pythag_win_pct.", "How many more (or fewer) wins the team got than its margin suggests.", "Lucky teams tend to regress; unlucky teams to rebound.", E),
 "corsi_pct": ("NHL shot-attempt share, all situations (MoneyPuck; D48).", "Share of all shot attempts in the team's games that the team took.", "Measures puck control; predictive of future results.", E),
 "xgoals_pct": ("NHL expected-goals share, all situations (MoneyPuck; **soft leakage, D54**).", "Share of shot *quality* the team generated.", "Strongest single NHL signal, but see the leakage note.", E),
 "pdo_5v5": ("NHL 5-on-5 shooting % + save %: GF/SOGF + 1 − GA/SOGA (D48).", "A luck gauge: shooting plus goaltending percentages, ≈1.000 on average.", "Extreme values tend to return to 1.000.", E),
 "underlying_source": ("MoneyPuck CSV URL.", "Where the hockey metrics came from.", "Audit only.", FX),
 # draft
 "draft_picks_used": ("Picks the team made in the year-t draft (D18, D19).", "How many new prospects the team drafted that year.", "More picks = more future talent (in theory).", DR),
 "draft_picks_rd1_2": ("Picks in rounds 1–2 (MLB incl. supplemental 1st, Competitive Balance Round A, PPI; D21).", "How many high-value early picks the team made.", "Early picks are the ones most likely to become good players.", DR),
 "draft_first_pick_number": ("Team's earliest overall pick in the year-t draft.", "Where the team picked first (1 = the first pick of the whole draft).", "Bad teams pick early; also a measure of incoming talent.", DR),
 "draft_rounds_in_year": ("Distinct round labels in that year's draft.", "How long the draft was that year.", "Context: MLB changed draft length.", DR),
 "draft_picks_used_pctile": ("Within league-season percentile of draft_picks_used (D20).", "Number of picks relative to other teams that year.", "Comparable across draft-length changes.", DR),
 "draft_source": ("API URL for the draft data.", "Where the draft data came from.", "Audit only.", FX),
 # front office
 "personnel_lead_tenure_years": ("Years the current GM has held the job at the prediction moment; GM only (D30, D36).", "How long the person running the roster has been in charge.", "New GMs often rebuild; long tenures can mean stability or stagnation.", PM),
 "personnel_lead_changed_past_year": ("1 if the GM at the moment differs from 365 days earlier (VACANT counts as a state). MLB 2026 is always 0 (D43).", "Whether the team changed its GM in the last year.", "A new GM can signal a rebuild.", PM),
 "personnel_lead_name": ("GM at the prediction moment (NaN if vacant or unknown).", "Who the GM was.", "Not a numeric feature.", PM),
 "personnel_lead_vacant": ("1 if the source shows no one held the GM title (D42).", "The team had no GM at that moment.", "Vacancies often follow upheaval.", PM),
 "personnel_lead_gap_carried": ("1 if the previous GM was carried across a short gap caused by year-only dates (D30, D37).", "Data-quality flag for the GM columns.", "Audit; treat these rows as less certain.", PM),
 "personnel_lead_tenure_left_censored": ("GM tenure reaches the start of the available history (≤1999), so the true tenure may be longer.", "Tenure may be undercounted.", "Audit.", PM),
 "coach_tenure_years": ("Consecutive seasons as season-end manager/head coach incl. t; a first season taken over mid-season counts 0.5 (D24).", "How long the current manager/coach has been in charge.", "Coaching changes often follow bad seasons.", RS),
 "coach_name": ("Manager/head coach at the end of regular season t.", "Who ran the team in games.", "Not a numeric feature.", RS),
 "coach_changed_during_regular_season": ("1 if more than one manager/coach ran the team during regular season t; later changes are not captured (D26).", "Whether the coach was replaced during the season.", "Mid-season firings signal trouble.", RS),
 "coach_tenure_left_censored": ("Tenure streak reaches the start of the coach history.", "Tenure may be undercounted.", "Audit.", RS),
 "manager_resolved_by_fallback": ("MLB: season-end manager chosen by the interim rule (D27).", "Data-quality flag (manager on leave, interim finished).", "Audit.", RS),
 # money
 "payroll_opening_day_usd": ("MLB Opening Day payroll, USD (Cot's Baseball Contracts; D53). 2020 pro-rated to 60 games.", "How much the team was paying its players at the start of the season.", "Money buys talent; also signals owner commitment.", OD),
 "payroll_rel_league_mean": ("Payroll / league mean payroll that season (D57).", "Spending relative to the average team that year (1.0 = average).", "Same as payroll but comparable across years.", OD),
 "payroll_rank": ("Within-season payroll rank, 1 = highest, recomputed from values (D53).", "Where the team ranked in spending.", "Same idea, ordinal.", OD),
 "cbt_threshold_usd": ("MLB luxury-tax (Competitive Balance Tax) threshold, USD; none 2000–02 (D50).", "The payroll level above which MLB teams pay a tax.", "Context for payroll_pct_of_cbt.", FX),
 "payroll_pct_of_cbt": ("payroll_opening_day_usd / cbt_threshold_usd.", "Payroll as a share of the luxury-tax line.", "Teams near the line spend like contenders.", OD),
 "cap_upper_limit_usd": ("NHL salary cap upper limit, USD (Wikipedia; D51).", "The most an NHL team may spend on player salaries that season.", "Context only (same for every team in a season).", FX),
 "team_cap_hit_usd": ("NHL team cap hit. **Empty by decision** (D52, D57).", "Would be the team's total salary-cap charge.", "Unavailable.", FX),
 "cap_space_pct": ("Teammate schema column; **empty for both leagues** (D57).", "Would be unused room under the salary cap.", "Unavailable; use `spending` for MLB.", FX),
 "payroll_source": ("Cot's page for the payroll.", "Where the payroll came from.", "Audit only.", FX),
 "spending_available": ("1 = spending observed (MLB); 0 = unavailable (NHL) (D57).", "Whether this league has a spending measure.", "Descriptor.", FX),
 # market
 "attendance_per_game": ("MLB average home attendance per game; 2020 NaN (D25). NHL not collected.", "How many fans came to home games.", "Market size and demand; partly a result of winning.", E),
 "attendance_rank": ("Within-season rank of attendance_per_game, 1 = highest.", "Where the team ranked in attendance.", "Same idea, ordinal.", E),
 "attendance_restricted": ("True for MLB 2020 and 2021 (COVID limits).", "Seasons when attendance was limited.", "Flag for unusual attendance.", FX),
 "market_available": ("1 = market proxy observed (MLB); 0 = unavailable (NHL).", "Whether this league has a market measure.", "Descriptor.", FX),
 # labels
 "observed_doom_next_3_seasons": ("Identical to `y_doom_3yr`; name required by the teammate's schema.", "The doom score (label).", "**Label, never a feature.**", LB),
 "y_pct_t1": ("win_pct_percentile in season t+1.", "Standing next season.", "**Label.**", LB),
 "y_pct_t2": ("win_pct_percentile in season t+2.", "Standing two seasons ahead.", "**Label.**", LB),
 "y_pct_t3": ("win_pct_percentile in season t+3.", "Standing three seasons ahead.", "**Label.**", LB),
 "y_doom_3yr": ("100 − mean(y_pct_t1, y_pct_t2, y_pct_t3); NaN unless all three exist (D11).", "The doom score: higher = worse finishes over the next three seasons.", "**The target.**", LB),
 "y_doomed_bottom25": ("y_doom_3yr ≥ 75 (binary).", "Whether the team averaged a bottom-quarter finish over the next three seasons.", "**Binary target.**", LB),
}

# crosswalk concepts (same order as FEATURE_CROSSWALK.md)
CW = [("roster_age_weighted", "age_weighted", "age_weighted"),
      ("vet_share", "share_production_age32plus", "share_production_age32plus"),
      ("vet_share_lq", "vet_share_lq", "vet_share_lq"),
      ("star_concentration", "top3_concentration", "top3_concentration"),
      ("margin_per_game", "point_diff_per_game", "point_diff_per_game"),
      ("luck", "luck", "luck"),
      ("underlying_quality", "pythag_win_pct", "corsi_pct"),
      ("draft_capital", "draft_picks_rd1_2", "draft_picks_rd1_2"),
      ("gm_tenure", "personnel_lead_tenure_years", "personnel_lead_tenure_years"),
      ("coach_tenure", "coach_tenure_years", "coach_tenure_years"),
      ("spending", "payroll_rel_league_mean", None),
      ("market", "attendance_per_game", None)]
for c, m, n in CW:
    if c in ("vet_share_lq", "luck"):
        pass
    else:
        base = META[m]
        META[c] = (f"**Shared concept.** Copy of MLB `{m}`" + (f" / NHL `{n}`" if n else " (NHL: unavailable)") + " (D58).",
                   base[1] if n == m or n is None else f"MLB: {base[1]} NHL: {META[n][1]}", base[2], base[3])
    src = META[c]
    META[c + "_lpct"] = (f"Within league-season percentile of `{c}`: (average rank − 1)/(n − 1) × 100 over non-missing values (D59).",
                         f"`{c}` expressed as 0–100 relative to the other teams in the same league and season.",
                         "Use this version when stacking leagues: raw units differ.", src[3])

GROUPS = [
 ("Playing-time weight", ["playing_time_weight", "team_pa", "team_bf", "skater_gp_sum", "goalie_gp_sum", "roster_players_used", "age_weight_coverage"]),
 ("roster_age_weighted", ["roster_age_weighted", "roster_age_weighted_lpct", "age_weighted", "age_weighted_hitters", "age_weighted_pitchers"]),
 ("vet_share", ["vet_share", "vet_share_lpct", "share_production_age32plus", "share_points_age32plus"]),
 ("vet_share_lq", ["vet_share_lq", "vet_share_lq_lpct", "vet_age_cut_lq"]),
 ("star_concentration", ["star_concentration", "star_concentration_lpct", "top3_concentration"]),
 ("margin_per_game", ["margin_per_game", "margin_per_game_lpct", "point_diff_per_game", "scored_per_game", "allowed_per_game"]),
 ("luck", ["luck", "luck_lpct"]),
 ("underlying_quality", ["underlying_quality", "underlying_quality_lpct", "pythag_win_pct", "corsi_pct", "xgoals_pct", "pdo_5v5", "underlying_source"]),
 ("draft_capital", ["draft_capital", "draft_capital_lpct", "draft_picks_rd1_2", "draft_picks_used", "draft_picks_used_pctile", "draft_first_pick_number", "draft_rounds_in_year", "draft_source"]),
 ("gm_tenure", ["gm_tenure", "gm_tenure_lpct", "personnel_lead_tenure_years", "personnel_lead_changed_past_year", "personnel_lead_name", "personnel_lead_vacant", "personnel_lead_gap_carried", "personnel_lead_tenure_left_censored"]),
 ("coach_tenure", ["coach_tenure", "coach_tenure_lpct", "coach_tenure_years", "coach_name", "coach_changed_during_regular_season", "coach_tenure_left_censored", "manager_resolved_by_fallback"]),
 ("spending", ["spending", "spending_lpct", "spending_available", "payroll_rel_league_mean", "payroll_opening_day_usd", "payroll_rank", "cbt_threshold_usd", "payroll_pct_of_cbt", "cap_space_pct", "cap_upper_limit_usd", "team_cap_hit_usd", "payroll_source"]),
 ("market", ["market", "market_lpct", "market_available", "attendance_per_game", "attendance_rank", "attendance_restricted"]),
 ("Identifiers and standings (not in the crosswalk)", ["league", "season_start_year", "franchise_id", "team", "team_name_then", "team_id", "wins", "losses", "ties", "ot_losses", "games", "win_pct", "win_pct_raw", "win_pct_percentile", "standings_source"]),
 ("Trajectory and context (not in the crosswalk)", ["win_pct_trailing_3_seasons", "win_pct_change_1yr", "win_pct_slope_3yr", "seasons_of_history", "short_season", "expansion_first_3_seasons"]),
]
LABELS = ["y_doom_3yr", "y_doomed_bottom25", "observed_doom_next_3_seasons", "y_pct_t1", "y_pct_t2", "y_pct_t3"]
documented = [c for _, cs in GROUPS for c in cs] + LABELS
assert sorted(documented) == sorted(df.columns), (set(df.columns) - set(documented), set(documented) - set(df.columns))
assert len(documented) == len(set(documented))
assert all(c in META for c in df.columns), [c for c in df.columns if c not in META]


def col_stats(c):
    out = {}
    for lg, g in (("MLB", M), ("NHL", N)):
        s = g[c]
        nn = s.notna() & (s.astype(str) != "")
        out[lg] = dict(cov=round(float(nn.mean()) * 100, 1),
                       first=int(g[nn].season_start_year.min()) if nn.any() else None,
                       last=int(g[nn].season_start_year.max()) if nn.any() else None)
    s = df[c].dropna()
    if s.astype(str).isin(["True", "False"]).all() and len(s):
        rng = f"share True = {s.astype(str).eq('True').mean() * 100:.1f}%"
    elif pd.api.types.is_numeric_dtype(df[c]) and len(s):
        if set(s.unique()) <= {0, 1}:
            rng = f"0/1; share 1 = {s.mean() * 100:.1f}%"
        else:
            rng = f"{fmt(s.min())} / {fmt(s.median())} / {fmt(s.max())}"
    elif len(s):
        rng = "e.g. " + ", ".join(f"`{v}`" for v in s.astype(str).value_counts().index[:2])
    else:
        rng = "— (empty)"
    leagues = ", ".join(lg for lg in ("MLB", "NHL") if out[lg]["cov"] > 0) or "none (empty)"
    cov = "; ".join(f"{lg} {out[lg]['cov']:.0f}%" + (f" ({out[lg]['first']}–{out[lg]['last']})" if out[lg]['first'] else "")
                    for lg in ("MLB", "NHL"))
    return dict(leagues=leagues, coverage=cov, range=rng)


COLS = {c: col_stats(c) for c in df.columns}
S["columns"] = COLS


def block(c):
    t, p, w, k = META[c]
    cs = COLS[c]
    return (f"**`{c}`**  \n"
            f"- Definition: {t}\n- Plain English: {p}\n- Why it might relate to doom: {w}\n"
            f"- Known: {k}\n- Leagues: {cs['leagues']} · Coverage: {cs['coverage']}\n"
            f"- Typical range (min / median / max): {cs['range']}\n")


# ---------------- DATA_COLLECTION.md ----------------
c = S["checks"]
ex = S["ex_draft"]
renames = "; ".join(f"`{k.split('|')[1]}` ({', '.join(v)})" for k, v in S["renames"].items())
phase_commits = "\n".join(f"| `{h}` | {d} | {m} |" for h, d, m in reversed(S["git"]))
corr_mlb = ", ".join(f"`{f}` ({p:+.2f})" for f, n, sp, p in S["corr_top"]["MLB"][:5])
corr_nhl = ", ".join(f"`{f}` ({p:+.2f})" for f, n, sp, p in S["corr_top"]["NHL"][:5])
tbd = ["playing-time weight", "roster_age_weighted", "vet_share", "vet_share_lq", "star_concentration",
       "margin_per_game", "luck", "underlying_quality", "draft_capital", "gm_tenure", "coach_tenure", "spending", "market"]

DC = f"""# How the MLB + NHL doom dataset was built

*For groupmates. All numbers below are computed by `docs/make_doc_stats.py` from the files in this repo. D-numbers refer to rows in `DECISIONS.md`.*

## 1. Goal

The dataset is for predicting which teams will be bad over the next few years. One row is one **team-season**: one club in one league in one season *t*. There are {fmt(S['rows'])} rows: {fmt(S['MLB_rows'])} for **MLB** (Major League Baseball, {S['MLB_first']}–{S['MLB_last']}) and {fmt(S['NHL_rows'])} for the **NHL** (National Hockey League, {S['NHL_first']}–{str(S['NHL_last'] + 1)[2:]}). The NHL season starts in the fall and ends the next spring, so "NHL {S['NHL_first']}" means the {S['NHL_first']}–{str(S['NHL_first'] + 1)[2:]} season.

**Doom score.** For each team-season we take the team's **league percentile** (where it finished relative to the other teams that year: 0 = worst record, 100 = best) in each of the next three seasons, average those three numbers, and subtract from 100: `y_doom_3yr = 100 − mean(percentile in t+1, t+2, t+3)`. Higher means more doomed. A team that finishes last three years running scores 100; a team that finishes first three years running scores 0. The score exists only when all three future seasons have been played, so the last three seasons of each league (MLB {S['MLB_label_last'] + 1}–{S['MLB_last']}, NHL {S['NHL_label_last'] + 1}–{S['NHL_last']}) have no label. Labelled rows: {fmt(S['MLB_labelled'])} MLB, {fmt(S['NHL_labelled'])} NHL. A binary version, `y_doomed_bottom25` (doom ≥ 75), is true for {S['MLB_bottom25_rate']}% of labelled MLB rows and {S['NHL_bottom25_rate']}% of NHL rows.

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

**Concrete example (D18).** The NHL holds its draft (the yearly selection of new young players) every June. For NHL season *t*, the June draft of year *t+1* happens *after* the June 15 prediction moment, and the draft order itself is set by season *t*'s results. Attaching that draft to season *t* would leak. So `draft_picks_used` and the other draft columns for NHL season *t* use only the June draft of year *t*, held before season *t* began. Example from the data: {ex['team']} {ex['season']} has `draft_first_pick_number` = {ex['first_pick']}, which is that June {ex['season'][:4]} draft. A second example: MLB year-end and luxury-tax payrolls are published after the prediction moment, so only the Opening Day payroll is used (D53).

## 3. Sources

| Source | What it provided | Years in this dataset | Access | Blocked / dropped and why |
|---|---|---|---|---|
| MLB Stats API (`statsapi.mlb.com`) | Standings, draft, managers, attendance, player stints, birthdates, official team totals | {S['MLB_first']}–{S['MLB_last']} (history from 1997; managers from 1990) | Public JSON API, cached | — |
| NHL stats REST (`api.nhle.com`) | Standings, franchise map, skater/goalie stints, birthdates | {S['NHL_first']}–{S['NHL_last']} (history 2002–04) | Public JSON API, cached | Team "percentages" report probed but not needed (D48) |
| NHL `api-web.nhle.com` | Draft picks; birthdates for players missing from the bios report | {S['NHL_first']}–{S['NHL_last']} | Public JSON API | — |
| Wikipedia | GM and head-coach history (team lists; individual articles for Braves/Orioles/Reds GMs); NHL salary cap by season | GM/coach spans from 1999; cap {S['cap_first']}–{S['cap_last']} | MediaWiki Action API, batched, descriptive User-Agent | Rate-limited (HTTP 429) once; one approved, throttled retry succeeded (D17). All rows `needs_verification` |
| Cot's Baseball Contracts (Baseball Prospectus) | MLB Opening Day payroll; luxury-tax thresholds | payroll {S['MLB_first']}–{S['MLB_last']}; tax {S['cbt_first']}–{S['cbt_last']} | Public web pages | Its printed payroll ranks contradict its own values → recomputed (D53) |
| Lahman database mirror | MLB salaries, cross-check only | 2000–2016 | CSV | First mirror returned 404; a second mirror worked |
| MoneyPuck | NHL Corsi, expected goals, PDO | {S['nhl_mp_first']}–{S['NHL_last']} | Public CSV | Starts in 2008, so NHL 2005–07 are empty (D48) |
| Spotrac | (would have been payroll / cap hits) | — | — | **Blocked** (HTTP 403) (D52) |
| PuckPedia | (NHL cap hits) | — | — | **Blocked** (anti-bot page) (D52) |
| CapWages | (NHL cap hits) | — | — | Reachable but only covers 2025-26 onward (D52) |
| Sports-Reference, FanGraphs | — | — | — | Not used by rule: they block automated access |

## 4. Phase by phase

Commits on the `adam` branch:

| Commit | Date | Message |
|---|---|---|
{phase_commits}

**Phase 1: core table and labels.**
- Built standings, percentiles, trailing features, cheap extras (Pythagorean win %, luck, trend) and the labels from the two league APIs.
- Mapped relocated and renamed clubs to one `franchise_id` each, e.g. the Thrashers → Jets and Coyotes → Utah (D05, D06).
- NHL overtime losses are stored in `ties` so that win % equals the NHL's official points % (D07).
- Checks: {c['phase1'][0]} of {c['phase1'][1]} passed. The two literal failures are expected and explained: {S['mlb_tie_rows']} MLB rows have a tie game (W+L+T = G holds everywhere), and tied best/worst records keep a percentile endpoint off exactly 0/100 (the tie-aware version passes).

**Phase 2: draft, front office, attendance.**
- Draft counts from the league APIs. MLB draft length changed a lot (D20 notes 40+ rounds before 2020 and 5 regular rounds in 2020; the data shows {S['mlb_draft_rounds_2020']} round labels for 2020 once bonus rounds are counted), so a within-season percentile was added (D20).
- Managers (MLB) from the API. The API's season list of managers turned out *not* to be in chronological order, so the season-end manager comes from a date query (D23); {S['fallback_rows']} rows needed an interim fallback rule (D27).
- GMs and NHL coaches parsed from Wikipedia. Problems found and fixed:
  - Wikipedia rate-limited the fetch; one approved, throttled retry succeeded (D17).
  - The date-range separator "to" matched inside "Oc**to**ber", silently dropping every term starting in October; fixing it recovered 14 spans (D40).
  - Achievement bullets such as "Won Presidents' Trophy" were read as people; a tenure-consistency check caught them (D44).
  - Many MLB pages give only years; a rule places year-only changes after that season so they never leak into it (D28, D39).
- Checks: {c['phase2'][0]} of {c['phase2'][1]} pass outright. The remaining item is a flag, not a failure: MLB 2026 shows 0 GM changes because every 2026 change in the sources has only a year (D43). A 5-row random source verification matched 5/5 (D41).

**Phase 3: roster age and composition.**
- Player-level playing time and birthdates from the league APIs; age-weighted roster features, veteran share and star concentration (D45).
- **Traded players** are counted by their stint with each team. The MLB query silently dropped players traded *away* in recent seasons; 29 team-seasons were repaired from per-player year-by-year stats, and player totals now equal official team totals for every MLB team-season (D46). NHL stints use a per-franchise filter (D47).
- NHL Corsi, expected goals and PDO from MoneyPuck (D48).
- Checks: {c['phase3'][0]} of {c['phase3'][1]} passed.

**Phase 4: money and final table.**
- MLB Opening Day payroll from Cot's for every team-season, cross-checked against Lahman (2000–16: r = {S['xcheck']['corr']:.3f}, median difference {S['xcheck']['median_abs_pct_diff']}%) (D53). Cot's printed ranks contradicted its own dollar values in most seasons, so ranks are recomputed.
- Luxury-tax thresholds (D50) and the NHL salary cap (D51) typed from cited sources, one citation per row.
- NHL team cap hits were unavailable (Spotrac blocked, PuckPedia anti-bot, CapWages no history); NHL spending is marked unavailable by decision (D52, D57).
- Final table with the teammate's 19 core columns first, the data dictionary, and a correlation review.
- Checks: {c['phase4'][0]} of {c['phase4'][1]} passed. Afterwards the feature crosswalk added shared concept columns ({c['crosswalk'][0]} of {c['crosswalk'][1]} checks passed).

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

- **Coverage gaps.** NHL Corsi / expected goals / PDO exist only from {S['nhl_mp_first']} ({S['nhl_mp_cov']}% of NHL rows). MLB GM is unknown (neither named nor vacant) for {S['MLB_gm_unknown']} team-seasons, mostly the Reds after 2008 (`data/manual/front_office_template.csv`, {S['fo_template_rows']} rows). NHL attendance was not collected.
- **Soft leakage.** MoneyPuck's expected-goals model is trained on all seasons, including those after *t* (D54). Separately, all sources were downloaded in {', '.join(S['download_dates'])} (git log), so season statistics reflect each source's current values. Any later stat corrections are therefore included; this effect was not measured.
- **Short seasons.** {', '.join(f"{k} ({v[0]}–{v[1]} games)" for k, v in S['short'].items())}. Records and counts from these seasons are noisier (`short_season`).
- **Front-office dates.** {S['spans_by_precision'].get('year', 0)} of {S['spans_total']} GM/coach spans have year-only dates ({S['spans_year_only_mlb']} of the {S['spans_mlb']} MLB spans). These changes are placed after that year's season, so they can show up a season late (D28). {S['MLB_gap_carried']} MLB and {S['NHL_gap_carried']} NHL rows carry the previous GM across a short date gap (`personnel_lead_gap_carried`).
- **Vacancies.** {S['MLB_vacant']} MLB and {S['NHL_vacant']} NHL rows have no GM according to the source (`personnel_lead_vacant` = 1); their tenure is empty by design.
- **NHL spending unavailable.** No historical team cap hits; `spending`, `cap_space_pct` and `team_cap_hit_usd` are empty for the NHL (D57).
- **MLB 2026 GM flags.** `personnel_lead_changed_past_year` sums to {S['mlb_2026_gm_changes']} for MLB 2026 because all 2026 changes are year-only (D43). That season has no label.
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

See `FEATURE_CROSSWALK.md`. Use the same 19 core columns (in order) and fill the shared concept columns plus their `_lpct` versions. Every NBA and NFL entry is still **TBD**: {', '.join(tbd)}. The `_lpct` formula is the same as `win_pct_percentile`: (average rank − 1)/(n − 1) × 100 within league-season, over non-missing values.
"""

# ---------------- DATASET_GUIDE.md ----------------
h, l = S["ex_high"], S["ex_low"]
ext = S["ex_ties"]
def ex_table(e):
    return ("| Season | Percentile |\n|---|---|\n"
            f"| {e['season']} (now, {e['wins']}–{e['losses']}) | {e['pct_now']} |\n" +
            "".join(f"| {s} | {p} |\n" for s, p in zip(e["next_seasons"], e["next3"])) +
            f"\nAverage of the next three: {e['mean_next3']} → doom = 100 − {e['mean_next3']} = **{e['recomputed']}** "
            f"(stored `y_doom_3yr` = {e['doom']}; `y_doomed_bottom25` = {e['bottom25']}).\n")

feat_sections = ""
for title, cols in GROUPS:
    feat_sections += f"\n### {title}\n\n" + "\n".join(block(c) for c in cols)
label_section = "\n".join(block(c) for c in LABELS)
reloc_lines = "\n".join(f"  - `{k.split('|')[1]}` ({k.split('|')[0]}): " + " → ".join(v) for k, v in S["renames"].items())
exp_lines = "; ".join(f"`{k}` first season {v[0]} (seasons_of_history starts at {v[1]})" for k, v in S["expansion"].items())
corr_rows = ""
for lg in ("MLB", "NHL"):
    for f, n, sp, p in S["corr_top"][lg][:6]:
        corr_rows += f"| {lg} | `{f}` | {int(n)} | {sp:+.2f} | {p:+.2f} |\n"

DG = f"""# MLB + NHL doom dataset: guide

*File: `data/processed/mlb_nhl_team_seasons.csv` ({fmt(S['rows'])} rows × {S['cols']} columns). All numbers come from `docs/make_doc_stats.py`. D-numbers refer to `DECISIONS.md`.*

## 1. Quick start

**One row = one team in one season *t*.** Key columns:
- `league`, `season_start_year`, `franchise_id`: identify the row (NHL `2017` = the 2017–18 season).
- `win_pct_percentile`: where the team finished in its league that season.
- The shared concept columns after the first 19 (e.g. `roster_age_weighted`, `spending`) and their `_lpct` versions.
- Labels: `y_doom_3yr` (0–100, higher = more doomed) and `y_doomed_bottom25` (yes/no).

**Reading a percentile.** Within one league and season, teams are ranked by record; the worst gets 0, the best 100, everyone else in between (ties share an average rank). A 75 means the team finished ahead of about three quarters of the league. Because it is relative, percentiles are comparable across leagues and years even though records are not.

**Worked example: high doom.** {h['team']} ({h['league']}), season {h['season']}:

{ex_table(h)}
**Worked example: low doom.** {l['team']} ({l['league']}), season {l['season']}:

{ex_table(l)}
Labels exist only for seasons with three played follow-up seasons: MLB through {S['MLB_label_last']}, NHL through {season_label('NHL', S['NHL_label_last'])}.

## 2. Sports primer

### MLB (baseball)

**Season.** {S['MLB_teams_per_season'][0]} teams each play a 162-game regular season (median `games` = {S['MLB_games_median']}), from spring to early fall, followed by playoffs ending with the World Series in October/November. The 2020 season was cut by the pandemic ({S['short']['MLB 2020'][0]}–{S['short']['MLB 2020'][1]} games per team in the data).

**Standings.** Teams are ranked by wins and losses. Ties are rare (games are normally played until someone wins); {S['mlb_tie_rows']} team-seasons here include one.

**GM vs manager.** The *general manager* (GM) builds the roster: trades, free-agent signings, the draft. Some clubs place a "president of baseball operations" above the GM; this dataset uses the GM (D36). The *manager* is the in-game boss who sets lineups and makes game decisions (the equivalent of a head coach).

**Draft.** Each summer teams select amateur players (high school and college). The draft is long (`draft_rounds_in_year` ranges {S['draft_rounds']['MLB'][0]}–{S['draft_rounds']['MLB'][1]} round labels here, counting bonus rounds), and drafted players usually take years to reach the major leagues.

**Payroll and the luxury tax.** MLB has no salary cap. Teams that spend above a threshold pay a *Competitive Balance Tax* ("luxury tax") on the excess. The threshold in this data runs from ${S['cbt_min_m']:.1f}M ({S['cbt_first']}) to ${S['cbt_max_m']:.1f}M ({S['cbt_last']}); there was no tax in 2000–02. "Opening Day payroll" is the salary total of the roster when the season starts.

**Plate appearances and batters faced.** A *plate appearance* (PA) is one completed turn at bat by a hitter. *Batters faced* (BF) counts the hitters a pitcher pitched to. PA + BF is used as a measure of how much a player played.

### NHL (hockey)

**Season.** {S['NHL_teams_per_season'][0]}–{S['NHL_teams_per_season'][-1]} teams (expansion: Vegas 2017, Seattle 2021) each play 82 regular-season games (median `games` = {S['NHL_games_median']}), October to April, then playoffs ending with the Stanley Cup final in June. Shortened seasons: 2012–13 (lockout), 2019–20 and 2020–21 (pandemic).

**Standings, overtime losses and points %.** A win earns 2 points. A game tied after 60 minutes goes to overtime and then a shootout. The loser of an overtime or shootout game is credited with an *overtime loss* (OTL) and still earns 1 point; a regulation loss earns 0. *Points %* = points / (2 × games). In this dataset `win_pct` equals points % because OTLs are stored in `ties` and get half credit (D07).

**GM vs head coach.** The GM builds the roster; the *head coach* runs practices and games.

**Draft.** Each June teams pick junior and amateur players; every NHL draft in this data has {S['draft_rounds']['NHL'][1]} rounds. Worse teams generally pick earlier.

**Salary cap.** The NHL has a hard cap: each team's total *cap hit* (average annual salary of its contracts) must stay under an upper limit, ${S['cap_min_m']:.1f}M in {S['cap_first']}–{str(S['cap_first'] + 1)[2:]} rising to ${S['cap_max_m']:.1f}M in {S['cap_last']}–{str(S['cap_last'] + 1)[2:]} (2012–13 shows the pro-rated ${S['cap_2012_m']:.1f}M). Team cap hits are not in this dataset.

**Time on ice.** *Time on ice* (TOI) is how long a player was on the ice; it is the hockey measure of playing time here.

**Corsi, expected goals and PDO.** *Corsi %* is the team's share of all shot attempts (shots, misses, blocked shots) in its games; teams that control the puck tend to win later. *Expected goals %* (xG %) weights each shot by how likely a shot like it is to score (from a model), then takes the team's share. *PDO* is 5-on-5 shooting % plus save %; it averages about 1.000 and extreme values usually do not last, so it is read as a luck gauge.

## 3. Feature reference

Grouped by concept in the order of `FEATURE_CROSSWALK.md`, then the remaining columns. "Coverage" is the share of rows that are non-missing, per league. "Typical range" is min / median / max over all rows.
{feat_sections}

## Labels — never use these as features

These columns describe seasons *t+1* to *t+3*. Using any of them, or anything computed from them, as a model input is leakage.

{label_section}

## 4. Gotchas

- **NHL `ties` holds overtime losses.** For NHL rows from 2005 on, `ties` equals `ot_losses` in {S['nhl_ties_equal_otl_share']}% of rows. Example: {ext['team']} {ext['season']} went {ext['w']}–{ext['l']}–{ext['otl']} (W–L–OTL), so `ties` = {ext['ties']} and `win_pct` = {ext['win_pct']} (points %), while `win_pct_raw` = {ext['win_pct_raw']}.
- **Short seasons.** {', '.join(f"{k}: {v[0]}–{v[1]} games" for k, v in S['short'].items())}. Use `short_season` to flag or down-weight them; counts such as wins are not comparable to full seasons.
- **Relocations and renames.** `franchise_id` follows the club, not the city. Clubs with more than one name in the data:
{reloc_lines}

  The Thrashers → Jets mapping comes from the NHL's own franchise IDs (D05); Coyotes → Utah is a manual mapping (D06). Some moves do not appear as a name change in the source: the Athletics (Oakland → Sacramento, `athletics`) and the Marlins (Florida → Miami, `miami-marlins`) keep the same short name, so see D03 for the full MLB mapping.
- **Vacant vs missing personnel.** `personnel_lead_vacant` = 1 ({S['MLB_vacant']} MLB, {S['NHL_vacant']} NHL rows) means the source shows no GM; `gm_tenure` is empty on purpose. A missing GM with vacant = 0 ({S['MLB_gm_unknown']} MLB, {S['NHL_gm_unknown']} NHL rows) means the data could not be found. Do not treat the two the same.
- **MLB 2020.** Attendance is NaN for all {S['att_2020_nan']} teams (no fans; D25). Payroll is pro-rated to 60 games: median Opening Day payroll ${S['pay_2020_median_m']:.1f}M in 2020 vs ${S['pay_2019_median_m']:.1f}M in 2019. Use `payroll_rel_league_mean` / `spending`, which compare teams within a season.
- **Expansion teams.** {exp_lines}. Their trailing features use fewer seasons; `seasons_of_history` tells you how many.
- **MLB 2026 GM changes are always 0** (year-only dates fall after the moment; D43). MLB 2026 is unlabelled.

## 5. Which features look predictive (exploratory)

From `reports/phase4.md` / `phase4_correlations.csv`. These are **exploratory correlations on labelled rows, not model results**. "Partial" is the Spearman correlation with `y_doom_3yr` after removing what `win_pct_percentile` already explains (D55). Negative means a higher value goes with *less* doom. Current standing alone has Spearman {S['corr_wpp']['MLB']:+.2f} (MLB) and {S['corr_wpp']['NHL']:+.2f} (NHL) with doom.

| League | Feature | n | Spearman | Partial (ctrl. percentile) |
|---|---|---|---|---|
{corr_rows}
Reading: after controlling for current standing, the clearest signals are NHL shot-based quality (expected goals, with its leakage caveat, and Corsi), scoring margin and Pythagorean win % in both leagues, and luck (lucky teams tend to slip). MLB payroll adds little beyond standing (partial {S['corr_payroll_mlb']:+.2f}). Some entries are data-quality flags (e.g. `personnel_lead_tenure_left_censored`, which marks long tenures cut off by the start of the history); treat them as artifacts, not signals. The correlations were computed before the shared concept columns were added, so they use the league column names (e.g. `point_diff_per_game` = `margin_per_game`).
"""

open(os.path.join(DOCS, "DATA_COLLECTION.md"), "w", encoding="utf-8").write(DC)
open(os.path.join(DOCS, "DATASET_GUIDE.md"), "w", encoding="utf-8").write(DG)
json.dump(S, open(os.path.join(DOCS, "doc_stats.json"), "w"), indent=1, default=str)
for name, txt in (("DATA_COLLECTION.md", DC), ("DATASET_GUIDE.md", DG)):
    print(f"{name}: {len(txt.split())} words")
