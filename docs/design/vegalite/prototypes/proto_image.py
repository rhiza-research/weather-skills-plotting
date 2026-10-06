# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""The heatmap-with-stations recipe with the grid drawn as one image instead of one rect per cell.

The rect layer's rows are replaced by a single row: the grid's outer cell edges
plus a PNG data URL, coloured in Python with the layer's own threshold scale.
An ``image`` mark with longitude/latitude(2) puts it under the same projection
as the base map. The rect layer stays with no rows so its colour scale still
drives the legend.

    uv run --script proto_image.py      # writes out/image_*.png and out/image_bound_spec.json
"""

import base64
import copy
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
SPEC = json.loads((HERE.parent / "examples" / "map_heatmap_stations.json").read_text())
INPUTS = {
    "obs": HERE / "data" / "obs_chirps_week.zarr",
    "stations": HERE / "data" / "stations_week.zarr",
}


def raster_row(da, scale):
    """One row: outer cell edges and the grid coloured by a threshold scale, north up, one pixel per cell."""
    da = da.squeeze(drop=True)
    lat_lo, lat_hi = vlbind._cell_edges(da["latitude"].values)
    lon_lo, lon_hi = vlbind._cell_edges(da["longitude"].values)
    da = da.sortby("latitude", ascending=False).sortby("longitude")
    rgb = np.array(
        [[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in scale["range"]], dtype=np.uint8
    )
    idx = np.searchsorted(np.asarray(scale["domain"], dtype=float), da.values, side="right")
    rgba = np.concatenate(
        [rgb[idx], np.where(np.isnan(da.values), 0, 255).astype(np.uint8)[..., None]], axis=-1
    )
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return {
        "lon": float(lon_lo.min()),
        "lon2": float(lon_hi.max()),
        "lat": float(lat_hi.max()),
        "lat2": float(lat_lo.min()),
        "url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
    }


def to_image(spec, inputs):
    """Swap the bound rect layer for an image layer (what the skill would do after bind + defaults)."""
    rect = spec["layer"][0]
    image = {
        "data": {"name": "obs_image"},
        "mark": {"type": "image", "aspect": False, "smooth": False, "clip": True},
        "encoding": {
            "longitude": {"field": "lon", "type": "quantitative"},
            "latitude": {"field": "lat", "type": "quantitative"},
            "longitude2": {"field": "lon2"},
            "latitude2": {"field": "lat2"},
            "url": {"field": "url", "type": "nominal"},
        },
    }
    spec["datasets"]["obs_image"] = [
        raster_row(inputs["obs"]["precip"], rect["encoding"]["color"]["scale"])
    ]
    spec["datasets"]["obs"] = []
    spec["layer"].insert(0, image)


def main():
    import vl_convert as vlc

    inputs = vlbind.open_inputs(INPUTS)
    for mode in ("rect", "image"):
        t0 = time.perf_counter()
        notes = []
        spec, meta = vlbind.bind_all(copy.deepcopy(SPEC), inputs, None, notes)
        classed = vlbind.apply_defaults(spec, meta, notes)
        if mode == "image":
            to_image(spec, inputs)
            shown = copy.deepcopy(spec)
            for k in ("lakes", "coast", "borders"):
                shown["datasets"][k] = f"<{len(spec['datasets'][k])} Natural Earth features>"
            shown["datasets"]["stations"] = spec["datasets"]["stations"][:2] + ["..."]
            url = shown["datasets"]["obs_image"][0]["url"]
            shown["datasets"]["obs_image"][0]["url"] = url[:40] + f"... ({len(url) // 1000} KB)"
            (OUT / "image_bound_spec.json").write_text(json.dumps(shown, indent=2))
        vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
        vlbind.seal_cells(vega)
        vlbind.classed_legends(vega, classed)
        png = vlc.vega_to_png(vega, scale=2)
        (OUT / f"image_{mode}.png").write_bytes(png)
        print(
            f"{mode:5} {time.perf_counter() - t0:.2f}s  spec {len(json.dumps(spec)) / 1e6:.2f} MB"
        )


if __name__ == "__main__":
    main()
