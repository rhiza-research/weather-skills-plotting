# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Why do the quiver's color (shading) and size (arrow) legends merge into one?"""

import copy
import json
import sys
from pathlib import Path

import vl_convert as vlc

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402

HERE = Path(__file__).parent
base = json.loads((HERE.parent / "examples" / "map_quiver_wind.json").read_text())
inputs = vlbind.open_inputs({"wind": HERE / "data/wind_10m.zarr"})


def legends(spec):
    bound, meta = vlbind.bind_all(spec, inputs)
    vlbind.apply_defaults(bound, meta, [])
    vg = vlc.vegalite_to_vega(bound, vl_version="6.4")
    vg = json.loads(vg) if isinstance(vg, str) else vg
    return [
        {k: lg.get(k) for k in ("fill", "size", "stroke", "shape", "type")}
        for lg in vg.get("legends", [])
    ]


def size_domain(s):
    s["layer"][3]["encoding"]["size"]["scale"]["domain"] = [0, 13]


def resolve_independent(s):
    s["resolve"] = {"legend": {"color": "independent", "size": "independent"}}


def no_size_legend_values(s):
    s["layer"][3]["encoding"]["size"]["legend"].pop("values")


for name, fn in {
    "as is": lambda s: None,
    "size domain differs": size_domain,
    "resolve legend independent": resolve_independent,
    "no size legend values": no_size_legend_values,
}.items():
    spec = copy.deepcopy(base)
    fn(spec)
    print(f"{name:28s} {legends(spec)}")
