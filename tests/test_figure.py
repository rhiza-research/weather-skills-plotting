"""Figure assembly: binds, panels, color axes, overlays, chart defaults."""

import json

import numpy as np
import pytest
import xarray as xr
from weather_skills_core.errors import UsageError

from conftest import make_forecast, make_gridded, make_station
from weather_skills_plotting import compile


def _trace(uid, **kw):
    # A map of the fixtures' precip unless the test names its own mapping.
    meta = kw.pop("meta", None) or {"z": "precip"}
    source = {"input": kw.pop("input", uid), **kw.pop("source", {})}
    return {"uid": uid, "type": kw.pop("type", "heatmap"), "meta": {"source": source, **meta}, **kw}


def _layout(fig):
    return fig.to_plotly_json()["layout"]


def _data(fig, kind=None):
    """Traces as Plotly objects (arrays stay numpy; JSON would base64 them)."""
    return [t for t in fig.data if kind is None or t["type"] == kind]


def test_heatmap_panels_each_time_with_one_discrete_colorbar():
    ds = make_gridded(n_time=3)
    fig = compile({"data": [_trace("a", meta={"z": "precip"})]}, {"a": ds})
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
    assert "%{customdata" in heat[0]["hovertemplate"]
    assert layout["yaxis"]["scaleanchor"] == "x"


def test_continuous_map_hovers_z_without_a_customdata_copy():
    ds = make_gridded(n_time=1, name="t2m", units="K")
    heat = _data(compile({"data": [_trace("a", meta={"z": "t2m"})]}, {"a": ds}), "heatmap")[0]
    assert heat["customdata"] is None
    assert "%{z:.4g}" in heat["hovertemplate"]


def test_user_trace_keys_lift_to_coloraxis_and_win():
    ds = make_gridded(n_time=1)
    spec = {
        "data": [
            _trace(
                "a",
                zmin=0,
                zmax=20,
                colorscale="Blues",
                colorbar={"title": {"text": "Rain"}},
                meta={"z": "precip"},
            )
        ]
    }
    axis = _layout(compile(spec, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (0, 20)
    assert axis["colorbar"]["title"]["text"] == "Rain"
    assert axis["colorscale"][0][1].lower() in ("rgb(247,251,255)", "#f7fbff")


def test_layout_coloraxis_override_wins():
    ds = make_gridded(n_time=1)
    spec = {
        "data": [_trace("a", meta={"z": "precip"})],
        "layout": {"coloraxis": {"colorbar": {"len": 0.3}}},
    }
    assert _layout(compile(spec, {"a": ds}))["coloraxis"]["colorbar"]["len"] == 0.3


def test_side_by_side_inputs_get_their_own_grid_and_one_scale_per_quantity():
    a = make_gridded(n_time=1)
    b = make_gridded(n_time=1, name="tp", lats=(1.5, 2.5), lons=(10.5, 12.5), fill=3.0)
    spec = {
        "data": [
            _trace("a", meta={"z": "precip"}),
            _trace("ECMWF", xaxis="x2", yaxis="y2", name="hover only", meta={"z": "tp"}),
        ]
    }
    fig = compile(spec, {"a": a, "ECMWF": b})
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
            _trace("a", coloraxis="coloraxis", meta={"z": "precip"}),
            _trace("b", xaxis="x2", yaxis="y2", coloraxis="coloraxis", meta={"z": "precip"}),
        ]
    }
    fig = compile(spec, {"a": a, "b": b})
    assert {t["coloraxis"] for t in _data(fig, "heatmap")} == {"coloraxis"}
    assert "coloraxis2" not in _layout(fig)


def test_one_trace_showscale_true_shows_its_shared_bar():
    # Rain on four panels shares one bar; the trace asking for it wins over the
    # others' showscale false, wherever it sits in the list.
    rain = [
        _trace(
            f"r{i}",
            input="r",
            showscale=(i == 0),
            meta={"z": "precip"},
            **({"xaxis": f"x{i + 1}"} if i else {}),
        )
        for i in range(4)
    ]
    prob = make_gridded(n_time=1, name="prob", units="1", fill=0.3)
    spec = {"data": [*rain, _trace("p", xaxis="x5", showscale=True, meta={"z": "prob"})]}
    layout = _layout(compile(spec, {"r": make_gridded(n_time=1), "p": prob}))
    assert layout["coloraxis"]["showscale"] is True
    assert layout["coloraxis2"]["showscale"] is True


def test_spec_placed_colorbars_keep_their_position():
    # A bar given x / y is not turned into an automatic horizontal bar under its column.
    prob = make_gridded(n_time=1, name="prob", units="1", fill=0.3)
    spec = {
        "data": [
            _trace("a", colorbar={"x": 1.01, "y": 0.75, "len": 0.45}, meta={"z": "precip"}),
            _trace(
                "p", xaxis="x2", colorbar={"x": 1.01, "y": 0.25, "len": 0.45}, meta={"z": "prob"}
            ),
        ]
    }
    layout = _layout(compile(spec, {"a": make_gridded(n_time=1), "p": prob}))
    for name, y in (("coloraxis", 0.75), ("coloraxis2", 0.25)):
        bar = layout[name]["colorbar"]
        assert (bar["x"], bar["y"]) == (1.01, y)
        assert "orientation" not in bar and "yref" not in bar and "xanchor" not in bar
        assert layout[name].get("showscale") is not False
    # Room on the right for the bars, none reserved below.
    assert layout["margin"]["r"] > layout["margin"]["l"]
    assert layout["margin"]["b"] < 60


def test_faceted_side_by_side_is_an_error():
    a = make_gridded(n_time=2)
    with pytest.raises(UsageError, match="single map"):
        grid = {"z": "precip"}
        spec = {"data": [_trace("a", meta=grid), _trace("b", input="a", xaxis="x2", meta=grid)]}
        compile(spec, {"a": a})


def test_leftover_dim_is_an_error_with_hint():
    ds = make_forecast(n_step=2)  # tests/conftest: number × step × lat × lon
    ds = ds.expand_dims(level=[850, 500])
    with pytest.raises(UsageError, match="dimensions 'level', 'number' remain.*isel"):
        compile({"data": [_trace("a", meta={"z": "tp"})]}, {"a": ds})


def test_step_panels_for_forecast():
    fig = compile(
        {"data": [_trace("a", meta={"z": "tp"})]}, {"a": make_forecast(n_number=0, n_step=4)}
    )
    assert len(_data(fig, "heatmap")) == 4


def test_ensemble_map_is_not_averaged():
    # The plotter selects but never averages: summarize-dim makes the ensemble mean.
    with pytest.raises(UsageError, match="'number' remains.*summarize-dim"):
        compile(
            {"data": [_trace("a", meta={"z": "tp"})]}, {"a": make_forecast(n_number=3, n_step=4)}
        )


def test_isel_and_bbox_subset():
    ds = make_gridded(n_time=3)
    spec = {
        "data": [_trace("a", source={"isel": {"time": 1}}, meta={"z": "precip"})],
        "layout": {"meta": {"geo": {"bbox": [3, 11, 1, 12]}}},
    }
    fig = compile(spec, {"a": ds})
    heat = _data(fig, "heatmap")
    assert len(heat) == 1
    assert list(heat[0]["x"]) == [11.0, 12.0]
    assert _layout(fig)["xaxis"]["range"] == [11.0, 12.0]


def test_contour_uses_class_edges_as_levels():
    spec = {"data": [_trace("a", type="contour", meta={"z": "precip"})]}
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
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace(
                "c",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            ),
        ]
    }
    fig = compile(spec, {"a": _pressure(), "c": stations})
    point = next(t for t in fig.data if t["uid"] == "c")
    assert len(point["x"]) == 1


def test_line_only_contour_over_shading_keeps_the_shading_colorbar():
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace(
                "iso",
                input="a",
                type="contour",
                contours={"coloring": "none"},
                showscale=False,
                meta={"z": "msl"},
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


def test_contour_over_heatmap_defaults_to_labeled_isobars_every_4_hpa():
    # --layer heatmap:msl.zarr --layer contour:msl.zarr with no spec.
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace("iso", input="a", type="contour", meta={"z": "msl"}),
        ]
    }
    fig = compile(spec, {"a": _pressure()})
    iso = _data(fig, "contour")[0]
    assert iso["coloraxis"] is None and iso["showscale"] is False
    assert iso["contours"]["coloring"] == "none" and iso["contours"]["showlabels"] is True
    assert iso["line"]["color"] == "black"
    assert iso["autocontour"] is False
    assert (iso["contours"]["start"], iso["contours"]["end"], iso["contours"]["size"]) == (
        988,
        1032,
        4,
    )
    assert "coloraxis2" not in _layout(fig)


def test_contour_over_heatmap_keeps_a_fill_or_levels_the_spec_asks_for():
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace(
                "iso",
                input="a",
                type="contour",
                contours={"start": 1000, "size": 10},
                meta={"z": "msl"},
            ),
        ]
    }
    iso = _data(compile(spec, {"a": _pressure()}), "contour")[0]
    assert iso["contours"]["coloring"] == "none"
    assert (iso["contours"]["start"], iso["contours"]["size"]) == (1000, 10)
    assert iso["contours"]["end"] is None
    spec["data"][1]["contours"] = {"coloring": "fill"}
    iso = _data(compile(spec, {"a": _pressure()}), "contour")[0]
    assert iso["contours"]["coloring"] == "fill" and iso["coloraxis"] == "coloraxis"


def test_text_only_points_have_no_colorbar_and_keep_customdata_in_images(tmp_path, monkeypatch):
    import plotly.io as pio

    from weather_skills_plotting import export

    stations = make_station(n_station=3, n_time=1).isel(time=0)
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace(
                "c",
                type="scatter",
                mode="text",
                texttemplate="<b>H</b><br>%{customdata:.0f}",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
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
        spec = {
            "data": [
                _trace(
                    "c",
                    type="scatter",
                    mode=mode,
                    meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
                )
            ]
        }
        trace = next(t for t in compile(spec, {"c": stations}).data if t["uid"] == "c")
        assert len(trace["x"]) == n and len(trace["customdata"]) == n
    # The station with no value is a ×, not a filled dot that reads as a class.
    assert list(trace["marker"]["symbol"]) == ["circle", "x", "circle"]


def test_local_extrema_points_print_h_or_l_unless_the_spec_restyles_them():
    # --layer heatmap:msl.zarr --layer scatter:lows.zarr with no spec.
    lows = make_station(n_station=3, n_time=1).isel(time=0)
    lows["precip"].attrs["extremum_kind"] = "low"
    lows["precip"].values[1] = np.nan
    spec = {
        "data": [
            _trace("a", meta={"z": "msl"}),
            _trace(
                "c",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            ),
        ]
    }
    fig = compile(spec, {"a": _pressure(), "c": lows})
    text = next(t for t in fig.data if t["uid"] == "c")
    assert text["mode"] == "text" and text["texttemplate"].startswith("<b>L</b>")
    assert len(text["x"]) == 2 and text["marker"]["coloraxis"] is None
    assert "coloraxis2" not in _layout(fig)
    spec["data"][1]["mode"] = "markers"
    marks = next(t for t in compile(spec, {"a": _pressure(), "c": lows}).data if t["uid"] == "c")
    assert marks["mode"] == "markers" and len(marks["x"]) == 3


def test_non_precip_gets_continuous_scale_symmetric_when_diverging():
    ds = make_gridded(n_time=1, name="t2m", units="degree_Celsius")
    ds["t2m"].values[:] = np.linspace(-2, 4, 12).reshape(1, 3, 4)
    axis = _layout(compile({"data": [_trace("a", meta={"z": "t2m"})]}, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (-4, 4)
    assert "ticktext" not in axis["colorbar"]


def test_sea_level_pressure_is_red_blue_with_white_at_standard_atmosphere():
    # Drawn in the file's units: white sits at 1013.25 hPa, or 101325 Pa.
    for units, scale in (("hPa", 1.0), ("Pa", 100.0)):
        ds = make_gridded(n_time=1, name="msl", units=units)
        ds["msl"].values[:] = np.linspace(1008, 1036, 12).reshape(1, 3, 4) * scale
        ds["msl"].attrs["standard_name"] = "air_pressure_at_mean_sea_level"
        axis = _layout(compile({"data": [_trace("a", meta={"z": "msl"})]}, {"a": ds}))["coloraxis"]
        assert axis["colorscale"][0][1] == "rgb(5,48,97)"  # RdBu_r: blue lows
        assert (axis["cmin"], axis["cmax"]) == pytest.approx((990.5 * scale, 1036 * scale))


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
            _trace("a", meta={"z": "precip"}),
            _trace(
                "b",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            ),
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
    grid = {"z": "precip"}
    off = compile(
        {"data": [_trace("a", meta=grid)], "layout": {"meta": {"overlays": False}}}, {"a": ds}
    )
    assert not [t for t in _data(off) if t["uid"].startswith("overlay")]
    styled = compile(
        {
            "data": [_trace("a", meta=grid)],
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
                _trace(
                    "a",
                    type="scatter",
                    source=src,
                    meta={"x": "step", "y": "tp", "along": "number"},
                )
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
                    meta={"x": "step", "y": "tp", "along": "number", "band": [10, 90]},
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
                    meta={
                        "x": "step",
                        "y": "tp",
                        "along": "number",
                        "band": [10, 90],
                        "members": False,
                    },
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
                    meta={"x": "step", "y": "tp", "along": "number", "along_color": "cycle"},
                )
            ]
        },
        {"a": ds},
    )
    assert [t["name"] for t in _data(cycle)] == ["0", "1", "2", "3", "4"]


def test_series_needs_select_or_along():
    with pytest.raises(UsageError, match="has dims.*that x 'time' lacks.*summarize-dim"):
        compile(
            {"data": [_trace("a", type="scatter", meta={"x": "time", "y": "precip"})]},
            {"a": make_gridded()},
        )


def test_several_variables_need_one_chosen():
    t = np.arange("2026-10-17", "2026-10-20", dtype="datetime64[D]")
    ds = xr.Dataset(
        {"east": (("time",), [1.0, 2, 3]), "dmi": (("time",), [0.1, 0.2, 0.3])}, {"time": t}
    )
    with pytest.raises(UsageError, match=r"y is not set.*east, dmi"):
        compile({"data": [_trace("a", type="scatter", meta={"x": "time"})]}, {"a": ds})
    spec = {"data": [_trace("a", type="scatter", meta={"x": "time", "y": "dmi"})]}
    assert list(_data(compile(spec, {"a": ds}))[0]["y"]) == [0.1, 0.2, 0.3]


def test_series_forecast_plots_valid_time():
    ds = make_forecast(n_number=0, n_step=3).mean(["latitude", "longitude"], keep_attrs=True)
    fig = compile({"data": [_trace("a", type="scatter", meta={"x": "step", "y": "tp"})]}, {"a": ds})
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


def _counties():
    names = ["Turkana", "Kisumu", "Nairobi", "Mombasa"]
    ds = xr.Dataset(
        {"precip_7d": (("county",), [12.0, np.nan, 40.5, 3.25], {"units": "mm"})},
        coords={"county": np.array(names, dtype=object)},
    )
    return ds, names


def test_xy_names_on_y_are_a_category_axis():
    ds, names = _counties()
    spec = {
        "data": [
            {
                "uid": "0",
                "type": "scatter",
                "mode": "markers+text",
                "texttemplate": "%{x:.1f}",
                "meta": {"x": "precip_7d", "y": "county"},
            }
        ],
        "layout": {"yaxis": {"categoryorder": "total ascending"}},
    }
    tr = _data(compile(spec, {"0": ds}))[0]
    # The county with no value is dropped, not drawn at 0.
    assert list(tr["y"]) == ["Turkana", "Nairobi", "Mombasa"]
    assert list(tr["x"]) == [12.0, 40.5, 3.25]
    # The user's labels win; none are generated, and edge labels are not clipped.
    assert tr["text"] is None and tr["texttemplate"] == "%{x:.1f}"
    assert tr["cliponaxis"] is False


def test_xy_names_on_x_and_missing_names():
    ds, names = _counties()
    ds = ds.assign(county=np.array(["Turkana", None, "Nairobi", np.nan], dtype=object))
    ds["precip_7d"].values[1] = 5.0
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "county", "y": "precip_7d"}}]}
    tr = _data(compile(spec, {"0": ds}))[0]
    assert list(tr["x"]) == ["Turkana", "Nairobi"] and list(tr["y"]) == [12.0, 40.5]
    assert tr["text"] is None  # names already on the axis


def test_xy_numbers_along_named_dim_keep_point_labels():
    ds = xr.Dataset(
        {"bias": (("model",), [0.5, -1.0, 2.0]), "mae": (("model",), [3.0, 4.0, 2.5])},
        coords={"model": ["ecmwf", "gefs", "cumulus"]},
    )
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "bias", "y": "mae"}}]}
    tr = _data(compile(spec, {"0": ds}))[0]
    assert list(tr["text"]) == ["ecmwf", "gefs", "cumulus"]


def test_xy_dates_and_leads_on_an_axis():
    import cftime

    times = np.array(["2026-10-13", "NaT", "2026-10-15"], dtype="datetime64[ns]")
    ds = xr.Dataset(
        {
            "precip": (("i",), [1.0, 2.0, 3.0]),
            "when": (("i",), times),
            "lead": (("i",), np.array([1, 2, 3], dtype="timedelta64[D]")),
            "model_day": (
                ("i",),
                np.array([cftime.DatetimeNoLeap(2026, 10, d) for d in (13, 14, 15)], dtype=object),
            ),
        }
    )

    def xy(x):
        spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": x, "y": "precip"}}]}
        return _data(compile(spec, {"0": ds}))[0]

    tr = xy("when")
    assert len(tr["x"]) == 2 and list(tr["y"]) == [1.0, 3.0]
    assert list(xy("lead")["x"]) == [1.0, 2.0, 3.0]  # leads in days
    assert list(xy("model_day")["x"])[0].startswith("2026-10-13")


def test_xy_counts_values_when_names_are_on_y():
    from weather_skills_plotting.qa import figure_counts

    ds, _ = _counties()
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "precip_7d", "y": "county"}}]}
    assert figure_counts(compile(spec, {"0": ds})) == [("0", 3, 3)]


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


def test_xy_against_time_points_to_along_and_align():
    # The chat case: weekly members against a day-of-year coordinate on time.
    time = np.arange("2026-10-25", "2026-11-15", 7, dtype="datetime64[D]").astype("datetime64[ns]")
    ds = xr.Dataset(
        {"tp": (("time", "number"), np.ones((3, 4))), "doy": (("time",), [298.0, 305.0, 312.0])},
        coords={"time": time, "number": np.arange(4)},
    )
    spec = {"data": [{"uid": "0", "type": "scatter", "meta": {"x": "doy", "y": "tp"}}]}
    with pytest.raises(
        UsageError, match=r'meta.x "time" and .*along \'number\'.*align "dayofyear"'
    ):
        compile(spec, {"0": ds})


@pytest.mark.parametrize("key, value", [("along", "number"), ("align", "dayofyear")])
def test_xy_rejects_series_keys(key, value):
    meta = {"x": "a", "y": "b", key: value}
    with pytest.raises(UsageError, match=f"{key} needs x to be the time or step dimension"):
        compile({"data": [{"uid": "0", "type": "scatter", "meta": meta}]}, {"0": make_gridded()})


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
        {
            "data": [
                {
                    "uid": "a",
                    "type": "barpolar",
                    "meta": {"bind": "windrose", "source": {"input": "a"}},
                }
            ]
        },
        {"a": ds},
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
    with pytest.raises(
        UsageError, match="bind 'speed' draws as type contour or heatmap, not 'bar'"
    ):
        compile({"data": [_trace("a", type="bar", meta={"bind": "speed"})]}, {"a": make_gridded()})


def test_unknown_input():
    with pytest.raises(UsageError, match="input 'zz' is not an input"):
        compile({"data": [_trace("a", input="zz", meta={"z": "precip"})]}, {"a": make_gridded()})


def test_two_scales_on_one_panel_do_not_overlap():
    grid = make_gridded(n_time=1, lats=(-1.0, 0.0, 1.0), lons=(36.0, 37.0, 38.0))
    stations = make_station(n_station=3, n_time=1)
    stations["precip"].attrs["units"] = "mm"  # different label → its own colorbar
    spec = {
        "data": [
            _trace("a", meta={"z": "precip"}),
            _trace(
                "b",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            ),
        ]
    }
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
                "meta": {
                    "x": "time",
                    "y": "precip",
                    "align": "dayofyear",
                    "source": {"input": "a"},
                },
            },
            {
                "uid": "b",
                "type": "scatter",
                "meta": {
                    "x": "time",
                    "y": "precip",
                    "align": "dayofyear",
                    "source": {"input": "b"},
                },
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
        "data": [
            {
                "uid": "a",
                "type": "scatter",
                "meta": {"x": "time", "y": "precip", "align": "dayofyear"},
            }
        ]
    }
    x = list(_data(compile(spec, {"a": ds}))[0]["x"])
    assert [v[:10] for v in x] == ["2001-02-28", "2001-02-28", "2001-03-01"]


def test_cf_flag_field_gets_named_classes():
    ds = make_gridded(n_time=1, name="event_hit", units=None)
    ds["event_hit"].values[:] = np.resize([-1.0, 0.0, 1.0], ds["event_hit"].shape)
    ds["event_hit"].attrs.update(flag_values=[-1, 0, 1], flag_meanings="disagree below hit")
    fig = compile({"data": [_trace("a", meta={"z": "event_hit"})]}, {"a": ds})
    bar = _layout(fig)["coloraxis"]["colorbar"]
    assert bar["ticktext"] == ["disagree", "below", "hit"]
    assert bar["tickvals"] == [0, 1, 2]
    z = np.asarray(_data(fig, "heatmap")[0]["z"], float)
    assert sorted(set(z.ravel().tolist())) == [0.0, 1.0, 2.0]


def test_default_precip_palette_names_follow_aggregation_window():
    from weather_skills_plotting.palettes import precip_window_palette
    from weather_skills_plotting.themes import load_theme

    # An all-positive field with no precip name: detection would not call it an anomaly.
    ds = make_gridded(n_time=1, name="diff", units="mm")
    ds["diff"].values[:] = 12.0
    ds["diff"].attrs["aggregation_period"] = "30 day"
    spec = {"data": [_trace("a", meta={"z": "diff", "palette": "Default_Precip_Anom"})]}
    bar = _layout(compile(spec, {"a": ds}))["coloraxis"]["colorbar"]
    month = precip_window_palette("ppt_anom_month", load_theme()["palettes"])
    assert bar["ticktext"] == [f"{b:g}" for b in month["bounds"]]

    spec = {"data": [_trace("a", meta={"z": "diff", "palette": "default_precip"})]}
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
    axis = _layout(compile({"data": [_trace("a", meta={"z": "precip"})]}, {"a": ds}))["coloraxis"]
    # A continuous scale (no class ticks) and a label that says what it is.
    assert "ticktext" not in axis["colorbar"]
    assert axis["colorbar"]["title"]["text"] == "Precipitation std. dev. (number) [mm]"


def test_member_panels_titled_and_bad_panel_title_named():
    ds = make_forecast(n_number=3, n_step=1).isel(step=0)
    fig = compile({"data": [_trace("a", meta={"z": "tp", "facet": "number"})]}, {"a": ds})
    titles = [
        a["text"] for a in _layout(fig)["annotations"] if a.get("name", "").startswith("panel")
    ]
    assert titles == ["Member 0", "Member 1", "Member 2"]
    with pytest.raises(
        UsageError,
        match=r"panel-title-0.*row by row.*panel-title-1 \(Member 0\), "
        r"panel-title-2 \(Member 1\), panel-title-3 \(Member 2\)",
    ):
        compile(
            {
                "data": [_trace("a", meta={"z": "tp", "facet": "number"})],
                "layout": {"annotations": [{"name": "panel-title-0", "text": "x"}]},
            },
            {"a": ds},
        )


def test_panel_titles_follow_axis_number_not_trace_order():
    # Two columns, traces placed down the first column: the second trace is on
    # xaxis3, so its title is panel-title-3 and panel-title-2 is no panel.
    ds = make_gridded(n_time=1).isel(time=0)
    data = [_trace("a"), _trace("b", xaxis="x3", yaxis="y3")]
    layout = {"grid": {"rows": 2, "columns": 2, "pattern": "independent"}}
    fig = compile(
        {
            "data": data,
            "layout": {**layout, "annotations": [{"name": "panel-title-3", "text": "B"}]},
        },
        {"a": ds, "b": ds},
    )
    by_name = {a.get("name"): a for a in _layout(fig)["annotations"]}
    assert by_name["panel-title-3"]["text"] == "B"
    assert by_name["panel-title-3"]["xref"] == "x3 domain"
    with pytest.raises(
        UsageError,
        match=r"panel-title-1 \(row 1, column 1: a\), panel-title-3 \(row 2, column 1: b\)",
    ):
        compile(
            {"data": data, "layout": {**layout, "annotations": [{"name": "panel-title-2"}]}},
            {"a": ds, "b": ds},
        )


def test_user_annotations_add_to_panel_titles():
    ds = make_gridded(n_time=2)
    ann = {"text": "Mine", "xref": "x2 domain", "yref": "y2 domain", "x": 0.5, "y": 1.04}
    spec = {"data": [_trace("a", meta={"z": "precip"})], "layout": {"annotations": [ann]}}
    fig = compile(spec, {"a": ds})
    assert [a["text"] for a in _layout(fig)["annotations"]] == ["1 Jan '26", "2 Jan '26", "Mine"]
    # A chart has no panel titles; an annotation above it is just an annotation.
    series = ds.mean(["latitude", "longitude"])
    spec = {
        "data": [_trace("s", type="scatter", meta={"x": "time", "y": "precip"})],
        "layout": {"annotations": [dict(ann, yref="y domain")]},
    }
    assert [a["text"] for a in _layout(compile(spec, {"s": series}))["annotations"]] == ["Mine"]


def test_string_bbox_and_horizontal_colorbar_below():
    ds = make_gridded(n_time=2)
    fig = compile(
        {
            "data": [_trace("a", meta={"z": "precip"})],
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
        "data": [
            _trace("a", meta={"z": "t2m"}),
            _trace(
                "b",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "temperature"}},
            ),
        ],
        # Smaller than one 1.5° cell and centred on none.
        "layout": {"meta": {"geo": {"bbox": [0.2, 36.5, -0.6, 37.1]}}},
    }
    fig = compile(spec, {"a": grid, "b": stations})
    field = next(t for t in _data(fig) if t["uid"].startswith("a"))
    assert np.asarray(field["z"]).size > 0
    points = next(t for t in _data(fig) if t["uid"].startswith("b"))
    assert points["marker"]["coloraxis"] == field["coloraxis"]


def test_theme_file_sets_palette_colorway_and_overlays(tmp_path):
    from weather_skills_plotting.themes import load_theme

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
    fig = compile({"data": [_trace("a", meta={"z": "precip"})]}, {"a": ds}, theme=theme)
    bar = _layout(fig)["coloraxis"]["colorbar"]
    assert list(bar["ticktext"]) == ["0", "1", "10"]
    borders = [t for t in _data(fig, "scatter") if str(t["uid"]).startswith("overlay-borders")]
    assert borders and all(t["line"]["color"] == "#ff0000" for t in borders)
    # A palette that exists only in the theme file is a known meta.palette name.
    fig = compile(
        {"data": [_trace("a", meta={"z": "precip", "palette": "agency"})]}, {"a": ds}, theme=theme
    )
    assert list(_layout(fig)["coloraxis"]["colorbar"]["ticktext"]) == ["0", "1", "10"]
    # Explicit series colors (ensemble members, band) follow the template's colorway.
    meta = {"x": "step", "y": "tp", "along": "number", "band": [10, 90]}
    area_mean = make_forecast(n_number=5, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    fig = compile({"data": [_trace("a", type="scatter", meta=meta)]}, {"a": area_mean}, theme=theme)
    assert _data(fig)[0]["line"]["color"] == "#123456"


def test_colorblind_template_keeps_its_colorway_under_a_theme(tmp_path):
    from weather_skills_plotting.themes import default_theme, load_theme

    path = tmp_path / "theme.json"
    path.write_text(json.dumps({"template": {"layout": {"colorway": ["#123456", "#654321"]}}}))
    meta = {"x": "step", "y": "tp", "along": "number"}
    area_mean = make_forecast(n_number=2, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    spec = {
        "data": [_trace("a", type="scatter", meta=meta)],
        "layout": {"template": "colorblind"},
    }
    fig = compile(spec, {"a": area_mean}, theme=load_theme(path))
    assert _data(fig)[0]["line"]["color"] == default_theme()["palettes"]["colorblind"]["colors"][0]


def test_precip_rate_keeps_its_mm_units_for_a_spec_palette():
    # unit-convert to mm/h: class edges in mm/h must meet mm/h values, not mm/day.
    ds = make_gridded(n_time=1, fill=2.0, units="mm h-1")
    ds["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    palette = {"colors": ["#ffffff", "#7fff7f", "#3dc83d", "#ff4d4d"], "bounds": [0, 1, 3, 5, 100]}
    fig = compile({"data": [_trace("a", meta={"z": "precip", "palette": palette})]}, {"a": ds})
    heat = _data(fig, "heatmap")[0]
    assert np.allclose(np.asarray(heat["customdata"], dtype=float), 2.0)
    assert "mm/h" in _layout(fig)["coloraxis"]["colorbar"]["title"]["text"]
    # A selected 6 hour mean (aggregation_period set, no step axis left) stays mm/h too.
    one = ds.isel(time=0)
    one["precip"].attrs["aggregation_period"] = "6 hour"
    heat = _data(
        compile({"data": [_trace("a", meta={"z": "precip", "palette": palette})]}, {"a": one}),
        "heatmap",
    )
    assert np.allclose(np.asarray(heat[0]["customdata"], dtype=float), 2.0)
    # A flux not in mm is drawn as stored, with a note to unit-convert.
    ds = make_gridded(n_time=1, fill=1 / 86400, units="kg m-2 s-1")
    ds["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    heat = _data(compile({"data": [_trace("a", meta={"z": "precip"})]}, {"a": ds}), "heatmap")[0]
    raw = heat["customdata"] if heat["customdata"] is not None else heat["z"]
    assert np.allclose(np.asarray(raw, dtype=float), 1 / 86400)


def test_dateline_grid_and_points_draw_on_one_continuous_window():
    # A 150E..80W fetch comes back on -180..180 with a gap; it must not span the globe.
    lons = tuple(float(x) for x in [*range(-180, -79, 10), *range(150, 180, 10)])
    grid = make_gridded(n_time=1, lats=(-5.0, 0.0, 5.0), lons=lons)
    station = make_station(n_station=1, n_time=1).isel(time=0)
    station = station.assign_coords(
        latitude=("station_id", [0.0]), longitude=("station_id", [-150.0])
    )
    spec = {
        "data": [
            _trace("a", meta={"z": "precip"}),
            _trace(
                "b",
                type="scatter",
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            ),
        ]
    }
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
        spec = {"data": [_trace("a", source={"sel": {"time": day}}, meta={"z": "precip"})]}
        heat = _data(compile(spec, {"a": ds}), "heatmap")
        assert len(heat) == 1


def test_temperature_difference_is_diverging_and_absolute_is_not():
    warm = make_gridded(n_time=1, name="sst", fill=2.0, units="delta_degC")
    warm["sst"].attrs["standard_name"] = "sea_surface_temperature"
    grid = {"z": "sst"}
    axis = _layout(compile({"data": [_trace("a", meta=grid)]}, {"a": warm}))["coloraxis"]
    # An all-positive anomaly is still centred on zero.
    assert axis["cmin"] == -axis["cmax"]
    sst = make_gridded(n_time=1, name="sst", units="degree_Celsius")
    sst["sst"].values[..., 0] = -1.8
    sst["sst"].values[..., 1:] = 28.0
    sst["sst"].attrs["standard_name"] = "sea_surface_temperature"
    axis = _layout(compile({"data": [_trace("a", meta=grid)]}, {"a": sst}))["coloraxis"]
    assert axis["cmin"] == pytest.approx(-1.8) and axis["cmax"] == pytest.approx(28.0)
    # Side by side they are two quantities: two colorbars.
    spec = {"data": [_trace("a", meta=grid), _trace("b", xaxis="x2", yaxis="y2", meta=grid)]}
    heat = _data(compile(spec, {"a": sst, "b": warm}), "heatmap")
    assert heat[0]["coloraxis"] != heat[1]["coloraxis"]


def test_input_names_title_side_by_side_panels_and_plain_traces_repeat():
    a, b = make_gridded(n_time=1), make_gridded(n_time=1, fill=3.0)
    spec = {
        "data": [
            _trace("CHIRPS", meta={"z": "precip"}),
            _trace("IMERG", xaxis="x2", yaxis="y2", meta={"z": "precip"}),
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


def test_second_y_axis_gets_its_own_round_ticks():
    t = np.arange(np.datetime64("2026-09-01"), np.datetime64("2026-09-05")).astype("datetime64[ns]")
    a = xr.Dataset({"x": (("time",), [1.0, 2.0, 3.0, 4.0])}, coords={"time": t})
    b = xr.Dataset({"y": (("time",), [10.0, 30.0, 20.0, 40.0])}, coords={"time": t})
    spec = {
        "data": [
            {
                "uid": "a",
                "type": "scatter",
                "meta": {"source": {"input": "a"}, "x": "time", "y": "x"},
            },
            {
                "uid": "b",
                "type": "scatter",
                "yaxis": "y2",
                "meta": {"source": {"input": "b"}, "x": "time", "y": "y"},
            },
        ],
        "layout": {"yaxis2": {"overlaying": "y", "side": "right"}},
    }
    axis = _layout(compile(spec, {"a": a, "b": b}))["yaxis2"]
    assert axis["tickmode"] == "auto" and axis["showgrid"] is False


def test_upside_down_bbox_and_several_leftover_dims_are_named():
    ds = make_gridded(n_time=1)
    grid = {"z": "precip"}
    spec = {
        "data": [_trace("a", meta=grid)],
        "layout": {"meta": {"geo": {"bbox": [-5, 10, 5, 13]}}},
    }
    with pytest.raises(UsageError, match="north is below south"):
        compile(spec, {"a": ds})
    cube = make_gridded(n_time=1).expand_dims(number=[0, 1], vertical=[500, 850])
    with pytest.raises(UsageError, match="dimensions 'number', 'vertical' remain"):
        compile({"data": [_trace("a", meta=grid)]}, {"a": cube})


def test_probability_spans_zero_to_one_and_precip_rate_change_is_brbg():
    prob = make_gridded(n_time=1, name="probability", fill=0.4, units="1")
    prob["probability"].values[..., 0] = 0.1
    axis = _layout(compile({"data": [_trace("a", meta={"z": "probability"})]}, {"a": prob}))[
        "coloraxis"
    ]
    assert (axis["cmin"], axis["cmax"]) == (0.0, 1.0)
    change = make_gridded(n_time=1, fill=2.0, units="mm day-1")
    change["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    change["precip"].values[..., 0] = -3.0
    axis = _layout(compile({"data": [_trace("a", meta={"z": "precip"})]}, {"a": change}))[
        "coloraxis"
    ]
    assert "ticktext" not in axis["colorbar"]  # continuous, not the mm classes
    assert axis["cmin"] == -axis["cmax"]


def test_xy_year_labels_do_not_share_a_spot():
    years = np.arange(2010, 2014)
    ds = xr.Dataset(
        {"a": (("year",), [1.0, 1.01, 3.0, 4.0]), "b": (("year",), [5.0, 5.02, 1.0, 2.0])},
        coords={"year": years},
    )
    fig = compile(
        {
            "data": [
                {
                    "uid": "s",
                    "type": "scatter",
                    "meta": {"x": "a", "y": "b", "source": {"input": "s"}},
                }
            ]
        },
        {"s": ds},
    )
    pos = list(next(t for t in fig.data if t["uid"] == "s")["textposition"])
    # The two near-identical points get different sides.
    assert pos[0] != pos[1]


def test_wind_speed_classes_are_one_ramp():
    from weather_skills_plotting.themes import default_theme

    lum = [
        sum(int(c[i : i + 2], 16) * w for i, w in ((1, 0.299), (3, 0.587), (5, 0.114)))
        for c in default_theme()["palettes"]["wind_rose"]["colors"]
    ]
    assert lum == sorted(lum, reverse=True)


def test_isel_range_picks_every_nth_position():
    ds = make_gridded(n_time=6)
    isel = {"time": {"start": 0, "stop": 6, "step": 2}}
    spec = {"data": [_trace("a", source={"isel": isel}, meta={"z": "precip"})]}
    assert len(_data(compile(spec, {"a": ds}), "heatmap")) == 3


def test_a_subtitle_moves_the_maps_down_and_survives_the_merge():
    ds = make_gridded(n_time=2)
    title = {"text": "ECMWF rainfall"}
    sub = {**title, "subtitle": {"text": "Week 1: 16–22 Oct"}}
    data = [_trace("0", meta={"z": "precip"})]
    plain = _layout(compile({"data": data, "layout": {"title": title}}, {"0": ds}))
    with_sub = _layout(compile({"data": data, "layout": {"title": sub}}, {"0": ds}))
    assert with_sub["margin"]["t"] > plain["margin"]["t"]
    assert with_sub["title"]["subtitle"]["text"] == "Week 1: 16–22 Oct"


# ------------------------------------------------- plain Plotly, no hidden rules


def test_br_title_lines_get_room():
    from weather_skills_plotting.layout import title_lines

    assert title_lines({"text": "One<br>Two<BR/>Three"}) == 3
    assert title_lines({"text": "One<br>Two", "subtitle": {"text": "x"}}) == 3


def test_fixed_marker_color_draws_without_a_scale():
    spec = {
        "data": [
            _trace(
                "s",
                type="scatter",
                marker={"color": "black"},
                source={"isel": {"time": 0}},
                meta={"x": "station_id", "y": "precip"},
            )
        ]
    }
    fig = compile(spec, {"s": make_station()})
    assert _data(fig)[0]["marker"]["color"] == "black"
    assert "coloraxis" not in _layout(fig)


def test_zmid_centres_the_scale():
    ds = make_gridded(n_time=1, units="degC")
    ds["precip"][:] = np.arange(12.0).reshape(1, 3, 4)  # 0 … 11
    axis = _layout(compile({"data": [_trace("a", zmid=2, meta={"z": "precip"})]}, {"a": ds}))[
        "coloraxis"
    ]
    assert (axis["cmin"], axis["cmax"]) == (-7, 11)


def test_limits_on_one_map_stay_on_that_map():
    a, b = make_gridded(n_time=1), make_gridded(n_time=1)
    grid = {"z": "precip"}
    spec = {
        "data": [
            _trace("a", meta=grid),
            _trace("b", xaxis="x2", yaxis="y2", zmin=0, zmax=50, meta=grid),
        ]
    }
    layout = _layout(compile(spec, {"a": a, "b": b}))
    assert layout["coloraxis2"]["cmax"] == 50 and layout["coloraxis"]["cmax"] != 50


def test_layers_at_different_times_are_an_error():
    rain, msl = make_gridded(n_time=3), make_gridded(n_time=3, name="msl", units="hPa")
    rain_map, msl_map = {"z": "precip"}, {"z": "msl"}
    spec = {
        "data": [
            _trace("r", source={"isel": {"time": 0}}, meta=rain_map),
            _trace("m", type="contour", meta=msl_map),
        ]
    }
    with pytest.raises(UsageError, match="'r' is one map.*3 panels"):
        compile(spec, {"r": rain, "m": msl})
    later = msl.isel(time=[1, 2])
    spec = {"data": [_trace("r", meta=rain_map), _trace("m", type="contour", meta=msl_map)]}
    with pytest.raises(UsageError, match="different times"):
        compile(spec, {"r": rain, "m": later})


def test_chart_traces_stay_on_their_own_axes():
    s = make_gridded(n_time=3).mean(["latitude", "longitude"], keep_attrs=True)
    line = {"x": "time", "y": "precip"}
    spec = {
        "data": [_trace(u, type="scatter", name=u, meta=line) for u in "abc"],
        "layout": {"grid": {"rows": 2, "columns": 1}, "showlegend": True},
    }
    fig = compile(spec, {u: s for u in "abc"})
    assert {(t["xaxis"], t["yaxis"]) for t in _data(fig)} == {("x", "y")}
    one = {"data": [_trace("a", type="scatter", name="a", showlegend=True, meta=line)]}
    assert _layout(compile(one, {"a": s})).get("showlegend") is not False


def test_several_wind_pairs_need_one_chosen():
    ds = make_gridded(n_time=1, name="u10", units="m s-1")
    for v in ("v10", "u100", "v100"):
        ds[v] = ds["u10"]
    with pytest.raises(UsageError, match="several wind components.*u10/v10.*u100/v100"):
        compile({"data": [_trace("w", meta={"bind": "speed"})]}, {"w": ds})


def test_station_labels_read_the_name_coordinate():
    ds = make_station().assign_coords(name=("station_id", ["Kibera", "", "Nyeri"]))
    spec = {
        "data": [
            _trace(
                "s",
                type="scatter",
                mode="markers+text",
                source={"isel": {"time": 0}},
                meta={"x": "longitude", "y": "latitude", "marker": {"color": "precip"}},
            )
        ]
    }
    tr = next(t for t in _data(compile(spec, {"s": ds})) if t["uid"] == "s")
    assert list(tr["text"]) == ["Kibera", "TA0001", "Nyeri"]
    assert list(tr["hovertext"]) == ["TA0000 Kibera", "TA0001", "TA0002 Nyeri"]


def test_chart_title_sits_above_the_legend_rows():
    s = make_gridded(n_time=3).mean(["latitude", "longitude"], keep_attrs=True)
    spec = {
        "data": [
            _trace(u, type="scatter", name=f"series {u}", meta={"x": "time", "y": "precip"})
            for u in "abc"
        ],
        "layout": {"title": {"text": "T", "subtitle": {"text": "S"}}},
    }
    title = _layout(compile(spec, {u: s for u in "abc"}))["title"]
    assert (title["yref"], title["y"], title["yanchor"], title["text"]) == (
        "container",
        1,
        "top",
        "T",
    )


def test_temperature_is_drawn_in_the_files_units(capsys):
    ds = make_gridded(n_time=1, name="t2m", units="K", fill=290.0)
    spec = {"data": [_trace("a", zmin=280, zmax=300, meta={"z": "t2m"})]}
    axis = _layout(compile(spec, {"a": ds}))["coloraxis"]
    assert (axis["cmin"], axis["cmax"]) == (280, 300)
    assert "K" in axis["colorbar"]["title"]["text"]


def test_band_parts_are_styled_by_their_own_uids():
    ds = make_forecast(n_number=5, n_step=4).mean(["latitude", "longitude"], keep_attrs=True)
    ds["tp"][:] = np.arange(20.0).reshape(5, 4)
    meta = {"x": "step", "y": "tp", "along": "number", "band": [0, 100]}
    spec = {
        "data": [
            _trace("f", type="scatter", name="Mean", line={"color": "red", "width": 4}, meta=meta),
            {"uid": "f-members", "line": {"color": "grey"}, "opacity": 0.3},
            {"uid": "f-band", "name": "Range", "fillcolor": "pink"},
        ]
    }
    by_uid = {t["uid"]: t for t in _data(compile(spec, {"f": ds}))}
    assert by_uid["f"]["name"] == "Mean" and by_uid["f"]["line"]["width"] == 4
    members = by_uid["f-members"]
    assert members["line"]["color"] == "grey" and members["opacity"] == 0.3
    assert members["line"]["width"] != 4 and members["name"] != "Mean"
    assert not members["showlegend"]
    spec["data"][1]["name"] = "Members"
    named = next(t for t in _data(compile(spec, {"f": ds})) if t["uid"] == "f-members")
    assert named["showlegend"] and named["name"] == "Members"
    band = by_uid["f-band"]
    assert (band["name"], band["fillcolor"]) == ("Range", "pink")
    # Without a style of its own, [0, 100] reads min–max.
    spec["data"] = spec["data"][:1]
    names = [t["name"] for t in _data(compile(spec, {"f": ds})) if t["uid"] == "f-band"]
    assert names == ["min–max"]


def test_band_part_without_a_band_is_an_error():
    from weather_skills_plotting.spec import merge_traces

    with pytest.raises(
        UsageError, match="'f-band' styles part of a trace only when 'f' has meta.band"
    ):
        merge_traces(
            [{"uid": "f", "meta": {"source": {"input": "f"}}}], [{"uid": "f-band", "name": "x"}]
        )


def test_xy_draws_bars_by_county():
    ds = xr.Dataset(
        {"precip": (("county",), [12.0, 30.5, 4.0])},
        coords={"county": ["Kisii", "Siaya", "Busia"]},
    )
    spec = {
        "data": [
            {"uid": "0", "type": "bar", "orientation": "h", "meta": {"x": "precip", "y": "county"}}
        ]
    }
    tr = _data(compile(spec, {"0": ds}))[0]
    assert tr["type"] == "bar" and tr["orientation"] == "h"
    assert list(tr["y"]) == ["Kisii", "Siaya", "Busia"] and list(tr["x"]) == [12.0, 30.5, 4.0]


def test_xy_isel_picks_only_where_the_dim_is():
    # A county total with a one-value time dim against the county names (no time).
    ds = xr.Dataset(
        {"precip": (("time", "county"), [[12.0, 30.5, 4.0]])},
        coords={"time": [np.datetime64("2026-10-13", "ns")], "county": ["Kisii", "Siaya", "Busia"]},
    )
    meta = {"x": "precip", "y": "county", "source": {"isel": {"time": 0}}}
    tr = _data(compile({"data": [{"uid": "0", "type": "bar", "meta": meta}]}, {"0": ds}))[0]
    assert list(tr["y"]) == ["Kisii", "Siaya", "Busia"]
    meta["source"] = {"isel": {"step": 0}}
    with pytest.raises(UsageError, match="isel dimension 'step' is not in the data"):
        compile({"data": [{"uid": "0", "meta": meta}]}, {"0": ds})


def _three_side_by_side(**layout):
    data = {k: make_gridded(n_time=1, fill=f) for k, f in (("A", 1.0), ("B", 2.0), ("C", 3.0))}
    spec = {
        "data": [
            _trace("A"),
            _trace("B", xaxis="x2", yaxis="y2"),
            _trace("C", xaxis="x3", yaxis="y3"),
        ],
        "layout": layout,
    }
    return compile(spec, data)


def test_grid_subplots_puts_each_map_in_its_cell():
    fig = _three_side_by_side(grid={"subplots": [["x3y3", "xy"], ["", "x2y2"]]})
    lay = _layout(fig)
    left, right = lay["xaxis3"]["domain"], lay["xaxis"]["domain"]
    assert left[1] < right[0]  # C in the left column, A to its right
    assert lay["xaxis2"]["domain"] == right  # B under A
    assert lay["yaxis2"]["domain"][1] < lay["yaxis"]["domain"][0]
    assert "grid" not in lay  # the plotter places the panels; Plotly gets explicit domains
    # Each map keeps its own axes, so its traces need no xaxis of their own.
    heat = {t["uid"]: t["xaxis"] for t in _data(fig, "heatmap")}
    assert heat == {"A-p1": "x", "B-p2": "x2", "C-p3": "x3"}


def test_grid_subplots_empty_panel_left_out_draws_nothing():
    # x, x3: panel 2 has no map; subplots need not name it.
    data = {k: make_gridded(n_time=1) for k in ("A", "C")}
    spec = {
        "data": [_trace("A"), _trace("C", xaxis="x3", yaxis="y3")],
        "layout": {"grid": {"subplots": [["xy", "x3y3"]]}},
    }
    fig = compile(spec, data)
    lay = _layout(fig)
    assert "xaxis2" not in lay
    assert not [t for t in fig.data if t["uid"].startswith("empty")]


@pytest.mark.parametrize(
    "grid, match",
    [
        ({"subplots": [["xy", "x2y2"]]}, "leaves out x3y3"),
        ({"subplots": [["xy", "x2y2", "x3y3", "x4y4"]]}, "'x4y4' names no map"),
        ({"subplots": [["xy", "xy", "x2y2", "x3y3"]]}, "names 'xy' twice"),
        ({"subplots": [["xy", "x2y3", "x3y3"]]}, "must name one map's axes"),
        ({"subplots": [["xy", "x2y2"], ["x3y3"]]}, "same length"),
        ({"subplots": "xy"}, "subplots. property"),
    ],
)
def test_grid_subplots_errors_say_what_to_fix(grid, match):
    with pytest.raises(UsageError, match=match):
        _three_side_by_side(grid=grid)


def test_maps_of_one_window_label_only_the_outer_axes():
    fig = compile({"data": [_trace("a")]}, {"a": make_gridded(n_time=4)})
    lay = _layout(fig)  # 2 x 2: x1 x2 / x3 x4
    hidden_x = [
        a for a in ("xaxis", "xaxis2", "xaxis3", "xaxis4") if lay[a].get("showticklabels") is False
    ]
    hidden_y = [
        a for a in ("yaxis", "yaxis2", "yaxis3", "yaxis4") if lay[a].get("showticklabels") is False
    ]
    assert hidden_x == ["xaxis", "xaxis2"]
    assert hidden_y == ["yaxis2", "yaxis4"]


def test_maps_of_different_windows_keep_every_tick_label():
    a = make_gridded(n_time=1)
    b = make_gridded(n_time=1, lats=(40.0, 41.0, 42.0), lons=(100.0, 101.0, 102.0, 103.0))
    spec = {"data": [_trace("a"), _trace("b", xaxis="x2", yaxis="y2")]}
    lay = _layout(compile(spec, {"a": a, "b": b}))
    assert all("showticklabels" not in lay[k] for k in ("xaxis", "yaxis", "xaxis2", "yaxis2"))


def test_a_map_above_an_empty_cell_keeps_its_longitudes():
    fig = _three_side_by_side(grid={"subplots": [["xy", "x2y2"], ["x3y3", ""]]})
    lay = _layout(fig)
    assert lay["xaxis"].get("showticklabels") is False  # C labels the column below A
    assert "showticklabels" not in lay["xaxis2"]  # nothing under B
    assert lay["yaxis2"].get("showticklabels") is False


def test_narrow_panels_put_name_and_dates_on_two_lines():
    names = ["KMSA downscaled", "ECMWF AIFS ENS", "WeatherNext 2", "Cumulus AI"]
    data = {n: make_gridded(n_time=1, start=f"2026-10-{26 + i:02d}") for i, n in enumerate(names)}
    traces = [
        _trace(n, **({"xaxis": f"x{i + 1}", "yaxis": f"y{i + 1}"} if i else {}))
        for i, n in enumerate(names)
    ]
    wide = _layout(compile({"data": traces}, data))
    narrow = _layout(
        compile({"data": traces, "layout": {"grid": {"columns": 4}, "width": 700}}, data)
    )
    title = lambda lay: next(a["text"] for a in lay["annotations"] if a["name"] == "panel-title-1")  # noqa: E731
    assert " · " in title(wide)
    assert title(narrow).startswith("KMSA downscaled<br>")
    assert narrow["margin"]["t"] > wide["margin"]["t"]
