# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Classed grid as one polygon per class instead of one rect per cell.

A threshold palette maps every cell to one of ~15 classes, so the figure only
has ~15 distinct regions. Merge cells of the same class (row runs, then a
coverage union) and draw each class as one geoshape. Cell edges stay exact and
any projection works; the cost scales with class-boundary length, not cells.

    uv run --script proto_dissolve.py [N ...]
    uv run --script proto_dissolve.py one MODE N    # MODE: rect | dissolve
"""

import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from proto_stages import grid, spec_for  # noqa: E402

OUT = Path(__file__).parent / "out"


def dissolve(da, domain):
    """One clockwise (Multi)Polygon feature per occupied class, with the class's lower bound as ``v``."""
    lat_lo, lat_hi = vlbind._cell_edges(da["latitude"].values)
    lon_lo, lon_hi = vlbind._cell_edges(da["longitude"].values)
    cls = np.searchsorted(np.asarray(domain, dtype=float), da.values, side="right")
    starts = np.ones(cls.shape, dtype=bool)
    starts[:, 1:] = cls[:, 1:] != cls[:, :-1]
    r, c0 = np.nonzero(starts)
    c1 = np.append(c0[1:], 0)
    c1[np.append(r[1:] != r[:-1], True)] = cls.shape[1]
    run_cls = cls[r, c0]
    boxes = shapely.box(lon_lo[c0], lat_lo[r], lon_hi[c1 - 1], lat_hi[r])
    feats = []
    for k in np.unique(run_cls):
        geom = shapely.coverage_union_all(boxes[run_cls == k])
        v = domain[k - 1] if k else domain[0] - 1
        feats.append(
            {"type": "Feature", "properties": {"v": v}, "geometry": shapely.geometry.mapping(geom)}
        )
    return vlbind._orient_for_d3(feats), len(boxes)


def one(mode, n):
    import vl_convert as vlc

    vlc.vegalite_to_png(
        {"mark": "point", "data": {"values": [{"a": 1}]}, "encoding": {"x": {"field": "a"}}}
    )
    ds = grid(n)
    t0 = time.perf_counter()
    notes = []
    spec, meta = vlbind.bind_all(spec_for("base", n), {"g": ds}, None, notes)
    classed = vlbind.apply_defaults(spec, meta, notes)
    spec["mark"] = {"type": "rect", "aria": False}
    extra = {}
    if mode == "dissolve":
        scale = spec["encoding"]["color"]["scale"]
        feats, runs = dissolve(ds["tp"], scale["domain"])
        extra = {"runs": runs, "features": len(feats)}
        spec["datasets"]["g"] = feats
        spec["mark"] = {"type": "geoshape", "aria": False}
        spec["encoding"] = {"color": {**spec["encoding"]["color"], "field": "properties.v"}}
        classed = {}
    t1 = time.perf_counter()
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    vlbind.seal_cells(vega)
    vlbind.classed_legends(vega, classed)
    svg = vlc.vega_to_svg(vega)
    t2 = time.perf_counter()
    png = vlc.vega_to_png(vega, scale=2)
    t3 = time.perf_counter()
    (OUT / f"dissolve_{mode}_{n}.png").write_bytes(png)
    print(
        json.dumps(
            {
                "mode": mode,
                "cells": n * n,
                **extra,
                "json_mb": round(len(json.dumps(spec)) / 1e6, 2),
                "svg_mb": round(len(svg) / 1e6, 2),
                "prep_s": round(t1 - t0, 2),
                "png_s": round(t3 - t2, 2),
                "peak_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    if sys.argv[1:2] == ["one"]:
        one(sys.argv[2], int(sys.argv[3]))
    else:
        for n in [int(a) for a in sys.argv[1:]] or [200, 450, 630]:
            for mode in ("rect", "dissolve"):
                res = subprocess.run(
                    [sys.executable, __file__, "one", mode, str(n)], capture_output=True, text=True
                )
                print(
                    res.stdout.strip().splitlines()[-1]
                    if res.returncode == 0
                    else res.stderr[-800:],
                    flush=True,
                )
