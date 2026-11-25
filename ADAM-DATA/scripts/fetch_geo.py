"""Download the US county boundaries the Doom Map regions are built from (M06, M49). Run from ADAM-DATA/:

    .venv/Scripts/python scripts/fetch_geo.py           # skips the download if the files are already there
    .venv/Scripts/python scripts/fetch_geo.py --force   # download again

Writes data/raw/geo/us_county/cb_2023_us_county_5m.{shp,shx,dbf,prj,cpg} (git-ignored, like all of data/raw/).
Only needed for `map/build_map.py --rebuild-regions`; the default build uses the committed map/data/regions.topo.json.

The Canadian census divisions (data/raw/geo/cd_0.geojson, cd_100.geojson, cd_200.geojson; M07) are NOT downloaded
here: StatCan's zip returns HTTP 403 to scripts, and the ArcGIS REST query used originally was not recorded.
See docs/ADD_A_LEAGUE.md, "Changing the regions", for the manual steps.
"""
import io, os, sys, zipfile

import requests

URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_5m.zip"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ADAM-DATA
OUT = os.path.join(ROOT, "data", "raw", "geo", "us_county")
STEM = "cb_2023_us_county_5m"
NEEDED = [STEM + ext for ext in (".shp", ".shx", ".dbf", ".prj")]
KEEP = NEEDED + [STEM + ".cpg"]


def main():
    force = "--force" in sys.argv[1:]
    if not force and all(os.path.isfile(os.path.join(OUT, f)) for f in NEEDED):
        print(f"already present in {os.path.relpath(OUT, ROOT)} (use --force to download again)")
        return
    print(f"downloading {URL}", flush=True)
    r = requests.get(URL, timeout=120, headers={"User-Agent": "doom-map-build"})
    r.raise_for_status()
    os.makedirs(OUT, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = {os.path.basename(n): n for n in z.namelist()}
        missing = [f for f in NEEDED if f not in names]
        if missing:
            sys.exit(f"zip is missing {missing}; the Census file layout may have changed")
        for f in KEEP:                       # extract only the expected files, by name (no paths from the zip)
            if f in names:
                with open(os.path.join(OUT, f), "wb") as fh:
                    fh.write(z.read(names[f]))
    print(f"wrote {', '.join(f for f in KEEP if f in names)} to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
