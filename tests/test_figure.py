"""Figure assembly: binds, panels, color axes, overlays, chart defaults."""

import json

import numpy as np
import pytest
import xarray as xr
from weather_skills_core.errors import UsageError

from conftest import make_forecast, make_gridded, make_station
from weather_skills_plotting import compile


def _trace(uid, **kw):
    meta = kw.pop("meta", {})
    source = {"input": kw.pop("input", uid), **kw.pop("source", {})}
    return {"uid": uid, "type": kw.pop("type", "heatmap"), "meta": {"source": source, **meta}, **kw}


def _layout(fig):
    return fig.to_plotly_json()["layout"]


def _data(fig, kind=None):
    """Traces as Plotly objects (arrays stay numpy; JSON would base64 them)."""
    return [t for t in fig.data if kind is None or t["type"] == kind]


def test_heatmap_panels_each_time_with_one_discrete_colorbar():
    ds = make_gridded(n_time=3)
    fig = compile({"data": [_trace("a")]}, {"a": ds})
    heat = _data(fig, "heatmap")
    assert len(heat) == 3
    assert [t["xaxis"] for t in heat] == ["x", "x2", "x3"]
    assert {t["coloraxis"] for t in heat} == {"coloraxis"}
    layout = _layout(fig)
    bar = layout["coloraxis"]["colorbar"]
    assert bar["orientation"] == "h"  # several panels: shared bar underneath
    assert bar["ticktext"][:3] == ["0", "1", "2"]
    titles = [
        a["text"] for a in layout["annotations"] if a.get("name", "").startswith("panel-title")
    ]
    assert titles == ["1 Jan '26", "2 Jan '26", "3 Jan '26"]
    # z holds class slots; the raw mm stay in customdata for hover.
    assert np.allclose(np.asarray(heat[0]["customdata"], dtype=float), 1.0)
    assert layout["yaxis"]["scaleanchor"] == "x"


def test_user_trace_keys_lift_to_coloraxis_and_win():
    ds = make_gridded(n_time=1)
    spec = {
        "data": [
            _trace("a", zmin=0, zmax=20, colorscale="Blues", colorbar={"title": {"text": "Rain"}})
        ]
    }
    axis = _layout(compile(spec, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (0, 20)
    assert axis["colorbar"]["title"]["text"] == "Rain"
    assert axis["colorscale"][0][1].lower() in ("rgb(247,251,255)", "#f7fbff")


def test_layout_coloraxis_override_wins():
    ds = make_gridded(n_time=1)
    spec = {"data": [_trace("a")], "layout": {"coloraxis": {"colorbar": {"len": 0.3}}}}
    assert _layout(compile(spec, {"a": ds}))["coloraxis"]["colorbar"]["len"] == 0.3


def test_side_by_side_inputs_get_their_own_grid_and_scale():
    a = make_gridded(n_time=1)
    b = make_gridded(n_time=1, name="tp", lats=(1.5, 2.5), lons=(10.5, 12.5), fill=3.0)
    spec = {"data": [_trace("a"), _trace("b", xaxis="x2", yaxis="y2", name="ECMWF")]}
    fig = compile(spec, {"a": a, "b": b})
    heat = _data(fig, "heatmap")
    assert [t["coloraxis"] for t in heat] == ["coloraxis", "coloraxis2"]
    assert list(heat[1]["x"]) == [10.5, 12.5]
    titles = [a["text"] for a in _layout(fig)["annotations"]]
    assert "ECMWF" in titles


def test_shared_coloraxis_on_request():
    a = make_gridded(n_time=1)
    b = make_gridded(n_time=1, fill=5.0)
    spec = {
        "data": [
            _trace("a", coloraxis="coloraxis"),
            _trace("b", xaxis="x2", yaxis="y2", coloraxis="coloraxis"),
        ]
    }
    fig = compile(spec, {"a": a, "b": b})
    assert {t["coloraxis"] for t in _data(fig, "heatmap")} == {"coloraxis"}
    assert "coloraxis2" not in _layout(fig)


def test_faceted_side_by_side_is_an_error():
    a = make_gridded(n_time=2)
    with pytest.raises(UsageError, match="single map"):
        compile({"data": [_trace("a"), _trace("b", input="a", xaxis="x2")]}, {"a": a})


def test_leftover_dim_is_an_error_with_hint():
    ds = make_forecast(n_step=2)  # tests/conftest: number × step × lat × lon
    ds = ds.expand_dims(level=[850, 500])
    with pytest.raises(UsageError, match="dimension 'level' remains.*isel"):
        compile({"data": [_trace("a")]}, {"a": ds})


def test_ensemble_mean_and_step_panels_for_forecast():
    fig = compile({"data": [_trace("a")]}, {"a": make_forecast(n_number=3, n_step=4)})
    assert len(_data(fig, "heatmap")) == 4


def test_isel_and_bbox_subset():
    ds = make_gridded(n_time=3)
    spec = {
        "data": [_trace("a", source={"isel": {"time": 1}})],
        "layout": {"meta": {"geo": {"bbox": [3, 11, 1, 12]}}},
    }
    fig = compile(spec, {"a": ds})
    heat = _data(fig, "heatmap")
    assert len(heat) == 1
    assert list(heat[0]["x"]) == [11.0, 12.0]
    assert _layout(fig)["xaxis"]["range"] == [11.0, 12.0]


def test_contour_uses_class_edges_as_levels():
    spec = {"data": [_trace("a", type="contour")]}
    tr = _data(compile(spec, {"a": make_gridded(n_time=1)}), "contour")[0]
    assert tr["contours"]["coloring"] == "fill"
    assert tr["contours"]["size"] == 1
    assert tr["autocontour"] is False


def test_non_precip_gets_continuous_scale_symmetric_when_diverging():
    ds = make_gridded(n_time=1, name="t2m", units="degree_Celsius")
    ds["t2m"].values[:] = np.linspace(-2, 4, 12).reshape(1, 3, 4)
    axis = _layout(compile({"data": [_trace("a")]}, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (-4, 4)
    assert "ticktext" not in axis["colorbar"]


def test_points_layer_over_field_and_static_outline(tmp_path):
    grid = make_gridded(n_time=2, lats=(-1.0, 0.0, 1.0), lons=(36.0, 37.0, 38.0))
    stations = make_station(n_station=3, n_time=2)
    stations["precip"].attrs["units"] = "mm day-1"
    geo = tmp_path / "box.geojson"
    geo.write_text(
        json.dumps({"type": "Polygon", "coordinates": [[[36, -1], [38, -1], [38, 1], [36, -1]]]})
    )
    spec = {
        "data": [
            _trace("a"),
            _trace("b", type="scatter", meta={"bind": "points"}),
            {
                "uid": "edge",
                "type": "scatter",
                "meta": {"bind": "geojson", "source": {"geojson": str(geo)}},
            },
            {"uid": "city", "type": "scatter", "mode": "markers", "x": [37], "y": [0]},
        ]
    }
    fig = compile(spec, {"a": grid, "b": stations})
    data = _data(fig)
    per_panel = [t for t in data if t["xaxis"] == "x2"]
    uids = [t["uid"] for t in per_panel]
    # draw order: field, overlays, points, outline, plain traces
    assert uids[0] == "a-p2"
    assert uids.index("b-p2") < uids.index("edge-p2") < uids.index("city-p2")
    assert any(u.startswith("overlay-") for u in uids)
    # same variable on one map shares a scale
    assert per_panel[uids.index("b-p2")]["marker"]["coloraxis"] == "coloraxis"


def test_overlays_switch_off_and_restyle():
    ds = make_gridded(n_time=1)
    off = compile({"data": [_trace("a")], "layout": {"meta": {"overlays": False}}}, {"a": ds})
    assert not [t for t in _data(off) if t["uid"].startswith("overlay")]
    styled = compile(
        {
            "data": [_trace("a")],
            "layout": {
                "meta": {"overlays": {"coastline": False, "borders": {"line": {"color": "red"}}}}
            },
        },
        {"a": ds},
    )
    over = [t for t in _data(styled) if t["uid"].startswith("overlay")]
    assert [t["uid"] for t in over] == ["overlay-borders-1"]
    assert over[0]["line"]["color"] == "red"


def test_series_spaghetti_band_and_cycle():
    ds = make_forecast(n_number=5, n_step=4)
    src = {"reduce": ["latitude", "longitude"]}
    same = compile(
        {
            "data": [
                _trace("a", type="scatter", source=src, meta={"bind": "series", "along": "number"})
            ]
        },
        {"a": ds},
    )
    lines = _data(same)
    assert len(lines) == 1 and list(lines[0]["x"]).count(None) == 5
    band = compile(
        {
            "data": [
                _trace(
                    "a",
                    type="scatter",
                    source=src,
                    meta={"bind": "series", "along": "number", "band": [10, 90]},
                )
            ]
        },
        {"a": ds},
    )
    assert [t["fill"] for t in _data(band)] == [None, "tonexty", None]
    cycle = compile(
        {
            "data": [
                _trace(
                    "a",
                    type="scatter",
                    source=src,
                    meta={"bind": "series", "along": "number", "along_color": "cycle"},
                )
            ]
        },
        {"a": ds},
    )
    assert [t["name"] for t in _data(cycle)] == ["0", "1", "2", "3", "4"]


def test_series_needs_reduce_or_along():
    with pytest.raises(UsageError, match="Nothing is averaged silently"):
        compile(
            {"data": [_trace("a", type="scatter", meta={"bind": "series"})]}, {"a": make_gridded()}
        )


def test_series_forecast_plots_valid_time_with_date_ticks():
    ds = make_forecast(n_number=0, n_step=3)
    fig = compile(
        {
            "data": [
                _trace(
                    "a",
                    type="scatter",
                    source={"reduce": ["latitude", "longitude"]},
                    meta={"bind": "series"},
                )
            ]
        },
        {"a": ds},
    )
    assert _data(fig)[0]["x"][0].startswith("2026-01-01")
    assert _layout(fig)["xaxis"]["tickformat"] == "%-d %b '%y"


def test_pair_on_year_labels_points():
    def yearly(start, values):
        times = np.array(
            [np.datetime64(f"{y}-09-01", "ns") for y in range(start, start + len(values))]
        )
        return xr.Dataset({"v": (("time",), np.asarray(values, float))}, coords={"time": times})

    spec = {
        "data": [
            {
                "uid": "xy",
                "type": "scatter",
                "meta": {
                    "bind": "pair",
                    "pair_on": "year",
                    "x": {"input": "x"},
                    "y": {"input": "y"},
                },
            }
        ]
    }
    fig = compile(spec, {"x": yearly(2000, [1, 2, 3]), "y": yearly(2001, [5, 6, 7])})
    tr = _data(fig)[0]
    assert list(tr["text"]) == ["2001", "2002"]
    assert list(tr["x"]) == [2, 3] and list(tr["y"]) == [5, 6]


def test_samples_box_and_mean_line():
    ds = make_forecast(n_number=4, n_step=3)
    src = {"point": {"lat": 0.9, "lon": 10.1}}
    fig = compile(
        {
            "data": [
                _trace("a", type="box", source=src, meta={"bind": "samples"}),
                _trace("m", input="a", type="scatter", source=src, meta={"bind": "samples"}),
            ]
        },
        {"a": ds},
    )
    box, mean = _data(fig)
    assert len(box["y"]) == 12 and list(box["x"][:4]) == ["+0d"] * 4
    assert list(mean["x"]) == ["+0d", "+1d", "+2d"]


def test_windrose_bins():
    lat, lon = [0.0, 1.0], [10.0, 11.0]
    u = np.full((2, 2, 2), 3.0)
    v = np.zeros((2, 2, 2))
    ds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), u),
            "v10": (("time", "latitude", "longitude"), v),
        },
        coords={
            "time": np.array(["2026-01-01", "2026-01-02"], dtype="datetime64[ns]"),
            "latitude": lat,
            "longitude": lon,
        },
    )
    for k in ("u10", "v10"):
        ds[k].attrs["units"] = "m s-1"
    fig = compile(
        {"data": [{"uid": "a", "type": "barpolar", "meta": {"source": {"input": "a"}}}]}, {"a": ds}
    )
    bars = _data(fig, "barpolar")
    assert [t["name"] for t in bars] == ["0–2 m/s", "2–4 m/s"]
    # westerly 3 m/s (from 270°) is all in the 2–4 bin at theta 270
    assert bars[1]["r"][12] == 100.0
    assert _layout(fig)["polar"]["angularaxis"]["direction"] == "clockwise"


def test_arrows_and_speed_quiver():
    lat, lon = np.arange(0, 5.0), np.arange(10, 15.0)
    shape = (1, 5, 5)
    ds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), np.full(shape, 5.0)),
            "v10": (("time", "latitude", "longitude"), np.zeros(shape)),
        },
        coords={"time": [np.datetime64("2026-01-01", "ns")], "latitude": lat, "longitude": lon},
    )
    for k in ("u10", "v10"):
        ds[k].attrs["units"] = "m s-1"
    spec = {
        "data": [
            {"uid": "a", "type": "heatmap", "meta": {"bind": "speed", "source": {"input": "a"}}},
            {
                "uid": "w",
                "type": "scatter",
                "meta": {"bind": "arrows", "source": {"input": "a"}, "arrows": {"step": 2}},
            },
        ]
    }
    fig = compile(spec, {"a": ds})
    heat = _data(fig, "heatmap")[0]
    assert np.allclose(np.asarray(heat["z"], float), 5.0)
    assert _layout(fig)["coloraxis"]["colorbar"]["title"]["text"] == "Wind speed [m/s]"
    arrows = next(t for t in _data(fig) if t["uid"] == "w")
    assert list(arrows["x"]).count(None) == 9 * 3  # 3×3 thinned arrows, shaft + two head strokes


def test_bind_type_mismatch():
    with pytest.raises(UsageError, match="draws as type contour or heatmap.*series"):
        compile({"data": [_trace("a", type="bar", meta={"bind": "field"})]}, {"a": make_gridded()})


def test_unknown_input():
    with pytest.raises(UsageError, match="input 'zz' is not an input"):
        compile({"data": [_trace("a", input="zz")]}, {"a": make_gridded()})
