# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Seams on fine grids: fractional overlap vs a 0.5 px stroke drawn from the color scale."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
full = json.loads((HERE.parent / "examples" / "map_side_by_side_grids.json").read_text())
inputs = vlbind.open_inputs(
    {"obs": HERE / "data/obs_chirps_week.zarr", "fcst": HERE / "data/fcst_weekly_mean.zarr"}
)


def chirps_only(mutate, name):
    spec = copy.deepcopy(full)
    panel = spec["hconcat"][0]
    spec = {"datasets": {k: spec["datasets"][k] for k in ("obs", "borders")}, **panel}
    mutate(spec)
    path = OUT / f"seam_{name}.png"
    print(name, vlbind.render(spec, inputs, path))
    im = Image.open(path).convert("RGB")
    w, h = im.size
    return im.crop((w // 4, h // 3, w // 4 + 200, h // 3 + 200)).resize((400, 400), Image.NEAREST)


def overlap(frac):
    def f(s):
        s["datasets"]["obs"]["cell_overlap"] = frac

    return f


def stroke_expr(s):
    s["layer"][0]["mark"]["stroke"] = {"expr": "scale('color', datum.precip)"}
    s["layer"][0]["mark"]["strokeWidth"] = 0.5


crops = [
    chirps_only(overlap(0.0), "overlap0"),
    chirps_only(overlap(0.02), "overlap2"),
    chirps_only(overlap(0.25), "overlap25"),
    chirps_only(stroke_expr, "stroke_expr"),
]
sheet = Image.new("RGB", (410 * len(crops), 400), "white")
for i, c in enumerate(crops):
    sheet.paste(c, (i * 410, 0))
sheet.save(OUT / "seam_sheet.png")
