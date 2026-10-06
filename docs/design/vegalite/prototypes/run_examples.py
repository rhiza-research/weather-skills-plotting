# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3",
#   "vl-convert-python>=1.9",
#   "numpy",
#   "pandas",
#   "xarray",
#   "zarr>=3",
#   "shapely>=2.1",
#   "contourpy>=1.3",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Render every ``../examples/*.json`` spec against the synthetic Zarrs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402

HERE = Path(__file__).parent
DATA = HERE / "data"
EXAMPLES = HERE.parent / "examples"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

# The ``-i NAME=PATH`` flags each example would be run with.
INPUTS = {
    "map_heatmap_stations": {"obs": "obs_chirps_week", "stations": "stations_week"},
    "map_forecast_leads_facet": {"fcst": "fcst_weekly_mean"},
    "map_anomaly_diverging": {"anom": "fcst_weekly_anom"},
    "map_side_by_side_grids": {"obs": "obs_chirps_week", "fcst": "fcst_weekly_mean"},
    "map_quiver_wind": {"wind": "wind_10m"},
    "timeseries_ensemble_spaghetti": {"ens": "ens_point_t2m"},
    "timeseries_multi_panel": {"ens": "ens_point_t2m"},
    "bar_model_comparison": {"scores": "scores"},
    "box_mediogram": {"ens": "ens_point_t2m"},
    "windrose": {"wind": "wind_10m"},
    "map_contours": {"fcst": "fcst_weekly_mean"},
}

names = sys.argv[1:] or sorted(p.stem for p in EXAMPLES.glob("*.json"))
failed = 0
for name in names:
    spec = json.loads((EXAMPLES / f"{name}.json").read_text())
    inputs = vlbind.open_inputs({k: DATA / f"{v}.zarr" for k, v in INPUTS.get(name, {}).items()})
    try:
        stats = vlbind.render(spec, inputs, OUT / f"{name}.png")
        notes = stats.pop("defaults")
        print(f"ok   {name}: {stats}")
        for note in notes:
            print(f"       default {note}")
    except Exception as exc:  # noqa: BLE001
        failed += 1
        print(f"FAIL {name}: {type(exc).__name__}: {str(exc)[:1500]}")
sys.exit(1 if failed else 0)
