# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Grid as plain x/y rects (lon -> x, lat -> y) with Natural Earth geoshapes drawn over it.

The geoshape layers use an ``identity`` projection whose scale and translate
reproduce the x/y scales: x = k*(lon - lon0), y = k*(lat1 - lat). The view
height is k * lat span so one degree is the same size on both axes, which is
what equirectangular does.

    uv run --script proto_xy.py     # out/xy_projected.png, out/xy_plain.png
"""

import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
SPEC = json.loads((HERE.parent / "examples" / "map_heatmap_stations.json").read_text())
INPUTS = {
    "obs": HERE / "data" / "obs_chirps_week.zarr",
    "stations": HERE / "data" / "stations_week.zarr",
}
GEO = {"longitude": "x", "latitude": "y", "longitude2": "x2", "latitude2": "y2"}


def to_xy(spec, extent):
    """Rewrite a bound, defaulted map spec from projection to linear x/y plus an identity projection."""
    lat1, lon0, lat0, lon1 = extent
    k = spec["width"] / (lon1 - lon0)
    spec["height"] = round(k * (lat1 - lat0))
    spec["projection"] = {
        "type": "identity",
        "reflectY": True,
        "scale": k,
        "translate": [-k * lon0, k * lat1],
    }
    for layer in spec["layer"]:
        enc = layer.get("encoding") or {}
        for geo, xy in GEO.items():
            if geo in enc:
                enc[xy] = enc.pop(geo)
        for ch, lo, hi in (("x", lon0, lon1), ("y", lat0, lat1)):
            if ch in enc:
                enc[ch]["scale"] = {"domain": [lo, hi], "zero": False, "nice": False}
                enc[ch]["axis"] = None


def main():
    import vl_convert as vlc

    inputs = vlbind.open_inputs(INPUTS)
    for mode in ("projected", "plain"):
        notes = []
        spec, meta = vlbind.bind_all(copy.deepcopy(SPEC), inputs, None, notes)
        classed = vlbind.apply_defaults(spec, meta, notes)
        if mode == "plain":
            to_xy(spec, meta["obs"]["extent"])
        t0 = time.perf_counter()
        vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
        vlbind.seal_cells(vega)
        vlbind.classed_legends(vega, classed)
        (OUT / f"xy_{mode}.png").write_bytes(vlc.vega_to_png(vega, scale=2))
        print(f"{mode:9} render {time.perf_counter() - t0:.2f}s")


if __name__ == "__main__":
    main()
