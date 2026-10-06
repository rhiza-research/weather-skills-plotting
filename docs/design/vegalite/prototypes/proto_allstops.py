# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Per-cell rect heatmap with the render-cost fixes stacked one at a time, one subprocess per step.

    uv run --script proto_allstops.py [N]        # default N=630 (396,900 cells)
    uv run --script proto_allstops.py one STEP N

Steps are cumulative:
  today   bind -> compile with rows inline -> seal_cells stroke -> vega_to_png
  aria    + "aria": false on the rect mark (no per-cell aria-label / role attributes)
  splice  + compile with 3-row datasets, then put the rows into the compiled Vega
  crisp   + no stroke; shape-rendering="crispEdges" on the rect group (svg -> png)
  lean    + only lon/lat/value shipped; cell edges computed in Vega
  xy      + plain x/y scales instead of a projection
  round   + values rounded to 4 significant digits, coordinates to 6 decimals
  scale1  + scale 1 output (half the pixels each way) instead of 2
"""

import json
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from proto_stages import grid  # noqa: E402

OUT = Path(__file__).parent / "out"
STEPS = ["today", "aria", "splice", "crisp", "lean", "xy", "round", "scale1"]


def build(on, n):
    half = 10 / (n - 1)
    lean = "lean" in on
    fields = (
        {"lon": "longitude", "lat": "latitude", "tp": "tp"}
        if lean
        else {
            "lon": "longitude.lo",
            "lon2": "longitude.hi",
            "lat": "latitude.lo",
            "lat2": "latitude.hi",
            "tp": "tp",
        }
    )
    pos = {"x": "longitude", "y": "latitude"} if "xy" not in on else {"x": "x", "y": "y"}
    enc = {
        "longitude" if "xy" not in on else "x": {"field": "lon", "type": "quantitative"},
        "latitude" if "xy" not in on else "y": {"field": "lat", "type": "quantitative"},
        pos["x"] + "2": {"field": "lon2"},
        pos["y"] + "2": {"field": "lat2"},
        "color": {"field": "tp", "type": "quantitative", "scale": {"scheme": "default_precip"}},
    }
    if "xy" in on:
        for ch in ("x", "y"):
            enc[ch]["scale"] = {"zero": False, "nice": False}
            enc[ch]["axis"] = None
    spec = {
        "width": 600,
        "height": 600,
        "datasets": {"g": {"zarr": "g", "fields": fields}},
        "data": {"name": "g"},
        "mark": {"type": "rect", "aria": False} if "aria" in on else "rect",
        "encoding": enc,
    }
    if "xy" not in on:
        spec["projection"] = {"type": "equirectangular"}
    if lean:
        spec["transform"] = [
            {"calculate": f"datum.lon + {half}", "as": "lon2"},
            {"calculate": f"datum.lat + {half}", "as": "lat2"},
            {"calculate": f"datum.lon - {half}", "as": "lon"},
            {"calculate": f"datum.lat - {half}", "as": "lat"},
        ]
    if "crisp" in on:
        spec["usermeta"] = {"seal_cells": False}
    return spec


def one(step, n):
    import vl_convert as vlc

    on = set(STEPS[: STEPS.index(step) + 1])
    vlc.vegalite_to_png(
        {"mark": "point", "data": {"values": [{"a": 1}]}, "encoding": {"x": {"field": "a"}}}
    )
    ds = grid(n)
    t0 = time.perf_counter()
    spec_in = build(on, n)
    notes = []
    spec, meta = vlbind.bind_all(spec_in, {"g": ds}, None, notes)
    classed = vlbind.apply_defaults(spec, meta, notes)
    spec["$schema"] = "https://vega.github.io/schema/vega-lite/v6.json"
    if "round" in on:
        for row in spec["datasets"]["g"]:
            for k, v in row.items():
                row[k] = float(f"{v:.4g}") if k == "tp" else round(v, 6)
    if "splice" in on:
        rows = spec.pop("datasets")
        spec["datasets"] = {k: v[:3] for k, v in rows.items()}
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    if "splice" in on:
        for d in vega["data"]:
            if d["name"] in rows:
                d["values"] = rows[d["name"]]
    if "crisp" not in on:
        vlbind.seal_cells(vega)
    vlbind.classed_legends(vega, classed)
    t1 = time.perf_counter()
    scale = 1 if "scale1" in on else 2
    if "crisp" in on:
        svg = vlc.vega_to_svg(vega)
        svg = svg.replace(
            'class="mark-rect role-mark',
            'shape-rendering="crispEdges" class="mark-rect role-mark',
            1,
        )
        png = vlc.svg_to_png(svg, scale=scale)
    else:
        png = vlc.vega_to_png(vega, scale=scale)
    t2 = time.perf_counter()
    (OUT / f"allstops_{step}_{n}.png").write_bytes(png)
    print(
        json.dumps(
            {
                "step": step,
                "cells": n * n,
                "prep_s": round(t1 - t0, 2),
                "render_s": round(t2 - t1, 2),
                "total_s": round(t2 - t0, 2),
                "peak_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["one"]:
        one(sys.argv[2], int(sys.argv[3]))
    else:
        n = int(sys.argv[1]) if sys.argv[1:] else 630
        print(
            f"{'step':8} {'cells':>7} {'prep_s':>7} {'render_s':>9} {'total_s':>8} {'peak_gb':>8}",
            flush=True,
        )
        for step in STEPS:
            res = subprocess.run(
                [sys.executable, __file__, "one", step, str(n)], capture_output=True, text=True
            )
            if res.returncode:
                print(f"{step:8} FAILED: {res.stderr.strip().splitlines()[-1:]}", flush=True)
                continue
            r = json.loads(res.stdout.strip().splitlines()[-1])
            print(
                f"{step:8} {r['cells']:>7} {r['prep_s']:>7} {r['render_s']:>9} {r['total_s']:>8} {r['peak_rss_gb']:>8}",
                flush=True,
            )
