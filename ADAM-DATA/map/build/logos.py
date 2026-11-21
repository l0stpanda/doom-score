"""Logo manifest with monogram fallbacks -> map/data/logo_manifest.csv (one row per team identity).

Logo source: only the logo_url column of dashboard/data/team_meta.csv. Files are cached (git-ignored) by the
existing dashboard/fetch_logos.py in dashboard/assets/logos/<league>_<franchise_id>.svg; this script does not
download anything. A team identity uses its logo when the cached file exists AND the season's team name still
contains the franchise's current nickname (so the Oakland Athletics and Florida Marlins use today's logo, but the
Arizona Coyotes, Utah Hockey Club and Cleveland Indians get a monogram instead of a later club's logo).
Monogram rule (used unless map/data_src/monogram_overrides.csv gives one): two-word city prefixes (New York,
Los Angeles, San Jose, St. Louis, Tampa Bay, ...) -> their initials + nickname initial; otherwise the first three
letters of the name. Overrides hold the leagues' official abbreviations where the rule differs.
"""
import os, re
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)
LOGOS = os.path.join(ROOT, "dashboard", "assets", "logos")
TWO_WORD_FIRST = {"New", "Los", "San", "St.", "Tampa", "Kansas", "Las", "Golden", "Oklahoma", "Green", "Salt"}


def rule_monogram(name):
    w = name.replace(".", ". ").split()
    w = [x for x in w if x]
    if w[0] == "St.":
        return ("ST" + w[1][0]).upper()
    if w[0] in TWO_WORD_FIRST and len(w) >= 3:
        return (w[0][0] + w[1][0] + w[2][0]).upper()
    return re.sub(r"[^A-Za-z]", "", w[0])[:3].upper()


def main():
    M = pd.read_csv(os.path.join(ROOT, "dashboard", "data", "team_meta.csv"))
    L = pd.read_csv(os.path.join(MAP, "data", "team_locations.csv"))
    ov_path = os.path.join(MAP, "data_src", "monogram_overrides.csv")
    ov = pd.read_csv(ov_path, encoding="utf-8") if os.path.exists(ov_path) else pd.DataFrame(columns=["league", "name", "monogram", "note"])
    ov = {(r.league, r["name"]): r.monogram for _, r in ov.iterrows()}

    ids = (L.groupby(["league", "franchise_id", "season_team_name"]).season.agg(first_season="min", last_season="max")
             .reset_index()
             .merge(M[["league", "franchise_id", "team", "logo_url"]], on=["league", "franchise_id"], how="left"))
    rows = []
    for r in ids.itertuples(index=False):
        local = os.path.join(LOGOS, f"{r.league}_{r.franchise_id}.svg")
        cached = os.path.exists(local) and os.path.getsize(local) > 0
        nickname = str(r.team).split()[-1] if isinstance(r.team, str) else ""
        same_club = bool(nickname) and nickname in r.season_team_name.split()
        mono = ov.get((r.league, r.season_team_name)) or rule_monogram(r.season_team_name)
        rows.append({"league": r.league, "franchise_id": r.franchise_id, "season_team_name": r.season_team_name,
                     "first_season": r.first_season, "last_season": r.last_season,
                     "logo_url": r.logo_url if isinstance(r.logo_url, str) else "",
                     "local_file": os.path.relpath(local, ROOT).replace("\\", "/") if cached else "",
                     "use_logo": cached and same_club, "monogram": mono,
                     "why_monogram": "" if cached and same_club else ("no cached logo" if not cached else
                                                                       "season name differs from current club")})
    out = pd.DataFrame(rows).sort_values(["league", "franchise_id", "first_season"])
    dup = out[out.duplicated(["league", "monogram"], keep=False)
              & ~out.duplicated(["league", "franchise_id", "monogram"], keep=False)]
    out.to_csv(os.path.join(MAP, "data", "logo_manifest.csv"), index=False, lineterminator="\n")
    print(f"logo manifest: {len(out)} identities, {int(out.use_logo.sum())} with logo, "
          f"{int((~out.use_logo).sum())} monogram")
    if len(dup):
        print("WARNING monogram collisions within a league:\n", dup[["league", "season_team_name", "monogram"]].to_string(index=False))
    print(out[["league", "season_team_name", "monogram", "use_logo"]].to_string(index=False))


if __name__ == "__main__":
    main()
