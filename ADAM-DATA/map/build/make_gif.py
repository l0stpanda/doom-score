"""Assemble zoom-animation frames (from map/build/shots_phase3.mjs) into GIFs that play at real speed.

Usage: python map/build/make_gif.py <frames_dir>  -> reports/figures/map_p3_<name>.gif for every <frames_dir>/<name>/
Frame durations come from the recorded in-page timestamps (captured slowed down, rescaled to real time); the last
frame is held for 1.5 s. Frames are downscaled to 760 px wide.
"""
import json, os, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIG = os.path.join(ROOT, "reports", "figures")


def build(src, name):
    meta = json.load(open(os.path.join(src, "times.json")))
    times = meta["times"]
    files = sorted(f for f in os.listdir(src) if f.endswith(".png"))[:len(times)]
    frames = []
    for f in files:
        im = Image.open(os.path.join(src, f)).convert("RGB")
        w = 760
        im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        frames.append(im.quantize(colors=192, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG))
    dur = [max(20, round(b - a)) for a, b in zip(times, times[1:])] + [1500]
    dur[0] = 600                                          # hold the starting view briefly
    out = os.path.join(FIG, f"map_p3_{name}.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=dur, loop=0, optimize=True, disposal=1)
    print(f"wrote {os.path.relpath(out, ROOT)}: {len(frames)} frames, animation {sum(dur[1:-1])} ms, "
          f"{os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    base = sys.argv[1]
    for name in sorted(os.listdir(base)):
        if os.path.isdir(os.path.join(base, name)) and os.path.exists(os.path.join(base, name, "times.json")):
            build(os.path.join(base, name), name)
