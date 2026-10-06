# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "psutil",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""How many grid cells can one rect heatmap take? Bind time, JSON size, render time, RSS."""

import sys
from pathlib import Path

import numpy as np
import psutil
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402

OUT = Path(__file__).parent / "out"


def grid(n):
    lat = np.linspace(-10, 10, n)
    lon = np.linspace(30, 50, n)
    lo, la = np.meshgrid(lon, lat)
    v = 50 + 45 * np.sin(lo * 1.3) * np.cos(la * 0.9)
    return xr.Dataset(
        {"tp": (("latitude", "longitude"), v, {"units": "mm", "aggregation_period": "7D"})},
        coords={"latitude": lat, "longitude": lon},
    )


spec = {
    "width": 600,
    "height": 600,
    "projection": {"type": "equirectangular", "fit": {"$bbox": [10, 30, -10, 50]}},
    "datasets": {
        "g": {
            "zarr": "g",
            "fields": {
                "lon": "longitude.lo",
                "lon2": "longitude.hi",
                "lat": "latitude.lo",
                "lat2": "latitude.hi",
                "tp": "tp",
            },
        }
    },
    "data": {"name": "g"},
    "mark": {"type": "rect", "strokeWidth": 0.5},
    "encoding": {
        "longitude": {"field": "lon", "type": "quantitative"},
        "latitude": {"field": "lat", "type": "quantitative"},
        "longitude2": {"field": "lon2"},
        "latitude2": {"field": "lat2"},
        "color": {
            "field": "tp",
            "type": "quantitative",
            "scale": {"$palette": "default_precip", "data": "g.tp"},
        },
        "stroke": {
            "field": "tp",
            "type": "quantitative",
            "legend": None,
            "scale": {"$palette": "default_precip", "data": "g.tp"},
        },
    },
}
proc = psutil.Process()
for n in [int(a) for a in sys.argv[1:]] or [200, 320, 450, 630]:
    stats = vlbind.render(spec, {"g": grid(n)}, OUT / f"perf_{n}.png")
    print(f"cells={n * n:>8}  {stats}  rss={proc.memory_info().rss / 1e9:.2f} GB", flush=True)
