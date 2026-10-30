"""Traces that name the variable or coordinate filling each Plotly attribute."""

import numpy as np
import pytest
import xarray as xr
from weather_skills_core.errors import UsageError

from conftest import make_gridded, make_station
from weather_skills_plotting import compile


def _members():
    time = np.arange("2026-10-25", "2026-11-15", 7, dtype="datetime64[D]").astype("datetime64[ns]")
    return xr.Dataset(
        {"tp": (("time", "number"), np.arange(12.0).reshape(3, 4))},
        coords={"time": time, "number": np.arange(4)},
    )


def test_ensemble_lines_along_time_one_per_member():
    spec = {
        "data": [
            {
                "uid": "ENS",
                "type": "scatter",
                "meta": {"source": {"input": "ENS"}, "x": "time", "y": "tp", "along": "number"},
            }
        ]
    }
    fig = compile(spec, {"ENS": _members()})
    (trace,) = fig.data
    # Members share one gapped trace: 4 members x (3 times + a gap).
    assert len(trace.x) == 16


def test_ensemble_without_along_names_the_leftover_dim():
    spec = {"data": [{"uid": "ENS", "meta": {"source": {"input": "ENS"}, "x": "time", "y": "tp"}}]}
    with pytest.raises(
        UsageError, match=r"y 'tp' has dims \['number'\] that x 'time' lacks.*along"
    ):
        compile(spec, {"ENS": _members()})


def test_station_map_from_longitude_latitude_and_marker_color():
    spec = {
        "data": [
            {
                "uid": "STN",
                "type": "scatter",
                "meta": {
                    "source": {"input": "STN", "isel": {"time": 0}},
                    "x": "longitude",
                    "y": "latitude",
                    "marker": {"color": "precip"},
                },
            }
        ]
    }
    fig = compile(spec, {"STN": make_station()})
    markers = [t for t in fig.data if t.uid == "STN"]
    assert len(markers) == 1 and len(markers[0].x) == 3
    assert markers[0].marker.coloraxis


def test_xy_scatter_of_two_variables():
    time = np.arange("2026-01-01", "2026-01-06", dtype="datetime64[D]").astype("datetime64[ns]")
    ds = xr.Dataset(
        {"dmi": (("time",), np.arange(5.0)), "precip": (("time",), np.arange(5.0) * 2)},
        coords={"time": time},
    )
    spec = {"data": [{"uid": "0", "meta": {"source": {"input": "0"}, "x": "dmi", "y": "precip"}}]}
    (trace,) = compile(spec, {"0": ds}).data
    assert list(trace.x) == [0, 1, 2, 3, 4] and list(trace.y) == [0, 2, 4, 6, 8]


def test_heatmap_from_z():
    spec = {
        "data": [
            {
                "uid": "0",
                "type": "heatmap",
                "meta": {"source": {"isel": {"time": 0}}, "z": "precip"},
            }
        ]
    }
    fig = compile(spec, {"0": make_gridded()})
    assert any(t.type == "heatmap" for t in fig.data)


def test_source_without_a_mapping_says_where_data_goes():
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"source": {"input": "0"}}}]}
    with pytest.raises(UsageError, match=r"nothing says where it goes"):
        compile(spec, {"0": _members()})


def test_chart_on_a_map_is_an_error():
    spec = {
        "data": [
            {
                "uid": "G",
                "type": "heatmap",
                "meta": {"source": {"input": "G", "isel": {"time": 0}}, "z": "precip"},
            },
            {
                "uid": "L",
                "meta": {"source": {"input": "L"}, "x": "time", "y": "tp", "along": "number"},
            },
        ]
    }
    with pytest.raises(UsageError, match=r"data\[1\] is a chart but this figure is a map"):
        compile(spec, {"G": make_gridded(), "L": _members()})


def test_uncolored_station_map_ignores_a_time_pick():
    meta = {"source": {"isel": {"time": 0}}, "x": "longitude", "y": "latitude"}
    fig = compile({"data": [{"uid": "0", "type": "scatter", "meta": meta}]}, {"0": make_station()})
    assert len([t for t in fig.data if t.uid == "0"][0].x) == 3


def test_forecast_line_on_time_points_to_step():
    from conftest import make_forecast

    meta = {"source": {"isel": {"latitude": 0, "longitude": 0}}, "x": "time", "y": "tp"}
    with pytest.raises(UsageError, match=r"x 'time' is one value here.*\"step\""):
        compile({"data": [{"uid": "0", "meta": meta}]}, {"0": make_forecast()})


def test_source_variable_alone_points_to_the_mapping():
    spec = {"data": [{"uid": "0", "type": "heatmap", "meta": {"source": {"variable": "precip"}}}]}
    with pytest.raises(UsageError, match=r"names data 'precip'.*in place of meta.source.variable"):
        compile(spec, {"0": make_gridded()})
