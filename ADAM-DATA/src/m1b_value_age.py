"""Value-weighted hitter/pitcher age from MLB Stats API player stints (replaces the Baseball-Reference WAR version).
Decision D90.

Value per player-team stint, season t:
  hitters  : batting runs above average (linear weights). pos = .47*1B + .78*2B + 1.09*3B + 1.40*HR
             + .33*(BB - IBB + HBP); outs = AB - H; out value x = sum(pos)/sum(outs) over the league-season, so the
             league total is 0; BRAA = pos - x*outs.
  pitchers : FIP-based runs above average = (L*IP - (13*HR + 3*(BB + HBP) - 2*K)) / 9, where
             L = league-season (13*HR + 3*(BB + HBP) - 2*K)/IP (the FIP constant cancels).
Weight = max(value, 0); age on June 30 of t (D45). Stints: /stats?teamId=T per team (fetch_phase3 URLs and cache
names), plus the D46 repair for players the teamId query omits (yearByYear per-team splits).

fetch(): python src/m1b_value_age.py fetch     build(): imported by src/m1b_features.py"""
import glob, json, os, sys, time
from datetime import date
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_phase3 as f3

RAW = f3.RAW
SEASONS = list(range(2000, 2027))
HIT = ("hits", "doubles", "triples", "homeRuns", "baseOnBalls", "intentionalWalks", "hitByPitch", "atBats",
       "plateAppearances")
PIT = ("homeRuns", "baseOnBalls", "hitByPitch", "strikeOuts", "outs", "battersFaced")


def team_ids():
    return [t["id"] for t in json.load(open(os.path.join(RAW, "mlb_statsapi", "teams_2026.json")))["teams"]]


def get(source, name, url):
    cached = os.path.exists(os.path.join(RAW, source, name + ".json"))
    out = f3.get(source, name, url)
    if not cached:
        time.sleep(0.2)
    return out


def fetch():
    tids = team_ids()
    for y in SEASONS:
        for t in tids:
            for g in ("hitting", "pitching"):
                get("mlb_player_stats", f"{y}_{t}_{g}", f3.MLB_STATS.format(g=g, y=y, t=t))
        print(f"stints {y}", flush=True)
    ids = set()
    for fn in glob.glob(os.path.join(RAW, "mlb_player_stats", "*.json")):
        for s in json.load(open(fn, encoding="utf-8"))["stats"][0]["splits"]:
            ids.add(s["player"]["id"])
    ids = sorted(ids)
    for i in range(0, len(ids), 100):
        get("mlb_people", f"batch_{i // 100:04d}", f3.MLB_PEOPLE.format(ids=",".join(map(str, ids[i:i + 100]))))
    print(f"people: {len(ids)}", flush=True)
    f3.mlb_repair()                                   # D46: rosters + yearByYear for omitted (traded-away) players


def age_on(birth, on):
    if not isinstance(birth, str) or len(birth) < 10:
        return np.nan
    return (on - date.fromisoformat(birth[:10])).days / 365.25


def stints():
    births, rows = {}, []
    for f in glob.glob(os.path.join(RAW, "mlb_people", "*.json")):
        for p in json.load(open(f, encoding="utf-8"))["people"]:
            births[p["id"]] = p.get("birthDate")
    keys = {"hitting": HIT, "pitching": PIT}
    for f in glob.glob(os.path.join(RAW, "mlb_player_stats", "*.json")):
        y, t, g = os.path.basename(f)[:-5].split("_")
        for s in json.load(open(f, encoding="utf-8"))["stats"][0]["splits"]:
            if s.get("team", {}).get("id") not in (None, int(t)):
                continue
            rows.append(dict(season_start_year=int(y), team_id=int(t), player_id=s["player"]["id"], group=g,
                             **{k: float(s["stat"].get(k, 0) or 0) for k in keys[g]}))
    bad_path = os.path.join(RAW, "mlb_yby", "_bad_team_seasons.json")
    bad = {tuple(x) for x in json.load(open(bad_path))} if os.path.exists(bad_path) else set()
    have = {(r["season_start_year"], r["team_id"], r["player_id"], r["group"]) for r in rows}
    for f in glob.glob(os.path.join(RAW, "mlb_yby", "batch_*.json")):
        for p in json.load(open(f, encoding="utf-8"))["people"]:
            births[p["id"]] = p.get("birthDate")
            for grp in p.get("stats", []):
                g = grp["group"]["displayName"]
                if g not in keys:
                    continue
                for s in grp["splits"]:
                    t, y = s.get("team", {}).get("id"), int(s["season"])
                    if (t is None or (y, t) not in bad or (y, t, p["id"], g) in have
                            or s.get("sport", {}).get("id", 1) != 1):
                        continue
                    rows.append(dict(season_start_year=y, team_id=t, player_id=p["id"], group=g,
                                     **{k: float(s["stat"].get(k, 0) or 0) for k in keys[g]}))
                    have.add((y, t, p["id"], g))
    st = pd.DataFrame(rows)
    st["age"] = [age_on(births.get(i), date(y, 6, 30)) for i, y in zip(st.player_id, st.season_start_year)]
    return st


def build():
    """Returns (team-season value ages, checks)."""
    st = stints()
    h = st[st.group == "hitting"].copy()
    h["b1"] = h.hits - h.doubles - h.triples - h.homeRuns
    h["pos"] = (.47 * h.b1 + .78 * h.doubles + 1.09 * h.triples + 1.40 * h.homeRuns
                + .33 * (h.baseOnBalls - h.intentionalWalks + h.hitByPitch))
    h["outs_b"] = h.atBats - h.hits
    x = h.groupby("season_start_year").apply(lambda d: d.pos.sum() / d.outs_b.sum(), include_groups=False)
    h["value"] = h.pos - h.season_start_year.map(x) * h.outs_b
    p = st[st.group == "pitching"].copy()
    p["ip"] = p.outs / 3
    p["fip_num"] = 13 * p.homeRuns + 3 * (p.baseOnBalls + p.hitByPitch) - 2 * p.strikeOuts
    L = p.groupby("season_start_year").apply(lambda d: d.fip_num.sum() / d.ip.sum(), include_groups=False)
    p["value"] = (p.season_start_year.map(L) * p.ip - p.fip_num) / 9
    out = []
    for d, who in ((h, "hitters"), (p, "pitchers")):
        d = d[d.age.notna()].copy()
        d["w"] = d.value.clip(lower=0)
        g = d.groupby(["season_start_year", "team_id"])
        r = g.apply(lambda z: np.average(z.age, weights=z.w) if z.w.sum() > 0 else np.nan, include_groups=False)
        out.append(r.rename(f"value_age_{who}").reset_index().merge(
            g.w.sum().rename(f"pos_value_{who}").reset_index(), on=["season_start_year", "team_id"]))
    res = out[0].merge(out[1], on=["season_start_year", "team_id"], how="outer")
    # checks: player sums vs official team totals (after the D46 repair), league BRAA sums to 0, birthdate coverage
    tot = []
    for y in SEASONS:
        for g, key, col in (("hitting", "plateAppearances", "plateAppearances"), ("pitching", "battersFaced", "battersFaced")):
            js = json.load(open(os.path.join(RAW, "mlb_team_totals", f"{y}_{g}.json")))
            for s in js["stats"][0]["splits"]:
                tot.append((y, s["team"]["id"], g, float(s["stat"][key])))
    tot = pd.DataFrame(tot, columns=["season_start_year", "team_id", "group", "official"])
    sums = pd.concat([h.groupby(["season_start_year", "team_id"]).plateAppearances.sum().rename("players")
                      .reset_index().assign(group="hitting"),
                      p.groupby(["season_start_year", "team_id"]).battersFaced.sum().rename("players")
                      .reset_index().assign(group="pitching")])
    m = tot.merge(sums, on=["season_start_year", "team_id", "group"], how="left")
    checks = [("player PA/BF sum = official team total (share of team-season-groups)",
               float((m.players == m.official).mean())),
              ("league BRAA sum, max abs over seasons", float(h.groupby("season_start_year").value.sum().abs().max())),
              ("stints with birthdate (share)", float(st.age.notna().mean())),
              ("hitter stints", float(len(h))), ("pitcher stints", float(len(p)))]
    return res, checks


if __name__ == "__main__":
    if "fetch" in sys.argv:
        fetch()
    r, c = build()
    print(r.describe().round(2).to_string())
    print(c)
