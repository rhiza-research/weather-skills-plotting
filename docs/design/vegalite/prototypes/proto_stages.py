# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Where does a big rect heatmap spend its time? Times each stage of the render path separately.

    uv run --script proto_stages.py                 # default sweep, one subprocess per run
    uv run --script proto_stages.py one VARIANT N   # a single run, prints one JSON line

Variants (all n x n cells, 600 x 600 px, scale 2):
  base      the skill's path: lo/hi edge columns, projection, color encoding, seal_cells stroke
  nostroke  seal_cells off (no stroke on the cells)
  noproj    plain x/y scales instead of a projection
  lean      only lon/lat/tp shipped; edges computed in Vega with a calculate transform
  padded    base plus 5 unused float columns: ~2x the JSON, same marks
  image     the raster fallback: Python colours the grid, one image mark
"""

import base64
import copy
import io
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402


def grid(n):
    lat = np.linspace(-10, 10, n)
    lon = np.linspace(30, 50, n)
    lo, la = np.meshgrid(lon, lat)
    v = 50 + 45 * np.sin(lo * 1.3) * np.cos(la * 0.9)
    return xr.Dataset(
        {"tp": (("latitude", "longitude"), v, {"units": "mm", "aggregation_period": "7D"})},
        coords={"latitude": lat, "longitude": lon},
    )


EDGES = {"lon": "longitude.lo", "lon2": "longitude.hi", "lat": "latitude.lo", "lat2": "latitude.hi", "tp": "tp"}
COLOR = {"field": "tp", "type": "quantitative", "scale": {"scheme": "default_precip"}}


def spec_for(variant, n):
    enc = {
        "longitude": {"field": "lon", "type": "quantitative"},
        "latitude": {"field": "lat", "type": "quantitative"},
        "longitude2": {"field": "lon2"},
        "latitude2": {"field": "lat2"},
        "color": COLOR,
    }
    spec = {
        "width": 600,
        "height": 600,
        "projection": {"type": "equirectangular"},
        "datasets": {"g": {"zarr": "g", "fields": dict(EDGES)}},
        "data": {"name": "g"},
        "mark": "rect",
        "encoding": enc,
    }
    if variant == "nostroke":
        spec["usermeta"] = {"seal_cells": False}
    elif variant == "noproj":
        del spec["projection"]
        enc["x"], enc["x2"] = enc.pop("longitude"), enc.pop("longitude2")
        enc["y"], enc["y2"] = enc.pop("latitude"), enc.pop("latitude2")
        for ch in ("x", "y"):
            enc[ch]["scale"] = {"zero": False, "nice": False}
            enc[ch]["axis"] = None
    elif variant == "lean":
        half = 10 / (n - 1)
        spec["datasets"]["g"]["fields"] = {"lon": "longitude", "lat": "latitude", "tp": "tp"}
        spec["transform"] = [
            {"calculate": f"datum.lon + {half}", "as": "lon2"},
            {"calculate": f"datum.lat + {half}", "as": "lat2"},
            {"calculate": f"datum.lon - {half}", "as": "lon"},
            {"calculate": f"datum.lat - {half}", "as": "lat"},
        ]
    return spec


def pad_rows(spec):
    for row in spec["datasets"]["g"]:
        for k in range(5):
            row[f"pad{k}"] = row["tp"] * (k + 1.123456789)


def image_spec(ds):
    """Raster fallback: colour the grid with the same threshold palette, ship one PNG."""
    from PIL import Image

    _, domain, colors = vlbind.palette_scale("default_precip", ds["tp"])
    rgb = np.array([[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in colors], dtype=np.uint8)
    idx = np.searchsorted(np.asarray(domain), ds["tp"].values[::-1], side="right")
    buf = io.BytesIO()
    Image.fromarray(rgb[idx]).save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "width": 600,
        "height": 600,
        "data": {"values": [{"url": url}]},
        "mark": {"type": "image", "width": 600, "height": 600, "aspect": False, "smooth": False},
        "encoding": {"url": {"field": "url", "type": "nominal"}, "x": {"value": 300}, "y": {"value": 300}},
    }


def one(variant, n):
    import vl_convert as vlc

    vlc.vegalite_to_png({"mark": "point", "data": {"values": [{"a": 1}]}, "encoding": {"x": {"field": "a"}}})
    out = {"variant": variant, "cells": n * n}
    ds = grid(n)
    t = time.perf_counter()
    if variant == "image":
        spec = image_spec(ds)
    else:
        spec_in = spec_for("base" if variant == "padded" else variant, n)
        notes = []
        spec, meta = vlbind.bind_all(spec_in, {"g": ds}, None, notes)
        classed = vlbind.apply_defaults(spec, meta, notes)
        if variant == "padded":
            pad_rows(spec)
        spec["$schema"] = "https://vega.github.io/schema/vega-lite/v6.json"
    out["bind_s"] = time.perf_counter() - t

    t = time.perf_counter()
    text = json.dumps(spec)
    out["dumps_s"] = time.perf_counter() - t
    out["json_mb"] = len(text) / 1e6

    t = time.perf_counter()
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    vega = json.loads(vega) if isinstance(vega, str) else vega
    out["compile_s"] = time.perf_counter() - t

    stub = copy.deepcopy({k: v for k, v in spec.items() if k != "datasets"})
    stub["datasets"] = {k: v[:3] for k, v in (spec.get("datasets") or {}).items()}
    t = time.perf_counter()
    vlc.vegalite_to_vega(stub, vl_version="6.4")
    out["compile_stub_s"] = time.perf_counter() - t

    if variant != "image":
        if (spec.get("usermeta") or {}).get("seal_cells", True):
            vlbind.seal_cells(vega)
        vlbind.classed_legends(vega, classed)

    # Vega dataflow (parse data + transforms + scales) with no mark items drawn.
    nomarks = copy.deepcopy(vega)
    nomarks["marks"] = [m for m in nomarks.get("marks", []) if m.get("type") != "rect"]
    t = time.perf_counter()
    vlc.vega_to_svg(nomarks)
    out["dataflow_s"] = time.perf_counter() - t

    t = time.perf_counter()
    svg = vlc.vega_to_svg(vega)
    out["to_svg_s"] = time.perf_counter() - t
    out["svg_mb"] = len(svg) / 1e6

    t = time.perf_counter()
    vlc.svg_to_png(svg, scale=2)
    out["svg_to_png_s"] = time.perf_counter() - t
    del svg

    t = time.perf_counter()
    png = vlc.vega_to_png(vega, scale=2)
    out["vega_to_png_s"] = time.perf_counter() - t
    (Path(__file__).parent / "out" / f"stages_{variant}_{n}.png").write_bytes(png)

    out["peak_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    print(json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in out.items()}), flush=True)


COLS = ["bind_s", "dumps_s", "json_mb", "compile_s", "compile_stub_s", "dataflow_s", "to_svg_s", "svg_mb",
        "svg_to_png_s", "vega_to_png_s", "peak_rss_gb"]


def sweep(runs):
    print(f"{'variant':9} {'cells':>7} " + " ".join(f"{c:>14}" for c in COLS))
    for variant, n in runs:
        res = subprocess.run([sys.executable, __file__, "one", variant, str(n)], capture_output=True, text=True)
        if res.returncode:
            print(f"{variant:9} {n * n:>7} FAILED: {res.stderr.strip().splitlines()[-1:]}", flush=True)
            continue
        r = json.loads(res.stdout.strip().splitlines()[-1])
        print(f"{variant:9} {r['cells']:>7} " + " ".join(f"{r[c]:>14}" for c in COLS), flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["one"]:
        one(sys.argv[2], int(sys.argv[3]))
    else:
        sizes = [int(a) for a in sys.argv[1:]] or [200, 450]
        sweep([(v, n) for n in sizes for v in ("base", "nostroke", "noproj", "lean", "padded", "image")])
