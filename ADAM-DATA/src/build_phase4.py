"""Phase 4 build: money (best effort) + final stacked table + data dictionary + correlation review.
Input: data/processed/mlb_nhl_core_phase3.csv. Outputs: data/processed/mlb_nhl_team_seasons.csv,
data/manual/{mlb_cbt_threshold,nhl_salary_cap,payroll_template}.csv,
reports/phase4_correlations.csv, reports/phase4_checks.csv."""
import glob, html, json, os, re, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_api_features as api

ROOT = api.ROOT
RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed")
MAN = os.path.join(ROOT, "data", "manual")
REP = os.path.join(ROOT, "reports")
KEY = ["league", "season_start_year", "franchise_id"]
COTS = "https://legacy.baseballprospectus.com/compensation/cots/"
COTS_CBA = COTS + "league-info/cba-history/"
NHL_CAP_URL = "https://en.wikipedia.org/wiki/NHL_salary_cap"
CORE = ["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ties", "games", "win_pct",
        "point_diff_per_game", "win_pct_percentile", "win_pct_trailing_3_seasons", "observed_doom_next_3_seasons",
        "draft_picks_used", "cap_space_pct", "personnel_lead_tenure_years", "personnel_lead_changed_past_year",
        "standings_source", "draft_source"]


# ---------------- static tables (typed from the cited source text) ----------------
def cbt_table():
    """MLB Competitive Balance Tax base thresholds, transcribed from Cot's CBA history (D50). 2000-02: no tax."""
    c = open(os.path.join(RAW, "cots", "cba-history.csv"), encoding="utf-8").read()
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)))
    vals = {2003: 117.0, 2004: 120.5, 2005: 128.0, 2006: 136.5, 2007: 148.0, 2008: 155.0, 2009: 162.0, 2010: 170.0,
            2011: 178.0, 2012: 178.0, 2013: 178.0, 2014: 189.0, 2015: 189.0, 2016: 189.0, 2017: 195.0, 2018: 197.0,
            2019: 206.0, 2020: 208.0, 2021: 210.0, 2022: 230.0, 2023: 233.0, 2024: 237.0, 2025: 241.0, 2026: 244.0}
    rows = []
    for y, v in vals.items():
        num = f"{v:g}"
        # every value must appear in the source text as "$<v> million" (2011 is printed as "2001" in the source)
        assert re.search(rf"\${re.escape(num)} million", txt), (y, v)
        rows.append(dict(season=y, cbt_threshold_usd=v * 1e6, source_url=COTS_CBA,
                         note="source typo: '$178 million in 2001' = 2011" if y == 2011 else ""))
    for y in (2000, 2001, 2002):
        rows.append(dict(season=y, cbt_threshold_usd=np.nan, source_url=COTS_CBA,
                         note="no tax: 1997-99 tax expired; 2003-06 thresholds start in the 2002 CBA"))
    t = pd.DataFrame(rows).sort_values("season")
    t.to_csv(os.path.join(MAN, "mlb_cbt_threshold.csv"), index=False)
    return t


def nhl_cap_table():
    """NHL cap upper limit by season from the Wikipedia 'NHL salary cap' chart data (D51)."""
    t = json.load(open(os.path.join(RAW, "wikipedia_money", "NHL_salary_cap.json"), encoding="utf-8"))["wikitext"]
    rows = [dict(season_start_year=int(m.group(2)), cap_upper_limit_usd=float(m.group(1)) * 1e6, source_url=NHL_CAP_URL,
                 note="2012-13 lockout season: pro-rated figure as charted" if m.group(2) == "2012" else "")
            for m in re.finditer(r"bar:\d+ from:0 till:([\d.]+)[^\n]*?\[\[(\d{4})[–-]\d{2} NHL season", t)]
    c = pd.DataFrame(rows).drop_duplicates("season_start_year").sort_values("season_start_year")
    c.to_csv(os.path.join(MAN, "nhl_salary_cap.csv"), index=False)
    return c


# ---------------- MLB payroll ----------------
def cots_payroll():
    rows = []
    for f in glob.glob(os.path.join(RAW, "cots", "*.csv")):
        fid = os.path.basename(f)[:-4]
        if fid in ("index", "cba-history"):
            continue
        t = open(f, encoding="utf-8").read()
        i = t.find("PAYROLLS")
        tb = t[i:t.find("</table>", i)]
        for tr in re.findall(r"<tr>(.*?)</tr>", tb, re.S):
            cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if not cells or not re.fullmatch(r"\d{4}", cells[0]):
                continue
            m = re.match(r"\$\s*([\d,]+)\s*\(\s*(\d+)\)", cells[1])
            if m:
                rows.append(dict(league="MLB", season_start_year=int(cells[0]), franchise_id=fid,
                                 payroll_opening_day_usd=float(m.group(1).replace(",", "")),
                                 payroll_rank_cots=int(m.group(2)), payroll_source=COTS + f"…/{fid}/"))
    p = pd.DataFrame(rows).drop_duplicates(["season_start_year", "franchise_id"])
    return p


LAHMAN_TEAM = {"ANA": "los-angeles-angels", "LAA": "los-angeles-angels", "ARI": "arizona-diamondbacks",
               "ATL": "atlanta-braves", "BAL": "baltimore-orioles", "BOS": "boston-red-sox", "CHA": "chicago-white-sox",
               "CHN": "chicago-cubs", "CIN": "cincinnati-reds", "CLE": "cleveland-guardians", "COL": "colorado-rockies",
               "DET": "detroit-tigers", "FLO": "miami-marlins", "MIA": "miami-marlins", "HOU": "houston-astros",
               "KCA": "kansas-city-royals", "LAN": "los-angeles-dodgers", "MIL": "milwaukee-brewers",
               "ML4": "milwaukee-brewers", "MIN": "minnesota-twins", "MON": "washington-nationals",
               "WAS": "washington-nationals", "NYA": "new-york-yankees", "NYN": "new-york-mets", "OAK": "athletics",
               "PHI": "philadelphia-phillies", "PIT": "pittsburgh-pirates", "SDN": "san-diego-padres",
               "SEA": "seattle-mariners", "SFN": "san-francisco-giants", "SLN": "st-louis-cardinals",
               "TBA": "tampa-bay-rays", "TEX": "texas-rangers", "TOR": "toronto-blue-jays"}


def lahman_payroll():
    s = pd.read_csv(os.path.join(RAW, "lahman", "Salaries.csv"))
    s = s[s.yearID >= 2000]
    s["franchise_id"] = s.teamID.map(LAHMAN_TEAM)
    return s.groupby(["yearID", "franchise_id"]).salary.sum().rename("lahman_payroll").reset_index() \
        .rename(columns={"yearID": "season_start_year"})


# ---------------- correlations ----------------
def rank_resid(x, z):
    """Residual of rank(x) after OLS on rank(z)."""
    rx, rz = x.rank(), z.rank()
    A = np.c_[np.ones(len(rz)), rz]
    beta, *_ = np.linalg.lstsq(A, rx.values, rcond=None)
    return rx.values - A @ beta


def correlations(df, features):
    out = []
    for lg, g in df[df.y_doom_3yr.notna()].groupby("league"):
        for c in features:
            sub = g[list(dict.fromkeys([c, "y_doom_3yr", "win_pct_percentile"]))].dropna()
            if len(sub) < 30 or sub[c].nunique() < 2:
                continue
            sp = sub[c].rank().corr(sub.y_doom_3yr.rank())
            if c == "win_pct_percentile":
                ps = np.nan
            else:
                ps = np.corrcoef(rank_resid(sub[c], sub.win_pct_percentile),
                                 rank_resid(sub.y_doom_3yr, sub.win_pct_percentile))[0, 1]
            out.append(dict(league=lg, feature=c, n=len(sub), spearman=round(sp, 3),
                            partial_spearman_ctrl_win_pct_percentile=round(ps, 3)))
    return pd.DataFrame(out)


def main():
    os.makedirs(MAN, exist_ok=True)
    df = pd.read_csv(os.path.join(PROC, "mlb_nhl_core_phase3.csv"))
    cbt, cap = cbt_table(), nhl_cap_table()
    print(f"CBT thresholds: {cbt.cbt_threshold_usd.notna().sum()} seasons; NHL cap: {len(cap)} seasons "
          f"{cap.season_start_year.min()}-{cap.season_start_year.max()}")

    pay = cots_payroll()
    lah = lahman_payroll()
    x = pay.merge(lah, on=["season_start_year", "franchise_id"], how="inner")
    rel = (x.payroll_opening_day_usd / x.lahman_payroll - 1).abs()
    xcheck = dict(n=len(x), corr=round(x.payroll_opening_day_usd.corr(x.lahman_payroll), 4),
                  median_abs_pct_diff=round(rel.median() * 100, 2), share_within_10pct=round((rel <= 0.10).mean(), 3))
    print(f"Cot's vs Lahman payroll (2000-2016): {xcheck}")

    df = df.merge(pay, on=KEY, how="left")
    df = df.merge(cbt[["season", "cbt_threshold_usd"]].rename(columns={"season": "season_start_year"})
                  .assign(league="MLB"), on=["league", "season_start_year"], how="left")
    df["payroll_pct_of_cbt"] = df.payroll_opening_day_usd / df.cbt_threshold_usd
    # D53: Cot's printed ranks disagree with its own dollar values in 23 of 27 seasons -> own rank (1 = highest)
    df["payroll_rank"] = df.groupby(["league", "season_start_year"]).payroll_opening_day_usd.rank(ascending=False, method="min")
    df = df.drop(columns="payroll_rank_cots")
    df["payroll_rel_league_mean"] = df.payroll_opening_day_usd / df.groupby(["league", "season_start_year"]) \
        .payroll_opening_day_usd.transform("mean")
    df = df.merge(cap.assign(league="NHL")[["league", "season_start_year", "cap_upper_limit_usd"]],
                  on=["league", "season_start_year"], how="left")
    df["team_cap_hit_usd"] = np.nan  # no historical source available (D52) -> template
    df["cap_space_pct"] = (df.cap_upper_limit_usd - df.team_cap_hit_usd) / df.cap_upper_limit_usd

    # manual template for missing money rows
    miss = df[((df.league == "MLB") & df.payroll_opening_day_usd.isna()) | ((df.league == "NHL") & df.team_cap_hit_usd.isna())]
    tmpl = miss[["league", "franchise_id", "season_start_year"]].rename(columns={"season_start_year": "season"})
    tmpl = tmpl.assign(payroll="", measure=np.where(tmpl.league == "NHL", "team cap hit (USD), season t",
                                                     "Opening Day payroll (USD)"), source_url="")
    tmpl.to_csv(os.path.join(MAN, "payroll_template.csv"), index=False)
    print(f"payroll template rows: {len(tmpl)} ({tmpl.league.value_counts().to_dict()})")

    # final column order: teammate core first, features, sources/audit, labels last
    labels = [c for c in df.columns if c.startswith("y_")]
    audit = ["team_name_then", "team_id", "payroll_source", "underlying_source"]
    rest = [c for c in df.columns if c not in CORE + labels + audit]
    df = df[CORE + rest + audit + labels].sort_values(KEY).reset_index(drop=True)
    df.to_csv(os.path.join(PROC, "mlb_nhl_team_seasons.csv"), index=False)
    print(f"wrote mlb_nhl_team_seasons.csv: {df.shape}")

    # correlations: every numeric feature (not labels / ids / audit)
    skip = set(labels) | {"observed_doom_next_3_seasons", "season_start_year", "team_id"}
    feats = [c for c in df.columns if c not in skip and c not in audit and pd.api.types.is_numeric_dtype(df[c])
             or (c in ("short_season", "expansion_first_3_seasons", "attendance_restricted", "coach_tenure_left_censored",
                       "personnel_lead_tenure_left_censored") and c not in skip)]
    for c in feats:
        df[c] = pd.to_numeric(df[c].map(lambda v: {True: 1, False: 0, "True": 1, "False": 0}.get(v, v)), errors="coerce")
    corr = correlations(df, feats)
    corr.to_csv(os.path.join(REP, "phase4_correlations.csv"), index=False)

    # checks
    m, n = df[df.league == "MLB"], df[df.league == "NHL"]
    checks = [
        ("core columns first, in the teammate's order", list(df.columns[:len(CORE)]) == CORE, ""),
        ("one row per key; 1,454 rows", (not df.duplicated(KEY).any()) and len(df) == 1454, str(len(df))),
        ("MLB Opening Day payroll for every team-season 2000-2026", m.payroll_opening_day_usd.notna().all(),
         f"missing {int(m.payroll_opening_day_usd.isna().sum())}"),
        ("payroll_rank recomputed from values (1..30 each MLB season)",
         m.groupby("season_start_year").payroll_rank.agg(lambda r: r.min() == 1 and r.max() <= 30).all(), ""),
        ("Cot's vs Lahman (2000-2016): >=80% within 10%", xcheck["share_within_10pct"] >= 0.8, str(xcheck)),
        ("every CBT threshold value found verbatim in the cited source text", True, "asserted on load"),
        ("NHL cap ceiling for every NHL season 2005-2025", n.cap_upper_limit_usd.notna().all(), ""),
        ("labels unchanged vs Phase 1 core (tolerance 1e-9)", np.allclose(
            df.set_index(KEY).y_doom_3yr.sort_index(),
            pd.read_csv(os.path.join(PROC, "mlb_nhl_core.csv")).set_index(KEY).y_doom_3yr.sort_index(),
            atol=1e-9, equal_nan=True), ""),
    ]
    for c, ok, det in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {c} {det}")
    pd.DataFrame(checks, columns=["check", "pass", "detail"]).to_csv(os.path.join(REP, "phase4_checks.csv"), index=False)
    json.dump(xcheck, open(os.path.join(REP, "phase4_payroll_crosscheck.json"), "w"))
    return df, corr


if __name__ == "__main__":
    main()
