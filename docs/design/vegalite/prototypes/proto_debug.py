# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["altair>=6.3", "vl-convert-python>=1.9", "numpy"]
# ///
"""Debug: does a geo-projected rect render, and does projection.fit zoom a layered map."""

import json
from pathlib import Path

import vl_convert as vlc

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
COUNTRIES = json.loads((Path(__file__).parent / "data" / "countries_110m.geojson").read_text())

W, S, E, N = 33.0, -5.5, 42.5, 6.0
rows = [
    {"lon": W + i, "lon2": W + i + 1, "lat": S + j, "lat2": S + j + 1, "v": i + j}
    for i in range(10)
    for j in range(12)
]
bbox = {
    "type": "Feature",
    "properties": {},
    "geometry": {"type": "Polygon", "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]},
}
RECT = {
    "data": {"values": rows},
    "mark": "rect",
    "encoding": {
        "longitude": {"field": "lon", "type": "quantitative"},
        "latitude": {"field": "lat", "type": "quantitative"},
        "longitude2": {"field": "lon2"},
        "latitude2": {"field": "lat2"},
        "color": {"field": "v", "type": "quantitative"},
    },
}
OUTLINE = {
    "data": {"values": COUNTRIES["features"]},
    "mark": {"type": "geoshape", "filled": False, "stroke": "black", "clip": True},
}

bbox_cw = {
    "type": "Feature",
    "properties": {},
    "geometry": {"type": "Polygon", "coordinates": [[[W, S], [W, N], [E, N], [E, S], [W, S]]]},
}
bbox_pts = {
    "type": "Feature",
    "properties": {},
    "geometry": {"type": "MultiPoint", "coordinates": [[W, S], [E, N]]},
}

variants = {
    "rect_only": {**RECT, "projection": {"type": "equirectangular"}},
    "layer_fit_cw": {
        "projection": {"type": "equirectangular", "fit": bbox_cw},
        "layer": [RECT, OUTLINE],
    },
    "layer_fit_pts": {
        "projection": {"type": "equirectangular", "fit": bbox_pts},
        "layer": [RECT, OUTLINE],
    },
    "rect_fit": {**RECT, "projection": {"type": "equirectangular", "fit": bbox}},
    "layer_fit_top": {
        "projection": {"type": "equirectangular", "fit": bbox},
        "layer": [RECT, OUTLINE],
    },
    "layer_fit_each": {
        "layer": [
            {**RECT, "projection": {"type": "equirectangular", "fit": bbox}},
            {**OUTLINE, "projection": {"type": "equirectangular", "fit": bbox}},
        ]
    },
    "layer_scale_center": {
        "projection": {
            "type": "equirectangular",
            "center": [(W + E) / 2, (S + N) / 2],
            "scale": 1500,
        },
        "layer": [RECT, OUTLINE],
    },
}

for name, body in variants.items():
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "width": 300,
        "height": 360,
        **body,
    }
    vg = vlc.vegalite_to_vega(spec)
    vg = json.loads(vg) if isinstance(vg, str) else vg
    print(name, "projections:", json.dumps(vg.get("projections"))[:300])
    (OUT / f"dbg_{name}.png").write_bytes(vlc.vegalite_to_png(spec, scale=1))
