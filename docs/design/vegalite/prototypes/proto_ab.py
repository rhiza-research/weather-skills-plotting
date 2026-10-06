# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""A/B: cell seams, threshold legend styles, sharing one color scale across layers."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
base = json.loads((HERE.parent / "examples" / "map_heatmap_stations.json").read_text())
inputs = vlbind.open_inputs(
    {"obs": HERE / "data/obs_chirps_week.zarr", "stations": HERE / "data/stations_week.zarr"}
)
BOX = [1.5, 36.0, -1.5, 39.0]


def variant(fn, name):
    spec = copy.deepcopy(base)
    spec["width"], spec["height"] = 300, 300
    spec["title"] = name
    n, w, s, e = BOX
    spec["projection"]["fit"] = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "MultiPoint", "coordinates": [[w, s], [e, n]]},
    }
    fn(spec)
    path = OUT / f"ab_{name}.png"
    print(name, vlbind.render(spec, inputs, path, scale=1.5))
    return path


def seams_none(s):
    pass


def seams_stroke(s):
    enc = s["layer"][0]["encoding"]
    enc["stroke"] = {**copy.deepcopy(enc["color"]), "legend": None}
    s["layer"][0]["mark"]["strokeWidth"] = 0.4


def seams_overlap(s):
    s["layer"][0]["mark"]["stroke"] = None
    s["layer"][0]["mark"]["strokeWidth"] = 0
    s["layer"][0]["mark"]["strokeOpacity"] = 0
    s["datasets"]["obs"]["fields"] = {
        "lon": "longitude.lo",
        "lon2": "longitude.hi",
        "lat": "latitude.lo",
        "lat2": "latitude.hi",
        "precip": "precip",
    }
    s["layer"][0]["encoding"]["longitude2"] = {"field": "lon2"}
    s["transform"] = []
    for lyr in s["layer"][:1]:
        lyr["transform"] = [
            {"calculate": "datum.lon2 + 0.004", "as": "lon2p"},
            {"calculate": "datum.lat2 + 0.004", "as": "lat2p"},
        ]
        lyr["encoding"]["longitude2"] = {"field": "lon2p"}
        lyr["encoding"]["latitude2"] = {"field": "lat2p"}


def legend_symbol(s):
    s["layer"][0]["encoding"]["color"]["legend"] = {
        "type": "symbol",
        "symbolType": "square",
        "symbolSize": 200,
    }


def legend_bottom(s):
    s["layer"][0]["encoding"]["color"]["legend"] = {
        "orient": "bottom",
        "direction": "horizontal",
        "gradientLength": 300,
    }


def shared_resolve(s):
    s["resolve"] = {"scale": {"color": "shared"}}


paths = [
    variant(seams_none, "seams_none"),
    variant(seams_stroke, "seams_stroke"),
    variant(seams_overlap, "seams_overlap"),
    variant(legend_symbol, "legend_symbol"),
    variant(legend_bottom, "legend_bottom"),
    variant(shared_resolve, "shared_resolve"),
]
ims = [Image.open(p).convert("RGB") for p in paths]
cols = 4
w = max(i.width for i in ims)
h = max(i.height for i in ims)
sheet = Image.new("RGB", (w * cols, h * ((len(ims) + cols - 1) // cols)), "white")
for k, im in enumerate(ims):
    sheet.paste(im, ((k % cols) * w, (k // cols) * h))
sheet.save(OUT / "ab_sheet.png")
