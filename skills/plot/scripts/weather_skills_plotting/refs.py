"""``@`` references: strings in the evaluated spec that stand for data in an input.

A string that starts with ``@`` is a reference; ``@@`` starts a literal ``@``.
The text after ``@`` is a Python expression, parsed with :mod:`ast` and walked
against a fixed table. Nothing is ``eval``'d.

Every operation in the table has one job: select values, reshape them, label
them, or give a display limit. Nothing computes new values, so every value
drawn is a value stored in an input; calculations belong in data skills.
"""

from __future__ import annotations

import ast

import numpy as np
from weather_skills_core.cf import cf_dim
from weather_skills_core.errors import UsageError

# Each method's job. A test checks every method has one of the four.
METHODS = {
    "isel": "select",
    "sel": "select",
    "dropna": "select",
    "clip": "select",
    "squeeze": "reshape",
    "transpose": "reshape",
    "flat": "reshape",
    "strftime": "label",
    "min": "limit",
    "max": "limit",
    "quantile": "limit",
}
JOBS = ("select", "reshape", "label", "limit")

# Time parts readable with .dt.NAME.
DT_FIELDS = ("year", "month", "day", "hour", "dayofyear", "days")

# Where a display limit may go: a reference ending in min / max / quantile is
# accepted only when its JSON path ends in one of these keys (or sits in a range).
LIMIT_KEYS = frozenset({"zmin", "zmax", "zmid", "cmin", "cmax", "cmid", "range", "tickvals"})

# A trace key holding a literal numeric list longer than this must be an input instead.
MAX_LITERAL_VALUES = 10
LITERAL_EXEMPT_KEYS = frozenset({"colorscale", "tickvals", "ticktext", "range", "domain"})

# Calculations the plotter refuses, and the data skill that does each.
UPSTREAM = {
    "mean": "summarize-dim",
    "sum": "summarize-dim",
    "median": "summarize-dim",
    "std": "summarize-dim",
    "var": "summarize-dim",
    "cumsum": "summarize-dim",
    "rolling": "aggregate-temporal",
    "resample": "aggregate-temporal",
    "coarsen": "aggregate-temporal or the coarsen skill",
    "groupby": "aggregate-temporal or label-group",
    "interp": "coarsen or downscale",
    "interp_like": "coarsen or downscale",
    "reindex": "coarsen or downscale",
    "where": "clip-region",
    "fillna": "nothing: missing data stays missing",
    "diff": "difference",
    "differentiate": "difference",
    "astype": "unit-convert",
}

_ALIASES = {"lat": "latitude", "lon": "longitude", "time": "time"}


def is_ref(value) -> bool:
    return isinstance(value, str) and value.startswith("@") and not value.startswith("@@")


class GeoLines:
    """Lines and polygon rings as NaN-separated ``x`` / ``y`` arrays."""

    def __init__(self, geoms, label):
        self.geoms, self.label = geoms, label

    def xy(self):
        from weather_skills_plotting.geodata import geoms_to_xy

        return geoms_to_xy(self.geoms)


class NaturalEarth:
    """The built-in ``NE`` input: ``NE.<layer>_<scale>.clip(n, w, s, e)``."""


class NELayer:
    def __init__(self, layer, scale):
        self.layer, self.scale = layer, scale


class _Accessor:
    """``.dt`` or ``.attrs`` of a DataArray, waiting for its field."""

    def __init__(self, kind, da):
        self.kind, self.da = kind, da


def _dim(da, name, ref):
    """The dim of ``da`` that ``name`` means: itself, or the CF lat / lon / time it aliases."""
    if name in da.dims:
        return name
    if name in _ALIASES:
        dim = cf_dim(da, _ALIASES[name])
        if dim in da.dims:
            return dim
    raise UsageError(f"{ref}: no dim {name!r}; its dims are {list(da.dims)}")


def _literal(node, ref):
    """A constant argument: number, string, None, list / tuple of those, -number, slice(...)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal(node.operand, ref)
        if isinstance(value, (int, float)):
            return -value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(n, ref) for n in node.elts]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "slice"
        and not node.keywords
    ):
        return slice(*[_literal(n, ref) for n in node.args])
    raise UsageError(
        f"{ref}: arguments must be numbers, strings, lists of them or slice(...); "
        f"got {ast.unparse(node)!r}"
    )


def _refuse(node, ref):
    """The error for syntax outside the table, naming the skill that does the job."""
    if isinstance(node, ast.BinOp):
        raise UsageError(
            f"{ref}: arithmetic ({ast.unparse(node)!r}) is not plotted; convert units with "
            "unit-convert, subtract with difference, then plot the result"
        )
    raise UsageError(
        f"{ref}: {type(node).__name__} is not allowed in a reference; references select, "
        "reshape and label stored values (see the reference table in SKILL.md)"
    )


def _method(base, name, args, kwargs, ref):
    """Apply one method from the table to ``base``."""
    if name not in METHODS:
        hint = UPSTREAM.get(name)
        if hint:
            raise UsageError(
                f"{ref}: .{name}() computes new values, which plot does not do; use {hint} "
                "first and plot its output"
            )
        raise UsageError(f"{ref}: unknown method .{name}(); allowed: {', '.join(METHODS)}")
    if isinstance(base, NELayer):
        if name != "clip" or len(args) != 4 or kwargs:
            raise UsageError(f"{ref}: a Natural Earth layer takes .clip(n, w, s, e)")
        from weather_skills_plotting.geodata import load_ne_layer

        n, w, s, e = (float(v) for v in args)
        return GeoLines(load_ne_layer(base.layer, base.scale, n, w, s, e), ref)
    if isinstance(base, _Accessor):
        if base.kind == "dt" and name == "strftime" and len(args) == 1 and not kwargs:
            return base.da.dt.strftime(args[0])
        raise UsageError(f"{ref}: .{base.kind}.{name}() is not allowed")
    if not hasattr(base, "dims"):
        raise UsageError(f"{ref}: .{name}() needs a variable or coordinate before it")
    da = base
    if name in ("isel", "sel"):
        if args:
            raise UsageError(f"{ref}: .{name}() takes dim=value pairs, e.g. .{name}(time=0)")
        method = kwargs.pop("method", None)
        if name == "isel" and method is not None:
            raise UsageError(f"{ref}: .isel() takes no method")
        if method not in (None, "nearest"):
            raise UsageError(f"{ref}: .sel() method must be 'nearest'")
        picks = {_dim(da, k, ref): v for k, v in kwargs.items()}
        try:
            return getattr(da, name)(picks, method=method) if method else getattr(da, name)(picks)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise UsageError(f"{ref}: {exc}") from None
    if name == "dropna":
        if len(args) != 1 or kwargs:
            raise UsageError(f"{ref}: .dropna(dim) takes one dim, e.g. .dropna('station_id')")
        return da.dropna(_dim(da, args[0], ref))
    if name == "squeeze":
        return da.squeeze()
    if name == "transpose":
        order = [_dim(da, d, ref) for d in args]
        extra = [d for d in da.dims if d not in order]
        if extra:
            raise UsageError(
                f"{ref}: dims {extra} are left besides {order}; pick a value along them with "
                ".isel(dim=…) / .sel(dim=…) before .transpose()"
            )
        return da.transpose(*order)
    if name == "flat":
        lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
        if set(da.dims) != {lat, lon}:
            raise UsageError(
                f"{ref}: .flat() needs a lat/lon grid and nothing else; dims are {list(da.dims)}"
            )
        grid = da.transpose(lat, lon)
        if not args:
            return np.asarray(grid.values).ravel()
        which = _dim(da, args[0], ref)
        lats, lons = np.asarray(da[lat].values), np.asarray(da[lon].values)
        return np.repeat(lats, lons.size) if which == lat else np.tile(lons, lats.size)
    if name in ("min", "max", "quantile"):
        if kwargs or (name != "quantile" and args) or (name == "quantile" and len(args) != 1):
            raise UsageError(
                f"{ref}: .{name}() works on the whole array only (a display limit); "
                "averages over a dim come from summarize-dim"
            )
        values = np.asarray(da.values, dtype=float)
        if not np.isfinite(values).any():
            raise UsageError(f"{ref}: every value is NaN")
        if name == "quantile":
            return float(np.nanquantile(values, float(args[0])))
        return float(np.nanmin(values) if name == "min" else np.nanmax(values))
    raise UsageError(f"{ref}: .{name}() is not allowed here")


def evaluate(text: str, inputs: dict):
    """The value a reference stands for (before conversion to JSON)."""
    ref = text
    try:
        tree = ast.parse(text[1:], mode="eval")
    except SyntaxError as exc:
        raise UsageError(f"{ref}: not a valid reference ({exc.msg})") from None

    def walk(node):
        if isinstance(node, ast.Name):
            if node.id == "NE":
                return NaturalEarth()
            if node.id not in inputs:
                raise UsageError(
                    f"{ref}: {node.id!r} is not an input; inputs are "
                    f"{', '.join(inputs) or 'none'} (name each with -i PATH=NAME)"
                )
            return inputs[node.id]
        if isinstance(node, ast.Attribute):
            base = walk(node.value)
            return _attribute(base, node.attr, ref)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                _refuse(node, ref)
            if node.func.attr not in METHODS:
                _method(None, node.func.attr, [], {}, ref)
            base = walk(node.func.value)
            args = [_literal(a, ref) for a in node.args]
            kwargs = {}
            for kw in node.keywords:
                if kw.arg is None:
                    _refuse(kw.value, ref)
                kwargs[kw.arg] = _literal(kw.value, ref)
            return _method(base, node.func.attr, args, kwargs, ref)
        _refuse(node, ref)

    return walk(tree.body), _last_method(tree.body)


def _last_method(node):
    """The method a reference ends in, e.g. ``max`` for ``@A.b.max()``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _attribute(base, attr, ref):
    if attr.startswith("_"):
        raise UsageError(f"{ref}: {attr!r} is not allowed")
    if isinstance(base, NaturalEarth):
        from weather_skills_plotting.geodata import NE_LAYERS

        layer, _, scale = attr.rpartition("_")
        if layer not in NE_LAYERS or scale not in ("10m", "50m", "110m"):
            raise UsageError(
                f"{ref}: NE has {', '.join(NE_LAYERS)}, each as NAME_10m, NAME_50m or "
                "NAME_110m (admin1 only 10m), e.g. @NE.coastline_50m.clip(n, w, s, e).x"
            )
        if layer == "admin1" and scale != "10m":
            raise UsageError(
                f"{ref}: NE.admin1 exists only at 10m: @NE.admin1_10m.clip(n, w, s, e)"
            )
        return NELayer(layer, scale)
    if isinstance(base, NELayer):
        raise UsageError(f"{ref}: clip a Natural Earth layer first: .clip(n, w, s, e).{attr}")
    if isinstance(base, GeoLines):
        if attr not in ("x", "y", "lon", "lat"):
            raise UsageError(f"{ref}: a GeoJSON input has .x (or .lon) and .y (or .lat)")
        return base.xy()[0 if attr in ("x", "lon") else 1]
    if isinstance(base, _Accessor):
        if base.kind == "attrs":
            if attr not in base.da.attrs:
                raise UsageError(f"{ref}: no attribute {attr!r}; has {list(base.da.attrs)}")
            return str(base.da.attrs[attr])
        if attr not in DT_FIELDS:
            raise UsageError(f"{ref}: .dt has {', '.join(DT_FIELDS)} and .strftime(format)")
        return getattr(base.da.dt, attr)
    if hasattr(base, "data_vars"):
        name = attr
        if attr in _ALIASES and attr not in base.variables:
            name = cf_dim(base, _ALIASES[attr])
        if name is None or name not in base.variables:
            raise UsageError(
                f"{ref}: no variable or coordinate {attr!r}; data variables: "
                f"{', '.join(map(str, base.data_vars))}; coordinates: "
                f"{', '.join(map(str, base.coords))}"
            )
        return base[name]
    if hasattr(base, "dims"):
        if attr in ("dt", "attrs"):
            if attr == "dt" and base.dtype.kind not in "mM" and base.dtype != object:
                raise UsageError(f"{ref}: .dt needs a time or timedelta coordinate")
            return _Accessor(attr, base)
        # A coordinate of what is left after a selection: the lon / lat of the
        # points .dropna() kept, the valid times of the steps picked.
        name = attr
        if attr in _ALIASES and attr not in base.coords:
            name = cf_dim(base, _ALIASES[attr])
        if name in base.coords:
            return base[name]
        raise UsageError(
            f"{ref}: {attr!r} is neither .dt, .attrs nor a coordinate of this selection "
            f"(coordinates: {', '.join(map(str, base.coords))})"
        )
    raise UsageError(f"{ref}: {attr!r} is not allowed here")


def to_json_value(value, path: str, ref: str):
    """A resolved reference as a Plotly value, checking its shape for the key at ``path``."""
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, (GeoLines, NELayer, NaturalEarth, _Accessor)) or hasattr(
        value, "data_vars"
    ):
        raise UsageError(f"{path} = {ref}: name a variable or coordinate to draw")
    key = path.rsplit(".", 1)[-1].split("[")[0]
    if hasattr(value, "dims"):
        da = value
        allowed = 2 if key in ("z", "customdata") else 1
        # A dim of length 1 (the one time of a period total) holds no choice: drop such
        # dims while there are more than the attribute takes.
        for dim in [d for d in da.dims if da.sizes[d] == 1]:
            if da.ndim > allowed:
                da = da.squeeze(dim)
        if key == "z":
            lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
            if da.ndim == 2 and set(da.dims) == {lat, lon}:
                da = da.transpose(lat, lon)
        if key == "z" and da.ndim != 2:
            raise UsageError(_shape_error(path, ref, da, 2))
        if da.ndim > allowed:
            raise UsageError(_shape_error(path, ref, da, allowed))
        values = np.asarray(da.values)
    else:
        values = np.asarray(value)
    if values.dtype.kind == "m":
        raise UsageError(
            f"{path} = {ref}: these are lead times; run step-to-time to plot by valid date, "
            "or use .dt.days for lead days"
        )
    if values.dtype.kind == "M":
        values = np.datetime_as_string(values, unit="s")
        return _strip_midnight(values)
    if values.dtype == object:
        values = np.vectorize(_iso, otypes=[object])(values)
    if values.ndim == 0:
        item = values.item()
        return float(item) if isinstance(item, (np.floating, float)) else item
    if values.dtype.kind in "biuf":
        return values.astype(float)
    return values.tolist()


def _iso(item):
    return item.isoformat() if hasattr(item, "isoformat") else str(item)


def _strip_midnight(values):
    """ISO times; a time that is midnight drops its clock part (2026-10-01)."""
    out = [v[:10] if v.endswith("T00:00:00") else v for v in np.ravel(values).tolist()]
    return (
        out[0]
        if np.ndim(values) == 0
        else np.reshape(np.array(out, dtype=object), values.shape).tolist()
    )


def _shape_error(path, ref, da, allowed):
    want = "2-D (a grid)" if allowed == 2 else "1-D or a single value"
    extra = [d for d in da.dims]
    return (
        f"{path} = {ref} has dims {extra}; {path.rsplit('.', 1)[-1]} needs {want}. "
        "Pick a position along the other dims with .isel(dim=…) / .sel(dim=…), "
        "draw one trace per value (a Jsonnet loop), or reduce it upstream with summarize-dim"
    )


def resolve(spec, inputs: dict):
    """Replace every reference in ``spec`` with its values; check guardrails first.

    Returns a new spec and ``{path: reference}`` for every reference resolved.
    """
    check_literals(spec)
    for path, node in _traces_and_layout(spec):
        if "meta" in node:
            raise UsageError(
                f"{path}.meta: plot has no meta keys. A palette is "
                "layout: ws.classBar(palette, title) (or a Plotly colorscale); an outline is a "
                "scatter with x: '@NAME.x', y: '@NAME.y'; data is an @ reference in the "
                "Plotly attribute itself (see --recipe)"
            )
    found = {}
    grids = []

    def walk(node, path):
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str) and node.startswith("@@"):
            return node[1:]
        if not is_ref(node):
            return node
        value, last = evaluate(node, inputs)
        if METHODS.get(last) == "limit" and not _limit_path(path):
            raise UsageError(
                f"{path} = {node}: .{last}() gives one number, for a scale only "
                f"({', '.join(sorted(LIMIT_KEYS))}); data to draw is stored values"
            )
        found[path] = node
        # A frame's trace may set only z; it takes x / y from the trace it updates.
        if path.startswith("data[") and path.endswith(".z") and hasattr(value, "dims"):
            if {cf_dim(value, "latitude"), cf_dim(value, "longitude")} <= set(value.dims):
                grids.append((path[:-2], node))
        return to_json_value(value, path, node)

    resolved = walk(spec, "")
    for trace_path, ref in grids:
        trace = resolved
        for part in trace_path.replace("[", ".[").split("."):
            trace = trace[int(part[1:-1])] if part.startswith("[") else trace[part]
        if "x" not in trace or "y" not in trace:
            name = ref[1:].split(".")[0]
            raise UsageError(
                f"{trace_path}: z = {ref} is a lat/lon grid; set x: '@{name}.lon' and "
                f"y: '@{name}.lat' too, so it sits on degree axes with outlines and the base map"
            )
    return resolved, found


def _traces_and_layout(spec):
    """``(path, object)`` for every trace (frames included) and the layout."""
    out = [(f"data[{i}]", t) for i, t in enumerate(spec.get("data") or []) if isinstance(t, dict)]
    for f, frame in enumerate(spec.get("frames") or []):
        out += [(f"frames[{f}].data[{i}]", t) for i, t in enumerate(frame.get("data") or [])]
    if isinstance(spec.get("layout"), dict):
        out.append(("layout", spec["layout"]))
    return out


def _limit_path(path: str) -> bool:
    parts = path.replace("[", ".[").split(".")
    keys = [p for p in parts if p and not p.startswith("[")]
    return bool(keys) and (
        keys[-1] in LIMIT_KEYS or "range" in keys[-2:] or "tickvals" in keys[-2:]
    )


def check_literals(spec):
    """Refuse literal numeric arrays longer than MAX_LITERAL_VALUES in traces."""
    traces = [(path, node) for path, node in _traces_and_layout(spec) if path != "layout"]

    def count(value):
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            return 1
        if isinstance(value, list):
            return sum(count(v) for v in value)
        return 0

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in LITERAL_EXEMPT_KEYS:
                    continue
                if isinstance(v, list) and count(v) > MAX_LITERAL_VALUES:
                    raise UsageError(
                        f"{path}.{k} holds {count(v)} typed-in numbers; data to draw comes from "
                        f"an input (-i FILE=NAME, then '@NAME.var'). Up to "
                        f"{MAX_LITERAL_VALUES} literal values are fine (markers, lines)"
                    )
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    for path, trace in traces:
        walk(trace, path)
