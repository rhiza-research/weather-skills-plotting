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
    # Each panel has its own explicit domain, anchored to its own axis, and
    # no two panels overlap; one vertical colorbar spans the maps.
    boxes = [
        (*layout[f"xaxis{s}"]["domain"], *layout[f"yaxis{s}"]["domain"]) for s in ("", "2", "3")
    ]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert a[1] <= b[0] or b[1] <= a[0] or a[3] <= b[2] or b[3] <= a[2]
    assert layout["yaxis2"]["anchor"] == "x2"
    assert "grid" not in layout
    assert "orientation" not in bar and bar["title"]["side"] == "right"
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


def test_side_by_side_inputs_get_their_own_grid_and_one_scale_per_quantity():
    a = make_gridded(n_time=1)
    b = make_gridded(n_time=1, name="tp", lats=(1.5, 2.5), lons=(10.5, 12.5), fill=3.0)
    spec = {"data": [_trace("a"), _trace("b", xaxis="x2", yaxis="y2", name="ECMWF")]}
    fig = compile(spec, {"a": a, "b": b})
    heat = _data(fig, "heatmap")
    # Two rainfall rates under different variable names are one quantity: one bar.
    assert [t["coloraxis"] for t in heat] == ["coloraxis", "coloraxis"]
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


def test_step_panels_for_forecast():
    fig = compile({"data": [_trace("a")]}, {"a": make_forecast(n_number=0, n_step=4)})
    assert len(_data(fig, "heatmap")) == 4


def test_ensemble_map_is_not_averaged():
    # The plotter selects but never averages: summarize-dim makes the ensemble mean.
    with pytest.raises(UsageError, match="'number' remains.*summarize-dim"):
        compile({"data": [_trace("a")]}, {"a": make_forecast(n_number=3, n_step=4)})


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


def _pressure():
    """MSLP in hPa: a 1030 high at (10N, 20E) and a 990 low at (-10N, 60E)."""
    lats, lons = np.arange(-30.0, 30.5, 1.0), np.arange(0.0, 80.5, 1.0)
    lat, lon = np.meshgrid(lats, lons, indexing="ij")
    z = (
        1010
        + 20 * np.exp(-((lat - 10) ** 2 + (lon - 20) ** 2) / 50)
        - 20 * np.exp(-((lat + 10) ** 2 + (lon - 60) ** 2) / 50)
    )
    ds = xr.Dataset(
        {"msl": (("latitude", "longitude"), z)}, coords={"latitude": lats, "longitude": lons}
    )
    ds["msl"].attrs.update(units="hPa", standard_name="air_pressure_at_mean_sea_level")
    return ds


def test_one_station_keeps_its_station_axis():
    # local-extrema finds a single high: a one-point file still draws as a point.
    stations = make_station(n_station=1, n_time=1).isel(time=0)
    spec = {"data": [_trace("a"), _trace("c", type="scatter", meta={"bind": "points"})]}
    fig = compile(spec, {"a": _pressure(), "c": stations})
    point = next(t for t in fig.data if t["uid"] == "c")
    assert len(point["x"]) == 1


def test_line_only_contour_over_shading_keeps_the_shading_colorbar():
    spec = {
        "data": [
            _trace("a"),
            _trace(
                "iso", input="a", type="contour", contours={"coloring": "none"}, showscale=False
            ),
        ]
    }
    fig = compile(spec, {"a": _pressure()})
    iso = _data(fig, "contour")[0]
    assert iso["coloraxis"] is None
    assert iso["showscale"] is False and iso["line"]["color"] == "black"
    layout = _layout(fig)
    assert layout["coloraxis"].get("showscale") is not False
    assert "coloraxis2" not in layout


def test_text_only_points_have_no_colorbar_and_keep_customdata_in_images(tmp_path, monkeypatch):
    import plotly.io as pio

    from weather_skills_plotting import export

    stations = make_station(n_station=3, n_time=1).isel(time=0)
    spec = {
        "data": [
            _trace("a"),
            _trace(
                "c",
                type="scatter",
                mode="text",
                texttemplate="<b>H</b><br>%{customdata:.0f}",
                meta={"bind": "points"},
            ),
        ]
    }
    fig = compile(spec, {"a": _pressure(), "c": stations})
    text = next(t for t in fig.data if t["uid"] == "c")
    assert text["marker"]["coloraxis"] is None
    layout = _layout(fig)
    assert "coloraxis2" not in layout and "orientation" not in layout["coloraxis"]["colorbar"]
    # A PNG drops the heatmap's hover copy but keeps what a texttemplate prints.
    written = {}
    monkeypatch.setattr(pio, "write_image", lambda image, *a, **k: written.update(image))
    monkeypatch.setattr("weather_skills_plotting.qa.report_figure", lambda *a, **k: None)
    export(fig, tmp_path / "map.png")
    kept = {t["uid"]: "customdata" in t for t in written["data"] if t["uid"] in ("a", "c")}
    assert kept == {"a": False, "c": True}


def test_text_only_points_skip_nan_but_markers_keep_them():
    stations = make_station(n_station=3, n_time=1).isel(time=0)
    stations["precip"].values[1] = np.nan
    for mode, n in (("text", 2), ("markers", 3)):
        spec = {"data": [_trace("c", type="scatter", mode=mode, meta={"bind": "points"})]}
        trace = next(t for t in compile(spec, {"c": stations}).data if t["uid"] == "c")
        assert len(trace["x"]) == n and len(trace["customdata"]) == n


def test_non_precip_gets_continuous_scale_symmetric_when_diverging():
    ds = make_gridded(n_time=1, name="t2m", units="degree_Celsius")
    ds["t2m"].values[:] = np.linspace(-2, 4, 12).reshape(1, 3, 4)
    axis = _layout(compile({"data": [_trace("a")]}, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (-4, 4)
    assert "ticktext" not in axis["colorbar"]


def test_sea_level_pressure_is_red_blue_with_white_at_standard_atmosphere():
    # Pa is drawn in hPa, so white sits at 1013.25 hPa either way.
    for units, scale in (("hPa", 1.0), ("Pa", 100.0)):
        ds = make_gridded(n_time=1, name="msl", units=units)
        ds["msl"].values[:] = np.linspace(1008, 1036, 12).reshape(1, 3, 4) * scale
        ds["msl"].attrs["standard_name"] = "air_pressure_at_mean_sea_level"
        axis = _layout(compile({"data": [_trace("a")]}, {"a": ds}))["coloraxis"]
        assert axis["colorscale"][0][1] == "rgb(5,48,97)"  # RdBu_r: blue lows
        assert (axis["cmin"], axis["cmax"]) == pytest.approx((990.5, 1036))


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
    # An area mean, as summarize-dim --dim latitude --dim longitude writes it.
    ds = make_forecast(n_number=5, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    src = {}
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
    # Faint members, the band's two edges, then the mean line.
    assert [t["fill"] for t in _data(band)] == [None, None, "tonexty", None]
    assert _data(band)[-1]["name"].endswith("ensemble mean")
    bare = compile(
        {
            "data": [
                _trace(
                    "a",
                    type="scatter",
                    source=src,
                    meta={"bind": "series", "along": "number", "band": [10, 90], "members": False},
                )
            ]
        },
        {"a": ds},
    )
    assert [t["fill"] for t in _data(bare)] == [None, "tonexty", None]
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


def test_series_needs_select_or_along():
    with pytest.raises(UsageError, match="remain besides.*summarize-dim"):
        compile(
            {"data": [_trace("a", type="scatter", meta={"bind": "series"})]}, {"a": make_gridded()}
        )


def test_series_forecast_plots_valid_time():
    ds = make_forecast(n_number=0, n_step=3).mean(["latitude", "longitude"], keep_attrs=True)
    fig = compile({"data": [_trace("a", type="scatter", meta={"bind": "series"})]}, {"a": ds})
    assert _data(fig)[0]["x"][0].startswith("2026-01-01")
    assert "tickformat" not in _layout(fig)["xaxis"]  # Plotly's own date ticks


def test_xy_scatter_of_two_variables():
    years = [2019, 2020, 2021, 2022]
    ds = xr.Dataset(
        {"dmi": (("year",), [1.9, -0.2, -0.3, -1.0]), "precip": (("year",), [210, 60, np.nan, 30])},
        coords={"year": years},
    )
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "dmi", "y": "precip"}}]}
    tr = _data(compile(spec, {"0": ds}))[0]
    assert list(tr["text"]) == ["2019", "2020", "2022"]
    assert list(tr["x"]) == [1.9, -0.2, -1.0] and list(tr["y"]) == [210, 60, 30]


def test_xy_scatter_of_a_grid_is_one_point_per_cell():
    ds = make_gridded(n_time=1)
    ds["t2m"] = ds["precip"] * 0 + 25.0
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "t2m", "y": "precip"}}]}
    tr = _data(compile(spec, {"0": ds}))[0]
    assert len(tr["x"]) == ds["precip"].size and tr["text"] is None


def test_xy_scatter_needs_the_same_dims():
    ds = make_forecast(n_number=3, n_step=2)
    ds["mean"] = ds["tp"].mean("number")
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "mean", "y": "tp"}}]}
    with pytest.raises(UsageError, match="source.isel / sel"):
        compile(spec, {"0": ds})


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


def test_two_scales_on_one_panel_do_not_overlap():
    grid = make_gridded(n_time=1, lats=(-1.0, 0.0, 1.0), lons=(36.0, 37.0, 38.0))
    stations = make_station(n_station=3, n_time=1)
    stations["precip"].attrs["units"] = "mm"  # different label → its own colorbar
    spec = {"data": [_trace("a"), _trace("b", type="scatter", meta={"bind": "points"})]}
    layout = _layout(compile(spec, {"a": grid, "b": stations}))
    bar1, bar2 = layout["coloraxis"]["colorbar"], layout["coloraxis2"]["colorbar"]
    # Two bars sit side by side along the bottom, each in its own half.
    assert bar1["orientation"] == bar2["orientation"] == "h"
    left = [b["x"] - b["len"] / 2 for b in (bar1, bar2)]
    right = [b["x"] + b["len"] / 2 for b in (bar1, bar2)]
    assert right[0] <= left[1]
    # The provenance seal sits in the bottom-right corner; the bars stop short of it.
    assert right[1] <= 0.88


def test_align_dayofyear_lines_up_leap_and_non_leap_years():
    def ond(year):
        times = np.arange(np.datetime64(f"{year}-09-30"), np.datetime64(f"{year}-10-03"))
        return xr.Dataset(
            {"precip": (("time",), [1.0, 2.0, 3.0])},
            coords={"time": times.astype("datetime64[ns]")},
        )

    spec = {
        "data": [
            {
                "uid": "a",
                "type": "scatter",
                "meta": {"bind": "series", "align": "dayofyear", "source": {"input": "a"}},
            },
            {
                "uid": "b",
                "type": "scatter",
                "meta": {"bind": "series", "align": "dayofyear", "source": {"input": "b"}},
            },
        ]
    }
    fig = compile(spec, {"a": ond(2024), "b": ond(2025)})
    xa, xb = (list(t["x"]) for t in _data(fig))
    assert xa == xb  # 1 Oct is day 275 in 2024 and 274 in 2025; both land on 1 Oct
    assert xa[1].startswith("2001-10-01")
    assert _layout(fig)["xaxis"]["tickformat"] == "%-d %b"


def test_align_dayofyear_folds_29_february():
    times = np.array(["2024-02-28", "2024-02-29", "2024-03-01"], dtype="datetime64[ns]")
    ds = xr.Dataset({"precip": (("time",), [1.0, 2.0, 3.0])}, coords={"time": times})
    spec = {
        "data": [{"uid": "a", "type": "scatter", "meta": {"bind": "series", "align": "dayofyear"}}]
    }
    x = list(_data(compile(spec, {"a": ds}))[0]["x"])
    assert [v[:10] for v in x] == ["2001-02-28", "2001-02-28", "2001-03-01"]


def test_cf_flag_field_gets_named_classes():
    ds = make_gridded(n_time=1, name="event_hit", units=None)
    ds["event_hit"].values[:] = np.resize([-1.0, 0.0, 1.0], ds["event_hit"].shape)
    ds["event_hit"].attrs.update(flag_values=[-1, 0, 1], flag_meanings="disagree below hit")
    fig = compile({"data": [_trace("a")]}, {"a": ds})
    bar = _layout(fig)["coloraxis"]["colorbar"]
    assert bar["ticktext"] == ["disagree", "below", "hit"]
    assert bar["tickvals"] == [0, 1, 2]
    z = np.asarray(_data(fig, "heatmap")[0]["z"], float)
    assert sorted(set(z.ravel().tolist())) == [0.0, 1.0, 2.0]


def test_default_precip_palette_names_follow_aggregation_window():
    from weather_skills_plotting.palettes import load_theme, precip_nested_anomaly_palette

    # An all-positive field with no precip name: detection would not call it an anomaly.
    ds = make_gridded(n_time=1, name="diff", units="mm")
    ds["diff"].values[:] = 12.0
    ds["diff"].attrs["aggregation_period"] = "30 day"
    spec = {"data": [_trace("a", meta={"palette": "Default_Precip_Anom"})]}
    bar = _layout(compile(spec, {"a": ds}))["coloraxis"]["colorbar"]
    month = precip_nested_anomaly_palette("ppt_anom_month")
    assert bar["ticktext"] == [f"{b:g}" for b in month["bounds"]]

    spec = {"data": [_trace("a", meta={"palette": "default_precip"})]}
    bar = _layout(compile(spec, {"a": ds}))["coloraxis"]["colorbar"]
    assert bar["ticktext"][-1] == "400"  # ppt_month window

    # A theme palette of the same name replaces the built-in one.
    theme = load_theme()
    theme["palettes"]["default_precip"] = {"colors": ["#fff", "#00f"], "bounds": [0, 5, 10]}
    bar = _layout(compile(spec, {"a": ds}, theme=theme))["coloraxis"]["colorbar"]
    assert bar["ticktext"] == ["0", "5", "10"]


def test_spread_from_summarize_dim_is_not_drawn_as_rain_totals():
    ds = make_gridded(n_time=1, units="mm")
    ds["precip"].attrs.update(
        long_name="Standard deviation of Total precipitation across number",
        cell_methods="number: standard_deviation",
    )
    axis = _layout(compile({"data": [_trace("a")]}, {"a": ds}))["coloraxis"]
    # A continuous scale (no class ticks) and a label that says what it is.
    assert "ticktext" not in axis["colorbar"]
    assert axis["colorbar"]["title"]["text"] == "Precipitation std. dev. (number) [mm]"


def test_member_panels_titled_and_bad_panel_title_named():
    ds = make_forecast(n_number=3, n_step=1).isel(step=0)
    fig = compile({"data": [_trace("a", meta={"facet": "number"})]}, {"a": ds})
    titles = [
        a["text"] for a in _layout(fig)["annotations"] if a.get("name", "").startswith("panel")
    ]
    assert titles == ["Member 0", "Member 1", "Member 2"]
    with pytest.raises(
        UsageError, match="panel-title-0.*panel-title-1, panel-title-2, panel-title-3"
    ):
        compile(
            {
                "data": [_trace("a", meta={"facet": "number"})],
                "layout": {"annotations": [{"name": "panel-title-0", "text": "x"}]},
            },
            {"a": ds},
        )


def test_string_bbox_and_horizontal_colorbar_below():
    ds = make_gridded(n_time=2)
    fig = compile(
        {
            "data": [_trace("a")],
            "layout": {
                "coloraxis": {"colorbar": {"orientation": "h"}},
                "meta": {"geo": {"bbox": "1/10/0/11"}},
            },
        },
        {"a": ds},
    )
    bar = _layout(fig)["coloraxis"]["colorbar"]
    assert bar["orientation"] == "h" and bar["yref"] == "container"


def test_same_standard_name_shares_a_bar_and_small_bbox_keeps_overlapped_cells():
    grid = make_gridded(n_time=1, lats=(-1.5, 0.0, 1.5), lons=(36.0, 37.5, 39.0), name="t2m")
    grid["t2m"].attrs.update(standard_name="air_temperature", long_name="2 m temperature")
    stations = make_station(n_station=3, n_time=1).rename(precip="temperature")
    stations["temperature"].attrs.update(
        standard_name="air_temperature", long_name="Surface air temperature"
    )
    for ds in (grid, stations):
        ds[list(ds.data_vars)[0]].attrs["units"] = "degree_Celsius"
    spec = {
        "data": [_trace("a"), _trace("b", type="scatter", meta={"bind": "points"})],
        # Smaller than one 1.5° cell and centred on none.
        "layout": {"meta": {"geo": {"bbox": [0.2, 36.5, -0.6, 37.1]}}},
    }
    fig = compile(spec, {"a": grid, "b": stations})
    field = next(t for t in _data(fig) if t["uid"].startswith("a"))
    assert np.asarray(field["z"]).size > 0
    points = next(t for t in _data(fig) if t["uid"].startswith("b"))
    assert points["marker"]["coloraxis"] == field["coloraxis"]


def test_theme_file_sets_palette_colorway_and_overlays(tmp_path):
    from weather_skills_plotting.palettes import load_theme

    path = tmp_path / "theme.json"
    path.write_text(
        json.dumps(
            {
                "template": {"layout": {"colorway": ["#123456", "#654321"]}},
                "palettes": {
                    "agency": {"colors": ["#fff", "#fff", "#0a0", "#00f"], "bounds": [0, 1, 10]}
                },
                "defaults": {"precip": "agency"},
                "overlays": {"borders": {"line": {"color": "#ff0000"}}},
            }
        )
    )
    theme = load_theme(path)
    ds = make_gridded(n_time=1)
    ds["precip"].attrs.update(units="mm", aggregation_period="7 day")
    fig = compile({"data": [_trace("a")]}, {"a": ds}, theme=theme)
    bar = _layout(fig)["coloraxis"]["colorbar"]
    assert list(bar["ticktext"]) == ["0", "1", "10"]
    borders = [t for t in _data(fig, "scatter") if str(t["uid"]).startswith("overlay-borders")]
    assert borders and all(t["line"]["color"] == "#ff0000" for t in borders)
    # A palette that exists only in the theme file is a known meta.palette name.
    fig = compile({"data": [_trace("a", meta={"palette": "agency"})]}, {"a": ds}, theme=theme)
    assert list(_layout(fig)["coloraxis"]["colorbar"]["ticktext"]) == ["0", "1", "10"]
    # Explicit series colors (ensemble members, band) follow the template's colorway.
    meta = {"bind": "series", "along": "number", "band": [10, 90]}
    area_mean = make_forecast(n_number=5, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    fig = compile({"data": [_trace("a", type="scatter", meta=meta)]}, {"a": area_mean}, theme=theme)
    assert _data(fig)[0]["line"]["color"] == "#123456"


def test_colorblind_template_keeps_its_colorway_under_a_theme(tmp_path):
    from weather_skills_plotting.palettes import COLORBLIND, load_theme

    path = tmp_path / "theme.json"
    path.write_text(json.dumps({"template": {"layout": {"colorway": ["#123456", "#654321"]}}}))
    meta = {"bind": "series", "along": "number"}
    area_mean = make_forecast(n_number=2, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    spec = {
        "data": [_trace("a", type="scatter", meta=meta)],
        "layout": {"template": "colorblind"},
    }
    fig = compile(spec, {"a": area_mean}, theme=load_theme(path))
    assert _data(fig)[0]["line"]["color"] == COLORBLIND[0]


def test_partial_theme_dict_gets_the_standard_keys():
    from weather_skills_plotting.palettes import builtin_palettes

    ds = make_gridded(n_time=1)
    fig = compile({"data": [_trace("a")]}, {"a": ds}, theme={"palettes": builtin_palettes()})
    assert any(str(t["uid"]).startswith("overlay-borders") for t in _data(fig, "scatter"))


def test_precip_rate_keeps_its_mm_units_for_a_spec_palette():
    # unit-convert to mm/h: class edges in mm/h must meet mm/h values, not mm/day.
    ds = make_gridded(n_time=1, fill=2.0, units="mm h-1")
    ds["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    palette = {"colors": ["#ffffff", "#7fff7f", "#3dc83d", "#ff4d4d"], "bounds": [0, 1, 3, 5, 100]}
    fig = compile({"data": [_trace("a", meta={"palette": palette})]}, {"a": ds})
    heat = _data(fig, "heatmap")[0]
    assert np.allclose(np.asarray(heat["customdata"], dtype=float), 2.0)
    assert "mm/h" in _layout(fig)["coloraxis"]["colorbar"]["title"]["text"]
    # A selected 6 hour mean (aggregation_period set, no step axis left) stays mm/h too.
    one = ds.isel(time=0)
    one["precip"].attrs["aggregation_period"] = "6 hour"
    heat = _data(compile({"data": [_trace("a", meta={"palette": palette})]}, {"a": one}), "heatmap")
    assert np.allclose(np.asarray(heat[0]["customdata"], dtype=float), 2.0)
    # A flux that is not in mm still reads in mm/day.
    ds = make_gridded(n_time=1, fill=1 / 86400, units="kg m-2 s-1")
    ds["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    heat = _data(compile({"data": [_trace("a")]}, {"a": ds}), "heatmap")[0]
    assert np.allclose(np.asarray(heat["customdata"], dtype=float), 1.0)


def test_dateline_grid_and_points_draw_on_one_continuous_window():
    # A 150E..80W fetch comes back on -180..180 with a gap; it must not span the globe.
    lons = tuple(float(x) for x in [*range(-180, -79, 10), *range(150, 180, 10)])
    grid = make_gridded(n_time=1, lats=(-5.0, 0.0, 5.0), lons=lons)
    station = make_station(n_station=1, n_time=1).isel(time=0)
    station = station.assign_coords(
        latitude=("station_id", [0.0]), longitude=("station_id", [-150.0])
    )
    spec = {"data": [_trace("a"), _trace("b", type="scatter", meta={"bind": "points"})]}
    fig = compile(spec, {"a": grid, "b": station})
    lo, hi = _layout(fig)["xaxis"]["range"]
    assert 140 < lo < 155 and 275 < hi < 290
    marker = next(t for t in _data(fig, "scatter") if t["uid"].startswith("b"))
    assert np.allclose(np.asarray(marker["x"], dtype=float), [210.0])
    labels = _layout(fig)["xaxis"]["ticktext"]
    assert "180°" in labels and "-160°" in labels


def test_sel_on_a_model_calendar_picks_the_nearest_date():
    import cftime

    times = [cftime.datetime(2099, m, 16, calendar="360_day") for m in (1, 2, 3)]
    ds = make_gridded(n_time=3).assign_coords(time=times)
    for day in ("2099-02-20", "2099-02-30"):
        spec = {"data": [_trace("a", source={"sel": {"time": day}})]}
        heat = _data(compile(spec, {"a": ds}), "heatmap")
        assert len(heat) == 1


def test_temperature_difference_is_diverging_and_absolute_is_not():
    warm = make_gridded(n_time=1, name="sst", fill=2.0, units="delta_degC")
    warm["sst"].attrs["standard_name"] = "sea_surface_temperature"
    axis = _layout(compile({"data": [_trace("a")]}, {"a": warm}))["coloraxis"]
    # An all-positive anomaly is still centred on zero.
    assert axis["cmin"] == -axis["cmax"]
    sst = make_gridded(n_time=1, name="sst", units="degree_Celsius")
    sst["sst"].values[..., 0] = -1.8
    sst["sst"].values[..., 1:] = 28.0
    sst["sst"].attrs["standard_name"] = "sea_surface_temperature"
    axis = _layout(compile({"data": [_trace("a")]}, {"a": sst}))["coloraxis"]
    assert axis["cmin"] == pytest.approx(-1.8) and axis["cmax"] == pytest.approx(28.0)
    # Side by side they are two quantities: two colorbars.
    spec = {"data": [_trace("a"), _trace("b", xaxis="x2", yaxis="y2")]}
    heat = _data(compile(spec, {"a": sst, "b": warm}), "heatmap")
    assert heat[0]["coloraxis"] != heat[1]["coloraxis"]


def test_input_names_title_side_by_side_panels_and_plain_traces_repeat():
    a, b = make_gridded(n_time=1), make_gridded(n_time=1, fill=3.0)
    spec = {
        "data": [
            _trace("CHIRPS"),
            _trace("IMERG", xaxis="x2", yaxis="y2"),
            {"uid": "city", "type": "scatter", "mode": "markers", "x": [11.0], "y": [2.0]},
        ]
    }
    fig = compile(spec, {"CHIRPS": a, "IMERG": b})
    titles = [
        x["text"] for x in _layout(fig)["annotations"] if x.get("name", "").startswith("panel")
    ]
    assert titles == ["CHIRPS", "IMERG"]
    cities = [t for t in fig.data if t["uid"].startswith("city")]
    assert sorted(t["xaxis"] for t in cities) == ["x", "x2"]
    assert {t["marker"]["color"] for t in cities} == {"#262626"}


def test_member_panels_are_titled_by_member():
    from weather_skills_plotting.labels import panel_title

    da = xr.DataArray(
        [0.0, 1.0], dims=["number"], coords={"number": ("number", [0, 1], {"units": "1"})}
    )
    assert panel_title(da, "number", 1, [0, 1]) == "Member 1"


def test_mistyped_uid_names_the_real_one():
    from weather_skills_plotting.spec import merge_traces

    with pytest.raises(UsageError, match="did you mean 'OBS'"):
        merge_traces([{"uid": "OBS", "type": "heatmap"}], [{"uid": "obs", "zmin": 0}])
