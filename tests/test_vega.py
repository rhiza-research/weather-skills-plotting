"""Library tests for weather_skills_plotting.vega: bindings, defaults, lint, validation, patches."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import shape
from vega_data import NE_FIXTURES, fcst_weekly_mean, obs_week, region_geojson, weekly_series

from weather_skills_plotting import vega
from weather_skills_plotting.vega import bind, defaults, naturalearth
from weather_skills_plotting.vega.errors import DataError, SpecError


@pytest.fixture(autouse=True)
def _ne_fixtures(monkeypatch):
    monkeypatch.setenv("WS_NE_CACHE", str(NE_FIXTURES))


@pytest.fixture
def rng():
    return np.random.default_rng(0)


@pytest.fixture
def fcst(rng):
    return fcst_weekly_mean(rng)


@pytest.fixture
def obs(rng):
    return obs_week(rng)


CELLS = {"lon": "longitude.lo", "lon2": "longitude.hi", "lat": "latitude.lo", "lat2": "latitude.hi"}


def cell_layer(name, field):
    return {
        "data": {"name": name},
        "mark": {"type": "rect", "clip": True},
        "encoding": {
            "longitude": {"field": "lon", "type": "quantitative"},
            "latitude": {"field": "lat", "type": "quantitative"},
            "longitude2": {"field": "lon2"},
            "latitude2": {"field": "lat2"},
            "color": {"field": field, "type": "quantitative"},
        },
    }


def map_spec(**extra):
    spec = {
        "projection": {"type": "equirectangular"},
        "datasets": {
            "obs": {"zarr": "obs", "fields": {**CELLS, "precip": "precip"}},
            "borders": {"naturalearth": "borders", "scale": "50m"},
        },
        "layer": [
            cell_layer("obs", "precip"),
            {
                "data": {"name": "borders"},
                "mark": {"type": "geoshape", "filled": False, "clip": True},
            },
        ],
    }
    spec.update(extra)
    return spec


# --------------------------------------------------------------------------- bindings


def test_cell_edges_ascending_descending_single():
    lo, hi = bind.cell_edges([0.0, 1.0, 2.0])
    np.testing.assert_allclose(lo, [-0.5, 0.5, 1.5])
    np.testing.assert_allclose(hi, [0.5, 1.5, 2.5])
    lo, hi = bind.cell_edges([2.0, 1.0, 0.0])
    np.testing.assert_allclose(lo, [1.5, 0.5, -0.5])
    np.testing.assert_allclose(hi, [2.5, 1.5, 0.5])
    lo, hi = bind.cell_edges([5.0])
    assert (lo[0], hi[0]) == (4.5, 5.5)


def test_bind_zarr_cells_and_extent(fcst):
    rows, meta = bind.bind_zarr(
        "f", {"zarr": "f", "sel": {"step": "7D"}, "fields": {**CELLS, "tp": "tp"}}, {"f": fcst}
    )
    assert len(rows) == fcst.sizes["latitude"] * fcst.sizes["longitude"]
    assert set(rows[0]) == {"lon", "lon2", "lat", "lat2", "tp"}
    assert all(r["lon2"] - r["lon"] == pytest.approx(0.5) for r in rows)
    assert all(r["lat2"] > r["lat"] for r in rows)
    n, w, s, e = meta["extent"]
    assert (n, w, s, e) == (6.0, 33.0, -5.5, 42.5)
    assert meta["var_cols"] == {"tp": "tp"}


def test_bind_zarr_leftover_dims_error(fcst):
    with pytest.raises(SpecError, match=r"dims \{'step': 4\} are not columns"):
        bind.bind_zarr("f", {"zarr": "f", "fields": {**CELLS, "tp": "tp"}}, {"f": fcst})


def test_bind_zarr_time_and_timedelta_values(fcst):
    rows, _ = bind.bind_zarr(
        "f",
        {
            "zarr": "f",
            "isel": {"latitude": 0, "longitude": 0},
            "fields": {"lead": "step", "valid": "valid_time", "tp": "tp"},
        },
        {"f": fcst},
    )
    assert [r["lead"] for r in rows] == [7.0, 14.0, 21.0, 28.0]
    first = pd.Timestamp(rows[0]["valid"], unit="ms")
    assert first == pd.Timestamp("2026-10-08")


def test_bind_zarr_sel_forms(rng):
    ds = weekly_series(rng)
    rows, _ = bind.bind_zarr(
        "w",
        {
            "zarr": "w",
            "sel": {"time": {"start": "2026-01-06", "stop": "2026-01-20"}},
            "fields": {"t": "time", "p": "precip"},
        },
        {"w": ds},
    )
    assert len(rows) == 3
    rows, _ = bind.bind_zarr(
        "w", {"zarr": "w", "sel": {"time": "2026-01-07"}, "fields": {"p": "precip"}}, {"w": ds}
    )
    assert len(rows) == 1
    with pytest.raises(SpecError, match="selects no values"):
        bind.bind_zarr(
            "w",
            {"zarr": "w", "sel": {"time": {"start": "2030-01-01"}}, "fields": {"p": "precip"}},
            {"w": ds},
        )


def test_bind_zarr_bbox_descending_lat_and_empty(fcst):
    binding = {"zarr": "f", "sel": {"step": "7D"}, "bbox": [2, 35, -2, 38], "fields": {**CELLS}}
    binding["fields"]["tp"] = "tp"
    rows, meta = bind.bind_zarr("f", binding, {"f": fcst})
    lats = {r["lat"] for r in rows}
    assert min(lats) >= -2.5 and max(lats) <= 2.0
    assert meta["extent"][0] <= 2.5
    with pytest.raises(SpecError, match="contains no data"):
        bind.bind_zarr("f", {**binding, "bbox": [60, 0, 50, 10]}, {"f": fcst})
    with pytest.raises(SpecError, match="north"):
        bind.bind_zarr("f", {**binding, "bbox": [-2, 35, 2, 38]}, {"f": fcst})


def test_bind_zarr_source_errors(fcst, obs):
    with pytest.raises(SpecError, match="fields is required"):
        bind.bind_zarr("f", {"zarr": "f"}, {"f": fcst})
    with pytest.raises(SpecError, match="names no data variable"):
        bind.bind_zarr("f", {"zarr": "f", "fields": {"lon": "longitude"}}, {"f": fcst})
    with pytest.raises(SpecError, match="'bogus' is not a dim, coord, or variable"):
        bind.bind_zarr("f", {"zarr": "f", "fields": {"x": "bogus", "tp": "tp"}}, {"f": fcst})
    with pytest.raises(SpecError, match="timeOffset"):
        bind.bind_zarr("o", {"zarr": "o", "fields": {"t": "time.hi", "p": "precip"}}, {"o": obs})
    with pytest.raises(SpecError, match="unknown key"):
        bind.bind_zarr("f", {"zarr": "f", "fieldz": {}}, {"f": fcst})


def test_bind_zarr_dropna(obs):
    ds = obs.copy(deep=True)
    ds["precip"][0, :10, :] = np.nan
    binding = {"zarr": "o", "fields": {"lon": "longitude", "lat": "latitude", "p": "precip"}}
    kept, _ = bind.bind_zarr("o", binding, {"o": ds})
    allrows, _ = bind.bind_zarr("o", {**binding, "dropna": False}, {"o": ds})
    assert len(allrows) - len(kept) == 10 * ds.sizes["longitude"]
    assert any(r["p"] is None for r in allrows)


def test_bind_contours(fcst):
    features, meta = bind.bind_contours(
        "b",
        {
            "zarr": "f",
            "sel": {"step": "7D"},
            "contours": {"variable": "tp", "levels": [0, 20, 50, 200], "filled": True},
        },
        {"f": fcst},
    )
    assert features and all(f["geometry"]["type"] == "Polygon" for f in features)
    assert {f["properties"]["lo"] for f in features} <= {0, 20, 50}
    assert meta["var_cols"]["properties.mid"] == "tp"
    lines, _ = bind.bind_contours(
        "l",
        {"zarr": "f", "sel": {"step": "7D"}, "contours": {"variable": "tp", "levels": [30]}},
        {"f": fcst},
    )
    assert lines[0]["properties"] == {"level": 30}
    with pytest.raises(SpecError, match="2-D latitude/longitude"):
        bind.bind_contours(
            "b", {"zarr": "f", "contours": {"variable": "tp", "levels": [10]}}, {"f": fcst}
        )


def test_input_kind_mismatch(fcst):
    with pytest.raises(SpecError, match=r'bind it with \{"zarr": "f"\}'):
        bind.bind_all({"datasets": {"g": {"geojson": "f"}}}, {"f": fcst})
    with pytest.raises(SpecError, match="is not an input"):
        bind.bind_all({"datasets": {"g": {"zarr": "nope", "fields": {"a": "tp"}}}}, {"f": fcst})


def test_bind_all_kinds_and_vector_bbox_default(obs):
    notes = []
    spec = {
        "datasets": {
            "obs": {"zarr": "obs", "fields": {**CELLS, "precip": "precip"}},
            "lakes": {"naturalearth": "lakes", "scale": "10m"},
            "region": {"geojson": "region"},
            "pts": [{"a": 1}],
        }
    }
    out, meta = bind.bind_all(spec, {"obs": obs, "region": region_geojson()}, notes)
    assert out["datasets"]["pts"] == [{"a": 1}]
    assert meta["lakes"]["kind"] == "naturalearth" and meta["lakes"]["rows"] > 0
    assert meta["region"]["rows"] == 1
    assert any(n.startswith("datasets.lakes.bbox <- extent") for n in notes)
    assert spec["datasets"]["obs"]["zarr"] == "obs"  # input spec untouched
    with pytest.raises(SpecError, match="exactly one of"):
        bind.bind_all({"datasets": {"x": {"zarr": "obs", "geojson": "r"}}}, {"obs": obs})


def test_geojson_shapes_accepted():
    geom = region_geojson()["features"][0]["geometry"]
    for data in (region_geojson(), {"type": "Feature", "properties": {}, "geometry": geom}, geom):
        assert len(bind.bind_geojson("r", {"geojson": "r"}, {"r": data})) == 1


def test_naturalearth_clip_properties_and_orientation():
    feats = naturalearth.bind_naturalearth(
        "c",
        {
            "naturalearth": "countries",
            "scale": "10m",
            "bbox": [5, 33.5, -5, 42],
            "properties": ["adm0_a3"],
        },
    )
    codes = {f["properties"]["ADM0_A3"] for f in feats}
    assert "KEN" in codes
    assert all(set(f["properties"]) == {"ADM0_A3"} for f in feats)
    for f in feats:
        g = shape(f["geometry"])
        polys = g.geoms if g.geom_type == "MultiPolygon" else [g]
        assert all(not p.exterior.is_ccw for p in polys)
    with pytest.raises(SpecError, match="choose one of"):
        naturalearth.bind_naturalearth("c", {"naturalearth": "roads"})
    with pytest.raises(SpecError, match="scale"):
        naturalearth.bind_naturalearth("c", {"naturalearth": "lakes", "scale": "5m"})


def test_naturalearth_offline_error(tmp_path, monkeypatch):
    monkeypatch.setenv("WS_NE_CACHE", str(tmp_path))

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(naturalearth.urllib.request, "urlopen", boom)
    with pytest.raises(DataError, match="WS_NE_CACHE"):
        naturalearth.layer_path("rivers", "110m")
    assert not list(tmp_path.iterdir())


# --------------------------------------------------------------------------- defaults


def test_defaults_precip_map(obs):
    prep = vega.prepare(map_spec(), {"obs": obs})
    color = prep.spec["layer"][0]["encoding"]["color"]
    assert color["scale"]["type"] == "threshold"
    assert color["scale"]["domain"][:3] == [0, 1, 2]
    assert len(color["scale"]["range"]) == len(color["scale"]["domain"]) + 1
    assert color["title"] == "Total precipitation [mm]"
    fit = prep.spec["projection"]["fit"]
    assert fit["geometry"]["type"] == "MultiPoint"
    assert fit["geometry"]["coordinates"] == [[33.5, -5.0], [42.0, 5.0]]
    assert any("ppt_week" in n for n in prep.notes)


def test_defaults_never_override_written_keys(obs):
    spec = map_spec()
    enc = spec["layer"][0]["encoding"]["color"]
    enc["title"] = None
    enc["scale"] = {"scheme": "viridis"}
    spec["projection"]["scale"] = 2000
    prep = vega.prepare(spec, {"obs": obs})
    out = prep.spec["layer"][0]["encoding"]["color"]
    assert out["title"] is None
    assert out["scale"] == {"scheme": "viridis"}
    assert "fit" not in prep.spec["projection"]


def test_palette_scheme_name_and_unknown_scheme(obs):
    spec = map_spec()
    spec["layer"][0]["encoding"]["color"]["scale"] = {"scheme": "PPT_MONTH", "reverse": True}
    scale = vega.prepare(spec, {"obs": obs}).spec["layer"][0]["encoding"]["color"]["scale"]
    assert scale["type"] == "threshold" and scale["domain"][-1] == 400 and scale["reverse"]
    spec["layer"][0]["encoding"]["color"]["scale"] = {"scheme": "rainbowz"}
    with pytest.raises(SpecError, match="is not a palette"):
        vega.prepare(spec, {"obs": obs})


def test_usermeta_defaults_off(obs):
    spec = map_spec(usermeta={"defaults": False})
    spec["projection"]["fit"] = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "MultiPoint", "coordinates": [[33.5, -5], [42, 5]]},
    }
    spec["datasets"]["borders"]["bbox"] = [5, 33.5, -5, 42]
    prep = vega.prepare(spec, {"obs": obs})
    color = prep.spec["layer"][0]["encoding"]["color"]
    assert "scale" not in color and "title" not in color
    assert prep.notes == []
    with pytest.raises(SpecError, match="true or false"):
        vega.prepare(map_spec(usermeta={"defaults": "no"}), {"obs": obs})


def test_computed_fields_get_no_defaults(obs):
    spec = map_spec()
    spec["layer"][0]["transform"] = [{"calculate": "datum.precip * 2", "as": "precip"}]
    color = vega.prepare(spec, {"obs": obs}).spec["layer"][0]["encoding"]["color"]
    assert "scale" not in color and "title" not in color


def test_non_precip_variable_title_only(rng):
    from vega_data import ens_point_t2m

    ens = ens_point_t2m(rng)
    spec = {
        "datasets": {"e": {"zarr": "e", "fields": {"v": "valid_time", "m": "number", "t": "t2m"}}},
        "data": {"name": "e"},
        "mark": "line",
        "encoding": {
            "x": {"field": "v", "type": "temporal"},
            "y": {"field": "t", "type": "quantitative"},
            "color": {"field": "t", "type": "quantitative"},
            "detail": {"field": "m"},
        },
    }
    enc = vega.prepare(spec, {"e": ens}).spec["encoding"]
    assert enc["y"]["title"] == "2 metre temperature [°C]"
    assert "scale" not in enc["color"]


def test_shared_layer_encoding_title_and_dedupe(rng):
    a = weekly_series(rng, name="precipitation_surface")
    b = weekly_series(rng)
    spec = {
        "datasets": {
            "a": {"zarr": "a", "fields": {"t": "time", "p": "precipitation_surface"}},
            "b": {"zarr": "b", "fields": {"t": "time", "p": "precip"}},
        },
        "encoding": {
            "x": {"field": "t", "type": "temporal"},
            "y": {"field": "p", "type": "quantitative"},
        },
        "layer": [
            {"data": {"name": "a"}, "mark": "line", "encoding": {"color": {"datum": "A"}}},
            {"data": {"name": "b"}, "mark": "line", "encoding": {"color": {"datum": "B"}}},
        ],
    }
    prep = vega.prepare(spec, {"a": a, "b": b})
    assert prep.spec["encoding"]["y"]["title"] == "Total precipitation [mm]"
    layered = {
        "datasets": spec["datasets"],
        "layer": [
            {
                "data": {"name": n},
                "mark": "line",
                "encoding": {
                    "x": {"field": "t", "type": "temporal"},
                    "y": {"field": "p", "type": "quantitative"},
                },
            }
            for n in ("a", "b")
        ],
    }
    out = vega.prepare(layered, {"a": a, "b": b}).spec["layer"]
    assert out[0]["encoding"]["y"]["title"] == "Total precipitation [mm]"
    assert "title" not in out[1]["encoding"]["y"]


def test_vega_scheme_names_loaded():
    names = defaults.vega_scheme_names()
    assert {"viridis", "blues", "redblue", "brownbluegreen", "category10"} <= names


# --------------------------------------------------------------------------- lint / validate


def _single(obs, **encoding):
    return {
        "datasets": {
            "o": {"zarr": "obs", "fields": {"lon": "longitude", "lat": "latitude", "p": "precip"}}
        },
        "data": {"name": "o"},
        "mark": "circle",
        "encoding": encoding,
    }


def test_lint_unknown_field_and_dataset(obs):
    spec = _single(
        obs,
        x={"field": "lon", "type": "quantitative"},
        color={"field": "rain", "type": "quantitative"},
    )
    with pytest.raises(
        SpecError, match=r"'rain' is not a column of 'o' \(columns: \['lat', 'lon', 'p'\]\)"
    ):
        vega.prepare(spec, {"obs": obs})
    spec = _single(obs, tooltip=[{"field": "nope", "type": "nominal"}])
    with pytest.raises(SpecError, match="tooltip.field 'nope'"):
        vega.prepare(spec, {"obs": obs})
    spec = _single(obs, x={"field": "lon", "type": "quantitative"})
    spec["data"] = {"name": "missing"}
    with pytest.raises(SpecError, match="'missing' is not a dataset"):
        vega.prepare(spec, {"obs": obs})


def test_lint_mark_without_data(obs):
    spec = _single(obs, x={"field": "lon", "type": "quantitative"})
    del spec["data"]
    with pytest.raises(SpecError, match="draws a mark but has no data"):
        vega.prepare(spec, {"obs": obs})


def test_lint_allows_transform_outputs(obs):
    spec = _single(
        obs,
        x={"field": "lon", "type": "quantitative"},
        y={"field": "double", "type": "quantitative"},
    )
    spec["transform"] = [{"calculate": "datum.p * 2", "as": "double"}]
    vega.prepare(spec, {"obs": obs})


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"mark": "circles"}, r"spec.mark: .*choose one of \[.*'boxplot'.*'circle'"),
        ({"encoding": {"x": {"field": "lon", "type": "quant"}}}, r"spec.encoding.x.type"),
        (
            {"encoding": {"x": {"field": "lon", "type": "quantitative", "scale": {"typ": "log"}}}},
            r"spec.encoding.x.scale: Additional properties .*'typ'",
        ),
    ],
)
def test_validate_messages(obs, patch, message):
    spec = {**_single(obs), **patch}
    with pytest.raises(SpecError, match=message):
        vega.prepare(spec, {"obs": obs})


def test_validate_concat_projection_message(obs):
    spec = {
        "datasets": {
            "o": {"zarr": "obs", "fields": {"lon": "longitude", "lat": "latitude", "p": "precip"}}
        },
        "data": {"name": "o"},
        "projection": {"type": "mercator"},
        "hconcat": [{"mark": "circle"}],
    }
    with pytest.raises(SpecError, match="HConcatChart` has no parameter named 'projection'"):
        vega.prepare(spec, {"obs": obs})


def test_top_level_composition_required(obs):
    with pytest.raises(SpecError, match="exactly one of mark"):
        vega.prepare({"datasets": {}}, {})
    with pytest.raises(SpecError, match="needs a 'spec'"):
        vega.prepare({"facet": {"field": "a"}, "data": {"values": []}}, {})


def test_row_guard(obs):
    spec = map_spec()
    with pytest.raises(SpecError, match="row limit"):
        vega.prepare(spec, {"obs": obs}, max_rows=100)


# --------------------------------------------------------------------------- compile patches + write


def test_patches_on_compiled_vega(obs):
    prep = vega.prepare(map_spec(), {"obs": obs})
    v = vega.to_vega(prep)
    rects = [m for m in v["marks"] if m.get("type") == "rect"]
    assert rects[0]["encode"]["update"]["stroke"] == rects[0]["encode"]["update"]["fill"]
    legend = v["legends"][0]
    assert legend["type"] == "symbol"
    # every value is >= 0, so the "< 0" under entry is dropped
    assert legend["values"] == prep.spec["layer"][0]["encoding"]["color"]["scale"]["domain"]

    off = vega.prepare(
        map_spec(usermeta={"seal_cells": False, "classed_legend": False}), {"obs": obs}
    )
    v2 = vega.to_vega(off)
    assert (
        "stroke" not in next(m for m in v2["marks"] if m.get("type") == "rect")["encode"]["update"]
    )
    assert v2["legends"][0].get("type") != "symbol"


def test_render_png_jpg_html(tmp_path, obs):
    for suffix in (".png", ".jpg", ".html"):
        out = tmp_path / f"map{suffix}"
        vega.render(map_spec(width=200, height=240), {"obs": obs}, out, scale=1)
        assert out.stat().st_size > 1000
    assert "<html" in (tmp_path / "map.html").read_text().lower()
    from PIL import Image

    with Image.open(tmp_path / "map.png") as img:
        assert img.size[0] > 200
    with pytest.raises(SpecError, match="use one of"):
        vega.write({}, tmp_path / "x.svg")


def test_truncate_rows(obs):
    prep = vega.prepare(map_spec(), {"obs": obs})
    short = vega.truncate_rows(prep.spec, 2)
    assert len(short["datasets"]["obs"]) == 2
    assert len(prep.spec["datasets"]["obs"]) == prep.rows["obs"]
    assert json.dumps(short)


# --------------------------------------------------------------------------- describe


def test_describe_inputs_and_bindings(obs, fcst):
    lines = vega.describe_inputs({"obs": obs, "fcst": fcst, "region": region_geojson()})
    text = "\n".join(lines)
    assert "input obs: zarr" in text and "aggregation_period='7D'" in text
    assert "valid_time" in text  # derived source on the forecast
    assert "input region: geojson" in text
    prep = vega.prepare(map_spec(), {"obs": obs})
    bound = "\n".join(vega.describe_bindings(prep))
    assert "bound obs: 8500 rows (lon, lon2, lat, lat2, precip)" in bound
    assert "default spec.projection.fit" in bound


def test_inputs_dequantified(obs):
    from weather_skills_core.units import quantify_dataset

    q = quantify_dataset(obs)
    prep = vega.prepare(map_spec(), {"obs": q})
    assert prep.spec["layer"][0]["encoding"]["color"]["title"] == "Total precipitation [mm]"
    assert isinstance(prep.spec["datasets"]["obs"][0]["precip"], float)


def test_xr_inputs_not_mutated(obs):
    before = obs.copy(deep=True)
    vega.prepare(map_spec(), {"obs": obs})
    xr.testing.assert_identical(obs, before)
