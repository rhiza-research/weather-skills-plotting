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


def test_mapped_trace_with_no_uid_restyles_the_input():
    # Positional restyle: a trace with no uid merges onto input 0, mapped or not.
    from weather_skills_plotting.spec import merge_spec

    base = {"data": [{"uid": "0", "type": "heatmap", "meta": {"source": {"input": "0"}}}]}
    merged = merge_spec(base, {"data": [{"type": "contour", "meta": {"z": "precip"}}]})
    fig = compile(merged, {"0": make_gridded(n_time=1).isel(time=0)})
    assert any(t.type == "contour" for t in fig.data)


def test_outline_alone_frames_its_own_map():
    import json
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "box.geojson"
    path.write_text(
        json.dumps(
            {"type": "Polygon", "coordinates": [[[30, -5], [40, -5], [40, 5], [30, 5], [30, -5]]]}
        )
    )
    meta = {"bind": "geojson", "source": {"geojson": str(path)}}
    fig = compile({"data": [{"uid": "0", "type": "scatter", "meta": meta}]}, {})
    xr_ = fig.layout.xaxis.range
    assert xr_[0] < 30 and xr_[1] > 40


def test_heatmap_with_no_z_lists_the_variables():
    ds = make_gridded(n_time=1).isel(time=0)
    ds["t2m"] = ds["precip"] * 0
    spec = {"data": [{"uid": "0", "type": "heatmap", "meta": {"source": {"input": "0"}}}]}
    with pytest.raises(UsageError, match=r"set data\[0\]\.meta\.z; the data holds precip, t2m"):
        compile(spec, {"0": ds})


def test_x_not_in_the_input_says_which_key_and_one_input():
    spec = {"data": [{"uid": "0", "meta": {"source": {"input": "0"}, "x": "dmi", "y": "precip"}}]}
    with pytest.raises(UsageError, match=r"meta\.x 'dmi' is not in input '0'.*merge two files"):
        compile(spec, {"0": make_gridded()})


def test_station_map_by_cf_role_whatever_the_coordinates_are_called():
    # CF-tagged coordinates are found by their attributes, whatever they are called.
    ds = make_station().rename({"longitude": "lon", "latitude": "lat"})
    ds["lon"].attrs.update(standard_name="longitude", units="degrees_east")
    ds["lat"].attrs.update(standard_name="latitude", units="degrees_north")
    meta = {
        "source": {"isel": {"time": 0}},
        "x": "longitude",
        "y": "latitude",
        "marker": {"color": "precip"},
    }
    fig = compile({"data": [{"uid": "0", "type": "scatter", "meta": meta}]}, {"0": ds})
    assert len([t for t in fig.data if t.uid == "0"][0].x) == 3
    swapped = {**meta, "x": "latitude", "y": "longitude"}
    with pytest.raises(UsageError, match="swap them"):
        compile({"data": [{"uid": "0", "type": "scatter", "meta": swapped}]}, {"0": ds})


def test_one_line_per_station_gets_its_own_color_and_legend():
    meta = {"source": {"input": "0"}, "x": "time", "y": "precip", "along": "station_id"}
    fig = compile({"data": [{"uid": "0", "meta": meta}]}, {"0": make_station()})
    lines = [t for t in fig.data if str(t.uid).startswith("0")]
    assert len(lines) == 3 and len({t.name for t in lines}) == 3
    same = compile(
        {"data": [{"uid": "0", "meta": {**meta, "along_color": "same"}}]}, {"0": make_station()}
    )
    assert len([t for t in same.data if str(t.uid).startswith("0")]) == 1


def test_rain_past_the_colour_window_says_which_palette_fits(capsys):
    ds = make_gridded(n_time=1, fill=300.0).isel(time=0)
    ds["precip"].attrs["aggregation_period"] = "1 day"
    compile({"data": [{"uid": "0", "type": "heatmap", "meta": {"z": "precip"}}]}, {"0": ds})
    err = capsys.readouterr().err
    assert "ppt_daily colors stop at 50 mm" in err and 'meta.palette "ppt_month"' in err


def test_one_map_under_a_spec_title_has_no_date_line():
    ds = make_gridded(n_time=1)
    trace = {"uid": "0", "type": "heatmap", "meta": {"z": "precip"}}
    dated = compile({"data": [trace]}, {"0": ds})
    assert [a.text for a in dated.layout.annotations if a.name == "panel-title-1"] != [""]
    titled = compile({"data": [trace], "layout": {"title": {"text": "Rain"}}}, {"0": ds})
    assert [a.text for a in titled.layout.annotations if a.name == "panel-title-1"] == [""]
    named = compile(
        {
            "data": [trace],
            "layout": {
                "title": {"text": "Rain"},
                "annotations": [{"name": "panel-title-1", "text": "1 Jan"}],
            },
        },
        {"0": ds},
    )
    assert [a.text for a in named.layout.annotations if a.name == "panel-title-1"] == ["1 Jan"]


def test_long_axis_title_goes_on_two_lines():
    time = np.arange("2026-01-01", "2026-01-04", dtype="datetime64[D]").astype("datetime64[ns]")
    ds = xr.Dataset({"tp": ("time", [1.0, 2.0, 3.0])}, coords={"time": time})
    ds["tp"].attrs.update(long_name="Sum of Total precipitation across step", units="mm")
    fig = compile({"data": [{"uid": "0", "meta": {"x": "time", "y": "tp"}}]}, {"0": ds})
    assert "<br>" in fig.layout.yaxis.title.text
