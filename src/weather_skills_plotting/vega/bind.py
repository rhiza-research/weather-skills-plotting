"""Data bindings: ``datasets.<name>`` binding objects -> Vega-Lite rows.

A binding has exactly one of ``zarr``, ``geojson`` or ``naturalearth``. A plain
list of rows passes through untouched. See ``skills/plot-vega/references/bindings.md``.
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd

from weather_skills_plotting.vega import naturalearth as ne
from weather_skills_plotting.vega.errors import SpecError

BINDING_KINDS = ("zarr", "geojson", "naturalearth")
ZARR_KEYS = frozenset({"zarr", "fields", "sel", "isel", "bbox", "dropna", "cell_overlap"})
CONTOUR_KEYS = frozenset({"zarr", "contours", "sel", "isel", "bbox"})
CONTOUR_OPTS = frozenset({"variable", "levels", "filled"})
GEOJSON_KEYS = frozenset({"geojson", "bbox"})
NATURALEARTH_KEYS = frozenset({"naturalearth", "scale", "bbox", "properties"})
DERIVED_HELP = "derived sources are '<dim>.lo', '<dim>.hi' (cell edges) and 'valid_time'"


def _check_keys(binding: dict, allowed: frozenset, loc: str) -> None:
    unknown = sorted(set(binding) - allowed)
    if unknown:
        raise SpecError(f"{loc}: unknown key(s) {unknown}; this binding takes {sorted(allowed)}")


def plain(ds):
    """The dataset without pint units (the CLI decorator opens Zarrs quantified)."""
    if any(getattr(getattr(ds[v], "pint", None), "units", None) for v in ds.data_vars):
        from weather_skills_core.units import dequantify_dataset

        return dequantify_dataset(ds)
    return ds


def cell_edges(values) -> tuple[np.ndarray, np.ndarray]:
    """Lower / upper cell edges from 1-D centres (midpoints; the end cells mirrored)."""
    v = np.asarray(values, dtype=float)
    if v.size == 1:
        return v - 0.5, v + 0.5
    mid = (v[:-1] + v[1:]) / 2
    edges = np.concatenate([[v[0] - (mid[0] - v[0])], mid, [v[-1] + (v[-1] - mid[-1])]])
    lo, hi = edges[:-1], edges[1:]
    return np.minimum(lo, hi), np.maximum(lo, hi)


def _slice_or_value(value, loc):
    if isinstance(value, dict):
        unknown = set(value) - {"start", "stop", "step"}
        if unknown:
            raise SpecError(f"{loc}: slice keys are start/stop/step, not {sorted(unknown)}")
        return slice(value.get("start"), value.get("stop"), value.get("step"))
    return value


def _coerce_label(coord, value):
    if value is None:
        return None
    if coord.dtype.kind == "m":
        return (
            [pd.to_timedelta(v) for v in value]
            if isinstance(value, list)
            else pd.to_timedelta(value)
        )
    if coord.dtype.kind == "M":
        return (
            [np.datetime64(v) for v in value] if isinstance(value, list) else np.datetime64(value)
        )
    return value


def _apply_sel(da, binding, loc):
    for dim, value in (binding.get("isel") or {}).items():
        if dim not in da.dims:
            raise SpecError(f"{loc}.isel: {dim!r} is not a dim (dims: {list(da.dims)})")
        da = da.isel({dim: _slice_or_value(value, f"{loc}.isel.{dim}")})
    for dim, value in (binding.get("sel") or {}).items():
        if dim not in da.dims:
            raise SpecError(f"{loc}.sel: {dim!r} is not a dim (dims: {list(da.dims)})")
        coord = da[dim]
        if isinstance(value, dict):
            target = _slice_or_value(
                {k: _coerce_label(coord, v) if k != "step" else v for k, v in value.items()},
                f"{loc}.sel.{dim}",
            )
        else:
            target = _coerce_label(coord, value)
        nearest = coord.dtype.kind in "iufmM" and not isinstance(target, (slice, list))
        try:
            da = da.sel({dim: target}, method="nearest" if nearest else None)
        except (KeyError, ValueError, TypeError) as exc:
            raise SpecError(
                f"{loc}.sel.{dim} {json.dumps(value)} matches nothing "
                f"({dim} runs {coord.values[0]} .. {coord.values[-1]}): {exc}"
            ) from exc
        if any(n == 0 for n in da.sizes.values()):
            raise SpecError(
                f"{loc}.sel.{dim} {json.dumps(value)} selects no values "
                f"({dim} runs {coord.values[0]} .. {coord.values[-1]})"
            )
    return da


def _latlon_names(obj):
    lat = next((d for d in ("latitude", "lat") if d in obj.coords), None)
    lon = next((d for d in ("longitude", "lon") if d in obj.coords), None)
    return lat, lon


def _apply_bbox(da, bbox, loc):
    if bbox is None:
        return da
    n, w, s, e = ne.check_bbox(bbox, loc)
    lat, lon = _latlon_names(da)
    if lat is None or lon is None:
        raise SpecError(f"{loc}.bbox: the data has no latitude/longitude coords")
    if lat in da.dims and lon in da.dims:
        lat_vals = da[lat].values
        lat_slice = slice(n, s) if lat_vals[0] > lat_vals[-1] else slice(s, n)
        out = da.sel({lat: lat_slice, lon: slice(w, e)})
    else:
        mask = (da[lat] >= s) & (da[lat] <= n) & (da[lon] >= w) & (da[lon] <= e)
        out = da.where(mask.compute(), drop=True)
    if any(size == 0 for size in out.sizes.values()):
        raise SpecError(f"{loc}.bbox {[n, w, s, e]} contains no data")
    return out


def _to_json_values(series: pd.Series):
    # Epoch milliseconds (UTC): Vega-Lite reads them as temporal without parsing strings,
    # so lookups/joins between datasets match whether or not a dataset feeds a temporal axis.
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.astype("datetime64[ms]").astype("int64").astype(float)
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds() / 86400.0
    return series


def _input(inputs: dict, binding: dict, kind: str, loc: str):
    """The ``-i`` input a binding names, checked to be a Zarr (``zarr``) or a GeoJSON file (``geojson``)."""
    src = binding[kind]
    obj = inputs.get(src)
    if obj is None:
        raise SpecError(f"{loc}.{kind} {src!r} is not an input (have {sorted(inputs)})")
    is_geojson = isinstance(obj, dict)
    if is_geojson != (kind == "geojson"):
        other = "geojson" if is_geojson else "zarr"
        raise SpecError(
            f"{loc}.{kind} {src!r} is a {other} input; bind it with {json.dumps({other: src})}"
        )
    return obj


def extent(obj, *, edges: bool) -> list[float] | None:
    """``[N, W, S, E]`` of the bound data: cell edges for grids, points for stations."""
    lat, lon = _latlon_names(obj)
    if lat is None or lon is None:
        return None
    if edges and lat in obj.dims and lon in obj.dims:
        lat_lo, lat_hi = cell_edges(obj[lat].values)
        lon_lo, lon_hi = cell_edges(obj[lon].values)
        return [
            float(lat_hi.max()),
            float(lon_lo.min()),
            float(lat_lo.min()),
            float(lon_hi.max()),
        ]
    la, lo = np.asarray(obj[lat].values, float), np.asarray(obj[lon].values, float)
    if not (np.isfinite(la).any() and np.isfinite(lo).any()):
        return None
    return [float(np.nanmax(la)), float(np.nanmin(lo)), float(np.nanmin(la)), float(np.nanmax(lo))]


def union(extents) -> list[float] | None:
    extents = [e for e in extents if e]
    if not extents:
        return None
    return [
        max(e[0] for e in extents),
        min(e[1] for e in extents),
        min(e[2] for e in extents),
        max(e[3] for e in extents),
    ]


def bind_zarr(name: str, binding: dict, inputs: dict) -> tuple[list[dict], dict]:
    """Tidy rows for one ``datasets.<name>`` Zarr binding, plus metadata for the defaults."""
    loc = f"datasets.{name}"
    _check_keys(binding, ZARR_KEYS, loc)
    ds = _input(inputs, binding, "zarr", loc)
    fields = binding.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise SpecError(
            f"{loc}.fields is required: a map of column name -> dim, coord, or variable "
            f'(e.g. {{"lon": "longitude", "lat": "latitude", "precip": "precip"}})'
        )
    for col, src in fields.items():
        if not isinstance(src, str):
            raise SpecError(f"{loc}.fields.{col} must be a string source, got {json.dumps(src)}")
    var_names = list(dict.fromkeys(src for src in fields.values() if src in ds.data_vars))
    if not var_names:
        raise SpecError(
            f"{loc}.fields names no data variable (variables: {list(ds.data_vars)}; "
            f"dims: {list(ds.dims)}; coords: {list(ds.coords)})"
        )
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
            if sub[base].dtype.kind not in "iuf":
                raise SpecError(
                    f"{loc}.fields.{col}: {src!r} needs a numeric dim; {base!r} is "
                    f"{sub[base].dtype}. For time bins, compute the end in the spec, e.g. "
                    '{"calculate": "timeOffset(\'day\', datum.week, 7)", "as": "week_end"}'
                )
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
                + DERIVED_HELP
            )
    leftover = {d: n for d, n in sub.sizes.items() if d not in wanted_dims and n > 1}
    if leftover:
        raise SpecError(
            f"{loc}: dims {leftover} are not columns in fields and have more than one value. "
            "Add each one to fields, pick one value with sel/isel, or reduce it upstream "
            "(summarize-dim, aggregate-temporal). Nothing is averaged for you."
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
                continue
            lo, hi = cell_edges(sub[base].values)
            pad = (hi - lo) * float(binding.get("cell_overlap", 0.0)) / 2
            lo, hi = lo - pad, hi + pad
            lookup = dict(
                zip(sub[base].values.tolist(), (lo if suffix == "lo" else hi).tolist(), strict=True)
            )
            out[col] = df[base].map(lookup)
        else:
            out[col] = _to_json_values(df[src])
    rows = json.loads(out.to_json(orient="records", date_format="iso"))
    meta = {
        "kind": "zarr",
        "columns": list(fields),
        "var_cols": {col: src for col, src in fields.items() if src in sub.data_vars},
        "ds": sub,
        "rows": len(rows),
        # Cell edges only when the agent asked for them (rect cells); points otherwise.
        "extent": extent(sub, edges=any(sfx in ("lo", "hi") for _, sfx in derived.values())),
    }
    return rows, meta


def bind_contours(name: str, binding: dict, inputs: dict) -> tuple[list[dict], dict]:
    """``{"zarr", "contours": {"variable", "levels", "filled"}}`` -> GeoJSON isolines or bands."""
    import contourpy

    loc = f"datasets.{name}"
    _check_keys(binding, CONTOUR_KEYS, loc)
    opts = binding["contours"]
    if not isinstance(opts, dict):
        raise SpecError(f"{loc}.contours must be an object with {sorted(CONTOUR_OPTS)}")
    _check_keys(opts, CONTOUR_OPTS, f"{loc}.contours")
    ds = _input(inputs, binding, "zarr", loc)
    var = opts.get("variable")
    if var not in ds.data_vars:
        raise SpecError(f"{loc}.contours.variable {var!r}: choose one of {list(ds.data_vars)}")
    levels = opts.get("levels")
    if not isinstance(levels, list) or len(levels) < (2 if opts.get("filled") else 1):
        raise SpecError(f"{loc}.contours.levels must be a list of numbers (two or more for filled)")
    da = _apply_sel(_apply_bbox(ds[var], binding.get("bbox"), loc), binding, loc).squeeze(drop=True)
    lat, lon = _latlon_names(da)
    if lat is None or set(da.dims) != {lat, lon}:
        raise SpecError(
            f"{loc}.contours needs a 2-D latitude/longitude field after sel/isel; dims are "
            f"{dict(da.sizes)}"
        )
    da = da.transpose(lat, lon)
    gen = contourpy.contour_generator(da[lon].values, da[lat].values, da.values.astype(float))
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
    meta = {
        "kind": "contours",
        "rows": len(features),
        "columns": ["type", "properties", "geometry"],
        "ds": da.to_dataset(name=var),
        # Band and line values are in the variable's units, so they get its defaults.
        "var_cols": {f"properties.{k}": var for k in ("lo", "hi", "mid", "level")},
        # Contours stop at the outermost cell centres, not the cell edges.
        "extent": extent(da, edges=False),
    }
    return ne.orient_for_d3(features), meta


def bind_geojson(name: str, binding: dict, inputs: dict) -> list[dict]:
    loc = f"datasets.{name}"
    _check_keys(binding, GEOJSON_KEYS, loc)
    data = _input(inputs, binding, "geojson", loc)
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
    elif data.get("type") == "Feature":
        features = [data]
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    if binding.get("bbox") is not None:
        features = ne.clip_features(features, ne.check_bbox(binding["bbox"], loc))
    return ne.orient_for_d3(features)


def bind_all(spec: dict, inputs: dict, notes: list | None = None, *, defaults: bool = True):
    """Replace every binding under ``datasets`` with rows. Returns ``(spec, meta)``.

    Zarr bindings go first so vector layers without a ``bbox`` can be clipped to
    the extent of the plotted data (a default, logged to ``notes``).
    """
    spec = copy.deepcopy(spec)
    notes = [] if notes is None else notes
    datasets = spec.get("datasets")
    if datasets is None:
        return spec, {}
    if not isinstance(datasets, dict):
        raise SpecError("datasets must be an object of name -> rows or binding")
    inputs = {k: plain(v) if hasattr(v, "data_vars") else v for k, v in inputs.items()}
    meta: dict[str, dict] = {}
    vectors = []
    for name, binding in list(datasets.items()):
        loc = f"datasets.{name}"
        if isinstance(binding, list):
            meta[name] = {
                "kind": "rows",
                "rows": len(binding),
                "columns": sorted({k for r in binding[:50] if isinstance(r, dict) for k in r}),
            }
            continue
        if not isinstance(binding, dict):
            raise SpecError(f"{loc} must be rows (a list) or a binding object")
        kinds = [k for k in BINDING_KINDS if k in binding]
        if len(kinds) != 1:
            raise SpecError(
                f"{loc} needs exactly one of {list(BINDING_KINDS)} (found {kinds or 'none'}); "
                "a plain list of rows is also accepted"
            )
        if kinds[0] != "zarr":
            vectors.append((name, kinds[0], binding))
            continue
        if "contours" in binding:
            rows, meta[name] = bind_contours(name, binding, inputs)
        else:
            rows, meta[name] = bind_zarr(name, binding, inputs)
        datasets[name] = rows
    data_extent = union(m.get("extent") for m in meta.values())
    for name, kind, binding in vectors:
        if defaults and "bbox" not in binding and data_extent:
            binding = {**binding, "bbox": [round(v, 4) for v in data_extent]}
            notes.append(f"datasets.{name}.bbox <- extent of the bound data {binding['bbox']}")
        if kind == "geojson":
            rows = bind_geojson(name, binding, inputs)
        else:
            _check_keys(binding, NATURALEARTH_KEYS, f"datasets.{name}")
            rows = ne.bind_naturalearth(name, binding)
        meta[name] = {
            "kind": kind,
            "rows": len(rows),
            "columns": ["type", "properties", "geometry"],
        }
        datasets[name] = rows
    return spec, meta
