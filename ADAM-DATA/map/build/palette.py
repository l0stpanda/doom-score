"""Palette construction and validation by measurement (pivot spec section 7, Phase-1 review change 1).

Ramps are interpolated in OKLCh between fixed stops. The default runs blue -> cyan -> green -> gold (hue
decreasing), then gold -> orange -> crimson. Out-of-gamut points are mapped back by reducing chroma at constant
L and hue. If the plain ramp fails a check, two families of variants are searched and the passing variant with the
smoothest CIELAB L* (smallest max |second difference|) is chosen:
  - an added teal stop at t = 0.25 (grid over OKLCh L, C, h);
  - a chroma floor (C = max(C, floor)).
Every candidate is in reports/map_derived/palette_search.csv.

Checks (per palette):
  a. L* profile: middle lighter than both ends, no reversals; smoothness reported.
  b. CIEDE2000 ends >= 20 and middle vs grey >= 15, for normal vision and simulated deuteranopia, protanopia and
     tritanopia (Machado et al. 2009 at severity 100, via colorspacious); each end vs grey reported.
  e. Whole ramp: all 101 samples >= 15 from the no-data grey in all four visions; minimum chroma reported.
  c. Dark mode: ends and grey >= 3:1 against the dark background (nudged lighter in OKLab if not; logged).
  d. Legend text >= 4.5:1 in both modes.
Outputs: map/data/palette.json (stops + 256-step lookup tables per palette and mode, used directly by the map),
         reports/map_derived/palette_checks.csv, palette_search.csv, reports/map_palette.png
"""
import itertools, json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from colorspacious import cspace_convert

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)
REP = os.path.join(ROOT, "reports", "map_derived")

PALETTES = {
    "default": {"label": "Blue - gold - crimson (default, colorblind-safe)",
                "lo": "#1F5FD6", "mid": "#F2B400", "hi": "#C21F32", "grey": "#A3A8B3", "search": True},
    "greenred": {"label": "Green - yellow - red (toggle)",
                 "lo": "#12A04A", "mid": "#F5D000", "hi": "#D7261E", "grey": "#A3A8B3", "search": False},
}
MODES = {"light": {"bg": "#F6F7F9", "text": "#1D2330", "muted": "#545B69", "card": "#FFFFFF", "swatch_line": "#737985"},
         "dark": {"bg": "#14171C", "text": "#E6E9EF", "muted": "#A3AAB6", "card": "#1C2026", "swatch_line": "#8B929E"}}
CVD = {"normal": None, "deuteranopia": "deuteranomaly", "protanopia": "protanomaly", "tritanopia": "tritanomaly"}
TARGET_ENDS, TARGET_MID_GREY, TARGET_RAMP_GREY, TARGET_DARK, TARGET_TEXT = 20, 15, 15, 3.0, 4.5
N_CHECK, N_LUT = 101, 256

# ---------- colour math (vectorised: arrays of shape (..., 3)) ----------
M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
               [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])
M1i, M2i = np.linalg.inv(M1), np.linalg.inv(M2)


def hex2rgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
def rgb2hex(c): return "#" + "".join(f"{int(round(v * 255)):02X}" for v in np.clip(c, 0, 1))
def to_lin(c): c = np.asarray(c, float); return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def to_srgb(c): c = np.asarray(c, float); return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)
def rgb2oklab(c): return np.cbrt(to_lin(c) @ M1.T) @ M2.T
def oklab2lin(lab): return ((np.asarray(lab) @ M2i.T) ** 3) @ M1i.T
def oklab2rgb(lab): return to_srgb(oklab2lin(lab))
def lch2lab(L, C, h): return np.stack([L, C * np.cos(np.radians(h)), C * np.sin(np.radians(h))], -1)


def rgb2lch(c):
    L, a, b = rgb2oklab(c).T if np.ndim(c) > 1 else rgb2oklab(c)
    return np.array([L, np.hypot(a, b), np.degrees(np.arctan2(b, a)) % 360])


def gamut_map(L, C, h):
    """Largest chroma <= C at (L, h) inside sRGB (binary search, vectorised)."""
    ok = lambda c: np.all((oklab2lin(lch2lab(L, c, h)) >= -1e-5) & (oklab2lin(lch2lab(L, c, h)) <= 1 + 1e-5), axis=-1)
    lo, hi = np.zeros_like(C), C.copy()
    inside = ok(C)
    for _ in range(25):
        m = (lo + hi) / 2
        good = ok(m)
        lo, hi = np.where(good, m, lo), np.where(good, hi, m)
    Cg = np.where(inside, C, lo)
    return np.clip(oklab2rgb(lch2lab(L, Cg, h)), 0, 1), Cg


def ramp_lch(stops, n=N_CHECK, floor=0.0):
    """stops: list of (t, (L, C, h)); hue always decreases along the ramp (blue->cyan->green->gold->orange->crimson)."""
    t = np.linspace(0, 1, n)
    L, C, H = np.zeros(n), np.zeros(n), np.zeros(n)
    for (t0, a), (t1, b) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1)
        u = (t[m] - t0) / (t1 - t0)
        dh = b[2] - a[2]
        dh = dh if dh <= 0 else dh - 360
        L[m], C[m], H[m] = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, (a[2] + dh * u) % 360
    return gamut_map(L, np.maximum(C, floor), H)


def lab(c): return cspace_convert(np.clip(c, 0, 1), "sRGB1", "CIELab")


def simulate(c, kind):
    if kind is None: return np.clip(c, 0, 1)
    return np.clip(cspace_convert(np.clip(c, 0, 1), {"name": "sRGB1+CVD", "cvd_type": kind, "severity": 100}, "sRGB1"), 0, 1)


def ciede2000(lab1, lab2):
    lab1, lab2 = np.broadcast_arrays(np.asarray(lab1, float), np.asarray(lab2, float))
    L1, a1, b1 = np.moveaxis(lab1, -1, 0); L2, a2, b2 = np.moveaxis(lab2, -1, 0)
    Cb = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2))
    hbp = np.where(C1p * C2p == 0, hs, hbp)
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def rel_lum(c): r, g, b = to_lin(c); return 0.2126 * r + 0.7152 * g + 0.0722 * b
def contrast(c1, c2): l1, l2 = sorted([rel_lum(c1), rel_lum(c2)], reverse=True); return (l1 + 0.05) / (l2 + 0.05)


def nudge_for_dark(hexc, bg):
    c = hex2rgb(hexc); L = rgb2oklab(c)
    while contrast(c, hex2rgb(bg)) < TARGET_DARK and L[0] < 0.98:
        L = L + np.array([0.005, 0, 0]); c = np.clip(oklab2rgb(L), 0, 1)
    return rgb2hex(c)


# ---------- ramp variants and measurement ----------
def stops_of(p, teal=None):
    s = [(0.0, tuple(rgb2lch(hex2rgb(p["lo"]))))]
    if teal is not None:
        s.append((teal[3], teal[:3]))
    return s + [(0.5, tuple(rgb2lch(hex2rgb(p["mid"])))), (1.0, tuple(rgb2lch(hex2rgb(p["hi"]))))]


def measure(r, grey):
    """Whole-ramp metrics for an (n, 3) sRGB ramp."""
    out = {}
    for vis, kind in CVD.items():
        d = ciede2000(lab(simulate(r, kind)), lab(simulate(grey, kind)))
        out[f"min_dE_grey_{vis}"] = float(d.min()); out[f"at_t_{vis}"] = float(np.argmin(d) / (len(r) - 1))
    Ls = lab(r)[:, 0]; mid = len(Ls) // 2
    out["profile_ok"] = bool(Ls[mid] > Ls[0] and Ls[mid] > Ls[-1] and np.all(np.diff(Ls[:mid + 1]) > -0.05)
                             and np.all(np.diff(Ls[mid:]) < 0.05))
    out["L_smooth"] = float(np.abs(np.diff(Ls, 2)).max())           # max |second difference| of L* (101 samples)
    Cab = np.hypot(*lab(r)[:, 1:].T)
    out["min_chroma_Cab"] = float(Cab.min()); out["min_chroma_at_t"] = float(np.argmin(Cab) / (len(r) - 1))
    out["min_dE_grey_all"] = min(out[f"min_dE_grey_{v}"] for v in CVD)
    return out


def choose(p):
    grey = hex2rgb(p["grey"])
    cands = [("oklch", "plain", stops_of(p), 0.0)]
    if p["search"]:
        for f in np.round(np.arange(0.06, 0.205, 0.01), 3):
            cands.append(("oklch+floor", f"floor C={f}", stops_of(p), f))
        for L, C, h in itertools.product(np.arange(0.50, 0.81, 0.03), np.arange(0.08, 0.19, 0.02), range(165, 236, 10)):
            cands.append(("oklch+teal", f"teal L={L:.2f} C={C:.2f} h={h}", stops_of(p, (L, C, h, 0.25)), 0.0))
        # teal + a darker yellow-green stop: crosses the tritan neutral (~570 nm) well below the grey's lightness
        lo_, mid_, hi_ = stops_of(p)[0], stops_of(p)[-2], stops_of(p)[-1]
        for tL, th, yL, yC, yh, ty in itertools.product([.48, .52, .56], [175, 190, 205], [.42, .46, .50, .54, .58],
                                                        [.10, .13, .16], [100, 110, 120], [.35, .40]):
            cands.append(("oklch+teal+yellowgreen", f"teal L={tL} C=0.14 h={th} @0.20; yg L={yL} C={yC} h={yh} @{ty}",
                          [lo_, (0.2, (tL, 0.14, th)), (ty, (yL, yC, yh)), mid_, hi_], 0.0))
    rows = []
    for fam, name, stops, floor in cands:
        r, _ = ramp_lch(stops, floor=floor)
        m = measure(r, grey)
        ends = min(float(ciede2000(lab(simulate(r[0], k)), lab(simulate(r[-1], k)))) for k in CVD.values())
        m.update({"family": fam, "variant": name, "ends_min_dE": ends,
                  "passes": m["profile_ok"] and m["min_dE_grey_all"] >= TARGET_RAMP_GREY and ends >= TARGET_ENDS})
        rows.append((m, stops, floor))
    S = pd.DataFrame([m for m, _, _ in rows])
    if p["search"]:
        S.to_csv(os.path.join(REP, "palette_search.csv"), index=False, float_format="%.3f")
    if rows[0][0]["passes"]:
        best = rows[0]
    elif any(m["passes"] for m, _, _ in rows):
        best = min((x for x in rows if x[0]["passes"]), key=lambda x: x[0]["L_smooth"])
    else:
        best = max(rows, key=lambda x: x[0]["min_dE_grey_all"])
    return best, S


def check(name, p, dark_grey=None):
    (m, stops, floor), S = choose(p)
    grey = hex2rgb(p["grey"])
    r, _ = ramp_lch(stops, floor=floor)
    rows = [{"palette": name, "check": "chosen variant", "vision": "-", "mode": "light",
             "value": f"{m['family']}: {m['variant']}", "target": "pass all, smoothest L*", "pass": m["passes"]}]
    Ls = lab(r)[:, 0]; mid = len(Ls) // 2
    rows.append({"palette": name, "check": "a. L* profile", "vision": "normal", "mode": "light",
                 "value": f"L* lo {Ls[0]:.1f} / mid {Ls[mid]:.1f} / hi {Ls[-1]:.1f}; max |d2 L*| {m['L_smooth']:.2f}",
                 "target": "mid > both ends, no reversals", "pass": m["profile_ok"]})
    sw = {k: v for k, v in zip(("lo", "mid", "hi"), (r[0], r[mid], r[-1]))}
    for vis, kind in CVD.items():
        L_ = {k: lab(simulate(v, kind)) for k, v in {**sw, "grey": grey}.items()}
        for a, b, tgt in [("lo", "hi", TARGET_ENDS), ("mid", "grey", TARGET_MID_GREY), ("lo", "grey", None), ("hi", "grey", None)]:
            d = float(ciede2000(L_[a], L_[b]))
            rows.append({"palette": name, "check": f"b. dE2000 {a}-{b}", "vision": vis, "mode": "light",
                         "value": f"{d:.1f}", "target": f">= {tgt}" if tgt else "report", "pass": (d >= tgt) if tgt else None})
        rows.append({"palette": name, "check": "e. whole ramp min dE2000 vs grey", "vision": vis, "mode": "light",
                     "value": f"{m[f'min_dE_grey_{vis}']:.1f} at t={m[f'at_t_{vis}']:.2f}", "target": f">= {TARGET_RAMP_GREY} at all 101 points",
                     "pass": m[f"min_dE_grey_{vis}"] >= TARGET_RAMP_GREY})
    rows.append({"palette": name, "check": "e. min chroma C*ab", "vision": "normal", "mode": "light",
                 "value": f"{m['min_chroma_Cab']:.1f} at t={m['min_chroma_at_t']:.2f}", "target": "report", "pass": None})
    out = {"light": {"lo": rgb2hex(r[0]), "mid": rgb2hex(r[mid]), "hi": rgb2hex(r[-1]), "grey": p["grey"]}}
    out["dark"] = {}
    bg = MODES["dark"]["bg"]
    for k in ("lo", "mid", "hi", "grey"):
        old = out["light"][k]
        new = nudge_for_dark(old, bg) if k != "mid" else old
        out["dark"][k] = new
        if k != "mid":
            rows.append({"palette": name, "check": f"c. dark contrast {k}", "vision": "normal", "mode": "dark",
                         "value": f"{contrast(hex2rgb(old), hex2rgb(bg)):.2f}" + (f" -> {contrast(hex2rgb(new), hex2rgb(bg)):.2f} ({old} -> {new})" if new != old else ""),
                         "target": f">= {TARGET_DARK}", "pass": contrast(hex2rgb(new), hex2rgb(bg)) >= TARGET_DARK})
    for mode, mm in MODES.items():           # M34: the no-data swatch is outlined at >= 3:1 against the legend card
        cr = contrast(hex2rgb(mm["swatch_line"]), hex2rgb(mm["card"]))
        rows.append({"palette": name, "check": "d. no-data swatch outline vs legend card", "vision": "normal", "mode": mode,
                     "value": f"{cr:.2f} ({mm['swatch_line']} on {mm['card']})", "target": f">= {TARGET_DARK}", "pass": cr >= TARGET_DARK})
        for t in ("text", "muted"):
            cr = contrast(hex2rgb(mm[t]), hex2rgb(mm["bg"]))
            rows.append({"palette": name, "check": f"d. legend {t} contrast", "vision": "normal", "mode": mode,
                         "value": f"{cr:.2f}", "target": f">= {TARGET_TEXT}", "pass": cr >= TARGET_TEXT})
    # lookup tables (the map indexes these directly; t = 0 bright future ... 1 doomed)
    luts = {}
    for mode in MODES:
        st = list(stops)
        if out[mode]["lo"] != out["light"]["lo"]: st[0] = (0.0, tuple(rgb2lch(hex2rgb(out[mode]["lo"]))))
        if out[mode]["hi"] != out["light"]["hi"]: st[-1] = (1.0, tuple(rgb2lch(hex2rgb(out[mode]["hi"]))))
        lr, _ = ramp_lch(st, n=N_LUT, floor=floor)
        luts[mode] = [rgb2hex(c) for c in lr]
    out["lut"] = luts
    out["method"] = {"family": m["family"], "variant": m["variant"], "chroma_floor": floor,
                     "stops_oklch": [[t, [round(float(v), 4) for v in s]] for t, s in stops]}
    # dark-mode "no data" grey (Phase-2 review change 2): darkest grey of the same hue/chroma that keeps the whole
    # dark ramp >= 15 dE2000 away in all four visions and >= 3:1 against the dark background
    if dark_grey is None:
        dark_grey, cand = derive_dark_grey(luts["dark"], p["grey"])
        cand.to_csv(os.path.join(REP, "dark_grey_search.csv"), index=False, float_format="%.3f")
    out["dark"]["grey"] = dark_grey
    bgd = hex2rgb(MODES["dark"]["bg"])
    rows.append({"palette": name, "check": "c. dark contrast grey (derived dark grey)", "vision": "normal", "mode": "dark",
                 "value": f"{contrast(hex2rgb(dark_grey), bgd):.2f} ({p['grey']} -> {dark_grey})",
                 "target": f">= {TARGET_DARK} (superseded: grey must recede, M34)", "pass": contrast(hex2rgb(dark_grey), bgd) >= TARGET_DARK})
    rd = lut101(luts["dark"])
    md = measure(rd, hex2rgb(dark_grey))
    for vis in CVD:
        rows.append({"palette": name, "check": "e. whole ramp min dE2000 vs grey", "vision": vis, "mode": "dark",
                     "value": f"{md[f'min_dE_grey_{vis}']:.1f} at t={md[f'at_t_{vis}']:.2f}",
                     "target": f">= {TARGET_RAMP_GREY} at all 101 points", "pass": md[f"min_dE_grey_{vis}"] >= TARGET_RAMP_GREY})
    return rows, out, S


def lut101(lut_hex):
    idx = np.round(np.linspace(0, len(lut_hex) - 1, N_CHECK)).astype(int)
    return np.array([hex2rgb(lut_hex[i]) for i in idx])


def derive_dark_grey(lut_dark, light_grey):
    """Dark-mode no-data grey (Phase-2 review change 2). Candidates keep the light grey's OKLCh hue and chroma and lower
    L in 0.0025 steps. A candidate must (a) be ΔE2000 >= 15 from all 101 dark-ramp samples in all four visions and
    (b) recede: L at least 0.15 below the light grey. The lightest such candidate is chosen (most visible land while
    receding). Contrast vs the dark background is reported: no grey can be dark enough to recede, keep ΔE >= 15 and
    reach 3:1 (the 0.38-0.70 L band collides with the ramp's mid-dark colours), so the old 3:1 rule is superseded."""
    r = lut101(lut_dark)
    L0, C0, h0 = rgb2lch(hex2rgb(light_grey))
    bg = hex2rgb(MODES["dark"]["bg"])
    rows = []
    for L in np.arange(0.28, L0 + 1e-9, 0.0025):
        g, _ = gamut_map(np.array([L]), np.array([C0]), np.array([h0]))
        g = g[0]
        mm = measure(r, g)
        rows.append({"oklch_L": L, "hex": rgb2hex(g), "contrast_vs_dark_bg": contrast(g, bg),
                     "min_dE_all_visions": mm["min_dE_grey_all"], **{f"min_dE_{v}": mm[f"min_dE_grey_{v}"] for v in CVD},
                     "recedes": L <= L0 - 0.15, "passes": mm["min_dE_grey_all"] >= TARGET_RAMP_GREY and L <= L0 - 0.15})
    C = pd.DataFrame(rows)
    ok = C[C.passes]
    best = ok.sort_values("oklch_L").iloc[-1].hex if len(ok) else light_grey
    C["chosen"] = C.hex == best
    return best, C


def figure(results):
    rows = [(name, vis, kind) for name in PALETTES for vis, kind in CVD.items()]
    ROW_H, TOP, BOT = 0.92, 1.05, 1.5
    H = TOP + len(rows) * ROW_H + BOT
    fig = plt.figure(figsize=(13, H), dpi=110)
    for mi, (mode, m) in enumerate(MODES.items()):
        fig.patches.append(plt.Rectangle((0.01 + mi * 0.495, BOT / H - 0.005), 0.485, len(rows) * ROW_H / H + 0.01,
                                         transform=fig.transFigure, color=m["bg"], zorder=-1))
    for ri, (name, vis, kind) in enumerate(rows):
        y0 = (H - TOP - (ri + 1) * ROW_H) / H
        for mi, (mode, m) in enumerate(MODES.items()):
            lut = np.array([hex2rgb(h) for h in results[name]["lut"][mode]])
            ax = fig.add_axes([0.025 + mi * 0.495, y0 + 0.30 / H, 0.455, 0.36 / H])
            ax.set_facecolor(m["bg"])
            ax.imshow(simulate(lut, kind)[None, :, :], aspect="auto", extent=[0, 0.86, 0, 1])
            ax.add_patch(plt.Rectangle((0.89, 0), 0.11, 1, color=simulate(hex2rgb(results[name][mode]["grey"]), kind)))
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values(): s.set_visible(False)
            title = (PALETTES[name]["label"] + " - " if vis == "normal" else "") + f"{vis}, {mode} mode"
            ax.text(0, 1.18, title, transform=ax.transAxes, fontsize=8.5, color=m["text"], weight="bold" if vis == "normal" else "normal")
            for x, t, ha in [(0, "Bright future", "left"), (0.43, "Middling", "center"), (0.86, "Doomed", "right"), (0.945, "No teams", "center")]:
                ax.text(x, -0.42, t, transform=ax.transAxes, fontsize=7.5, color=m["muted"], ha=ha)
    fig.text(0.01, 1 - 0.35 / H, "Doom Map palettes: OKLCh ramps, normal vision and Machado (2009) dichromacy simulations",
             fontsize=12, weight="bold")
    fig.text(0.01, 1 - 0.62 / H, "Left: light mode.  Right: dark mode, with its own derived no-data grey.", fontsize=9, color="#545B69")
    return fig, BOT / H


def main():
    os.makedirs(REP, exist_ok=True)
    rows, results = [], {}
    dark_grey = None
    for name, p in PALETTES.items():                 # default first: its derived dark grey is shared by the toggle
        r, out, _ = check(name, p, dark_grey); rows += r; results[name] = out
        dark_grey = out["dark"]["grey"]
    C = pd.DataFrame(rows)
    C.to_csv(os.path.join(REP, "palette_checks.csv"), index=False)
    fig, bot = figure(results)

    def cellm(pal, chk, vis, mode):
        r = C[(C.palette == pal) & (C.check == chk) & (C.vision == vis) & (C["mode"] == mode)]
        return r.value.iloc[0].split(" at")[0] if len(r) else ""

    def cell(pal, chk, vis):
        r = C[(C.palette == pal) & (C.check == chk) & (C.vision == vis)]
        return r.value.iloc[0].split(" at")[0] if len(r) else ""
    lines = ["ΔE2000, normal / deutan / protan / tritan".ljust(30) + "ends".ljust(27) + "whole ramp vs grey, light".ljust(27) + "whole ramp vs grey, dark".ljust(27) + "ramp"]
    for pal in PALETTES:
        lines.append(f"{pal:30s}" + " / ".join(cell(pal, 'b. dE2000 lo-hi', v) for v in CVD).ljust(27) +
                     " / ".join(cellm(pal, 'e. whole ramp min dE2000 vs grey', v, 'light') for v in CVD).ljust(27) +
                     " / ".join(cellm(pal, 'e. whole ramp min dE2000 vs grey', v, 'dark') for v in CVD).ljust(27) +
                     results[pal]["method"]["family"] + " " + results[pal]["method"]["variant"])
    dk = C[C.check.str.startswith("c. dark") & ~C.check.str.contains("derived")]
    lines.append("Dark-mode no-data grey: " + results["default"]["light"]["grey"] + " -> " + results["default"]["dark"]["grey"] +
                 " (lightest grey of the same hue that recedes, L >= 0.15 below the light grey, and keeps the whole dark ramp >= 15 dE away in all visions)")
    lines.append(f"Targets: ends >= {TARGET_ENDS}; middle vs grey >= {TARGET_MID_GREY}; whole ramp >= {TARGET_RAMP_GREY} at all 101 points; "
                 f"dark-mode contrast >= {TARGET_DARK}:1; legend text >= {TARGET_TEXT}:1.")
    lines.append("Dark contrast (default): " + ", ".join(f"{r.check.split()[-1]} {r.value}" for r in dk[dk.palette == 'default'].itertuples()))
    fig.text(0.01, bot - 0.012, "\n".join(lines), fontsize=7.6, family="monospace", va="top")
    fig.savefig(os.path.join(ROOT, "reports", "map_palette.png"))
    json.dump({"palettes": {k: {"label": PALETTES[k]["label"], **results[k]} for k in PALETTES}, "modes": MODES,
               "interpolation": "oklch"}, open(os.path.join(MAP, "data", "palette.json"), "w"), indent=1)
    pd.set_option("display.width", 220, "display.max_colwidth", 70)
    print(C.to_string(index=False))


if __name__ == "__main__":
    main()
