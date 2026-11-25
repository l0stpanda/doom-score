"""Write FAKE NBA and NFL demo scores for trying out the Doom Map (M60). Run from ADAM-DATA/:

    .venv/Scripts/python map/make_demo_scores.py

Writes map/inputs/scores/DEMO_nba_scores.csv and DEMO_nfl_scores.csv (git-ignored; read only by a demo build,
`map/build_map.py --demo`, which map/demo.py runs). Every optional column is filled so every part of the page is
exercised. NOTHING here is a model output:
- real: win_pct, win_pct_percentile and record, from the teammate's NBA/NFL standings, seasons 2017-2024, via the
  committed snapshot map/inputs/demo_standings_nba_nfl.csv (its header names the source branch, file and commit; M63);
- fake: doom_pred = 50 + 0.55 * ((100 - standing) - 50) + noise (sd 9), clipped to 0-100; an 80% range of +-25;
  p_doom75 from that range and the matching band (D99: Low < 10%, Moderate 10-30%, High 30-50%, Very high >= 50%);
  a 3-season path proj_pct_t1..t3 that averages to 100 - doom_pred; invented driver text; and, where three later
  seasons exist in the file (2017-2021), actual_doom = doom_pred + noise (sd 15).
Fixed seed, so the files are the same on every run.
"""
import math, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))          # map/
ROOT = os.path.dirname(HERE)                                # ADAM-DATA
OUT = os.path.join(HERE, "inputs", "scores")
SRC = os.path.join(HERE, "inputs", "demo_standings_nba_nfl.csv")   # snapshot of the teammate's standings (M63)
SEED = 20261124
UP = ["Older roster", "Few recent draft picks", "Tight cap space", "Front-office turnover", "Injury-shortened season"]
DOWN = ["Young core", "Extra draft capital", "Cap room to add talent", "Stable front office", "Improving second half"]


def standings():
    return pd.read_csv(SRC, comment="#")


def band(p):
    return "Low" if p < 0.10 else "Moderate" if p < 0.30 else "High" if p < 0.50 else "Very high"


def drivers(rng, r, doom):
    """Plausible but invented 'what moves this prediction' text, signed like the model's ('+' = toward doom)."""
    up, down = [], []
    gap = doom - 50
    if r.win_pct_percentile < 50:
        up.append(f"Weak current standing (+{abs(gap) * rng.uniform(.5, .8):.1f})")
    else:
        down.append(f"Strong current standing (-{abs(gap) * rng.uniform(.5, .8):.1f})")
    if pd.notna(r.point_diff_per_game):
        (up if r.point_diff_per_game < 0 else down).append(
            f"{'Negative' if r.point_diff_per_game < 0 else 'Positive'} point differential "
            f"({'+' if r.point_diff_per_game < 0 else '-'}{rng.uniform(.5, 4):.1f})")
    for lst, pool, sign in [(up, UP, "+"), (down, DOWN, "-")]:
        for name in rng.choice(pool, size=3 - len(lst), replace=False):
            lst.append(f"{name} ({sign}{rng.uniform(.3, 3):.1f})")
    return up[:3], down[:3]


def main():
    rng = np.random.default_rng(SEED)
    S = standings().sort_values(["league", "season_start_year", "franchise_id"]).reset_index(drop=True)
    last = S.groupby("league").season_start_year.max()
    sd80 = 25 / 1.2816                                          # an 80% range of +-25 -> sd of a normal
    rows = []
    for r in S.itertuples(index=False):
        doom = round(float(np.clip(50 + 0.55 * ((100 - r.win_pct_percentile) - 50) + rng.normal(0, 9), 0, 100)), 1)
        m = 100 - doom                                          # mean league percentile over the next 3 seasons
        reach = min(m, 100 - m)
        d = float(np.clip((r.win_pct_percentile - m) * 0.5, -reach, reach))
        p75 = 0.5 * math.erfc((75 - doom) / (sd80 * math.sqrt(2)))
        up, down = drivers(rng, r, doom)
        actual = (float(np.clip(doom + rng.normal(0, 15), 0, 100))
                  if r.season_start_year + 3 <= last[r.league] else None)
        rows.append({
            "league": r.league, "season_start_year": int(r.season_start_year), "franchise_id": r.franchise_id,
            "doom_pred": round(doom, 1), "doom_lo80": round(max(0, doom - 25), 1), "doom_hi80": round(min(100, doom + 25), 1),
            "win_pct": round(float(r.win_pct), 4), "win_pct_percentile": round(float(r.win_pct_percentile), 2), "record": r.record,
            "band": band(p75), "p_doom75": round(p75, 3),
            **{f"driver_up_{i + 1}": up[i] for i in range(3)}, **{f"driver_down_{i + 1}": down[i] for i in range(3)},
            "driver_note": "DEMO: fake score and invented drivers for trying out the map; not a model output.",
            "proj_pct_t1": round(m + d, 3), "proj_pct_t2": round(m, 3), "proj_pct_t3": round(m - d, 3),
            "actual_doom": None if actual is None else round(actual, 1)})
    D = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    for lg, g in D.groupby("league"):
        path = os.path.join(OUT, f"DEMO_{lg.lower()}_scores.csv")
        g.to_csv(path, index=False, lineterminator="\n")
        print(f"{os.path.relpath(path, ROOT)}: {len(g)} rows, seasons {g.season_start_year.min()}-{g.season_start_year.max()}, "
              f"{g.franchise_id.nunique()} franchises, actuals for {g.actual_doom.notna().sum()} rows (FAKE scores)")


if __name__ == "__main__":
    main()
