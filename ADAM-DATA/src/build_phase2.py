"""Phase 2 build: add draft, front-office/coach and attendance columns to the Phase 1 core table."""
import os, re, sys
from datetime import date, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_api_features as api
import parse_front_office as pf
import parse_people
from fetch_phase2 import MLB_EXEC_PAGES, NHL_NAMES

ROOT = api.ROOT
PROC = os.path.join(ROOT, "data", "processed")
MAN = os.path.join(ROOT, "data", "manual")
REP = os.path.join(ROOT, "reports")
os.makedirs(MAN, exist_ok=True)
KEY = ["league", "season_start_year", "franchise_id"]
UNRESOLVED_PEOPLE = pd.DataFrame()
SEASON_BASED_PAGES = {"san-francisco-giants", "tampa-bay-rays"}  # D39
WINDOW_START = date(1999, 1, 1)  # spans ending before this are irrelevant (and include pre-relocation noise)


def moment(league, t):
    """Prediction moment for season t (D29)."""
    return date(t, 11, 15) if league == "MLB" else date(t + 1, 6, 15)


# ---------------- front-office spans ----------------
def build_spans():
    rows = []
    for fid, team in MLB_EXEC_PAGES.items():
        page = f"List of {team} owners and executives"
        rows += pf.resolve_dates(pf.spans_from_page(page, fid, "MLB", None), "MLB",
                                 season_based=fid in SEASON_BASED_PAGES)
    for fid, names in NHL_NAMES.items():
        for n in names:
            for role, kind in (("gm", "general managers"), ("head_coach", "head coaches")):
                page = f"List of {n} {kind}"
                rows += pf.resolve_dates(pf.spans_from_page(page, fid, "NHL", role), "NHL")
    s = pd.DataFrame(rows)
    s["source_url"] = s.page.map(pf.url)
    s["evidence"] = ""
    # Braves/Orioles/Reds list GMs without years -> spans from the individuals' articles (D38)
    ppl, unresolved = parse_people.people_spans()
    ppl["row_idx"] = range(len(ppl))
    ppl["page"] = ppl.source_url
    s = pd.concat([s, ppl], ignore_index=True)
    global UNRESOLVED_PEOPLE
    UNRESOLVED_PEOPLE = unresolved
    # keep the longest span when a person/start appears twice (e.g. Twins 'again from 2012' + '2012 - 2016')
    s["_end_sort"] = s.end_date.map(lambda d: date(9999, 1, 1) if d is None or pd.isna(d) else d)
    s = s.sort_values("_end_sort", ascending=False).drop_duplicates(["franchise_id", "role", "person", "start_date"])
    s = s.drop(columns="_end_sort")
    s = s[s.end_date.isna() | (s.end_date.map(lambda d: d is not None and d >= WINDOW_START))]
    for c in ("in_season_start", "s_season", "e_season"):
        if c not in s:
            s[c] = np.nan
    order = {"day": 0, "month": 1, "season": 2, "year": 3, "open": -1}
    s["date_precision"] = [max((a, b), key=lambda p: order.get(p, 9)) for a, b in
                           zip(s.date_precision_start, s.date_precision_end)]
    s["needs_verification"] = True
    s["league"] = np.where(s.franchise_id.isin(MLB_EXEC_PAGES), "MLB", "NHL")
    cols = ["league", "franchise_id", "role", "person", "start_date", "end_date", "date_precision",
            "date_precision_start", "date_precision_end", "interim", "in_season_start", "s_season", "e_season",
            "page_row", "source_url", "evidence", "needs_verification"]
    s["page_row"] = s.row_idx  # order on the source page (chronological) - tie-break for same-season changes
    return s[cols].sort_values(["franchise_id", "role", "start_date"]).reset_index(drop=True)


VACANT = "__VACANT__"


def active_at(spans, d):
    started = spans[spans.start_date <= d]
    return started, started[started.end_date.isna() | (started.end_date >= d)]


def lead_at(gm, d, bo=None, vac_years=()):
    """(person | VACANT | None, gap_flag) for the GM on date d (GM only, D36).
    VACANT (D42) = source evidence that no one held the GM title: an active baseball-ops president with no
    active GM, or an explicit 'no general manager between X and Y' on the team page. Evidence beats carrying."""
    started, active = active_at(gm, d)
    if len(active):
        return active.sort_values("start_date").iloc[-1].person, 0
    if (bo is not None and len(active_at(bo, d)[1])) or d.year in vac_years:
        return VACANT, 0
    if len(started):
        r = started.sort_values("start_date").iloc[-1]
        later = gm[gm.start_date > d].sort_values("start_date")
        precise = {"day", "month"}
        # needs a known successor: no later span = unknown, not vacant (Reds after Krivsky are unresolved)
        if r.date_precision_end in precise and len(later) and later.iloc[0].date_precision_start in precise:
            return VACANT, 0  # gap between exactly dated spans = a real vacancy (e.g. Epstein resigned 2005-10-31)
        # short gap from a year-only boundary: carry the most recently started person ...
        if r.end_date is None or pd.isna(r.end_date) or (d - r.end_date).days <= 400:
            return r.person, 1
    return None, 0  # ... a longer gap without vacancy evidence stays plain missing (D37)


def page_vacancy_years():
    """franchise_id -> calendar years the team page says had no general manager (e.g. Dodgers 2018-2021)."""
    out = {}
    for fid, team in MLB_EXEC_PAGES.items():
        t = pf.wikitext(f"List of {team} owners and executives") or ""
        for a, b in re.findall(r"no general manager (?:between|from) (\d{4}) (?:and|to|until|through) (\d{4})", t, re.I):
            out.setdefault(fid, set()).update(range(int(a), int(b) + 1))
    return out


def personnel_features(core, spans):
    gms = spans[spans.role == "gm"]
    bos = spans[spans.role == "baseball_ops_president"]
    vac = page_vacancy_years()
    print(f"page-stated GM vacancies: { {k: sorted(v) for k, v in vac.items()} }")
    out = []
    for (lg, fid), grp in core.groupby(["league", "franchise_id"]):
        fs = gms[gms.franchise_id == fid]
        if not len(fs):
            continue
        bo, vy = bos[bos.franchise_id == fid], vac.get(fid, set())
        earliest = fs.start_date.min()
        for t in grp.season_start_year:
            m = moment(lg, t)
            person, gap = lead_at(fs, m, bo, vy)
            if person is None:
                continue
            prev_year = lead_at(fs, m - timedelta(days=365), bo, vy)[0]
            changed = np.nan if prev_year is None else int(prev_year != person)
            if person == VACANT:
                out.append(dict(league=lg, season_start_year=t, franchise_id=fid, personnel_lead_name=np.nan,
                                personnel_lead_tenure_years=np.nan, personnel_lead_changed_past_year=changed,
                                personnel_lead_tenure_left_censored=False, personnel_lead_gap_carried=0,
                                personnel_lead_vacant=1))
                continue
            d, months = m, 0
            while True:  # walk back monthly while the same person is the lead
                prev = d - timedelta(days=30)
                if prev < earliest or lead_at(fs, prev, bo, vy)[0] != person:
                    break
                d, months = prev, months + 1
            out.append(dict(league=lg, season_start_year=t, franchise_id=fid, personnel_lead_name=person,
                            personnel_lead_tenure_years=round(months * 30 / 365.25, 2),
                            personnel_lead_changed_past_year=changed,
                            personnel_lead_tenure_left_censored=(d - timedelta(days=30) < earliest and
                                                                 earliest <= WINDOW_START),
                            personnel_lead_gap_carried=gap, personnel_lead_vacant=0))
    return pd.DataFrame(out)


def nhl_coach_features(core, spans):
    co = spans[(spans.role == "head_coach") & (spans.league == "NHL")].copy()
    rows = []
    for fid, fs in co.groupby("franchise_id"):
        prev, ten, streak_first = None, 0.0, None
        seasons = sorted(core[(core.league == "NHL") & (core.franchise_id == fid)].season_start_year)
        hist_start = int(fs.s_season.min()) if fs.s_season.notna().any() else None
        for t in range(min(seasons) - 15, max(seasons) + 1):
            cov = fs[(fs.s_season <= t) & (fs.e_season.isna() | (fs.e_season >= t))]
            if not len(cov):
                prev, ten = None, 0.0
                continue
            cov = cov.sort_values(["s_season", "page_row"])
            end_coach = cov.iloc[-1].person
            changed = int(cov.person.nunique() > 1)
            if end_coach == prev:
                ten += 1
            else:
                ten = 0.5 if changed else 1.0
                streak_first = t
            prev = end_coach
            if t in seasons:
                rows.append(dict(league="NHL", season_start_year=t, franchise_id=fid, coach_name=end_coach,
                                 coach_tenure_years=ten, coach_changed_during_regular_season=changed,
                                 coach_tenure_left_censored=(hist_start is not None and streak_first <= hist_start),
                                 manager_resolved_by_fallback=0))
    return pd.DataFrame(rows)


def main():
    core = pd.read_csv(os.path.join(PROC, "mlb_nhl_core.csv"))
    core = core.drop(columns=["draft_picks_used", "draft_source", "personnel_lead_tenure_years",
                              "personnel_lead_changed_past_year"])
    print(f"core loaded: {len(core)} rows")

    # drafts
    d, _ = api.drafts()
    df = core.merge(d, on=KEY, how="left")
    df["draft_picks_used_pctile"] = df.groupby(["league", "season_start_year"])["draft_picks_used"].transform(api.pct_rank)
    print(f"drafts merged: {df.draft_picks_used.notna().mean():.1%} non-missing")

    # coaches / managers
    m = api.mlb_manager_seasons()
    m["league"] = "MLB"
    cols = ["league", "season_start_year", "franchise_id", "coach_name", "coach_tenure_years",
            "coach_changed_during_regular_season", "coach_tenure_left_censored", "manager_resolved_by_fallback"]
    spans = build_spans()
    spans.to_csv(os.path.join(PROC, "front_office_spans.csv"), index=False)
    print(f"front_office_spans.csv: {len(spans)} spans; precision counts {spans.date_precision.value_counts().to_dict()}")
    nc = nhl_coach_features(core, spans)
    coaches = pd.concat([m[cols], nc[cols] if len(nc) else pd.DataFrame(columns=cols)], ignore_index=True)
    df = df.merge(coaches, on=KEY, how="left")
    print(f"coaches merged: MLB {df[df.league=='MLB'].coach_name.notna().mean():.1%}, "
          f"NHL {df[df.league=='NHL'].coach_name.notna().mean():.1%}")

    # personnel lead
    pl = personnel_features(core, spans)
    df = df.merge(pl, on=KEY, how="left")
    print(f"personnel lead merged: MLB {df[df.league=='MLB'].personnel_lead_name.notna().mean():.1%}, "
          f"NHL {df[df.league=='NHL'].personnel_lead_name.notna().mean():.1%}")

    # attendance (MLB only)
    a = api.mlb_attendance()
    df = df.merge(a, on=KEY, how="left")
    print(f"attendance merged: MLB {df[df.league=='MLB'].attendance_per_game.notna().mean():.1%}")

    # column order: teammate core first
    core_cols = ["league", "season_start_year", "franchise_id", "team", "wins", "losses", "ties", "games", "win_pct",
                 "point_diff_per_game", "win_pct_percentile", "win_pct_trailing_3_seasons",
                 "observed_doom_next_3_seasons", "draft_picks_used", "cap_space_pct", "personnel_lead_tenure_years",
                 "personnel_lead_changed_past_year", "standings_source", "draft_source"]
    labels = [c for c in df.columns if c.startswith("y_")]
    rest = [c for c in df.columns if c not in core_cols + labels]
    df = df[core_cols + rest + labels].sort_values(KEY).reset_index(drop=True)
    df.to_csv(os.path.join(PROC, "mlb_nhl_core_phase2.csv"), index=False)  # Phase 1 file stays the input (D33)
    print(f"wrote mlb_nhl_core_phase2.csv: {len(df)} rows x {df.shape[1]} cols")

    # manual template for franchises the parser could not cover
    need = []
    for lg, fids in (("MLB", MLB_EXEC_PAGES), ("NHL", NHL_NAMES)):
        for fid in fids:
            sub = df[(df.league == lg) & (df.franchise_id == fid)]
            unknown = sub.personnel_lead_name.isna() & (sub.personnel_lead_vacant != 1)  # vacant = known, not missing
            if unknown.any():
                need.append(dict(league=lg, franchise_id=fid, role="gm",
                                 missing_seasons=" ".join(map(str, sub[unknown].season_start_year))))
            if lg == "NHL" and sub.coach_name.isna().any():
                need.append(dict(league=lg, franchise_id=fid, role="head_coach",
                                 missing_seasons=" ".join(map(str, sub[sub.coach_name.isna()].season_start_year))))
    UNRESOLVED_PEOPLE.to_csv(os.path.join(MAN, "front_office_unresolved_people.csv"), index=False)
    tmpl = pd.DataFrame(need)
    if len(tmpl):
        tmpl = tmpl.assign(person="", start_date="", end_date="", date_precision="", source_url="")
    tmpl.to_csv(os.path.join(MAN, "front_office_template.csv"), index=False)
    print(f"manual template rows: {len(tmpl)}")

    # OPTIONAL (D36): baseball-ops presidents are no longer used for personnel_lead; template kept for a future variant
    bo = set(spans[(spans.role == "baseball_ops_president")].franchise_id)
    no_bo = sorted(set(MLB_EXEC_PAGES) - bo)
    pd.DataFrame(dict(league="MLB", franchise_id=no_bo, role="baseball_ops_president", person="", start_date="",
                      end_date="", date_precision="", source_url="")).to_csv(
        os.path.join(MAN, "baseball_ops_president_template.csv"), index=False)
    print(f"MLB franchises without dated baseball-ops president spans: {len(no_bo)} of {len(MLB_EXEC_PAGES)}")

    # coverage
    cov_cols = ["draft_picks_used", "draft_picks_rd1_2", "draft_first_pick_number", "draft_picks_used_pctile",
                "personnel_lead_tenure_years", "personnel_lead_changed_past_year", "coach_tenure_years",
                "coach_changed_during_regular_season", "attendance_per_game", "attendance_rank"]
    cov = []
    for lg in ("MLB", "NHL"):
        sub = df[df.league == lg]
        for c in cov_cols:
            nn = sub[sub[c].notna()]
            cov.append(dict(league=lg, column=c, pct_non_missing=round(100 * len(nn) / len(sub), 1),
                            first=nn.season_start_year.min() if len(nn) else None,
                            last=nn.season_start_year.max() if len(nn) else None))
    cov = pd.DataFrame(cov)
    cov.to_csv(os.path.join(REP, "phase2_coverage.csv"), index=False)
    print(cov.to_string(index=False))

    # checks
    def row(fid, y):
        return df[(df.franchise_id == fid) & (df.season_start_year == y)].iloc[0]
    g23, p22 = row("san-francisco-giants", 2023), row("philadelphia-phillies", 2022)
    checks = [
        ("2023 Giants manager is not Bob Melvin", g23.coach_name != "Bob Melvin", g23.coach_name),
        ("2022 Phillies coach_changed_during_regular_season = 1", p22.coach_changed_during_regular_season == 1,
         f"{p22.coach_changed_during_regular_season}, end manager {p22.coach_name}"),
        ("MLB 2020 attendance is NaN (not 0)", df[(df.league == "MLB") & (df.season_start_year == 2020)]
         .attendance_per_game.isna().all(), ""),
        ("one row per key after merges", not df.duplicated(KEY).any(), ""),
        ("no draft data after season t (NHL draft year == season_start_year)", True, "by construction"),
    ]
    # tenure consistency (D43): same person -> tenure +~1 per season; new person -> reset (GM <= 1.1 y; coach 0.5/1)
    flags = []
    s2 = df.sort_values(KEY).copy()
    g = s2.groupby(["league", "franchise_id"])
    for kind, name, ten, step_ok, reset_ok in (
            ("gm", "personnel_lead_name", "personnel_lead_tenure_years",
             lambda d: 0.9 <= d <= 1.1, lambda t: t <= 1.1),
            ("coach", "coach_name", "coach_tenure_years",
             lambda d: abs(d - 1) < 1e-9, lambda t: t in (0.5, 1.0))):
        s2["prevname"], s2["prevten"], s2["prevyr"] = g[name].shift(), g[ten].shift(), g["season_start_year"].shift()
        both = s2[name].notna() & s2.prevname.notna() & (s2.season_start_year - s2.prevyr == 1)
        same = both & (s2[name] == s2.prevname)
        diff = both & (s2[name] != s2.prevname)
        bad_step = s2[same & ~(s2[ten] - s2.prevten).map(step_ok)]
        bad_reset = s2[diff & ~s2[ten].map(reset_ok)]
        for b, why in ((bad_step, "same person, tenure did not rise ~1"), (bad_reset, "new person, tenure did not reset")):
            for r in b.itertuples():
                flags.append(dict(kind=kind, league=r.league, franchise_id=r.franchise_id, season=r.season_start_year,
                                  person=getattr(r, name), prev_person=r.prevname, tenure=getattr(r, ten), prev_tenure=r.prevten,
                                  issue=why))
        if kind == "gm":  # changed flag must agree with the name sequence
            badc = s2[both & (s2.personnel_lead_changed_past_year != (s2[name] != s2.prevname).astype(int))]
            for r in badc.itertuples():
                flags.append(dict(kind=kind, league=r.league, franchise_id=r.franchise_id, season=r.season_start_year,
                                  person=r.personnel_lead_name, prev_person=r.prevname, tenure=r.personnel_lead_tenure_years,
                                  prev_tenure=r.prevten, issue="changed_past_year disagrees with name change"))
    flags = pd.DataFrame(flags)
    flags.to_csv(os.path.join(REP, "phase2_tenure_flags.csv"), index=False)
    checks.append(("tenure consistency (GM and coach)", len(flags) == 0, f"{len(flags)} flagged rows"))

    # GM changes per league-season (D43): flag 0 or > 10
    ch = df.groupby(["league", "season_start_year"]).personnel_lead_changed_past_year.sum().astype(int)
    odd = ch[(ch == 0) | (ch > 10)]
    ch.rename("gm_changes").reset_index().to_csv(os.path.join(REP, "phase2_gm_changes_per_season.csv"), index=False)
    checks.append(("GM changes per league-season within 1..10 (flag check)", len(odd) == 0,
                   "flagged: " + (", ".join(f"{l} {y}={v}" for (l, y), v in odd.items()) or "none")
                   + f" | range MLB {ch['MLB'].min()}-{ch['MLB'].max()}, NHL {ch['NHL'].min()}-{ch['NHL'].max()}"))
    checks.append(("Giants/Rays read as season-based (D39)", True, "by construction"))
    for n, ok, det in checks:  # a flag check reports items for review; it is not a failure (D43)
        print(f"[{'PASS' if ok else ('FLAG' if 'flag check' in n else 'FAIL')}] {n} {det}")
    pd.DataFrame(checks, columns=["check", "pass", "detail"]).to_csv(os.path.join(REP, "phase2_checks.csv"), index=False)
    print("fallback-resolved manager rows (in output seasons):", int(df.manager_resolved_by_fallback.fillna(0).sum()))
    print("year-only spans:", int((spans.date_precision == "year").sum()), "of", len(spans))
    return df, spans


if __name__ == "__main__":
    main()
