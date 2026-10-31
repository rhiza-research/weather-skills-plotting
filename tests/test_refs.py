"""@ references: what they select, and the guardrails that stop them computing."""

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from conftest import make_forecast, make_gridded
from weather_skills_plotting.refs import JOBS, METHODS, UPSTREAM, resolve


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
        ("@OBS.precip.values", "neither .dt, .attrs nor a coordinate"),
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
        ("@OBS.precip.transpose('lat', 'lon')", r"dims \['time'\] are left"),
    ],
)
def test_errors_name_the_fix(inputs, ref, match):
    with pytest.raises(UsageError, match=match):
        one(ref, inputs)


def test_lead_days(inputs):
    assert one("@FC.step.dt.days", inputs).tolist() == [0, 1, 2]


def test_at_at_is_a_literal_at(inputs):
    assert one("@@rhiza", inputs) == "@rhiza"


def test_size_one_dims_are_dropped(inputs):
    total = inputs["OBS"].isel(time=[0])
    z = one("@T.precip", {"T": total}, key="z")
    assert z.shape == (3, 4)


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


def test_dropna_and_the_coords_of_what_is_left(inputs):
    obs = inputs["OBS"].copy(deep=True)
    obs["precip"][0, 0, 1:] = np.nan
    row = "@OBS.precip.isel(time=0, lat=0).dropna('lon')"
    assert one(row, {"OBS": obs}).tolist() == [0]
    assert one(row + ".lon", {"OBS": obs}).tolist() == [10]


def test_x_and_y_must_pair_up(inputs):
    with pytest.raises(UsageError, match="x has 3 values and y has 2"):
        resolve({"data": [{"x": "@OBS.time", "y": "@FC.tp.isel(step=0, lat=0, lon=0)"}]}, inputs)
    shifted = {
        "A": inputs["OBS"],
        "B": inputs["OBS"].assign_coords(time=inputs["OBS"].time + np.timedelta64(1, "D")),
    }
    with pytest.raises(UsageError, match="run along different time values"):
        resolve(
            {"data": [{"x": "@A.precip.isel(lat=0, lon=0)", "y": "@B.precip.isel(lat=0, lon=0)"}]},
            shifted,
        )


def test_the_innermost_refused_method_is_named(inputs):
    with pytest.raises(UsageError, match="rolling.*aggregate-temporal"):
        one("@OBS.precip.rolling(time=7).mean()", inputs)


def test_one_colorbar_in_two_units_warns(inputs, capsys):
    rate, total = inputs["OBS"], inputs["OBS"].copy()
    total["precip"].attrs["units"] = "mm"
    trace = {
        "x": "@{0}.lon",
        "y": "@{0}.lat",
        "z": "@{0}.precip.isel(time=0)",
        "coloraxis": "coloraxis",
    }
    spec = {
        "data": [
            {k: v.format("R") for k, v in trace.items()},
            {k: v.format("T") for k, v in trace.items()},
        ]
    }
    resolve(spec, {"R": rate, "T": total})
    assert "colors traces in different units" in capsys.readouterr().err


def test_a_grid_across_the_dateline_draws_in_one_piece():
    import xarray as xr

    from weather_skills_plotting.geodata import window_parts
    from weather_skills_plotting.spec import input_metadata

    lons = [170.0, 175.0, -180.0, -175.0]
    ds = xr.Dataset(
        {"sst": (("latitude", "longitude"), np.arange(8.0).reshape(2, 4))},
        coords={"latitude": [0.0, 1.0], "longitude": lons},
    )
    bbox = input_metadata(ds)["bbox"]
    assert (bbox["w"], bbox["e"]) == (170.0, 185.0)
    assert one("@X.sst.lon360().lon", {"X": ds}).tolist() == [170, 175, 180, 185]
    assert window_parts(170, -175) == [(170, 180, 0.0), (-180, -175, 360.0)]
    assert window_parts(20, 120) == [(20, 120, 0.0)]


def test_size_arithmetic_only_on_pixel_keys(inputs):
    size = "@OBS.precip.isel(time=0, lat=0)"
    trace = {
        "x": "@OBS.lon",
        "y": "@OBS.lon",
        "marker": {"size": size + " * 2 + 4", "standoff": size + " / const.k"},
    }
    resolved, _ = resolve({"data": [trace]}, {**inputs, "const": {"k": 2.0}})
    assert resolved["data"][0]["marker"]["size"].tolist() == [4, 6, 8, 10]
    assert resolved["data"][0]["marker"]["standoff"].tolist() == [0, 0.5, 1, 1.5]
    with pytest.raises(UsageError, match="only sets a size in pixels"):
        one("@OBS.lon * 2", inputs)
    for ref in (size + " - OBS.precip.isel(time=1, lat=0)", "@const.k + 2"):
        with pytest.raises(UsageError, match="only a size in pixels"):
            resolve(
                {"data": [{"x": "@OBS.lon", "y": "@OBS.lon", "marker": {"size": ref}}]},
                {**inputs, "const": {"k": 2.0}},
            )


@pytest.mark.parametrize(
    ("ref", "match"),
    [
        ("@OBS", "name a variable or coordinate to draw"),
        ("@OBS.precip.isel(0)", "takes dim=value pairs"),
        ("@OBS.precip.isel(time=0, method='nearest')", "takes no method"),
        ("@OBS.precip.sel(time='2026-01-01', method='pad')", "method must be 'nearest'"),
        ("@OBS.time.dt.weekday", ".dt has"),
        ("@OBS.precip.dt.year", "needs a time or timedelta"),
        ("@OBS.precip.attrs.nope", "no attribute 'nope'"),
        ("@NE.foo_10m.clip(1, 2, 0, 3).x", "NE has"),
        ("@NE.coastline_50m.clip(1, 2, 3).x", "a Natural Earth layer takes"),
        ("@OBS.precip.clip(1, 2, 0, 3)", "not allowed here"),
        ("@OBS.precip.isel(time=0", "not a valid reference"),
        ("@OBS.precip.dropna('lon', 'x')", "takes one dim"),
        ("@OBS.precip.flat()", "needs two dims"),
        ("@OBS.precip.isel(time=1 - 1)", "arithmetic"),
        ("@OBS.precip.frobnicate()", "unknown method"),
    ],
)
def test_more_errors_name_the_fix(inputs, ref, match):
    with pytest.raises(UsageError, match=match):
        one(ref, inputs)


def test_flat_on_members_by_lead(inputs):
    point = "@FC.tp.isel(latitude=0, longitude=0)"
    assert one(point + ".flat('step')", inputs).tolist() == [0, 1, 2, 0, 1, 2]  # lead days
    assert one(point + ".flat()", inputs).size == 6


def test_lon180_and_lon360_order_the_field():
    import xarray as xr

    ds = xr.Dataset(
        {"v": (("latitude", "longitude"), [[1.0, 2.0, 3.0, 4.0]])},
        coords={"latitude": [0.0], "longitude": [350.0, 355.0, 0.0, 5.0]},
    )
    assert one("@X.v.lon180().lon", {"X": ds}).tolist() == [-10, -5, 0, 5]
    assert one("@X.lon.lon180()", {"X": ds}).tolist() == [-10, -5, 0, 5]
    across = ds.assign_coords(longitude=[175.0, -180.0, 170.0, -175.0])
    z = one("@X.v.lon360()", {"X": across}, key="z")
    assert z.tolist() == [[3, 1, 2, 4]]  # 170, 175, 180, 185


def test_size_arithmetic_edges(inputs):
    size = "@OBS.precip.isel(time=0, lat=0)"
    trace = {
        "x": "@OBS.lon",
        "y": "@OBS.lon",
        "marker": {"line": {"width": size + " / 2"}},
        "textfont": {"size": size + " + 1"},
    }
    resolve({"data": [trace]}, inputs)
    with pytest.raises(UsageError, match="only sets a size in pixels"):
        resolve(
            {
                "data": [
                    {"x": "@OBS.lon", "y": "@OBS.lon", "line": {"width": "@OBS.precip.max() * 2"}}
                ]
            },
            inputs,
        )
    with pytest.raises(UsageError, match="division by zero"):
        resolve(
            {"data": [{"x": "@OBS.lon", "y": "@OBS.lon", "marker": {"size": size + " / 0"}}]},
            inputs,
        )
    with pytest.raises(UsageError, match="is not a number"):
        resolve(
            {"data": [{"x": "@OBS.lon", "y": "@OBS.lon", "marker": {"size": size + " * const.t"}}]},
            {**inputs, "const": {"t": "big"}},
        )


def test_mixed_units_warn_for_marker_colors_too(inputs, capsys):
    total = inputs["OBS"].copy()
    total["precip"].attrs["units"] = "mm"
    spec = {
        "data": [
            {"x": "@R.lon", "y": "@R.lat", "z": "@R.precip.isel(time=0)", "coloraxis": "coloraxis"},
            {
                "x": "@T.lon",
                "y": "@T.lon",
                "marker": {"color": "@T.precip.isel(time=0, lat=0)", "coloraxis": "coloraxis"},
            },
        ]
    }
    resolve(spec, {"R": inputs["OBS"], "T": total})
    assert "colors traces in different units" in capsys.readouterr().err
    resolve(spec, {"R": inputs["OBS"], "T": inputs["OBS"]})
    assert "different units" not in capsys.readouterr().err
