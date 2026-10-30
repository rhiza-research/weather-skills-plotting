"""Every --help recipe draws on stand-in data with the flags its title names."""

import json

import numpy as np
import pytest
import xarray as xr
from skill_conftest import (
    load_skill,
    make_forecast,
    make_gridded,
    make_point_obs,
    run_skill,
    write_zarr,
)

from weather_skills_plotting.reference import _RECIPES

plot_mod = load_skill("plot", "plot")

# Around Nairobi (-1.29, 36.82), where the recipes put their points.
LATS = (-2.0, -1.0, 0.0, 1.0, 2.0)
LONS = (35.0, 36.0, 37.0, 38.0)
GRID = ["-i", "grid.zarr"]
TWO_GRIDS = ["-i", "grid.zarr", "-i", "grid.zarr"]
TWO_SERIES = ["-i", "series.zarr", "-i", "series.zarr"]
MSLP = ["--layer", "contour:msl.zarr=MSLP"]
CENTRES = ["--layer", "scatter:highs.zarr=HIGHS", "--layer", "scatter:lows.zarr=LOWS"]
TT = ["--theme-file", "tropical_tidbits"]
VERIFY = ["--obs", "obs.zarr", "--forecast", "fc1.zarr", "--forecast", "fc2.zarr"]
VERIFY += ["--verify", "v1.zarr", "--verify", "v2.zarr"]

# The input flags each recipe's title asks for, keyed by the start of the title; a new
# recipe needs an entry here.
ARGS = {
    "Title and font size": GRID,
    "Two-line title (subtitle, or <br> in text)": GRID,
    "Contour instead of heatmap": GRID,
    "MSLP chart:": ["--layer", "heatmap:anom.zarr", *MSLP, *CENTRES],
    "Tropical Tidbits MSLP & precip ": [
        *TT,
        "--layer",
        "heatmap:grid.zarr=PRECIP",
        *MSLP,
        *CENTRES,
    ],
    "Tropical Tidbits MSLP & 10 m wind": [*TT, "--layer", "quiver:uv.zarr=WIND", *MSLP],
    "Tropical Tidbits total precip": [*TT, "-i", "total.zarr"],
    "Tropical Tidbits MSLP & precipitable water": [*TT, "--layer", "heatmap:pwat.zarr=PWAT", *MSLP],
    "Tropical Tidbits 500 mb height": [*TT, "--layer", "contour:z500.zarr=Z500", *MSLP],
    "Color limits and colorscale (continuous)": GRID,
    "Class palette": GRID,
    "Your own class palette (6 classes on 7 edges, plus a color above 100)": GRID,
    "Latest time only": ["-i", "days.zarr"],
    "First two forecast weeks as two panels": ["-i", "weeks.zarr"],
    "First 4 ensemble members, 2x2": ["-i", "members.zarr"],
    "One day of a station file drawn over a map (--layer heatmap:… --layer scatter:…)": [
        "--layer",
        "heatmap:grid.zarr",
        "--layer",
        "scatter:stations.zarr",
    ],
    "Colorbar label and ticks": GRID,
    "Grid shape and gaps (map gaps are fractions of a panel)": GRID * 5,
    'Arrange -i maps xy, x2y2, … by cell, row by row; "" leaves a cell empty': GRID * 5,
    "Colorbar under the maps (placed for you; leave x / y unset)": GRID,
    "Rename panel 2, the panel of traces on x2 / y2": TWO_GRIDS,
    "Map window": GRID,
    "2x pixels in PNG/JPG": GRID,
    "Base-map layers": GRID,
    "Separate colorbars for side-by-side maps (same quantity shares one by default)": TWO_GRIDS,
    "The variable to draw from a multi-variable file": ["-i", "grid.zarr", "-i", "multi.zarr"],
    "Boundary outline": GRID,
    "City markers (a plain Plotly trace; repeats on every map panel)": GRID,
    "Box outline on the map": GRID,
    "Wind quiver map (or --layer quiver:PATH), an arrow every 3rd cell": ["-i", "uv.zarr"],
    "Wind rose at a point": ["-i", "uv_times.zarr"],
    "Area-mean time series of a grid": ["-i", "series.zarr"],
    "One variable against another (e.g. a merge --by-year output)": ["-i", "years.zarr"],
    "Ensemble spaghetti with a 10–90% band": ["-i", "ens_series.zarr"],
    "Band parts styled apart": ["-i", "ens_series.zarr"],
    "Bars instead of lines; stacked": ["-i", "series.zarr"],
    "Second series on a right-hand axis": TWO_SERIES,
    "One stacked panel per series": TWO_SERIES,
    "Text label on panel 1": ["-i", "series.zarr"],
    "Shaded period on a time axis": ["-i", "series.zarr"],
    "Verification grid (--obs": VERIFY,
    "Verification grid: rename the obs panel; fix the verify row range (coloraxis2)": VERIFY,
    "Mediogram (--mediogram": ["--mediogram", "-i", "fc.zarr", "-i", "mclimate.zarr"],
    "Animation (--animate -i GRID -o out.html): slower frames, first 12 steps": [
        "--animate",
        "-i",
        "weeks.zarr",
    ],
}


def _vary(ds, base=10.0, spread=5.0, seed=0):
    """Give every data variable values that differ from cell to cell."""
    rng = np.random.default_rng(seed)
    for var in ds.data_vars:
        ds[var].values = base + spread * rng.random(ds[var].shape)
    return ds


def _grid(name="precip", units="mm day-1", n_time=1, **attrs):
    ds = _vary(make_gridded(n_time=n_time, lats=LATS, lons=LONS, name=name))
    ds[name].attrs.update(units=units, **attrs)
    return ds


def _points(ds, lats, lons):
    ds = ds.assign_coords(latitude=("point_id", lats), longitude=("point_id", lons))
    ds["latitude"].attrs.update(standard_name="latitude", units="degrees_north")
    ds["longitude"].attrs.update(standard_name="longitude", units="degrees_east")
    return ds


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("recipes")
    write_zarr(_grid(), d / "grid.zarr")
    days = _vary(make_gridded(n_time=4, lats=LATS, lons=LONS, start="2026-10-01"))
    write_zarr(days, d / "days.zarr")
    write_zarr(_vary(make_forecast(n_step=3, lats=LATS, lons=LONS)), d / "weeks.zarr")
    write_zarr(_vary(make_forecast(n_step=2, lats=LATS, lons=LONS, members=4)), d / "members.zarr")
    stations = _vary(make_point_obs(n_time=3, n_points=3, start="2026-10-01"))
    write_zarr(_points(stations, [-1.3, 0.1, 1.5], [36.8, 35.3, 37.6]), d / "stations.zarr")

    msl = _grid("msl", "hPa", standard_name="air_pressure_at_mean_sea_level")
    msl["msl"] += 1000
    write_zarr(msl, d / "msl.zarr")
    write_zarr(_grid("msl_anom", "hPa"), d / "anom.zarr")
    for kind, lats in (("high", [1.5, -1.5]), ("low", [0.5, -0.5])):
        centres = make_point_obs(n_time=1, n_points=2, name="msl", fill=1010.0).isel(time=0)
        centres["msl"].attrs = {"units": "hPa", "extremum_kind": kind}
        write_zarr(_points(centres, lats, [35.5, 37.5]), d / f"{kind}s.zarr")

    uv = _grid("u10", "m s-1", n_time=4, standard_name="eastward_wind")
    uv["v10"] = _grid("v10", "m s-1", n_time=4, standard_name="northward_wind")["v10"]
    uv["v10"] -= 12
    write_zarr(uv.isel(time=[0]), d / "uv.zarr")
    write_zarr(uv, d / "uv_times.zarr")
    write_zarr(_grid(units="mm", aggregation_period="2 day"), d / "total.zarr")
    write_zarr(_grid("tcwv", "mm"), d / "pwat.zarr")
    write_zarr(_grid("z", "dam", standard_name="geopotential_height"), d / "z500.zarr")
    multi = _grid()
    multi["t2m"] = _grid("t2m", "K", standard_name="air_temperature")["t2m"] + 285
    write_zarr(multi, d / "multi.zarr")

    # Area means: one line along time, and an ensemble along step.
    month = _vary(make_gridded(n_time=20, lats=LATS, lons=LONS, start="2026-09-25"))
    write_zarr(month.mean(["latitude", "longitude"], keep_attrs=True), d / "series.zarr")
    ens = _vary(make_forecast(n_step=8, lats=LATS, lons=LONS, members=5))
    write_zarr(ens.mean(["latitude", "longitude"], keep_attrs=True), d / "ens_series.zarr")
    years = np.arange(2000, 2026)
    by_year = _vary(xr.Dataset({"dmi": ("year", years * 0.0), "precip": ("year", years * 0.0)}))
    by_year = by_year.assign_coords(year=years)
    by_year["dmi"].attrs["units"] = "K"
    by_year["precip"].attrs["units"] = "mm"
    write_zarr(by_year, d / "years.zarr")

    # Verification grid: obs and two weeks of forecasts, each with its hits map.
    for name, fill in (("obs", 10.0), ("fc1", 6.0), ("fc2", 7.0)):
        week = _grid(units="mm", aggregation_period="7 day")
        week["precip"] += fill
        write_zarr(week, d / f"{name}.zarr")
    for k in (1, 2):
        hits = make_gridded(n_time=1, lats=LATS, lons=LONS, name="event_hit")
        hits["event_hit"].values[:] = np.resize([-1.0, 0.0, 1.0], hits["event_hit"].shape)
        hits["event_hit"].attrs = {}
        hits.attrs.update(verify_metric="hits", verify_score_summary="score 0.5")
        write_zarr(hits, d / f"v{k}.zarr")

    write_zarr(_vary(make_forecast(n_step=6, lats=LATS, lons=LONS, members=5)), d / "fc.zarr")
    mclimate = make_forecast(n_step=6, lats=LATS, lons=LONS, members=9, init="2025-10-12")
    write_zarr(_vary(mclimate, base=5.0), d / "mclimate.zarr")

    ring = [[35.0, 2.0], [38.0, 2.0], [38.0, -2.0], [35.0, -2.0], [35.0, 2.0]]
    geometry = {"type": "Polygon", "coordinates": [ring]}
    feature = {"type": "Feature", "properties": {"name": "Kenya"}, "geometry": geometry}
    (d / "kenya.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]})
    )
    return d


def _args(title):
    return [args for start, args in ARGS.items() if title.startswith(start)]


def test_every_recipe_has_its_inputs():
    assert [title for title, _ in _RECIPES if len(_args(title)) != 1] == []
    assert len(ARGS) == len(_RECIPES)


@pytest.mark.parametrize("title, spec", _RECIPES, ids=[t[:40] for t, _ in _RECIPES])
def test_recipe_draws(title, spec, data_dir, tmp_path, monkeypatch):
    # The outline recipe names kenya.geojson relative to where the command runs.
    monkeypatch.chdir(data_dir)
    out = tmp_path / "out.html"
    run_skill(plot_mod.plot, *_args(title)[0], "--spec", spec, "-o", str(out))
    assert out.is_file()
