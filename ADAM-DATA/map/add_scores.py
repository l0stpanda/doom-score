"""Add (or replace) one league's doom scores and rebuild the Doom Map (docs/SCORES_FORMAT.md, M50-M54). From ADAM-DATA/:

    .venv/Scripts/python map/add_scores.py path/to/nba_scores.csv                 # validate, resolve, copy, rebuild
    .venv/Scripts/python map/add_scores.py path/to/nba_scores.csv --freeze-params # keep sigma and the colour range
    .venv/Scripts/python map/add_scores.py path/to/nba_scores.csv --check         # validate and resolve only

Steps:
 1. Validate columns, types and ranges (map/build/scores.py). Any problem stops here with line numbers.
 2. Resolve every franchise_id through the team registry and aliases: an id, a season's team name, a current or
    former name, a nickname, or an abbreviation ("OAK", "Sonics", "Oakland Raiders", "philadelphia-sixers").
    Names are matched within the league and, where a name moved between franchises (e.g. "Hornets"), the season.
    Unmatched names are listed and nothing is copied.
 3. Report season coverage against the registry (teams per season, and teams with no score = "too new to score").
 4. Copy the file, with canonical franchise_ids, to map/inputs/scores/<same file name>. A file of that name is
    replaced only with --replace; a team-season already scored in another file stops the run.
 5. Rebuild (map/build_map.py --no-renders; add --renders for the check images), re-deriving sigma, the opacity
    cutoffs and the colour-scale ends unless --freeze-params keeps today's values (map/data_src/frozen_params.json).
    Old and new values are printed.
Removing a league: delete its file from map/inputs/scores/ and run map/build_map.py.
"""
import json, os, shutil, subprocess, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))          # map/
ROOT = os.path.dirname(HERE)                                # ADAM-DATA
sys.path.insert(0, os.path.join(HERE, "build"))
from scores import SCORES_DIR, ScoresError, load_scores, read_file, validate   # noqa: E402
from team_locations import alias_key                                          # noqa: E402

DATA = os.path.join(HERE, "data")
FROZEN = os.path.join(HERE, "data_src", "frozen_params.json")
PARAMS = ["sigma_mi", "opacity_w0", "opacity_w1", "z_lo", "z_hi"]
INFO = ["verdict_lo", "verdict_hi", "eb_tau2", "eb_s2_within", "default_season"]


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def resolver():
    """(league, season, key) -> franchise_id, using the registry for that season first, then the aliases table."""
    reg = pd.read_csv(os.path.join(DATA, "team_registry.csv"))
    ali = pd.read_csv(os.path.join(DATA, "team_aliases.csv"), keep_default_na=False)
    by_season = {}
    for r in reg.itertuples(index=False):
        nick = r.season_team_name.split()[-1]
        names = {r.franchise_id, r.season_team_name, r.team, nick, f"{r.city.rsplit(' ', 1)[0]} {nick}"}
        for n in names:
            by_season.setdefault((r.league, int(r.season), alias_key(n)), set()).add(r.franchise_id)
    by_alias = {(r.league, r.alias_key): r.franchise_id for r in ali.itertuples(index=False)}
    in_reg = set(zip(reg.league, reg.season.astype(int), reg.franchise_id))

    def resolve(league, season, raw):
        k = alias_key(raw)
        hit = by_season.get((league, season, k))
        if hit and len(hit) == 1:
            return next(iter(hit)), "season"
        fid = by_alias.get((league, k))
        return (fid, "alias") if fid else (None, None)
    return reg, in_reg, resolve


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    known = {"--freeze-params", "--check", "--replace", "--renders"}
    if len(args) != 1 or flags - known:
        sys.exit(__doc__ + f"\nusage: python map/add_scores.py <file> [{' '.join(sorted(known))}]")
    src = args[0]
    name = os.path.basename(src)
    if not name.lower().endswith(".csv"):
        sys.exit("the scores file must be a .csv")

    # 1. validate
    try:
        df, warns = validate(read_file(src), name)
    except ScoresError as e:
        sys.exit(f"Scores problem: {e}")
    for w in warns:
        print("WARNING", w)
    print(f"{name}: {len(df)} rows, leagues {', '.join(sorted(df.league.unique()))}; "
          f"optional columns: {', '.join(c for c in df.columns if c not in ('league', 'season_start_year', 'franchise_id', 'doom_pred')) or 'none'}")

    # 2. resolve teams
    reg, in_reg, resolve = resolver()
    no_league = sorted(set(df.league) - set(reg.league))
    if no_league:
        sys.exit(f"no team registry for league(s) {no_league}: add stints, team_logos.csv rows and a leagues.csv row "
                 f"first (docs/ADD_A_LEAGUE.md)")
    out, unmatched, notthere = [], {}, []
    for r in df.itertuples(index=False):
        fid, how = resolve(r.league, int(r.season_start_year), r.franchise_id)
        if fid is None:
            unmatched.setdefault((r.league, r.franchise_id), []).append(int(r.season_start_year))
        elif (r.league, int(r.season_start_year), fid) not in in_reg:
            notthere.append((r.league, int(r.season_start_year), r.franchise_id, fid))
        out.append(fid)
    if unmatched:
        print(f"\nUNMATCHED team names ({len(unmatched)}); nothing was copied. Add them to map/data_src/team_aliases.csv "
              f"(league, alias, franchise_id, kind, note) or fix the file:")
        for (lg, raw), yrs in sorted(unmatched.items()):
            print(f"  {lg}  {raw!r:40}  seasons {min(yrs)}-{max(yrs)} ({len(yrs)} rows)")
        sys.exit(1)
    if notthere:
        print("\nTeams scored in a season the registry has no location for (e.g. before an expansion team existed):")
        for lg, y, raw, fid in notthere[:30]:
            print(f"  {lg} {y} {raw!r} -> {fid}")
        sys.exit(1)
    renamed = sorted({(r.league, r.franchise_id, f) for r, f in zip(df.itertuples(index=False), out) if r.franchise_id != f})
    df["franchise_id"] = out
    if df.duplicated(["league", "season_start_year", "franchise_id"]).any():
        d = df[df.duplicated(["league", "season_start_year", "franchise_id"], keep=False)]
        sys.exit("two rows resolve to the same team-season:\n" + d[["league", "season_start_year", "franchise_id"]].to_string(index=False))
    if renamed:
        print(f"resolved {len(renamed)} name(s) to franchise ids:")
        for lg, a, b in renamed:
            print(f"  {lg}  {a!r} -> {b}")

    # 3. coverage
    for lg, g in df.groupby("league"):
        R = reg[(reg.league == lg) & reg.season.between(g.season_start_year.min(), g.season_start_year.max())]
        per = g.groupby("season_start_year").size()
        exp = R.groupby("season").size()
        print(f"\n{lg} coverage: seasons {g.season_start_year.min()}-{g.season_start_year.max()} "
              f"({g.season_start_year.nunique()} seasons, {len(g)} team-seasons; registry {reg[reg.league == lg].season.min()}"
              f"-{reg[reg.league == lg].season.max()})")
        gaps = sorted(set(range(g.season_start_year.min(), g.season_start_year.max() + 1)) - set(per.index))
        if gaps:
            print(f"  seasons with no scores inside the range (their teams show as too new to score): {gaps}")
        short = [(y, int(per.get(y, 0)), int(n)) for y, n in exp.items() if per.get(y, 0) < n]
        for y, a, b in short[:10]:
            have = set(g[g.season_start_year == y].franchise_id)
            miss = sorted(set(R[R.season == y].franchise_id) - have)
            print(f"  {y}: {a} of {b} registry teams scored; not scored (too new to score): {', '.join(miss)}")
        if not short:
            print("  every registry team is scored in every season of the range")
    if "--check" in flags:
        print("\n--check: valid; nothing copied or rebuilt.")
        return

    # 4. copy
    dest = os.path.join(SCORES_DIR, name)
    if os.path.exists(dest) and "--replace" not in flags:
        sys.exit(f"{os.path.relpath(dest, ROOT)} exists; pass --replace to overwrite it")
    try:
        others, _, _ = load_scores(quiet=True)
        others = others[others._file != name]
    except ScoresError:
        others = pd.DataFrame(columns=["league", "season_start_year", "franchise_id", "_file"])
    clash = df.merge(others, on=["league", "season_start_year", "franchise_id"])
    if len(clash):
        sys.exit("these team-seasons are already scored in another file:\n"
                 + clash[["_file", "league", "season_start_year", "franchise_id"]].head(20).to_string(index=False))
    os.makedirs(SCORES_DIR, exist_ok=True)
    df.to_csv(dest, index=False, lineterminator="\n")
    print(f"\ncopied to {os.path.relpath(dest, ROOT)}")

    # 5. parameters + rebuild
    dpath = os.path.join(DATA, "derived.json")
    old = json.load(open(dpath)) if os.path.exists(dpath) else {}
    if "--freeze-params" in flags:
        if not os.path.exists(FROZEN):
            json.dump({k: old[k] for k in PARAMS}, open(FROZEN, "w"), indent=1)
            print(f"froze {', '.join(PARAMS)} at today's values in {os.path.relpath(FROZEN, ROOT)}")
        else:
            print(f"parameters already frozen by {os.path.relpath(FROZEN, ROOT)}")
    elif os.path.exists(FROZEN):
        os.remove(FROZEN)
        print(f"removed {os.path.relpath(FROZEN, ROOT)}: parameters will be re-derived")
    leagues = sorted(df.league.unique())
    run([sys.executable, "map/build/fetch_logos.py", *leagues])
    run([sys.executable, "map/build_map.py"] + ([] if "--renders" in flags else ["--no-renders"]))
    new = json.load(open(dpath))
    print("\nparameter            old        new" + ("   (frozen)" if new.get("params_frozen") else "   (re-derived)"))
    for k in PARAMS + INFO:
        print(f"  {k:16} {str(old.get(k, '-')):>10} {str(new.get(k)):>10}")
    if new.get("params_frozen"):
        print(f"  (re-derived values would be: {new.get('params_computed')})")


if __name__ == "__main__":
    main()
