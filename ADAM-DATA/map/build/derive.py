"""Derive every number the map uses from the data (Phase 1, sections 5-8 of the pivot spec).

Inputs : dashboard/data/doom_predictions.csv, map/data/team_locations.csv, map/data/team_regions.csv,
         map/data/land_grid.csv (25 km equal-area land grid inside the map crop), map/data_src/regions.csv
Outputs: map/data/team_seasons.csv   one row per located team-season: location, region, raw doom, z-scores
         map/data/derived.json       sigma, opacity cutoffs, colour-scale ends, season list (read by the map)
         reports/map_derived/*.csv   standardisation stats, sigma diagnostics, region counts by season and league
Nothing here hard-codes a league: leagues, seasons and teams all come from the input files.
"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)
DATA = os.path.join(MAP, "data")
REP = os.path.join(ROOT, "reports", "map_derived")

SIGMAS = list(range(50, 401, 25))        # miles, tested grid (spec: 50-400 in 25-mile steps)
FAR_MI = 300                             # "empty interior" = land farther than this from every team
VISIBLE_W = 0.1                          # weight at which colour is perceptible (10% of one team's full weight)
PAIRS = [("Baltimore", "Washington DC", "close"), ("Los Angeles", "Anaheim", "close"),
         ("Los Angeles", "San Diego", "medium"), ("Anaheim", "San Diego", "medium"),
         ("Toronto", "Buffalo", "close"), ("Seattle", "Vancouver", "medium"),
         ("Dallas–Fort Worth", "Houston", "far")]
EARTH_MI = 3958.8


def gc_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance matrix (len(lat1) x len(lat2)) in miles."""
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dl = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_MI * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def zscore(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd > 0 else s * 0.0


def build_team_seasons():
    P = pd.read_csv(os.path.join(ROOT, "dashboard", "data", "doom_predictions.csv"))
    L = pd.read_csv(os.path.join(DATA, "team_locations.csv"))
    TR = pd.read_csv(os.path.join(DATA, "team_regions.csv"))
    P = P.rename(columns={"season_start_year": "season"})
    # z within league-season (population SD), for predicted doom and, where labels exist, actual doom
    P["z_pred"] = P.groupby(["league", "season"]).doom_pred.transform(zscore)
    lab = P.actual_doom.notna()
    P.loc[lab, "z_actual"] = P[lab].groupby(["league", "season"]).actual_doom.transform(zscore)
    keep = ["league", "season", "franchise_id", "team", "pred_type", "doom_pred", "doom_lo80", "doom_hi80",
            "doom_band", "p_doom75", "z_pred", "actual_doom", "z_actual", "win_pct", "win_pct_percentile",
            "wins", "losses", "ot_losses", "games"]
    T = (L.merge(TR[["league", "season", "franchise_id", "region_id"]], on=["league", "season", "franchise_id"])
          .merge(P[keep], on=["league", "season", "franchise_id"], how="left"))
    T["scored"] = T.doom_pred.notna()                  # "too new to score" = located but no prediction row
    T["proj_standing"] = 100 - T.doom_pred             # y of the dashboard scatter
    x, y = T.win_pct_percentile >= 50, T.proj_standing >= 50
    T["quadrant"] = np.select([x & y, x & ~y, ~x & y, ~x & ~y], ["Contender", "Cliff ahead", "Rising", "Stuck"], "")
    T.loc[~T.scored, "quadrant"] = ""
    T["place"] = np.where(T.metro == "Los Angeles", T.city.str.replace(r" CA$", "", regex=True), T.metro)
    return P, T


def standardisation_stats(P):
    rows = []
    for lg, g in P.groupby("league"):
        for col, lab in [("doom_pred", "raw doom_pred"), ("z_pred", "z (within league-season)")]:
            rows.append({"league": lg, "values": lab, "n": len(g), "mean": g[col].mean(), "sd": g[col].std(ddof=0),
                         "mean_within_season_sd": g.groupby("season")[col].std(ddof=0).mean(),
                         "min": g[col].min(), "max": g[col].max()})
    return pd.DataFrame(rows)


def sigma_diagnostics(T, grid):
    S = T[T.scored]
    glat, glon = grid.lat.to_numpy(), grid.lon.to_numpy()
    rows, per = [], {s: {"own": [], "far_w": [], "metro_w": [], "pairs": {p[:2]: [] for p in PAIRS}} for s in SIGMAS}
    far_counts = []
    for season, g in S.groupby("season"):
        tl, to = g.lat.to_numpy(), g.lon.to_numpy()
        dg = gc_miles(glat, glon, tl, to)                                   # grid x teams
        far = dg.min(axis=1) > FAR_MI
        far_counts.append(far.mean())
        metros = g.groupby("metro").agg(lat=("lat", "mean"), lon=("lon", "mean"))
        dm = gc_miles(metros.lat.to_numpy(), metros.lon.to_numpy(), tl, to)  # metro centres x teams
        own_mask = (g.metro.to_numpy()[None, :] == metros.index.to_numpy()[:, None])
        places = g.groupby("place").agg(lat=("lat", "mean"), lon=("lon", "mean"))
        dp = gc_miles(places.lat.to_numpy(), places.lon.to_numpy(), tl, to)
        pidx = {p: i for i, p in enumerate(places.index)}
        for s in SIGMAS:
            wm = np.exp(-dm ** 2 / (2 * s * s))
            per[s]["own"] += list((wm * own_mask).sum(1) / wm.sum(1))
            per[s]["metro_w"] += list(wm.sum(1))
            per[s]["far_w"] += list(np.exp(-dg[far] ** 2 / (2 * s * s)).sum(1))
            wp = np.exp(-dp ** 2 / (2 * s * s))
            for a, b, _ in PAIRS:
                if a in pidx and b in pidx:
                    ia, ib = pidx[a], pidx[b]
                    from_b = wp[ia, (g.place == b).to_numpy()].sum() / wp[ia].sum()
                    from_a = wp[ib, (g.place == a).to_numpy()].sum() / wp[ib].sum()
                    per[s]["pairs"][(a, b)].append((from_b, from_a))
    for s in SIGMAS:
        d = per[s]
        far_w = np.array(d["far_w"])
        r = {"sigma_mi": s, "own_metro_median": np.median(d["own"]), "own_metro_min": np.min(d["own"]),
             "far_land_visible_share": float((far_w >= VISIBLE_W).mean()) if len(far_w) else 0.0,
             "far_land_W_p95": float(np.percentile(far_w, 95)) if len(far_w) else 0.0,
             "metro_centre_W_p10": float(np.percentile(d["metro_w"], 10))}
        for a, b, kind in PAIRS:
            v = np.array(d["pairs"][(a, b)])
            r[f"{a}<-{b}"] = np.median(v[:, 0]) if len(v) else np.nan
            r[f"{b}<-{a}"] = np.median(v[:, 1]) if len(v) else np.nan
        rows.append(r)
    D = pd.DataFrame(rows)
    return D, float(np.mean(far_counts))


def choose_sigma(D):
    """Largest sigma (smoothest surface, most blending) such that
       - metros stay themselves: median own-metro share >= 0.6;
       - empty interiors go grey: <= 5% of land > FAR_MI from any team reaches visible weight;
       - blending follows distance: every close pair blends more (both directions) than the far pair does."""
    cols = lambda kind: [f"{a}<-{b}" for a, b, k in PAIRS if k == kind] + [f"{b}<-{a}" for a, b, k in PAIRS if k == kind]
    ok = ((D.own_metro_median >= 0.6) & (D.far_land_visible_share <= 0.05)
          & (D[cols("close")].min(axis=1) > D[cols("far")].max(axis=1)))
    if not ok.any():
        raise SystemExit("no sigma passes the rule")
    return int(D[ok].sigma_mi.max()), ok


def eb_components(T):
    """Empirical-Bayes variance components for region averages of team z (method of moments, all seasons, all leagues).
    Per season: s2_within = pooled within-region variance; excess = var(region means) - mean(s2_within / n_r).
    Pooled: s2_within = mean over seasons; tau2 = max(0, mean(excess)) (unclipped mean, so no upward bias).
    Shrunk region average = mu + B_r (xbar_r - mu), B_r = tau2 / (tau2 + s2_within / n_r), mu = mean of all scored teams."""
    rows = []
    for season, g in T[T.scored].groupby("season"):
        R = g.groupby("region_id").z_pred.agg(["mean", "count"])
        ss = g.groupby("region_id").z_pred.apply(lambda x: ((x - x.mean()) ** 2).sum()).sum()
        s2w = ss / (R["count"] - 1).sum()
        rows.append({"season": season, "regions": len(R), "s2_within": s2w, "var_region_means": R["mean"].var(ddof=1),
                     "mean_sampling_var": (s2w / R["count"]).mean()})
    E = pd.DataFrame(rows)
    E["excess"] = E.var_region_means - E.mean_sampling_var
    s2w, tau2 = float(E.s2_within.mean()), max(0.0, float(E.excess.mean()))
    return E, s2w, tau2


def main():
    os.makedirs(REP, exist_ok=True)
    P, T = build_team_seasons()
    grid = pd.read_csv(os.path.join(DATA, "land_grid.csv"))

    stats = standardisation_stats(P)
    D, far_share = sigma_diagnostics(T, grid)
    sigma, ok = choose_sigma(D)
    D["passes_rule"] = ok
    ch = D.set_index("sigma_mi").loc[sigma]
    W0, W1 = float(ch.far_land_W_p95), float(ch.metro_centre_W_p10)

    z = P.z_pred.dropna()
    z_lo, z_hi = float(np.percentile(z, 2)), float(np.percentile(z, 98))
    za = P.z_actual.dropna()

    cnt = (T[T.scored].groupby(["region_id", "season", "league"]).size().unstack("league", fill_value=0))
    regions = pd.read_csv(os.path.join(MAP, "data_src", "regions.csv"))
    seasons = sorted(T.season.unique())
    full = pd.MultiIndex.from_product([regions.region_id, seasons], names=["region_id", "season"])
    cnt = cnt.reindex(full, fill_value=0)
    cnt["total"] = cnt.sum(axis=1)
    too_new = T[~T.scored].groupby(["region_id", "season"]).size().rename("too_new")
    cnt = cnt.join(too_new).fillna({"too_new": 0}).astype(int)

    E, eb_s2w, eb_tau2 = eb_components(T)
    # verdict thresholds (Phase-2 review change 3): tertiles of the pooled raw region averages (all seasons, all leagues)
    RA = T[T.scored].groupby(["season", "region_id"]).z_pred.mean()
    v_lo, v_hi = float(RA.quantile(1 / 3)), float(RA.quantile(2 / 3))
    pd.DataFrame({"n_region_seasons": [len(RA)], "tertile_1": [v_lo], "tertile_2": [v_hi], "min": [RA.min()], "max": [RA.max()]}
                 ).to_csv(os.path.join(REP, "verdict_thresholds.csv"), index=False, float_format="%.3f")
    E.to_csv(os.path.join(REP, "eb_components_by_season.csv"), index=False, float_format="%.3f")
    T.to_csv(os.path.join(DATA, "team_seasons.csv"), index=False, float_format="%.4f", lineterminator="\n")
    stats.to_csv(os.path.join(REP, "standardisation.csv"), index=False, float_format="%.3f")
    D.to_csv(os.path.join(REP, "sigma_diagnostics.csv"), index=False, float_format="%.3f")
    cnt.reset_index().to_csv(os.path.join(REP, "region_counts_by_season_league.csv"), index=False)

    league_seasons = {lg: sorted(map(int, g.season.unique())) for lg, g in P.groupby("league")}
    actual_seasons = {lg: sorted(map(int, g[g.actual_doom.notna()].season.unique())) for lg, g in P.groupby("league")}
    derived = {
        "sigma_mi": sigma, "opacity_w0": round(W0, 4), "opacity_w1": round(W1, 4),
        "z_lo": round(z_lo, 3), "z_hi": round(z_hi, 3),
        "z_outside_lo": int((z < z_lo).sum()), "z_outside_hi": int((z > z_hi).sum()), "z_n": int(len(z)),
        "z_actual_outside": int(((za < z_lo) | (za > z_hi)).sum()), "z_actual_n": int(len(za)),
        "far_mi": FAR_MI, "visible_w": VISIBLE_W, "far_land_share_mean": round(far_share, 4),
        "leagues": sorted(P.league.unique()), "seasons": [int(s) for s in seasons],
        "league_seasons": league_seasons, "actual_seasons": actual_seasons,
        "default_season": int(max(s for s in seasons if all(s in v for v in league_seasons.values()))),
        "verdict_lo": round(v_lo, 3), "verdict_hi": round(v_hi, 3),
        "eb_s2_within": round(eb_s2w, 4), "eb_tau2": round(eb_tau2, 4),
        "eb_shrink_by_n": {n: round(eb_tau2 / (eb_tau2 + eb_s2w / n), 3) for n in range(1, 7)},
        "n_team_seasons": int(len(T)), "n_scored": int(T.scored.sum()), "n_too_new": int((~T.scored).sum()),
    }
    with open(os.path.join(DATA, "derived.json"), "w") as f:
        json.dump(derived, f, indent=1)

    pd.set_option("display.width", 250, "display.max_columns", 40)
    print(stats.round(2).to_string(index=False))
    print(D.round(3).to_string(index=False))
    print(json.dumps({k: v for k, v in derived.items() if not isinstance(v, (list, dict))}, indent=1))
    print("regions with no scored team, by season:")
    print(cnt[cnt.total == 0].reset_index().groupby("region_id").season.apply(
        lambda s: f"{len(s)} seasons" if len(s) == len(seasons) else ",".join(map(str, s))).to_string())


if __name__ == "__main__":
    main()
