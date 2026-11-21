"""Expand map/data_src/team_location_stints.csv into one row per team-season -> map/data/team_locations.csv.

Seasons and leagues come from the data, not from code: every (league, season_start_year, franchise_id) in
dashboard/data/doom_predictions.csv must get exactly one location, and stints may also add team-seasons that
have no prediction (these become "too new to score"). A stint with blank first/last season is open-ended and
covers every prediction season of its league. The build fails if a predicted team-season has no location
or matches two stints.
"""
import os, sys, unicodedata
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)                                   # ADAM-DATA
PRED = os.path.join(ROOT, "dashboard", "data", "doom_predictions.csv")
STINTS = os.path.join(MAP, "data_src", "team_location_stints.csv")
OUT = os.path.join(MAP, "data", "team_locations.csv")

COLS = ["franchise_id", "league", "season", "city", "metro", "lat", "lon", "source_url",
        "season_team_name", "venue", "verified", "note"]


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "-".join(w for w in "".join(c if c.isalnum() else " " for c in s).split())


def main():
    P = pd.read_csv(PRED, usecols=["league", "season_start_year", "franchise_id"])
    S = pd.read_csv(STINTS, dtype={"first_season": "Int64", "last_season": "Int64"})
    seasons = P.groupby("league").season_start_year.agg(["min", "max"])   # league season range from data
    rows = []
    for st in S.itertuples(index=False):
        if st.league not in seasons.index:
            continue                                          # location rows for a league with no predictions yet
        lo = st.first_season if pd.notna(st.first_season) else seasons.loc[st.league, "min"]
        hi = st.last_season if pd.notna(st.last_season) else seasons.loc[st.league, "max"]
        lo, hi = max(lo, seasons.loc[st.league, "min"]), min(hi, seasons.loc[st.league, "max"])
        for y in range(int(lo), int(hi) + 1):
            rows.append({"franchise_id": st.franchise_id, "league": st.league, "season": y, "city": st.city,
                         "metro": st.metro, "lat": st.lat, "lon": st.lon, "source_url": st.source_url,
                         "season_team_name": st.season_team_name, "venue": st.venue, "verified": st.verified,
                         "note": st.note if isinstance(st.note, str) else ""})
    L = pd.DataFrame(rows, columns=COLS)
    L["metro_id"] = L.metro.map(slug)

    dup = L[L.duplicated(["league", "season", "franchise_id"], keep=False)]
    if len(dup):
        sys.exit(f"Overlapping stints:\n{dup[['league', 'season', 'franchise_id']].to_string()}")
    k = P.rename(columns={"season_start_year": "season"}).merge(L, how="left", on=["league", "season", "franchise_id"],
                                                                 indicator=True)
    missing = k[k._merge == "left_only"]
    if len(missing):
        sys.exit(f"Predicted team-seasons with no location:\n{missing[['league', 'season', 'franchise_id']].to_string()}")
    L = L.sort_values(["league", "season", "franchise_id"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    L.to_csv(OUT, index=False, lineterminator="\n")
    print(f"team_locations: {len(L)} team-seasons, {L.franchise_id.nunique()} franchises, "
          f"{L.metro_id.nunique()} metros -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
