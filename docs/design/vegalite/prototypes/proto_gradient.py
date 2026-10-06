# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Classed grid as one rect per latitude row, filled with a hard-stop linear gradient.

Vega passes a gradient object from a data field straight through to an SVG
<linearGradient>, so each row of cells becomes one <rect> whose gradient jumps
colour at every class change along the row (two stops per run of equal class).
Mark items scale with rows, SVG size with class runs.

    uv run --script proto_gradient.py [N ...]          # smooth field
    uv run --script proto_gradient.py --noisy [N ...]  # lognormal(0, 0.5) noise on top
"""

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from proto_stages import grid  # noqa: E402

OUT = Path(__file__).parent / "out"


def gradient_rows(da, domain, colors):
    """One row per latitude: outer lon edges, the row's lat edges and a horizontal hard-stop gradient."""
    lat_lo, lat_hi = vlbind._cell_edges(da["latitude"].values)
    lon_lo, lon_hi = vlbind._cell_edges(da["longitude"].values)
    west, east = lon_lo.min(), lon_hi.max()
    cls = np.searchsorted(np.asarray(domain, dtype=float), da.values, side="right")
    rows = []
    for r, c in enumerate(cls):
        starts = np.r_[0, np.nonzero(c[1:] != c[:-1])[0] + 1]
        ends = np.r_[starts[1:], len(c)]
        stops = []
        for s, e in zip(starts, ends, strict=True):
            color = colors[c[s]]
            stops.append({"offset": round((lon_lo[s] - west) / (east - west), 6), "color": color})
            stops.append(
                {"offset": round((lon_hi[e - 1] - west) / (east - west), 6), "color": color}
            )
        rows.append(
            {
                "lon": west,
                "lon2": east,
                "lat": lat_lo[r],
                "lat2": lat_hi[r],
                "g": {"gradient": "linear", "x1": 0, "y1": 0, "x2": 1, "y2": 0, "stops": stops},
            }
        )
    return rows, [[west, lat_lo.min()], [east, lat_hi.max()]]


def run(n, noisy):
    import vl_convert as vlc

    da = grid(n)["tp"]
    if noisy:
        da.values[:] = np.clip(
            da.values * np.random.default_rng(0).lognormal(0, 0.5, da.shape), 0, None
        )
    _, domain, colors = vlbind.palette_scale("default_precip", da)
    t0 = time.perf_counter()
    rows, corners = gradient_rows(da, domain, colors)
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "width": 600,
        "height": 600,
        "projection": {
            "type": "equirectangular",
            "fit": {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "MultiPoint", "coordinates": corners},
            },
        },
        "data": {"values": rows},
        "mark": {"type": "rect", "aria": False},
        "encoding": {
            "longitude": {"field": "lon", "type": "quantitative"},
            "latitude": {"field": "lat", "type": "quantitative"},
            "longitude2": {"field": "lon2"},
            "latitude2": {"field": "lat2"},
            "fill": {"field": "g", "type": "nominal", "scale": None},
        },
    }
    t1 = time.perf_counter()
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    png = vlc.vega_to_png(vega, scale=2)
    t2 = time.perf_counter()
    svg = vlc.vega_to_svg(vega)
    (OUT / f"gradient_{'noisy_' if noisy else ''}{n}.png").write_bytes(png)
    stops = sum(len(r["g"]["stops"]) for r in rows)
    print(
        f"cells={n * n:>7} rows={len(rows)} stops={stops:>7} json={len(json.dumps(spec)) / 1e6:5.1f}MB "
        f"svg={len(svg) / 1e6:5.1f}MB png={len(png) / 1e6:.2f}MB prep={t1 - t0:.2f}s render={t2 - t1:.2f}s "
        f"peak={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.2f}GB",
        flush=True,
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    noisy = "--noisy" in args
    for n in [int(a) for a in args if a != "--noisy"] or [200, 450, 630]:
        run(n, noisy)
