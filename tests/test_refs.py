"""@ references: what they select, and the guardrails that stop them computing."""

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from conftest import make_forecast, make_gridded
from weather_skills_plotting.refs import JOBS, METHODS, UPSTREAM, check_literals, resolve


@pytest.fixture
def inputs():
    grid = make_gridded(n_time=3)
    grid["precip"].values = np.arange(grid["precip"].size, dtype=float).reshape(
        grid["precip"].shape
    )
    grid["precip"].attrs["long_name"] = "Rainfall"
    return {"OBS": grid, "FC": make_forecast(n_number=2, n_step=3)}


def one(value, inputs, key="y"):
    trace = {key: value, "x": [0], "y": [0]} if key == "z" else {key: value}
    resolved, found = resolve({"data": [trace]}, inputs)
    return resolved["data"][0][key]


def test_every_method_has_a_job():
    assert set(METHODS.values()) <= set(JOBS)
    assert not set(METHODS) & set(UPSTREAM)


def test_selection_reshape_and_labels(inputs):
    assert one("@OBS.precip.isel(time=0, lat=0)", inputs).tolist() == [0, 1, 2, 3]
    assert one("@OBS.precip.sel(time='2026-01-02', lon=11.0)", inputs).tolist() == [13, 17, 21]
    assert one("@OBS.precip.sel(lat=2.4, lon=12.6, method='nearest').isel(time=-1)", inputs) == 31
    assert one("@OBS.precip.isel(time=slice(0, 2), lat=0, lon=0)", inputs).tolist() == [0, 12]
    assert one("@OBS.time", inputs) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert one("@OBS.time.dt.dayofyear", inputs).tolist() == [1, 2, 3]
    assert one("@OBS.time.dt.strftime('%d %b')", inputs) == ["01 Jan", "02 Jan", "03 Jan"]
    assert one("@OBS.precip.attrs.long_name", inputs) == "Rainfall"
    assert one("@OBS.lat", inputs).tolist() == [1, 2, 3]


def test_flat_lists_grid_cells_as_points(inputs):
    sel = "@OBS.precip.isel(time=0, lat=slice(0, 2), lon=slice(0, 2))"
    assert one(sel + ".flat()", inputs).tolist() == [0, 1, 4, 5]
    assert one(sel + ".flat('lon')", inputs).tolist() == [10, 11, 10, 11]
    assert one(sel + ".flat('lat')", inputs).tolist() == [1, 1, 2, 2]


def test_z_is_a_lat_by_lon_grid(inputs):
    z = one("@OBS.precip.isel(time=0).transpose('lon', 'lat')", inputs, key="z")
    assert z.shape == (3, 4)  # rows are latitudes, whatever order was asked for


def test_limits_only_on_scale_keys(inputs):
    resolved, _ = resolve(
        {
            "data": [{"zmax": "@OBS.precip.max()", "zmin": "@OBS.precip.min()"}],
            "layout": {"yaxis": {"range": [0, "@OBS.precip.quantile(0.5)"]}},
        },
        inputs,
    )
    assert resolved["data"][0]["zmax"] == 35.0 and resolved["layout"]["yaxis"]["range"][1] == 17.5
    with pytest.raises(UsageError, match="for a scale only"):
        one("@OBS.precip.max()", inputs)


@pytest.mark.parametrize(
    ("ref", "match"),
    [
        ("@OBS.precip * 25.4", "unit-convert"),
        ("@OBS.precip - OBS.precip", "difference"),
        ("@OBS.precip.mean('time')", "summarize-dim"),
        ("@OBS.precip.rolling(time=7)", "aggregate-temporal"),
        ("@OBS.precip.resample(time='1W')", "aggregate-temporal"),
        ("@OBS.precip.interp(lat=0)", "coarsen or downscale"),
        ("@OBS.precip.where(OBS.precip > 1)", "clip-region"),
        ("@OBS.precip.fillna(0)", "missing data stays missing"),
        ("@OBS.precip.diff('time')", "difference"),
        ("@OBS.precip.__class__", "not allowed"),
        ("@OBS.precip.values", "not allowed after a variable"),
        ("@OBS.precip.max(dim='time')", "whole array only"),
        ("@OBS.precip[0]", "Subscript is not allowed"),
        ("@OBS.precip.isel(time=len('ab'))", "arguments must be"),
        ("@open('x')", "Call is not allowed"),
        ("@NE.coastline_50m.x", "clip a Natural Earth layer first"),
        ("@NE.admin1_50m.clip(1, 2, 0, 3).x", "only at 10m"),
    ],
)
def test_forbidden_references(inputs, ref, match):
    with pytest.raises(UsageError, match=match):
        one(ref, inputs)


@pytest.mark.parametrize(
    ("ref", "match"),
    [
        ("@OBS.precip.isel(time=0)", r"has dims \['latitude', 'longitude'\]"),
        ("@OBS.precip.isel(step=0)", "no dim 'step'"),
        ("@OBS.prcp", "data variables: precip"),
        ("@FC.step", "lead times; run step-to-time"),
        ("@OBS.precip.sel(time='1999-01-01')", "OBS.precip"),
    ],
)
def test_errors_name_the_fix(inputs, ref, match):
    with pytest.raises(UsageError, match=match):
        one(ref, inputs)


def test_lead_days(inputs):
    assert one("@FC.step.dt.days", inputs).tolist() == [0, 1, 2]


def test_literal_values_are_capped():
    check_literals(
        {"data": [{"y": list(range(10))}], "layout": {"xaxis": {"tickvals": list(range(50))}}}
    )
    check_literals({"data": [{"colorscale": [[i / 20, "#000"] for i in range(21)]}]})
    with pytest.raises(UsageError, match=r"frames\[0\].data\[0\].z holds 12"):
        check_literals({"frames": [{"data": [{"z": [[1] * 6, [2] * 6]}]}]})


def test_at_at_is_a_literal_at(inputs):
    assert one("@@rhiza", inputs) == "@rhiza"


def test_size_one_dims_are_dropped(inputs):
    total = inputs["OBS"].isel(time=[0])
    z = one("@T.precip", {"T": total}, key="z")
    assert z.shape == (3, 4)


def test_meta_is_refused(inputs):
    with pytest.raises(UsageError, match="plot has no meta keys"):
        resolve({"data": [{"type": "heatmap", "meta": {"palette": "kmsa"}}]}, inputs)


def test_a_grid_needs_its_lon_lat_axes(inputs):
    with pytest.raises(UsageError, match="set x: '@OBS.lon' and y: '@OBS.lat'"):
        resolve({"data": [{"type": "heatmap", "z": "@OBS.precip.isel(time=0)"}]}, inputs)
    # A frame's trace takes x / y from the trace it updates.
    resolve({"frames": [{"data": [{"z": "@OBS.precip.isel(time=0)"}]}]}, inputs)


def test_geojson_lon_lat_name_its_x_y():
    from shapely.geometry import LineString

    from weather_skills_plotting.refs import GeoLines

    lines = {"K": GeoLines([LineString([(30, 1), (31, 2)])], "K")}
    assert one("@K.lon", lines).tolist()[:2] == [30, 31]
    assert one("@K.lat", lines).tolist()[:2] == [1, 2]
