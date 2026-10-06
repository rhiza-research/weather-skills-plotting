"""Prototype engine: bind Zarr data into a Vega-Lite spec, fill defaults, render.

This is the design prototype, not the shipped library. It exists to prove the
API in ``../DESIGN.md``: a spec is plain Vega-Lite; ``datasets.<name>`` may be a
*binding* object instead of an array of rows; anything the agent leaves unset
(colour scale, title, projection fit, base-map clip box) gets a default derived
from the bound data; our palette names work as ``scale.scheme``; Altair
validates and dispatches the top-level chart type; vl-convert renders.
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
    """Tidy rows for one ``datasets.<name>`` Zarr binding, plus metadata for the defaults."""
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
    meta = {
        "columns": list(fields),
        "var_cols": {col: src for col, src in fields.items() if src in sub.data_vars},
        "ds": sub,
        "rows": len(rows),
        # Cell edges only when the agent asked for them (rect cells); points otherwise.
        "extent": _extent(sub, edges=any(sfx in ("lo", "hi") for _, sfx in derived.values())),
    }
    return rows, meta


def _extent(obj, *, edges: bool) -> list[float] | None:
    """``[N, W, S, E]`` of the bound data: cell edges for grids, points for stations."""
    lat = next((d for d in ("latitude", "lat") if d in obj.coords), None)
    lon = next((d for d in ("longitude", "lon") if d in obj.coords), None)
    if lat is None or lon is None:
        return None
    if edges and lat in obj.dims and lon in obj.dims:
        lat_lo, lat_hi = _cell_edges(obj[lat].values)
        lon_lo, lon_hi = _cell_edges(obj[lon].values)
        return [
            float(lat_hi.max()),
            float(lon_lo.min()),
            float(lat_lo.min()),
            float(lon_hi.max()),
        ]
    la, lo = np.asarray(obj[lat].values, float), np.asarray(obj[lon].values, float)
    return [float(np.nanmax(la)), float(np.nanmin(lo)), float(np.nanmin(la)), float(np.nanmax(lo))]


def _union(extents) -> list[float] | None:
    extents = [e for e in extents if e]
    if not extents:
        return None
    return [
        max(e[0] for e in extents),
        min(e[1] for e in extents),
        min(e[2] for e in extents),
        max(e[3] for e in extents),
    ]


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
    var = opts["variable"]
    meta = {
        "rows": len(features),
        "columns": ["type", "properties", "geometry"],
        "ds": da.to_dataset(name=var),
        # Band and line values are in the variable's units, so they get its defaults.
        "var_cols": {f"properties.{k}": var for k in ("lo", "hi", "mid", "level")},
        # Contours stop at the outermost cell centres, not the cell edges.
        "extent": _extent(da, edges=False),
    }
    return features, meta


def bind_all(
    spec: dict,
    inputs: dict,
    geojsons: dict | None = None,
    notes: list | None = None,
    *,
    defaults: bool = True,
):
    """Replace every binding object under ``datasets`` with rows. Returns (spec, meta).

    Zarr bindings go first so vector layers without a ``bbox`` can be clipped to
    the extent of the plotted data.
    """
    spec = copy.deepcopy(spec)
    notes = [] if notes is None else notes
    meta = {}
    vectors = []
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
        if kinds[0] != "zarr":
            vectors.append((name, kinds[0], binding))
            continue
        if "contours" in binding:
            rows, meta[name] = bind_contours(name, binding, inputs)
        else:
            rows, meta[name] = bind_zarr(name, binding, inputs)
        spec["datasets"][name] = rows
    data_extent = _union(m.get("extent") for m in meta.values())
    for name, kind, binding in vectors:
        if defaults and "bbox" not in binding and data_extent:
            binding = {**binding, "bbox": [round(v, 4) for v in data_extent]}
            notes.append(f"datasets.{name}.bbox <- extent of the bound data {binding['bbox']}")
        if kind == "geojson":
            rows = bind_geojson(name, binding, geojsons or {})
        else:
            rows = bind_naturalearth(name, binding)
        meta[name] = {"rows": len(rows), "columns": ["type", "properties", "geometry"]}
        spec["datasets"][name] = rows
    return spec, meta


# --------------------------------------------------------------------------- defaults

COLOR_CHANNELS = ("color", "fill", "stroke")
TITLE_CHANNELS = ("x", "y", "color", "fill", "stroke", "size", "opacity", "theta", "radius")
# Any of these in a colour scale means the agent chose the scale; the skill leaves it alone.
SCALE_CHOICE_KEYS = ("type", "scheme", "range", "domain", "domainMid", "domainMin", "domainMax")
FIT_KEYS = ("fit", "scale", "translate")


def _label(da) -> str:
    from weather_skills_core.units import format_units_for_display

    name = da.attrs.get("long_name") or da.name
    units = da.attrs.get("units")
    return f"{name} [{format_units_for_display(units)}]" if units else str(name)


def _palette_names() -> frozenset[str]:
    named = [k for k, v in THEME.default_theme()["colormaps"].items() if v.get("bounds")]
    return frozenset(k.lower() for k in (*THEME.DEFAULT_PRECIP_PALETTES, *named))


PALETTE_NAMES = _palette_names()


def _threshold(entry: dict) -> tuple[list, list]:
    """Vega threshold ``(domain, range)``: range is under + one colour per class + over."""
    colors, bounds = list(entry["colors"]), list(entry["bounds"])
    n_bins = len(bounds) - 1
    if len(colors) == n_bins:
        colors = [entry.get("under", colors[0]), *colors, entry.get("over", colors[-1])]
    elif len(colors) > n_bins + 2:
        # Dev's packing rule: first is under, last is over, classes follow the under.
        colors = [colors[0], *colors[1 : 1 + n_bins], colors[-1]]
    elif len(colors) != n_bins + 2:
        raise SpecError(f"palette has {len(colors)} colours for {n_bins} classes")
    return bounds, colors


def palette_scale(name: str, da=None) -> tuple[str, list, list]:
    """``(resolved name, bounds, colours)`` for one of our palette names."""
    key = name.lower()
    if key in THEME.DEFAULT_PRECIP_PALETTES:
        window = THEME.default_precip_scale_name(key, da)
        build = (
            THEME.precip_nested_anomaly_palette
            if THEME.DEFAULT_PRECIP_PALETTES[key]
            else THEME.precip_nested_palette
        )
        return (window, *_threshold(build(window)))
    entry, _ = THEME._palette_entry(THEME.default_theme()["colormaps"], key)
    return (key, *_threshold(entry))


def _detected_palette(da):
    """Dev's automatic choice: precip totals / anomalies by window, SPI, percent of normal."""
    if not (THEME.is_precip(da) or THEME.is_spi(da) or THEME.is_precip_poa(da)):
        return None
    name, colors, bounds = THEME.named_precip_scale(da)
    return (name, *_threshold({"colors": colors, "bounds": bounds}))


def _derived_names(transforms) -> set[str]:
    """Columns that transforms create or overwrite (no longer the raw bound variable)."""
    out = set()
    for t in transforms or []:
        if not isinstance(t, dict):
            continue
        v = t.get("as")
        if isinstance(v, str):
            out.add(v)
        elif isinstance(v, list):
            out.update(x for x in v if isinstance(x, str))
        for key in ("aggregate", "window", "joinaggregate"):
            for item in t.get(key) or []:
                if isinstance(item, dict) and item.get("as"):
                    out.add(item["as"])
        if "lookup" in t:
            out.update((t.get("from") or {}).get("fields") or [])
        if "pivot" in t:
            out.add("*pivot*")
        if "fold" in t and "as" not in t:
            out.update(["key", "value"])
        if "quantile" in t and "as" not in t:
            out.update(["prob", "value"])
    return out


def _units(node, data_name=None, derived=frozenset(), path="spec"):
    """Yield ``(view, data name, derived columns, JSON path)`` for every view, with inheritance."""
    if not isinstance(node, dict):
        return
    data = node.get("data")
    if isinstance(data, dict) and "name" in data:
        data_name = data["name"]
    elif isinstance(data, dict) and data:
        data_name = None
    derived = derived | _derived_names(node.get("transform"))
    yield node, data_name, derived, path
    for key in ("layer", "hconcat", "vconcat", "concat"):
        for i, child in enumerate(node.get(key) or []):
            yield from _units(child, data_name, derived, f"{path}.{key}[{i}]")
    yield from _units(node.get("spec"), data_name, derived, f"{path}.spec")


def _data_names(node) -> set[str]:
    out = set()
    if isinstance(node, dict):
        data = node.get("data")
        if isinstance(data, dict) and "name" in data:
            out.add(data["name"])
        for key, value in node.items():
            if key != "datasets":
                out |= _data_names(value)
    elif isinstance(node, list):
        for value in node:
            out |= _data_names(value)
    return out


def _fit_default(node, data_name, meta, path, notes):
    proj = node.get("projection")
    if not isinstance(proj, dict) or any(k in proj for k in FIT_KEYS):
        return
    names = ({data_name} if data_name else set()) | _data_names(node)
    extent = _union(meta.get(n, {}).get("extent") for n in sorted(names))
    if not extent:
        return
    n, w, s, e = (round(v, 4) for v in extent)
    # Two corner points: no ring, so no d3 winding to get wrong.
    proj["fit"] = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "MultiPoint", "coordinates": [[w, s], [e, n]]},
    }
    notes.append(f"{path}.projection.fit <- extent of the bound data [{n}, {w}, {s}, {e}]")


def _color_default(enc, da, loc, notes, classed):
    if enc.get("type") != "quantitative" or enc.get("scale", {}) is None:
        return
    scale = enc.get("scale") or {}
    scheme = scale.get("scheme")
    if isinstance(scheme, str) and scheme.lower() in PALETTE_NAMES:
        name, bounds, colors = palette_scale(scheme, da)
        how = f"scheme {scheme!r}"
    elif da is None or any(k in scale for k in SCALE_CHOICE_KEYS):
        return
    else:
        found = _detected_palette(da)
        if not found:
            return
        name, bounds, colors = found
        how = "default for this variable"
    rest = {k: v for k, v in scale.items() if k != "scheme"}
    enc["scale"] = {**rest, "type": "threshold", "domain": bounds, "range": colors}
    values = np.asarray(da.values, dtype=float) if da is not None else np.array([])
    finite = values[np.isfinite(values)]
    below = finite.size == 0 or bool(finite.min() < bounds[0])
    classed[tuple(bounds)] = classed.get(tuple(bounds), False) or below
    notes.append(f"{loc}.scale <- {name} ({how}; {len(bounds) - 1} classes)")


def apply_defaults(spec: dict, meta: dict, notes: list) -> dict:
    """Fill what the agent left unset from the bound data. Mutates and returns ``spec``.

    Only encodings whose field is a bound variable column (not created by a
    transform) get title and colour-scale defaults; a value computed in the
    spec has no attributes to go on. Returns ``{bounds: show_under_entry}`` for
    the classed legend patch.
    """
    classed: dict[tuple, bool] = {}
    titles = {}  # id(encoding) -> (encoding, loc, label)
    for node, data_name, derived, path in _units(spec):
        _fit_default(node, data_name, meta, path, notes)
        var_cols = (meta.get(data_name) or {}).get("var_cols", {})
        for ch, enc in (node.get("encoding") or {}).items():
            if not isinstance(enc, dict):
                continue
            field = enc.get("field")
            src = var_cols.get(field) if isinstance(field, str) and field not in derived else None
            da = meta[data_name]["ds"][src] if src else None
            loc = f"{path}.encoding.{ch}"
            if da is not None and ch in TITLE_CHANNELS and "title" not in enc:
                titles[id(enc)] = (enc, loc, _label(da))
            if ch in COLOR_CHANNELS:
                _color_default(enc, da, loc, notes, classed)
    # Layers share axes and legends, and Vega-Lite joins differing layer titles with
    # commas. Only the first layer that has a title for a channel keeps it.
    for node, *_ in _units(spec):
        for ch in TITLE_CHANNELS:
            encs = [
                child["encoding"][ch]
                for child in node.get("layer") or []
                if isinstance((child.get("encoding") or {}).get(ch), dict)
            ]
            owners = [e for e in encs if "title" in e or id(e) in titles]
            for enc in owners[1:]:
                titles.pop(id(enc), None)
    for enc, loc, label in titles.values():
        enc["title"] = label
        notes.append(f"{loc}.title <- {label!r}")
    return classed


def classed_legends(vega: dict, classed: dict) -> int:
    """Turn threshold-scale legends into one equal-size swatch per class.

    Vega-Lite draws a threshold legend as a gradient sized by value, so narrow
    classes (0–1 mm beside 200–400 mm) vanish, and it ignores ``legend.type``
    for these scales. The compiled Vega legend accepts ``type: symbol``, which
    labels each class with its range. The under entry (``< 0``) is dropped when
    no plotted value falls below the first bound.
    """
    count = 0

    def walk(node, scales):
        nonlocal count
        scales = {**scales, **{s["name"]: s for s in node.get("scales") or []}}
        for lg in node.get("legends") or []:
            sc = scales.get(lg.get("fill") or lg.get("stroke"))
            if not sc or sc.get("type") != "threshold":
                continue
            for key in ("gradientLength", "gradientThickness", "gradientStrokeWidth"):
                lg.pop(key, None)
            lg["type"] = "symbol"
            lg["symbolType"] = "square"
            lg.setdefault("symbolSize", 196)
            lg.setdefault("symbolStrokeColor", "#888")
            lg.setdefault("symbolStrokeWidth", 0.5)
            domain = sc.get("domain")
            if (
                "values" not in lg
                and isinstance(domain, list)
                and not classed.get(tuple(domain), True)
            ):
                lg["values"] = domain
            count += 1
        for mark in node.get("marks") or []:
            if mark.get("type") == "group":
                walk(mark, scales)

    walk(vega, {})
    return count


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


def lint_fields(spec: dict, meta: dict) -> list[str]:
    """Encoding fields that are not a column of their dataset (Vega-Lite would draw nothing)."""
    problems = []
    for node, data_name, derived, path in _units(spec):
        if data_name not in meta or "*pivot*" in derived:
            continue
        cols = set(meta[data_name]["columns"]) | derived
        for ch, enc in (node.get("encoding") or {}).items():
            field = enc.get("field") if isinstance(enc, dict) else None
            if not isinstance(field, str):
                continue
            if field not in cols and field.split(".")[0] not in cols:
                problems.append(
                    f"{path}.encoding.{ch}.field {field!r} is not a column of {data_name!r} "
                    f"(columns: {sorted(cols)})"
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

    usermeta = spec_in.get("usermeta") or {}
    use_defaults = usermeta.get("defaults", True)
    notes: list[str] = []
    t0 = time.time()
    spec, meta = bind_all(spec_in, inputs, geojsons, notes, defaults=use_defaults)
    t1 = time.time()
    classed = apply_defaults(spec, meta, notes) if use_defaults else {}
    spec.setdefault("$schema", "https://vega.github.io/schema/vega-lite/v6.json")
    problems = lint_fields(spec, meta)
    if problems:
        raise SpecError("\n".join(problems))
    validate(spec)
    t2 = time.time()
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    vega = json.loads(vega) if isinstance(vega, str) else vega
    if usermeta.get("seal_cells", True):
        seal_cells(vega)
    if use_defaults and usermeta.get("classed_legend", True):
        classed_legends(vega, classed)
    png = vlc.vega_to_png(vega, scale=scale)
    out.write_bytes(png)
    t3 = time.time()
    return {
        "rows": {k: m["rows"] for k, m in meta.items()},
        "bind_s": round(t1 - t0, 2),
        "validate_s": round(t2 - t1, 2),
        "render_s": round(t3 - t2, 2),
        "json_mb": round(len(json.dumps(spec)) / 1e6, 2),
        "defaults": notes,
    }


def open_inputs(named: dict[str, Path]) -> dict:
    return {k: xr.open_zarr(v, consolidated=True) for k, v in named.items()}
