"""Team registry, aliases and the located team-seasons the map shows (M03-M05, M50, M52, M53).

Inputs : map/data_src/team_location_stints.csv  one row per stint (venue + name over a span of seasons), all leagues
         map/data_src/leagues.csv               registry season range per league (a blank stint season = that end)
         map/data_src/team_logos.csv            current franchise name + official logo URL
         map/data_src/monogram_overrides.csv    official abbreviations where the monogram rule differs
         map/data_src/team_aliases.csv          hand-made aliases: abbreviations, common and former names
         map/inputs/scores/*.csv                (only for which leagues/seasons to show; read via scores.py)
Outputs: map/data/team_registry.csv  one row per league x season x franchise over the registry range, scores or not
                                     (region_id is filled in by team_regions.mjs)
         map/data/team_aliases.csv   every name that resolves to a franchise_id (hand-made + derived from the registry)
         map/data/team_locations.csv the registry rows for leagues that have scores, over the seasons they score
The build stops if stints overlap, a franchise has no logo row, or a scored team-season has no location.
"""
import os, sys, unicodedata
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)                                   # ADAM-DATA
SRC, DATA = os.path.join(MAP, "data_src"), os.path.join(MAP, "data")
sys.path.insert(0, HERE)
from logos import rule_monogram                               # noqa: E402
from scores import ScoresError, load_scores                    # noqa: E402

COLS = ["franchise_id", "league", "season", "city", "metro", "lat", "lon", "source_url",
        "season_team_name", "venue", "verified", "secondary_source_url", "note"]
REG_COLS = ["league", "season", "franchise_id", "season_team_name", "team", "city", "metro", "metro_id", "venue",
            "lat", "lon", "region_id", "logo_url", "monogram", "verified", "source_url", "secondary_source_url", "note"]


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "-".join(w for w in "".join(c if c.isalnum() else " " for c in s).split())


def alias_key(s):
    """How names are compared: accents, case, punctuation and spacing ignored ('St. Louis' == 'st louis')."""
    return slug(str(s)).replace("-", " ")


def build_registry():
    Lg = pd.read_csv(os.path.join(SRC, "leagues.csv")).set_index("league")
    S = pd.read_csv(os.path.join(SRC, "team_location_stints.csv"), dtype={"first_season": "Int64", "last_season": "Int64"})
    logos = pd.read_csv(os.path.join(SRC, "team_logos.csv"))
    ov_path = os.path.join(SRC, "monogram_overrides.csv")
    ov = pd.read_csv(ov_path, encoding="utf-8")
    ov = {(r.league, r["name"]): r.monogram for _, r in ov.iterrows()}
    unknown = sorted(set(S.league) - set(Lg.index))
    if unknown:
        sys.exit(f"stints for league(s) not in map/data_src/leagues.csv: {unknown}")
    rows = []
    for st in S.itertuples(index=False):
        lo_r, hi_r = int(Lg.loc[st.league, "registry_first"]), int(Lg.loc[st.league, "registry_last"])
        lo = int(st.first_season) if pd.notna(st.first_season) else lo_r
        hi = int(st.last_season) if pd.notna(st.last_season) else hi_r
        for y in range(max(lo, lo_r), min(hi, hi_r) + 1):
            rows.append({"franchise_id": st.franchise_id, "league": st.league, "season": y, "city": st.city,
                         "metro": st.metro, "lat": st.lat, "lon": st.lon, "source_url": st.source_url,
                         "season_team_name": st.season_team_name, "venue": st.venue, "verified": st.verified,
                         "secondary_source_url": st.secondary_source_url if isinstance(st.secondary_source_url, str) else "",
                         "note": st.note if isinstance(st.note, str) else ""})
    R = pd.DataFrame(rows, columns=COLS)
    R["metro_id"] = R.metro.map(slug)
    dup = R[R.duplicated(["league", "season", "franchise_id"], keep=False)]
    if len(dup):
        sys.exit(f"Overlapping stints:\n{dup[['league', 'season', 'franchise_id']].to_string()}")
    R = R.merge(logos[["league", "franchise_id", "team", "logo_url"]], on=["league", "franchise_id"], how="left")
    nologo = R[R.team.isna()][["league", "franchise_id"]].drop_duplicates()
    if len(nologo):
        sys.exit(f"franchises with no row in map/data_src/team_logos.csv:\n{nologo.to_string(index=False)}")
    R["monogram"] = [ov.get((lg, n)) or rule_monogram(n) for lg, n in zip(R.league, R.season_team_name)]
    R["region_id"] = ""
    return R.sort_values(["league", "season", "franchise_id"]).reset_index(drop=True), Lg


def build_aliases(R):
    """Hand-made aliases win; derived ones (ids, current/season names, unique nicknames and city+nickname) fill in.
    A derived alias that would point to two franchises in one league is dropped and listed."""
    man = pd.read_csv(os.path.join(SRC, "team_aliases.csv"), keep_default_na=False)
    known = set(zip(R.league, R.franchise_id))
    bad = man[[(l, f) not in known for l, f in zip(man.league, man.franchise_id)]]
    if len(bad):
        sys.exit(f"map/data_src/team_aliases.csv points to unknown franchises:\n{bad.to_string(index=False)}")
    der = []
    ids = R.drop_duplicates(["league", "franchise_id"])
    for r in ids.itertuples(index=False):
        der += [(r.league, r.franchise_id, r.franchise_id, "franchise_id"), (r.league, r.team, r.franchise_id, "current_name"),
                (r.league, r.team.split()[-1], r.franchise_id, "nickname")]
    for r in R.drop_duplicates(["league", "franchise_id", "season_team_name"]).itertuples(index=False):
        der.append((r.league, r.season_team_name, r.franchise_id, "season_name"))
        der.append((r.league, r.season_team_name.split()[-1], r.franchise_id, "nickname"))
        city = r.city.rsplit(" ", 1)[0]
        der.append((r.league, f"{city} {r.season_team_name.split()[-1]}", r.franchise_id, "city_nickname"))
    D = pd.DataFrame(der, columns=["league", "alias", "franchise_id", "kind"])
    M = man[["league", "alias", "franchise_id", "kind"]].copy()
    A = pd.concat([M.assign(src=0), D.assign(src=1)])
    A["alias_key"] = A.alias.map(alias_key)
    A = A.drop_duplicates(["league", "alias_key", "franchise_id"])
    manual_keys = set(zip(M.league, M.alias.map(alias_key)))
    clash = A.groupby(["league", "alias_key"]).franchise_id.transform("nunique") > 1
    hand = [(l, k) in manual_keys for l, k in zip(A.league, A.alias_key)]
    dropped = A[clash & ~pd.Series(hand, index=A.index)]
    A = A[~clash | (pd.Series(hand, index=A.index) & (A.src == 0))]
    if A.duplicated(["league", "alias_key"]).any():
        sys.exit("map/data_src/team_aliases.csv gives one alias two franchises:\n"
                 + A[A.duplicated(["league", "alias_key"], keep=False)].to_string(index=False))
    A = A.sort_values(["league", "franchise_id", "kind", "alias"])[["league", "alias", "alias_key", "franchise_id", "kind"]]
    return A, dropped.drop_duplicates(["league", "alias_key"])[["league", "alias"]]


def main():
    R, Lg = build_registry()
    A, dropped = build_aliases(R)
    os.makedirs(DATA, exist_ok=True)
    R[REG_COLS].to_csv(os.path.join(DATA, "team_registry.csv"), index=False, lineterminator="\n")
    A.to_csv(os.path.join(DATA, "team_aliases.csv"), index=False, lineterminator="\n")
    cov = R.groupby("league").agg(first=("season", "min"), last=("season", "max"), franchises=("franchise_id", "nunique"),
                                  team_seasons=("season", "size"))
    print("team_registry:\n" + cov.to_string())
    print(f"team_aliases: {len(A)} aliases" + (f"; ambiguous, left out: {', '.join(f'{l}:{a}' for l, a in dropped.itertuples(index=False))}"
                                                if len(dropped) else ""))

    try:
        P, _, _ = load_scores(quiet=True)
    except ScoresError as e:
        sys.exit(f"Scores problem: {e}")
    P = P[["league", "season_start_year", "franchise_id"]].rename(columns={"season_start_year": "season"})
    no_reg = sorted(set(P.league) - set(R.league))
    if no_reg:
        sys.exit(f"scores for league(s) with no team registry: {no_reg} (add stints, a team_logos.csv row per franchise "
                 f"and a leagues.csv row; docs/ADD_A_LEAGUE.md)")
    out = []
    for lg, g in P.groupby("league"):
        lo, hi = int(g.season.min()), int(g.season.max())
        r_lo, r_hi = int(Lg.loc[lg, "registry_first"]), int(Lg.loc[lg, "registry_last"])
        if lo < r_lo or hi > r_hi:
            sys.exit(f"{lg} scores cover {lo}-{hi}, but the {lg} team registry covers {r_lo}-{r_hi} "
                     f"(extend it in map/data_src/leagues.csv and the stints)")
        out.append(R[(R.league == lg) & R.season.between(lo, hi)])
    L = pd.concat(out)
    k = P.merge(L, how="left", on=["league", "season", "franchise_id"], indicator=True)
    missing = k[k._merge == "left_only"]
    if len(missing):
        sys.exit(f"Scored team-seasons with no location in the registry:\n{missing[['league', 'season', 'franchise_id']].to_string()}")
    L = L[COLS + ["metro_id"]].sort_values(["league", "season", "franchise_id"]).reset_index(drop=True)
    L.to_csv(os.path.join(DATA, "team_locations.csv"), index=False, lineterminator="\n")
    print(f"team_locations: {len(L)} team-seasons, {L.franchise_id.nunique()} franchises, "
          f"{L.metro_id.nunique()} metros -> map/data/team_locations.csv")


if __name__ == "__main__":
    main()
