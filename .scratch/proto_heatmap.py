# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["altair>=6.3", "vl-convert-python>=1.9", "numpy"]
# ///
"""Prototype: gridded rect heatmap on equirectangular projection + outlines + stations."""

import json
import sys
import time

import altair as alt
import numpy as np
import vl_convert as vlc

print("altair", alt.__version__, "vl-convert", vlc.__version__, vlc.get_vegalite_versions()[-3:])

COUNTRIES = json.load(
    open("/Users/joshuaadkins/rhiza/weather-skills-core/src/weather_skills_core/data/countries.geojson")
)

N, W, S, E = 6.0, 33.0, -5.5, 42.5  # Kenya-ish


def grid_rows(res):
    lats = np.arange(S + res / 2, N, res)
    lons = np.arange(W + res / 2, E, res)
    lon2d, lat2d = np.meshgrid(lons, lats)
    val = 40 + 35 * np.sin(lon2d / 1.3) * np.cos(lat2d / 1.7)
    rows = [
        {
            "lon": float(lo - res / 2),
            "lon2": float(lo + res / 2),
            "lat": float(la - res / 2),
            "lat2": float(la + res / 2),
            "tp": float(v),
        }
        for lo, la, v in zip(lon2d.ravel(), lat2d.ravel(), val.ravel(), strict=True)
    ]
    return rows


bounds = [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200]
colors = ["#ffffff", "#ffffff", "#f6e8c3", "#e8d4a0", "#c8ffbe", "#78f573", "#1eb41e",
          "#50a5f5", "#1e6eeb", "#a08cff", "#7060dc", "#fffaaa", "#ffa000", "#ff1400", "#a50000"]
# threshold: len(range) == len(domain)+1 ; first = under (<0), last = over (>200)


def spec_for(rows, stations):
    bbox_feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]},
    }
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "width": 500,
        "height": 600,
        "title": "Prototype precip",
        "projection": {"type": "equirectangular", "fit": bbox_feature},
        "datasets": {
            "fcst": rows,
            "countries": COUNTRIES["features"],
            "stations": stations,
        },
        "layer": [
            {
                "data": {"name": "fcst"},
                "mark": {"type": "rect", "clip": True},
                "encoding": {
                    "longitude": {"field": "lon", "type": "quantitative"},
                    "latitude": {"field": "lat", "type": "quantitative"},
                    "longitude2": {"field": "lon2"},
                    "latitude2": {"field": "lat2"},
                    "color": {
                        "field": "tp",
                        "type": "quantitative",
                        "scale": {"type": "threshold", "domain": bounds, "range": colors},
                        "title": "Total precipitation [mm]",
                    },
                },
            },
            {
                "data": {"name": "countries"},
                "mark": {"type": "geoshape", "filled": False, "stroke": "black", "strokeWidth": 0.8, "clip": True},
            },
            {
                "data": {"name": "stations"},
                "mark": {"type": "circle", "size": 80, "stroke": "black", "strokeWidth": 0.6, "opacity": 1},
                "encoding": {
                    "longitude": {"field": "lon", "type": "quantitative"},
                    "latitude": {"field": "lat", "type": "quantitative"},
                    "color": {"field": "tp", "type": "quantitative"},
                },
            },
        ],
    }


rng = np.random.default_rng(0)
stations = [
    {"lon": float(rng.uniform(34, 41)), "lat": float(rng.uniform(-4, 4)), "tp": float(rng.uniform(0, 120))}
    for _ in range(40)
]

for res in [float(r) for r in sys.argv[1:]] or [0.5, 0.25, 0.1, 0.05]:
    rows = grid_rows(res)
    spec = spec_for(rows, stations)
    t0 = time.time()
    chart = alt.Chart.from_dict(spec)
    t1 = time.time()
    chart.save(f"heat_{res}.png", scale_factor=2)
    t2 = time.time()
    print(f"res={res} cells={len(rows)} type={type(chart).__name__} from_dict={t1 - t0:.2f}s save={t2 - t1:.2f}s")
