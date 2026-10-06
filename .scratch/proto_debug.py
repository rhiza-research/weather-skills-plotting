# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["altair>=6.3", "vl-convert-python>=1.9", "numpy"]
# ///
"""Debug: does rect with lon/lat/lon2/lat2 render; does projection.fit work."""

import json

import vl_convert as vlc

W, S, E, N = 33.0, -5.5, 42.5, 6.0
rows = [
    {"lon": W + i, "lon2": W + i + 1, "lat": S + j, "lat2": S + j + 1, "v": i + j}
    for i in range(9)
    for j in range(11)
]
bbox = {
    "type": "Feature",
    "properties": {},
    "geometry": {"type": "Polygon", "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]},
}

variants = {
    "rect_lonlat": {
        "mark": "rect",
        "encoding": {
            "longitude": {"field": "lon", "type": "quantitative"},
            "latitude": {"field": "lat", "type": "quantitative"},
            "longitude2": {"field": "lon2"},
            "latitude2": {"field": "lat2"},
            "color": {"field": "v", "type": "quantitative"},
        },
    },
}

for name, body in variants.items():
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "width": 300,
        "height": 350,
        "data": {"values": rows},
        "projection": {"type": "equirectangular", "fit": bbox},
        **body,
    }
    vg = json.loads(vlc.vegalite_to_vega(spec)) if isinstance(vlc.vegalite_to_vega(spec), str) else vlc.vegalite_to_vega(spec)
    marks = vg.get("marks", [])
    print(name, json.dumps(marks[0]["encode"]["update"], indent=None)[:900])
    print("projections:", json.dumps(vg.get("projections"))[:600])
    open(f"dbg_{name}.png", "wb").write(vlc.vegalite_to_png(spec, scale=1))
