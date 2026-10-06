"""Prototype engine: bind Zarr data into a Vega-Lite spec, expand placeholders, render.

This is the design prototype, not the shipped library. It exists to prove the
API in ``../DESIGN.md``: a spec is plain Vega-Lite; ``datasets.<name>`` may be a
*binding* object instead of an array of rows; a few ``$``-prefixed placeholder
objects expand to concrete Vega-Lite values; Altair validates and dispatches
the top-level chart type; vl-convert renders.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TZ", "UTC")  # vl-convert's JS runtime parses ISO datetimes as local time

import numpy as np
import pandas as pd
import xarray as xr

HERE = Path(__file__).parent
REPO = HERE.parents[3]
NE_CACHE = Path(os.environ.get("WS_NE_CACHE", HERE / "data" / "naturalearth"))
NE_VERSION = "v5.1.2"
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{NE_VERSION}/geojson/ne_{{scale}}_{{name}}.geojson"
)
NE_LAYERS = {
    "countries": "admin_0_countries",
    "borders": "admin_0_boundary_lines_land",
    "coastline": "coastline",
    "lakes": "lakes",
    "rivers": "rivers_lake_centerlines",
    "admin1": "admin_1_states_provinces_lines",
    "ocean": "ocean",
    "land": "land",
}


class SpecError(ValueError):
    """A spec problem the agent can fix; the message names the JSON path."""


def _theme():
    """The dev branch palette module, loaded without the matplotlib-backed package."""
    spec = importlib.util.spec_from_file_location(
        "ws_theme", REPO / "src/weather_skills_plotting/theme.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


THEME = _theme()


# --------------------------------------------------------------------------- binding


def _cell_edges(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lower / upper cell edges from 1-D centers (midpoints; ends mirrored)."""
    v = np.asarray(values, dtype=float)
    if v.size == 1:
        return v - 0.5, v + 0.5
    mid = (v[:-1] + v[1:]) / 2
    edges = np.concatenate([[v[0] - (mid[0] - v[0])], mid, [v[-1] + (v[-1] - mid[-1])]])
    lo, hi = edges[:-1], edges[1:]
    return np.minimum(lo, hi), np.maximum(lo, hi)


def _slice_or_value(value):
    if isinstance(value, dict):
        unknown = set(value) - {"start", "stop", "step"}
        if unknown:
            raise SpecError(f"slice keys are start/stop/step, not {sorted(unknown)}")
        return slice(value.get("start"), value.get("stop"), value.get("step"))
    return value


def _apply_sel(da, binding, loc):
    for dim, value in (binding.get("isel") or {}).items():
        if dim not in da.dims:
            raise SpecError(f"{loc}.isel: {dim!r} is not a dim (dims: {list(da.dims)})")
        da = da.isel({dim: _slice_or_value(value)})
    for dim, value in (binding.get("sel") or {}).items():
        if dim not in da.dims:
            raise SpecError(f"{loc}.sel: {dim!r} is not a dim (dims: {list(da.dims)})")
        coord = da[dim]
        if coord.dtype.kind == "m" and not isinstance(value, dict):
            value = pd.to_timedelta(value)
        elif coord.dtype.kind == "M" and not isinstance(value, dict):
            value = (
                np.datetime64(value)
                if not isinstance(value, list)
                else [np.datetime64(v) for v in value]
            )
        target = _slice_or_value(value)
        method = (
            "nearest"
            if coord.dtype.kind in "iufM" and not isinstance(target, (slice, list))
            else None
        )
        da = da.sel({dim: target}, method=method)
    return da


def _apply_bbox(da, bbox, loc):
    if bbox is None:
        return da
    n, w, s, e = bbox
    lat = next((d for d in ("latitude", "lat") if d in da.coords), None)
    lon = next((d for d in ("longitude", "lon") if d in da.coords), None)
    if lat is None or lon is None:
        raise SpecError(f"{loc}.bbox: data has no latitude/longitude coords")
    if lat in da.dims and lon in da.dims:
        lat_vals = da[lat].values
        lat_slice = slice(n, s) if lat_vals[0] > lat_vals[-1] else slice(s, n)
        return da.sel({lat: lat_slice, lon: slice(w, e)})
    mask = (da[lat] >= s) & (da[lat] <= n) & (da[lon] >= w) & (da[lon] <= e)
    return da.where(mask, drop=True)


def _to_json_values(series: pd.Series):
    # Epoch milliseconds (UTC): Vega-Lite treats them as temporal without string parsing, so
    # lookups/joins between datasets match whether or not a dataset feeds a temporal axis.
    if pd.api.types.is_datetime64_any_dtype(series):
        return (series.astype("datetime64[ms]").astype("int64")).astype(float)
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds() / 86400.0
    return series


def bind_zarr(name: str, binding: dict, inputs: dict) -> tuple[list[dict], dict]:
    """Tidy rows for one ``datasets.<name>`` Zarr binding, plus metadata for placeholders."""
    loc = f"datasets.{name}"
    ds = inputs.get(binding["zarr"])
    if ds is None:
        raise SpecError(f"{loc}.zarr {binding['zarr']!r} is not an input (have {sorted(inputs)})")
    fields = binding.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise SpecError(
            f"{loc}.fields is required: a map of column name -> dim, coord, or variable"
        )
    var_names = [src for src in fields.values() if src in ds.data_vars]
    if not var_names:
        raise SpecError(f"{loc}.fields names no data variable (have {list(ds.data_vars)})")
    sub = ds[var_names]
    sub = _apply_bbox(sub, binding.get("bbox"), loc)
    sub = _apply_sel(sub, binding, loc)

    wanted_dims = set()
    derived = {}
    for col, src in fields.items():
        base, _, suffix = src.partition(".")
        if src in sub.data_vars:
            continue
        if suffix in ("lo", "hi") and base in sub.dims:
            wanted_dims.add(base)
            derived[col] = (base, suffix)
        elif src == "valid_time" and "time" in sub.coords and "step" in sub.coords:
            wanted_dims.update(d for d in ("time", "step") if d in sub.dims)
            derived[col] = ("valid_time", None)
        elif src in sub.dims:
            wanted_dims.add(src)
        elif src in sub.coords:
            wanted_dims.update(sub[src].dims)
        else:
            raise SpecError(
                f"{loc}.fields.{col}: {src!r} is not a dim, coord, or variable "
                f"(dims {list(sub.dims)}, coords {list(sub.coords)}, variables {list(sub.data_vars)}); "
                "derived sources are '<dim>.lo', '<dim>.hi', 'valid_time'"
            )
    leftover = {d: n for d, n in sub.sizes.items() if d not in wanted_dims and n > 1}
    if leftover:
        raise SpecError(
            f"{loc}: dims {leftover} are not columns in fields and have more than one value. "
            "Add each one to fields, pick one value with sel/isel, or reduce it upstream "
            "(reduce, aggregate-temporal). Nothing is averaged for you."
        )
    sub = sub.squeeze(
        [d for d in sub.dims if d not in wanted_dims and sub.sizes[d] == 1], drop=False
    )
    df = sub.to_dataframe().reset_index()
    if binding.get("dropna", True):
        df = df.dropna(subset=var_names, how="all")
    out = pd.DataFrame(index=df.index)
    for col, src in fields.items():
        if col in derived:
            base, suffix = derived[col]
            if base == "valid_time":
                out[col] = _to_json_values(pd.to_datetime(df["time"]) + pd.to_timedelta(df["step"]))
            else:
                lo, hi = _cell_edges(sub[base].values)
                # Opt-in: abutting rects show antialiasing seams; overlap hides them on fine grids.
                pad = (hi - lo) * float(binding.get("cell_overlap", 0.0)) / 2
                lo, hi = lo - pad, hi + pad
                lookup = dict(
                    zip(
                        sub[base].values.tolist(),
                        (lo if suffix == "lo" else hi).tolist(),
                        strict=True,
                    )
                )
                out[col] = df[base].map(lookup)
        else:
            out[col] = _to_json_values(df[src])
    rows = json.loads(out.to_json(orient="records", date_format="iso"))
    meta = {"columns": list(fields), "fields": fields, "ds": sub, "rows": len(rows)}
    return rows, meta


def _clip_features(features, bbox, pad=1.0):
    from shapely.geometry import box, mapping, shape

    n, w, s, e = bbox
    clip = box(w - pad, s - pad, e + pad, n + pad)
    out = []
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        g = shape(geom)
        if not g.intersects(clip):
            continue
        g = g.intersection(clip)
        if g.is_empty:
            continue
        out.append(
            {"type": "Feature", "properties": feat.get("properties") or {}, "geometry": mapping(g)}
        )
    return out


def _orient_for_d3(features):
    """d3-geo wants clockwise exterior rings; shapely's orient(sign=-1) gives that."""
    from shapely.geometry import MultiPolygon, Polygon, mapping, shape
    from shapely.geometry.polygon import orient

    out = []
    for feat in features:
        g = shape(feat["geometry"])
        if isinstance(g, Polygon):
            g = orient(g, sign=-1.0)
        elif isinstance(g, MultiPolygon):
            g = MultiPolygon([orient(p, sign=-1.0) for p in g.geoms])
        out.append({**feat, "geometry": mapping(g)})
    return out


def bind_naturalearth(name: str, binding: dict) -> list[dict]:
    loc = f"datasets.{name}"
    layer = binding["naturalearth"]
    if layer not in NE_LAYERS:
        raise SpecError(f"{loc}.naturalearth {layer!r}: choose one of {sorted(NE_LAYERS)}")
    scale = binding.get("scale", "50m")
    path = NE_CACHE / f"ne_{scale}_{NE_LAYERS[layer]}.geojson"
    if not path.exists():
        import urllib.request

        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(NE_URL.format(scale=scale, name=NE_LAYERS[layer]), path)
    features = json.loads(path.read_text())["features"]
    if binding.get("bbox"):
        features = _clip_features(features, binding["bbox"])
    keep = binding.get("properties", ["name"])
    for feat in features:
        feat["properties"] = {
            k: v for k, v in (feat.get("properties") or {}).items() if k.lower() in keep
        }
    return _orient_for_d3(features)


def bind_geojson(name: str, binding: dict, geojsons: dict) -> list[dict]:
    src = binding["geojson"]
    path = Path(geojsons.get(src, src))
    data = json.loads(path.read_text())
    features = data["features"] if data.get("type") == "FeatureCollection" else [data]
    if binding.get("bbox"):
        features = _clip_features(features, binding["bbox"])
    return _orient_for_d3(features)


def bind_contours(name: str, binding: dict, inputs: dict) -> tuple[list[dict], dict]:
    """``{"zarr", "contours": {"variable", "levels", "filled"}}`` -> GeoJSON lines or bands.

    Vega-Lite has no contour mark; contourpy (numpy only) traces the field and
    each feature carries ``properties.level`` (lines) or ``lo`` / ``hi`` (bands)
    for the color encoding.
    """
    import contourpy

    loc = f"datasets.{name}"
    opts = binding["contours"]
    ds = inputs[binding["zarr"]]
    da = _apply_sel(
        _apply_bbox(ds[opts["variable"]], binding.get("bbox"), loc), binding, loc
    ).squeeze(drop=True)
    if set(da.dims) != {"latitude", "longitude"}:
        raise SpecError(
            f"{loc}.contours needs a 2-D latitude/longitude field after sel; dims are {list(da.dims)}"
        )
    da = da.transpose("latitude", "longitude")
    gen = contourpy.contour_generator(
        da["longitude"].values, da["latitude"].values, da.values.astype(float)
    )
    levels = list(opts["levels"])
    features = []
    if opts.get("filled"):
        for lo, hi in zip(levels[:-1], levels[1:], strict=True):
            points, offsets = gen.filled(lo, hi)
            for pts, offs in zip(points, offsets, strict=True):
                rings = [pts[a:b].tolist() for a, b in zip(offs[:-1], offs[1:], strict=True)]
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"lo": lo, "hi": hi, "mid": (lo + hi) / 2},
                        "geometry": {"type": "Polygon", "coordinates": rings},
                    }
                )
    else:
        for level in levels:
            lines = [seg.tolist() for seg in gen.lines(level) if len(seg) > 1]
            if lines:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"level": level},
                        "geometry": {"type": "MultiLineString", "coordinates": lines},
                    }
                )
    features = _orient_for_d3(features)
    meta = {
        "rows": len(features),
        "columns": ["type", "properties", "geometry"],
        "ds": da.to_dataset(name=opts["variable"]),
        "fields": {opts["variable"]: opts["variable"]},
    }
    return features, meta


def bind_all(spec: dict, inputs: dict, geojsons: dict | None = None):
    """Replace every binding object under ``datasets`` with rows. Returns (spec, meta)."""
    spec = copy.deepcopy(spec)
    meta = {}
    for name, binding in list((spec.get("datasets") or {}).items()):
        if isinstance(binding, list):
            meta[name] = {
                "rows": len(binding),
                "columns": sorted({k for r in binding[:50] for k in r}),
            }
            continue
        if not isinstance(binding, dict):
            raise SpecError(f"datasets.{name} must be rows (a list) or a binding object")
        kinds = [k for k in ("zarr", "geojson", "naturalearth") if k in binding]
        if len(kinds) != 1:
            raise SpecError(f"datasets.{name} needs exactly one of zarr, geojson, naturalearth")
        if kinds[0] == "zarr" and "contours" in binding:
            rows, meta[name] = bind_contours(name, binding, inputs)
        elif kinds[0] == "zarr":
            rows, meta[name] = bind_zarr(name, binding, inputs)
        elif kinds[0] == "geojson":
            rows = bind_geojson(name, binding, geojsons or {})
            meta[name] = {"rows": len(rows), "columns": ["type", "properties", "geometry"]}
        else:
            rows = bind_naturalearth(name, binding)
            meta[name] = {"rows": len(rows), "columns": ["type", "properties", "geometry"]}
        spec["datasets"][name] = rows
    return spec, meta


# --------------------------------------------------------------------------- placeholders


def _var_da(ref: str, meta: dict, loc: str):
    """``"fcst.tp"`` -> the bound DataArray (after sel/bbox)."""
    data, _, column = ref.partition(".")
    if data not in meta or "ds" not in meta[data]:
        raise SpecError(f"{loc}: {data!r} is not a Zarr binding (have {sorted(meta)})")
    src = meta[data]["fields"].get(column, column)
    ds = meta[data]["ds"]
    if src not in ds.data_vars:
        raise SpecError(f"{loc}: {column!r} is not a variable column of {data!r}")
    return ds[src]


def _label(da) -> str:
    from weather_skills_core.units import format_units_for_display

    name = da.attrs.get("long_name") or da.name
    units = da.attrs.get("units")
    return f"{name} [{format_units_for_display(units)}]" if units else str(name)


def _palette_scale(value: dict, meta: dict, loc: str) -> dict:
    """``{"$palette": name|{colors,bounds,under,over}, "data": "fcst.tp"}`` -> threshold scale."""
    pal = value["$palette"]
    da = _var_da(value["data"], meta, loc) if value.get("data") else None
    if isinstance(pal, str):
        key = pal.lower()
        if key in THEME.DEFAULT_PRECIP_PALETTES:
            window = THEME.default_precip_scale_name(key, da)
            entry = (
                THEME.precip_nested_anomaly_palette
                if THEME.DEFAULT_PRECIP_PALETTES[key]
                else THEME.precip_nested_palette
            )(window)
        else:
            entry, _ = THEME._palette_entry(THEME.default_theme()["colormaps"], pal)
            if not entry or not entry.get("bounds"):
                raise SpecError(
                    f"{loc}.$palette {pal!r} is not a class palette; use a Vega scheme instead"
                )
    else:
        entry = THEME._validate_colormap_object(pal, loc=f"{loc}.$palette")
    colors, bounds = list(entry["colors"]), list(entry["bounds"])
    n_bins = len(bounds) - 1
    if len(colors) == n_bins:
        colors = [entry.get("under", colors[0]), *colors, entry.get("over", colors[-1])]
    elif entry.get("under") or entry.get("over"):
        colors = [entry.get("under", colors[0]), *colors, entry.get("over", colors[-1])]
    scale = {"type": "threshold", "domain": bounds, "range": colors}
    return {**scale, **{k: v for k, v in value.items() if k not in ("$palette", "data")}}


def _fmt(b: float) -> str:
    return f"{b:g}"


def _colorbar(value: dict, meta: dict, loc: str) -> dict:
    """``{"$colorbar": palette, "data": "fcst.tp", ...}`` -> a unit chart drawing equal-width classes.

    Vega legends size threshold classes by value, so a 0–1 mm class next to a
    200–400 mm class is invisible. Classed weather colorbars give every class the
    same width, labelled at the class edges, with under/over triangles.
    """
    scale = _palette_scale({"$palette": value["$colorbar"], "data": value.get("data")}, meta, loc)
    bounds, colors = scale["domain"], scale["range"]
    under, classes, over = colors[0], colors[1:-1], colors[-1]
    n = len(classes)
    extend = value.get("extend", "both")
    lo_ext = 0.8 if extend in ("both", "min") else 0.0
    hi_ext = 0.8 if extend in ("both", "max") else 0.0
    horizontal = value.get("orient", "horizontal") == "horizontal"
    length = value.get("length", 400)
    thick = value.get("thickness", 14)
    title = value.get("title")
    if title is None and value.get("data"):
        title = _label(_var_da(value["data"], meta, loc))
    pos, pos2, other = ("x", "x2", "y") if horizontal else ("y", "y2", "x")
    labels = json.dumps([_fmt(b) for b in bounds])
    rows = [{"i": k, "i2": k + 1, "color": c} for k, c in enumerate(classes)]
    tri = []
    if lo_ext:
        tri.append(
            {
                "i": -lo_ext / 2,
                "color": under,
                "shape": "triangle-left" if horizontal else "triangle-down",
            }
        )
    if hi_ext:
        tri.append(
            {
                "i": n + hi_ext / 2,
                "color": over,
                "shape": "triangle-right" if horizontal else "triangle-up",
            }
        )
    axis = {
        "values": list(range(n + 1)),
        # Vega thins explicit `values` down to tickCount, which VL derives from the length.
        "tickCount": n + 1,
        "labelExpr": f"{labels}[datum.value]",
        "title": title,
        "grid": False,
        "domain": False,
        "ticks": True,
        "labelFlush": False,
        "labelOverlap": False,
        "labelFontSize": value.get("label_size", 10),
        "orient": "bottom" if horizontal else "right",
    }
    pos_scale = {"domain": [-lo_ext, n + hi_ext], "nice": False, "zero": False}
    size = {"width": length, "height": thick} if horizontal else {"width": thick, "height": length}
    layers = [
        {
            "data": {"values": rows},
            "mark": {"type": "rect", "stroke": "#333", "strokeWidth": 0.5},
            "encoding": {
                pos: {"field": "i", "type": "quantitative", "scale": pos_scale, "axis": axis},
                pos2: {"field": "i2"},
                "color": {"field": "color", "type": "nominal", "scale": None, "legend": None},
            },
        }
    ]
    if tri:
        layers.append(
            {
                "data": {"values": tri},
                "mark": {
                    "type": "point",
                    "filled": True,
                    "opacity": 1,
                    "stroke": "#333",
                    "strokeWidth": 0.5,
                    "size": (thick * 1.25) ** 2,
                },
                "encoding": {
                    pos: {"field": "i", "type": "quantitative", "scale": pos_scale},
                    other: {"value": thick / 2},
                    "shape": {"field": "shape", "type": "nominal", "scale": None, "legend": None},
                    "color": {"field": "color", "type": "nominal", "scale": None, "legend": None},
                },
            }
        )
    return {
        **size,
        "layer": layers,
        "resolve": {"scale": {"color": "independent"}},
        "view": {"stroke": None},
    }


def _bbox_feature(value, meta, loc):
    bbox = value["$bbox"]
    if isinstance(bbox, str):
        da = meta[bbox]["ds"]
        lat = da["latitude"].values
        lon = da["longitude"].values
        bbox = [
            float(np.nanmax(lat)),
            float(np.nanmin(lon)),
            float(np.nanmin(lat)),
            float(np.nanmax(lon)),
        ]
    n, w, s, e = bbox
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "MultiPoint", "coordinates": [[w, s], [e, n]]},
    }


def _extent(value, meta, loc):
    da = _var_da(value["$extent"], meta, loc)
    vals = np.asarray(da.values, dtype=float)
    lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
    if value.get("symmetric"):
        m = max(abs(lo), abs(hi))
        lo, hi = -m, m
    return [lo, hi]


PLACEHOLDERS = {
    "$palette": _palette_scale,
    "$colorbar": _colorbar,
    "$bbox": _bbox_feature,
    "$label": lambda v, meta, loc: _label(_var_da(v["$label"], meta, loc)),
    "$attr": lambda v, meta, loc: str(
        _var_da(v["$attr"].rsplit(".", 1)[0], meta, loc).attrs.get(v["$attr"].rsplit(".", 1)[1], "")
    ),
    "$extent": _extent,
}


def expand(node, meta, loc="spec"):
    if isinstance(node, dict):
        keys = [k for k in node if k.startswith("$") and k != "$schema"]
        if keys:
            if len(keys) > 1:
                raise SpecError(f"{loc}: one placeholder per object, got {keys}")
            fn = PLACEHOLDERS.get(keys[0])
            if fn is None:
                raise SpecError(
                    f"{loc}: unknown placeholder {keys[0]!r}; known: {sorted(PLACEHOLDERS)}"
                )
            return fn(node, meta, loc)
        return {
            k: (v if k == "datasets" else expand(v, meta, f"{loc}.{k}")) for k, v in node.items()
        }
    if isinstance(node, list):
        return [expand(v, meta, f"{loc}[{i}]") for i, v in enumerate(node)]
    return node


# --------------------------------------------------------------------------- dispatch / lint / render

COMPOSITION_KEYS = ("layer", "hconcat", "vconcat", "concat", "facet", "repeat", "mark")


def chart_class(spec: dict):
    import altair as alt

    present = [k for k in COMPOSITION_KEYS if k in spec]
    if "facet" in present or "repeat" in present:
        if "spec" not in spec:
            raise SpecError(f"top-level {present[0]!r} needs a 'spec' to repeat")
        return alt.FacetChart if "facet" in present else alt.RepeatChart
    if len(present) != 1:
        raise SpecError(
            f"top level must have exactly one of layer, hconcat, vconcat, concat, facet+spec, "
            f"repeat+spec, mark; found {present or 'none'}"
        )
    return {
        "layer": alt.LayerChart,
        "hconcat": alt.HConcatChart,
        "vconcat": alt.VConcatChart,
        "concat": alt.ConcatChart,
        "mark": alt.Chart,
    }[present[0]]


def validate(spec: dict):
    """Altair schema validation on a copy with each dataset cut to a few rows (full validation is slow)."""
    stub = copy.deepcopy({k: v for k, v in spec.items() if k != "datasets"})
    stub["datasets"] = {k: v[:3] for k, v in (spec.get("datasets") or {}).items()}
    cls = chart_class(spec)
    return cls.from_dict(stub)


def _walk_units(node, data_name=None, path="spec"):
    """Yield (data_name, path, field, derived_names) for every encoding field in every unit spec."""
    if isinstance(node, dict):
        data = node.get("data", {})
        if isinstance(data, dict) and "name" in data:
            data_name = data["name"]
        elif isinstance(data, dict) and data:
            data_name = None
        derived = set()
        for t in node.get("transform", []) or []:
            for key in ("as",):
                v = t.get(key)
                if isinstance(v, str):
                    derived.add(v)
                elif isinstance(v, list):
                    derived.update(x for x in v if isinstance(x, str))
            for agg in t.get("aggregate", []) or []:
                derived.add(agg.get("as"))
            for agg in t.get("window", []) or []:
                derived.add(agg.get("as"))
            if "pivot" in t:
                derived.add("*pivot*")
            if "fold" in t:
                derived.update(t.get("as", ["key", "value"]))
            if "quantile" in t:
                derived.update(t.get("as", ["prob", "value"]))
        for ch, enc in (node.get("encoding") or {}).items():
            if isinstance(enc, dict) and isinstance(enc.get("field"), str):
                yield data_name, f"{path}.encoding.{ch}", enc["field"], derived
        for key in ("layer", "hconcat", "vconcat", "concat"):
            for i, child in enumerate(node.get(key, []) or []):
                for item in _walk_units(child, data_name, f"{path}.{key}[{i}]"):
                    yield item[0], item[1], item[2], item[3] | derived
        if isinstance(node.get("spec"), dict):
            for item in _walk_units(node["spec"], data_name, f"{path}.spec"):
                yield item[0], item[1], item[2], item[3] | derived


def lint_fields(spec: dict, meta: dict) -> list[str]:
    """Encoding fields that are not a column of their dataset (Vega-Lite would draw nothing)."""
    problems = []
    for data_name, path, field, derived in _walk_units(spec):
        if data_name not in meta or "*pivot*" in derived:
            continue
        cols = set(meta[data_name]["columns"]) | derived
        top = field.split(".")[0]
        if field not in cols and top not in cols:
            problems.append(
                f"{path}.field {field!r} is not a column of {data_name!r} (columns: {sorted(cols)})"
            )
    return problems


def seal_cells(vega: dict) -> int:
    """Stroke scale-filled rect marks with their own fill so abutting cells show no seams.

    Antialiasing leaves hairline gaps between abutting rects (grid cells). Only
    Vega-Lite ``rect`` marks whose fill comes from a scale and that set no
    stroke are touched; bars, geoshapes and anything with an explicit stroke are
    left alone. Patching the compiled Vega avoids knowing scale names
    (``color`` vs ``concat_0_color``) and leaves legends untouched.
    """
    count = 0

    def walk(marks):
        nonlocal count
        for mark in marks:
            if mark.get("type") == "group":
                walk(mark.get("marks", []))
                continue
            style = mark.get("style") or []
            style = [style] if isinstance(style, str) else style
            update = mark.get("encode", {}).get("update", {})
            fill = update.get("fill")
            if (
                mark.get("type") == "rect"
                and "rect" in style
                and isinstance(fill, dict)
                and "scale" in fill
                and "stroke" not in update
            ):
                update["stroke"] = copy.deepcopy(fill)
                update.setdefault("strokeWidth", {"value": 0.5})
                count += 1

    walk(vega.get("marks", []))
    return count


def render(spec_in: dict, inputs: dict, out: Path, *, geojsons=None, scale=2.0) -> dict:
    import vl_convert as vlc

    t0 = time.time()
    bound, meta = bind_all(spec_in, inputs, geojsons)
    t1 = time.time()
    spec = expand(bound, meta)
    spec.setdefault("$schema", "https://vega.github.io/schema/vega-lite/v6.json")
    problems = lint_fields(spec, meta)
    if problems:
        raise SpecError("\n".join(problems))
    validate(spec)
    t2 = time.time()
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    vega = json.loads(vega) if isinstance(vega, str) else vega
    if (spec.get("usermeta") or {}).get("seal_cells", True):
        seal_cells(vega)
    png = vlc.vega_to_png(vega, scale=scale)
    out.write_bytes(png)
    t3 = time.time()
    rows = {k: m["rows"] for k, m in meta.items()}
    return {
        "rows": rows,
        "bind_s": round(t1 - t0, 2),
        "validate_s": round(t2 - t1, 2),
        "render_s": round(t3 - t2, 2),
        "json_mb": round(len(json.dumps(spec)) / 1e6, 2),
    }


def open_inputs(named: dict[str, Path]) -> dict:
    return {k: xr.open_zarr(v, consolidated=True) for k, v in named.items()}
