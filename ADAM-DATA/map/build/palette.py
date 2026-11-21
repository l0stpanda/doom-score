"""Palette validation by measurement (pivot spec section 7).

For each palette (default blue-gold-crimson, toggle green-yellow-red) this script
  (a) samples the OKLab-blended ramp and checks the CIELAB L* profile (middle lighter than both ends, no reversals);
  (b) computes CIEDE2000 between ends, middle vs grey, and each end vs grey, for normal vision and simulated
      deuteranopia / protanopia / tritanopia (Machado et al. 2009 matrices at severity 100, via colorspacious);
  (c) checks WCAG contrast of both ends and the grey against the dark-mode background (target >= 3:1) and, if one
      fails, raises its OKLab lightness in 0.005 steps until it passes (logged old -> new);
  (d) checks legend text contrast (>= 4.5:1) in both modes.
Outputs: map/data/palette.json (the hexes the map uses, per mode), reports/map_derived/palette_checks.csv,
         reports/map_palette.png
"""
import json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from colorspacious import cspace_convert

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.dirname(HERE)
ROOT = os.path.dirname(MAP)

PALETTES = {
    "default": {"label": "Blue - gold - crimson (default, colorblind-safe)",
                "lo": "#1F5FD6", "mid": "#F2B400", "hi": "#C21F32", "grey": "#A3A8B3"},
    "greenred": {"label": "Green - yellow - red (toggle)",
                 "lo": "#12A04A", "mid": "#F5D000", "hi": "#D7261E", "grey": "#A3A8B3"},
}
MODES = {"light": {"bg": "#F6F7F9", "text": "#1D2330", "muted": "#545B69"},
         "dark": {"bg": "#14171C", "text": "#E6E9EF", "muted": "#A3AAB6"}}
CVD = {"normal": None, "deuteranopia": "deuteranomaly", "protanopia": "protanomaly", "tritanopia": "tritanomaly"}
TARGET_ENDS, TARGET_MID_GREY, TARGET_DARK, TARGET_TEXT = 20, 15, 3.0, 4.5


# ---------- colour math ----------
def hex2rgb(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
def rgb2hex(c): return "#" + "".join(f"{int(round(v * 255)):02X}" for v in np.clip(c, 0, 1))
def to_lin(c): c = np.asarray(c, float); return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def to_srgb(c): c = np.asarray(c, float); return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.cbrt(c) ** (3 / 1.2) - 0.055) if False else np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)

M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
               [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])


def rgb2oklab(c): return M2 @ np.cbrt(M1 @ to_lin(c))
def oklab2rgb(lab): return to_srgb(np.linalg.inv(M1) @ (np.linalg.inv(M2) @ lab) ** 3)


def ramp(p, n=101):
    """OKLab blend lo -> mid -> hi (t in [0, 1], mid at 0.5)."""
    lo, mid, hi = (rgb2oklab(hex2rgb(p[k])) for k in ("lo", "mid", "hi"))
    out = []
    for t in np.linspace(0, 1, n):
        a, b, u = (lo, mid, t * 2) if t <= 0.5 else (mid, hi, (t - 0.5) * 2)
        out.append(np.clip(oklab2rgb(a + (b - a) * u), 0, 1))
    return np.array(out)


def lab(c): return cspace_convert(np.clip(c, 0, 1), "sRGB1", "CIELab")


def simulate(c, kind):
    if kind is None: return np.clip(c, 0, 1)
    return np.clip(cspace_convert(np.clip(c, 0, 1), {"name": "sRGB1+CVD", "cvd_type": kind, "severity": 100}, "sRGB1"), 0, 1)


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1; L2, a2, b2 = lab2
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2); Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    if C1p * C2p == 0: dh = 0
    elif dh > 180: dh -= 360
    elif dh < -180: dh += 360
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0: hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180: hbp = (h1p + h2p) / 2
    else: hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return float(np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh)))


def rel_lum(c): r, g, b = to_lin(c); return 0.2126 * r + 0.7152 * g + 0.0722 * b
def contrast(c1, c2): l1, l2 = sorted([rel_lum(c1), rel_lum(c2)], reverse=True); return (l1 + 0.05) / (l2 + 0.05)


def nudge_for_dark(hexc, bg):
    """Raise OKLab L in small steps (hue/chroma kept) until contrast vs bg >= TARGET_DARK."""
    c = hex2rgb(hexc); L = rgb2oklab(c)
    while contrast(c, hex2rgb(bg)) < TARGET_DARK and L[0] < 0.98:
        L = L + np.array([0.005, 0, 0]); c = np.clip(oklab2rgb(L), 0, 1)
    return rgb2hex(c)


# ---------- checks ----------
def check(name, p):
    rows, out = [], {"light": {k: p[k] for k in ("lo", "mid", "hi", "grey")}}
    r = ramp(p)
    Ls = lab(r)[:, 0]
    mid_i = len(Ls) // 2
    rises = np.all(np.diff(Ls[:mid_i + 1]) > -0.05); falls = np.all(np.diff(Ls[mid_i:]) < 0.05)
    lights = Ls[mid_i] > Ls[0] and Ls[mid_i] > Ls[-1]
    rows.append({"palette": name, "check": "a. L* profile", "vision": "normal", "mode": "light",
                 "value": f"L* lo {Ls[0]:.1f} / mid {Ls[mid_i]:.1f} / hi {Ls[-1]:.1f}; max step {np.abs(np.diff(Ls)).max():.2f}",
                 "target": "mid > both ends, no reversals", "pass": bool(rises and falls and lights)})
    for vis, kind in CVD.items():
        sw = {k: lab(simulate(hex2rgb(p[k]), kind)) for k in ("lo", "mid", "hi", "grey")}
        for (a, b, tgt) in [("lo", "hi", TARGET_ENDS), ("mid", "grey", TARGET_MID_GREY), ("lo", "grey", None), ("hi", "grey", None)]:
            d = ciede2000(sw[a], sw[b])
            rows.append({"palette": name, "check": f"b. dE2000 {a}-{b}", "vision": vis, "mode": "light",
                         "value": f"{d:.1f}", "target": f">= {tgt}" if tgt else "report", "pass": (d >= tgt) if tgt else None})
        # e. (added) closest any ramp colour comes to the "no teams" grey: a heatmap value must never read as "no data"
        rs = simulate(r, kind); gl = lab(simulate(hex2rgb(p["grey"]), kind))
        dmin = [ciede2000(lab(c), gl) for c in rs]; i = int(np.argmin(dmin))
        rows.append({"palette": name, "check": "e. min dE2000 ramp-grey", "vision": vis, "mode": "light",
                     "value": f"{dmin[i]:.1f} at t={i / (len(rs) - 1):.2f}", "target": "report (>= 10 wanted)",
                     "pass": dmin[i] >= 10})
    bg = MODES["dark"]["bg"]
    out["dark"] = {}
    for k in ("lo", "mid", "hi", "grey"):
        old = p[k]; cr = contrast(hex2rgb(old), hex2rgb(bg))
        new = nudge_for_dark(old, bg) if k != "mid" else old
        out["dark"][k] = new
        if k != "mid":
            rows.append({"palette": name, "check": f"c. dark contrast {k}", "vision": "normal", "mode": "dark",
                         "value": f"{cr:.2f}" + (f" -> {contrast(hex2rgb(new), hex2rgb(bg)):.2f} ({old} -> {new})" if new != old else ""),
                         "target": f">= {TARGET_DARK}", "pass": contrast(hex2rgb(new), hex2rgb(bg)) >= TARGET_DARK,
                         "adjusted": new != old})
    for mode, m in MODES.items():
        for t in ("text", "muted"):
            cr = contrast(hex2rgb(m[t]), hex2rgb(m["bg"]))
            rows.append({"palette": name, "check": f"d. legend {t} contrast", "vision": "normal", "mode": mode,
                         "value": f"{cr:.2f}", "target": f">= {TARGET_TEXT}", "pass": cr >= TARGET_TEXT})
    return rows, out


def figure(results):
    rows = [(name, vis, kind) for name in PALETTES for vis, kind in CVD.items()]
    ROW_H, TOP, BOT = 0.92, 1.05, 1.3                       # inches
    H = TOP + len(rows) * ROW_H + BOT
    fig = plt.figure(figsize=(13, H), dpi=110)
    for mi, (mode, m) in enumerate(MODES.items()):           # one background panel per mode
        fig.patches.append(plt.Rectangle((0.01 + mi * 0.495, BOT / H - 0.005), 0.485, len(rows) * ROW_H / H + 0.01,
                                         transform=fig.transFigure, color=m["bg"], zorder=-1))
    for ri, (name, vis, kind) in enumerate(rows):
        y0 = (H - TOP - (ri + 1) * ROW_H) / H
        for mi, (mode, m) in enumerate(MODES.items()):
            pm = {**PALETTES[name], **results[name][mode]}
            ax = fig.add_axes([0.025 + mi * 0.495, y0 + 0.30 / H, 0.455, 0.36 / H])
            ax.set_facecolor(m["bg"])
            r = simulate(ramp(pm, 256), kind)
            ax.imshow(r[None, :, :], aspect="auto", extent=[0, 0.86, 0, 1])
            ax.add_patch(plt.Rectangle((0.89, 0), 0.11, 1, color=simulate(hex2rgb(pm["grey"]), kind)))
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values(): s.set_visible(False)
            title = (PALETTES[name]["label"] + " - " if vis == "normal" else "") + f"{vis}, {mode} mode"
            ax.text(0, 1.18, title, transform=ax.transAxes, fontsize=8.5, color=m["text"],
                    weight="bold" if vis == "normal" else "normal")
            for x, t, ha in [(0, "Bright future", "left"), (0.43, "Middling", "center"), (0.86, "Doomed", "right"),
                             (0.945, "No teams", "center")]:
                ax.text(x, -0.42, t, transform=ax.transAxes, fontsize=7.5, color=m["muted"], ha=ha)
    fig.text(0.01, 1 - 0.35 / H, "Doom Map palettes: OKLab ramps, normal vision and Machado (2009) dichromacy simulations",
             fontsize=12, weight="bold")
    fig.text(0.01, 1 - 0.62 / H, "Left: light mode.  Right: dark mode (an end or the grey is nudged lighter only if it "
             "misses 3:1 against the background; none needed it).", fontsize=9, color="#545B69")
    return fig, BOT / H


def main():
    os.makedirs(os.path.join(ROOT, "reports", "map_derived"), exist_ok=True)
    rows, results = [], {}
    for name, p in PALETTES.items():
        r, out = check(name, p); rows += r; results[name] = out
    C = pd.DataFrame(rows)
    C.to_csv(os.path.join(ROOT, "reports", "map_derived", "palette_checks.csv"), index=False)
    fig, bot = figure(results)
    # compact results table under the ramps
    def cell(pal, chk, vis):
        r = C[(C.palette == pal) & (C.check == chk) & (C.vision == vis)]
        return r.value.iloc[0].split(" at")[0] if len(r) else ""
    lines = ["ΔE2000, normal / deutan / protan / tritan".ljust(44) + "ends".ljust(28) + "middle vs grey".ljust(28) + "closest ramp point vs grey"]
    for pal in PALETTES:
        lines.append(f"{pal:44s}" + " / ".join(cell(pal, 'b. dE2000 lo-hi', v) for v in CVD).ljust(28) +
                     " / ".join(cell(pal, 'b. dE2000 mid-grey', v) for v in CVD).ljust(28) +
                     " / ".join(cell(pal, 'e. min dE2000 ramp-grey', v) for v in CVD))
    lines.append(f"Targets: ends >= {TARGET_ENDS}, middle vs grey >= {TARGET_MID_GREY}; dark-mode contrast of ends and grey >= "
                 f"{TARGET_DARK}:1 (default: blue 3.14, crimson 3.02, grey 7.54); legend text >= {TARGET_TEXT}:1 (all >= 6.3).")
    fig.text(0.01, bot - 0.012, "\n".join(lines), fontsize=8, family="monospace", va="top")
    fig.savefig(os.path.join(ROOT, "reports", "map_palette.png"))
    json.dump({"palettes": {k: {"label": PALETTES[k]["label"], **results[k]} for k in PALETTES}, "modes": MODES,
               "interpolation": "oklab"}, open(os.path.join(MAP, "data", "palette.json"), "w"), indent=1)
    pd.set_option("display.width", 220)
    print(C.drop(columns=[c for c in ["adjusted"] if c in C]).to_string(index=False))


if __name__ == "__main__":
    main()
