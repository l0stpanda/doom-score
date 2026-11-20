"""Phase 2 features from official APIs: drafts, MLB managers, MLB attendance.
Each function returns a DataFrame keyed by (league, season_start_year, franchise_id)."""
import json, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
MLB_DRAFT = "https://statsapi.mlb.com/api/v1/draft/{y}"
NHL_DRAFT = "https://api-web.nhle.com/v1/draft/picks/{y}/all"
MANAGER_JOBS = ("MNGR", "NTRM")  # Manager, Interim Manager


def load(src, name):
    p = os.path.join(RAW, src, name + ".json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def slug(name):
    return name.lower().replace(".", "").replace("é", "e").replace(" ", "-")


def mlb_franchise_map():
    return {t["id"]: slug(t["name"]) for t in load("mlb_meta", "teams_2026")["teams"]}


def nhl_franchise_map():
    fr = {f["id"]: f["fullName"] for f in load("nhl_meta", "franchise")["data"]}
    out = {}
    for t in load("nhl_meta", "team")["data"]:
        fid = {28: 40}.get(t["franchiseId"], t["franchiseId"])  # Coyotes -> Utah (D06)
        if fid in fr:
            out[t["id"]] = slug(fr[fid])
    return out


def pct_rank(s):
    return (s.rank(method="average", ascending=True) - 1) / (len(s) - 1) * 100


# ---------------- drafts ----------------
def drafts():
    rows = []
    mfr = mlb_franchise_map()
    for y in range(1997, 2027):
        rounds = load("mlb_draft", str(y))["drafts"]["rounds"]
        labels = [r["round"] for r in rounds]
        early = set(labels[: labels.index("2") + 1])  # everything listed up to and incl. round 2 (D21)
        for r in rounds:
            for p in r["picks"]:
                if p.get("isPass") or "team" not in p:
                    continue
                rows.append(dict(league="MLB", season_start_year=y, franchise_id=mfr[p["team"]["id"]],
                                 pick=p["pickNumber"], early=r["round"] in early, round=r["round"],
                                 draft_source=MLB_DRAFT.format(y=y)))
    nfr = nhl_franchise_map()
    for y in [2002, 2003] + list(range(2005, 2026)):
        for p in load("nhl_draft", str(y))["picks"]:
            rows.append(dict(league="NHL", season_start_year=y, franchise_id=nfr[p["teamId"]], pick=p["overallPick"],
                             early=p["round"] in (1, 2), round=str(p["round"]), draft_source=NHL_DRAFT.format(y=y)))
    picks = pd.DataFrame(rows)
    rounds_per_year = picks.groupby(["league", "season_start_year"])["round"].nunique().rename("draft_rounds_in_year")
    g = picks.groupby(["league", "season_start_year", "franchise_id"])
    d = pd.DataFrame({"draft_picks_used": g.size(), "draft_picks_rd1_2": g["early"].sum(),
                      "draft_first_pick_number": g["pick"].min(), "draft_source": g["draft_source"].first()})
    d = d.reset_index().merge(rounds_per_year.reset_index(), on=["league", "season_start_year"])
    return d, picks


# ---------------- MLB managers ----------------
def mlb_manager_seasons():
    """One row per team-season 1990-2026: managers listed, end-of-season manager, in-season change."""
    mfr = mlb_franchise_map()
    rows = []
    for y in range(1990, 2027):
        for tid, fid in mfr.items():
            r = load("mlb_coaches", f"{tid}_{y}")
            if r is None:
                continue
            mgrs = []
            for x in r.get("roster", []):
                if x.get("jobId") in MANAGER_JOBS and x["person"]["fullName"] not in mgrs:
                    mgrs.append(x["person"]["fullName"])
            if not mgrs:
                continue  # team did not exist yet
            # The season roster is NOT in chronological order (verified: of 108 multi-manager seasons resolved by
            # the season-end date query, the end manager is listed last 60x, first 43x). Never resolve by order.
            fallback = 0
            if len(mgrs) == 1:
                end_mgr, end_src = mgrs[0], "single_manager"
            else:
                e = load("mlb_coaches_end", f"{tid}_{y}")
                em = [(x["person"]["fullName"], x["jobId"]) for x in (e or {}).get("roster", [])
                      if x.get("jobId") in MANAGER_JOBS]
                interims = [n for n, j in em if j == "NTRM"]
                if len({n for n, _ in em}) == 1:
                    end_mgr, end_src = em[0][0], "date_query_season_end"
                elif len(em) == 2 and len(interims) == 1:
                    # titled manager on leave + interim in the dugout on the last day -> interim (D27)
                    end_mgr, end_src, fallback = interims[0], "fallback_interim_at_season_end", 1
                else:
                    end_mgr, end_src, fallback = None, "unresolved", 1
            rows.append(dict(franchise_id=fid, season_start_year=y, managers=" | ".join(mgrs), n_managers=len(mgrs),
                             end_manager=end_mgr, end_manager_source=end_src, manager_resolved_by_fallback=fallback))
    m = pd.DataFrame(rows).sort_values(["franchise_id", "season_start_year"]).reset_index(drop=True)
    # Only changes up to the last regular-season game are visible (e.g. 2023 Giants: Kapler fired 9/29, interim
    # Kai Correa absent from the API) -> named for what it measures (D26)
    m["coach_changed_during_regular_season"] = (m.n_managers > 1).astype(int)
    # tenure in seasons as of end of season t; a first season taken over mid-season counts 0.5
    ten, cens = [], []
    for fid, grp in m.groupby("franchise_id", sort=False):
        prev, t, first_year = None, 0.0, grp.season_start_year.min()
        streak_start = None
        for _, r in grp.iterrows():
            if r.end_manager == prev:
                t += 1
            else:
                t = 0.5 if r.n_managers > 1 else 1.0
                streak_start = r.season_start_year
            prev = r.end_manager
            ten.append(t)
            cens.append(streak_start == first_year)
    m["coach_tenure_years"] = ten
    m["coach_tenure_left_censored"] = cens
    m["coach_name"] = m.end_manager
    return m


# ---------------- MLB attendance ----------------
def mlb_attendance():
    mfr = mlb_franchise_map()
    rows = []
    for y in range(1997, 2027):
        for r in load("mlb_attendance", str(y))["records"]:
            avg = r.get("attendanceAverageHome")
            rows.append(dict(league="MLB", season_start_year=y, franchise_id=mfr[r["team"]["id"]],
                             attendance_per_game=avg))
    a = pd.DataFrame(rows)
    a["attendance_restricted"] = a.season_start_year.isin([2020, 2021])
    a.loc[a.season_start_year == 2020, "attendance_per_game"] = np.nan  # no fans; 0 is not a real value (D25)
    a.loc[a.attendance_per_game == 0, "attendance_per_game"] = np.nan
    a["attendance_rank"] = a.groupby("season_start_year")["attendance_per_game"].rank(ascending=False, method="min")
    return a
