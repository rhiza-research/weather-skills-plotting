"""Bind: fill each ``@`` reference in the rendered spec with data from an input.

A string that starts with ``@`` is a reference; ``@@`` starts a literal ``@``.
The text after ``@`` is a Python expression, parsed with :mod:`ast` and walked
against a fixed table. Nothing is ``eval``'d.

Every operation in the table has one job: select values, reshape them, label
them, or give a display limit. Nothing computes new values, so every value
drawn is a value stored in an input; calculations belong in data skills. The one
exception is a size in pixels: ``+ - * /`` by a number or constant, only on
``SCALED_KEYS`` (marker.size, marker.standoff, marker.line.width, textfont.size).
"""

from __future__ import annotations

import ast
import json
import sys
from importlib.resources import files

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
    "lon360": "reshape",
    "lon180": "reshape",
    "transpose": "reshape",
    "flat": "reshape",
    "strftime": "label",
    "min": "limit",
    "max": "limit",
    "quantile": "limit",
}
JOBS = ("select", "reshape", "label", "limit")

# Sizes in pixels, the only keys whose reference may take arithmetic by a number:
# '@W.wind_speed.flat() * 3' draws a marker 3 px per unit, the way Plotly's own sizeref
# scales marker.size. The data drawn is unchanged; only its size on screen is.
SCALED_KEYS = ("marker.size", "marker.standoff", "marker.line.width", "textfont.size")
ARITHMETIC = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide}

# Time parts readable with .dt.NAME.
DT_FIELDS = ("year", "month", "day", "hour", "dayofyear", "days")

# Where a display limit may go: a reference ending in min / max / quantile is
# accepted only when its JSON path ends in one of these keys (or sits in a range).
LIMIT_KEYS = frozenset({"zmin", "zmax", "zmid", "cmin", "cmax", "cmid", "range", "tickvals"})


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
        return geoms_to_xy(self.geoms)


class NaturalEarth:
    """The built-in ``NE`` input: ``NE.<layer>_<scale>.clip(n, w, s, e)``."""


class NELayer:
    def __init__(self, layer, scale):
        self.layer, self.scale = layer, scale


class _Constants:
    """``@const.NAME``: a number or text passed with --const NAME=VALUE."""

    def __init__(self, values):
        self.values = values


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
            f"{ref}: arithmetic ({ast.unparse(node)!r}) is only a size in pixels: + - * / by a "
            f"number or @const, on {', '.join(SCALED_KEYS)}. For data, convert units with "
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
            # Say what each picked dim holds, so the right value or position is plain.
            held = []
            for dim in picks:
                values = da[dim].values
                first, last = (
                    _iso(values[0].item() if hasattr(values[0], "item") else values[0]),
                    None,
                )
                last = _iso(values[-1].item() if hasattr(values[-1], "item") else values[-1])
                held.append(f"{dim} has {values.size} values, {first} to {last}")
            raise UsageError(
                f"{ref}: nothing at that {'position' if name == 'isel' else 'value'} "
                f"({exc}); {'; '.join(held)}"
            ) from None
    if name == "dropna":
        if len(args) != 1 or kwargs:
            raise UsageError(f"{ref}: .dropna(dim) takes one dim, e.g. .dropna('station_id')")
        return da.dropna(_dim(da, args[0], ref))
    if name in ("lon360", "lon180"):
        # Longitudes as 0..360 or -180..180, in order, so a field that crosses the dateline
        # (lon360) or the prime meridian (lon180) draws as one piece.
        lon = _dim(da, "lon", ref) if "lon" not in da.coords else "lon"
        wrap = (lambda v: v % 360) if name == "lon360" else (lambda v: (v + 180) % 360 - 180)
        if da.name == lon:
            da = da.copy(data=wrap(np.asarray(da.values)))
        da = da.assign_coords({lon: wrap(da[lon])})
        return da.sortby(lon) if lon in da.dims else da
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
        # A 2-D selection as one value per cell (a lat/lon grid row by row), and with a dim
        # named, that dim's coordinate for each value: grid cells as points, or members
        # with their lead for one box per lead.
        if da.ndim != 2:
            raise UsageError(f"{ref}: .flat() needs two dims; dims are {list(da.dims)}")
        lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
        grid = da.transpose(lat, lon) if set(da.dims) == {lat, lon} else da
        if not args:
            return np.asarray(grid.values).ravel()
        which = _dim(da, args[0], ref)
        values = np.asarray(grid[which].broadcast_like(grid).transpose(*grid.dims).values).ravel()
        if values.dtype.kind == "m":
            # A lead time, in days.
            values = values / np.timedelta64(1, "D")
        return values
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
        raise UsageError(
            f"{ref}: not a valid reference ({exc.msg}). A string that starts with @ is a "
            'reference; start literal text with @@ ("@@home" draws @home)'
        ) from None

    def walk(node):
        if isinstance(node, ast.Name):
            if node.id == "NE":
                return NaturalEarth()
            if node.id == "const":
                return _Constants(inputs.get("const", {}))
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
            refused = [
                n.func.attr
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr not in METHODS
            ]
            if refused:
                # The innermost one is the step to do upstream (.rolling(...) in .rolling().mean()).
                _method(None, refused[-1], [], {}, ref)
            base = walk(node.func.value)
            args = [_literal(a, ref) for a in node.args]
            kwargs = {}
            for kw in node.keywords:
                if kw.arg is None:
                    _refuse(kw.value, ref)
                kwargs[kw.arg] = _literal(kw.value, ref)
            return _method(base, node.func.attr, args, kwargs, ref)
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            # A pixel size: data on exactly one side, a number (or a const) on the other, so
            # a size never combines two fields.
            if _has_data(node.left) == _has_data(node.right):
                _refuse(node, ref)
            sides = [
                walk(n) if _has_data(n) else _number(n, inputs, ref)
                for n in (node.left, node.right)
            ]
            data = [
                np.asarray(side.values if hasattr(side, "dims") else side, float) for side in sides
            ]
            if isinstance(node.op, ast.Div) and not np.all(data[1]):
                raise UsageError(f"{ref}: division by zero")
            return ARITHMETIC[type(node.op)](*data)
        _refuse(node, ref)

    last = "arithmetic" if isinstance(tree.body, ast.BinOp) else _last_method(tree.body)
    if last != "arithmetic" and any(isinstance(n, ast.BinOp) for n in ast.walk(tree.body)):
        _refuse(next(n for n in ast.walk(tree.body) if isinstance(n, ast.BinOp)), ref)
    return walk(tree.body), last


def _has_data(node):
    """Whether an operand names an input (anything but a number or @const)."""
    names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
    return any(name != "const" for name in names)


def _number(node, inputs, ref):
    """A number operand: a literal, or @const.NAME."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "const"
    ):
        value = _attribute(_Constants(inputs.get("const", {})), node.attr, ref)
    else:
        value = _literal(node, ref)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise UsageError(f"{ref}: {ast.unparse(node)!r} is not a number")
    return float(value)


def _last_method(node):
    """The method a reference ends in, e.g. ``max`` for ``@A.b.max()``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _attribute(base, attr, ref):
    if attr.startswith("_"):
        raise UsageError(f"{ref}: {attr!r} is not allowed")
    if isinstance(base, _Constants):
        if attr not in base.values:
            raise UsageError(
                f"{ref}: no constant {attr!r}; pass it with --const {attr}=VALUE "
                f"(given: {', '.join(base.values) or 'none'})"
            )
        return base.values[attr]
    if isinstance(base, NaturalEarth):
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
        if key == "z" and da.ndim < 2:
            raise UsageError(
                f"{path} = {ref} has dims {list(da.dims)}; z needs a 2-D grid, so keep two dims "
                "(lat and lon, or e.g. vertical and lon) and pick only the others"
            )
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
    found = {}
    grids = []
    # The dim and coordinate values each 1-D reference runs along, to check x / y pair up.
    along = {}
    # The units of what fills each color (z, marker.color), to check shared colorbars.
    color_units = {}

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
        if last == "arithmetic" and not path.endswith(SCALED_KEYS):
            raise UsageError(
                f"{path} = {node}: arithmetic only sets a size in pixels ({', '.join(SCALED_KEYS)}); "
                "data to draw is stored values (unit-convert, difference first)"
            )
        if METHODS.get(last) == "limit" and not _limit_path(path):
            raise UsageError(
                f"{path} = {node}: .{last}() gives one number, for a scale only "
                f"({', '.join(sorted(LIMIT_KEYS))}); data to draw is stored values"
            )
        found[path] = node
        if hasattr(value, "attrs") and path.endswith((".z", ".marker.color")):
            color_units[path] = str(value.attrs.get("units", ""))
        # A whole input (a Dataset) has no dims of its own; to_json_value names the fix.
        if hasattr(value, "dims") and not hasattr(value, "data_vars") and value.squeeze().ndim == 1:
            dim = value.squeeze().dims[0]
            if dim in value.coords:
                along[path] = (dim, np.asarray(value.squeeze()[dim].values))
        # A frame's trace may set only z; it takes x / y from the trace it updates.
        if path.startswith("data[") and path.endswith(".z") and hasattr(value, "dims"):
            if {cf_dim(value, "latitude"), cf_dim(value, "longitude")} <= set(value.dims):
                grids.append((path[:-2], node))
        return to_json_value(value, path, node)

    resolved = walk(spec, "")
    # x and y pair up point by point; different lengths mean a dim was left in one of them.
    for path, trace in _traces_and_layout(resolved):
        # Gridded traces (z) take x and y as the grid's two axes, of their own lengths.
        if path == "layout" or "z" in trace:
            continue
        x, y = trace.get("x"), trace.get("y")
        if (
            hasattr(x, "__len__")
            and hasattr(y, "__len__")
            and not isinstance(x, str)
            and not isinstance(y, str)
        ):
            if np.ndim(x) == 1 and np.ndim(y) == 1 and len(x) != len(y):
                raise UsageError(
                    f"{path}: x has {len(x)} values and y has {len(y)}, so they don't pair up; "
                    f"pick the same positions for both (x = {found.get(path + '.x', 'literal')}, "
                    f"y = {found.get(path + '.y', 'literal')}). A dim left in one of them, such as "
                    "number, needs .isel(...) or one trace per value"
                )
            ax, ay = along.get(path + ".x"), along.get(path + ".y")
            if ax and ay and ax[0] == ay[0] and not np.array_equal(ax[1], ay[1]):
                raise UsageError(
                    f"{path}: x and y run along different {ax[0]} values "
                    f"({found[path + '.x']} vs {found[path + '.y']}), so their points would pair "
                    f"up wrongly; put both variables in one file first (merge), or pick the same "
                    f"{ax[0]} values for both"
                )
    for trace_path, ref in grids:
        trace = _at(resolved, trace_path)
        if "x" not in trace or "y" not in trace:
            name = ref[1:].split(".")[0]
            raise UsageError(
                f"{trace_path}: z = {ref} is a lat/lon grid; set x: '@{name}.lon' and "
                f"y: '@{name}.lat' too, so it sits on degree axes with outlines and the base map"
            )
    # Traces on one coloraxis share one colorbar; different units there mislabel one of them.
    by_axis = {}
    for path, units in color_units.items():
        trace_path = (
            path.rsplit(".z", 1)[0] if path.endswith(".z") else path.rsplit(".marker", 1)[0]
        )
        trace = _at(resolved, trace_path)
        axis = trace.get("coloraxis") or (trace.get("marker") or {}).get("coloraxis")
        if axis and units:
            by_axis.setdefault(axis, {}).setdefault(units, []).append(trace_path)
    for axis, units in by_axis.items():
        if len(units) > 1:
            listed = "; ".join(f"{u} in {', '.join(paths)}" for u, paths in units.items())
            print(
                f"Warning: {axis} colors traces in different units ({listed}); one colorbar "
                "can only label one. Convert them to one unit, or give each its own coloraxis",
                file=sys.stderr,
            )
    return resolved, found


def _at(tree, path):
    for part in path.replace("[", ".[").split("."):
        if part:
            tree = tree[int(part[1:-1])] if part.startswith("[") else tree[part]
    return tree


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


# ---- Lines for maps: Natural Earth layers (the built-in ``NE`` input) and GeoJSON inputs

# NE layer name → (Natural Earth category, shapefile name, agreed-boundary filter).
# ``borders`` is agreed international boundaries; ``disputed`` is every other land
# line (disputed, indefinite, line of control). ``admin1`` exists only at 10m.
NE_LAYERS = {
    "admin1": ("cultural", "admin_1_states_provinces", None),
    "rivers": ("physical", "rivers_lake_centerlines", None),
    "lakes": ("physical", "lakes", None),
    "borders": ("cultural", "admin_0_boundary_lines_land", True),
    "disputed": ("cultural", "admin_0_boundary_lines_land", False),
    "coastline": ("physical", "coastline", None),
}


def window_parts(w, e):
    """``[(west, east, shift)]``: a lon window in Natural Earth's [-180, 180] longitudes.

    A window past 180° (170 to 200, or w > e as 170 to -160) is split at the
    dateline; its far part is clipped at -180..-160 and moved by ``shift`` (360°)
    to sit beside the near part on the map's continuous axis.
    """
    if w > e:
        e += 360.0
    parts = []
    for shift in (0.0, 360.0, -360.0):
        west, east = max(w - shift, -180.0), min(e - shift, 180.0)
        if west < east:
            parts.append((west, east, shift))
    return parts


def load_ne_layer(layer: str, scale: str, n, w, s, e):
    """A Natural Earth layer's shapes clipped to the bbox (downloaded once by cartopy).

    If borders or coastline can't be fetched, the country outlines bundled with
    core stand in for both, with a warning; other layers are left out.
    """
    import shapely
    from shapely.geometry import box

    category, name, agreed = NE_LAYERS[layer]
    geoms = []
    for west, east, shift in window_parts(w, e):
        clip = box(west, s, east, n)
        try:
            import cartopy.io.shapereader as shpreader

            path = shpreader.natural_earth(resolution=scale, category=category, name=name)
            records = list(shpreader.Reader(path, bbox=clip.bounds).records())
        except Exception as exc:  # noqa: BLE001 — offline, or cartopy missing
            if layer not in ("borders", "coastline"):
                print(f"Warning: NE.{layer} unavailable ({exc}); not drawn.", file=sys.stderr)
                return []
            print(
                f"Warning: NE.{layer} unavailable ({exc}); drawing the bundled country outlines.",
                file=sys.stderr,
            )
            parts = _bundled_country_lines(clip)
        else:
            parts = []
            for rec in records:
                if agreed is not None:
                    is_agreed = str(rec.attributes.get("FEATURECLA", "")).startswith(
                        "International boundary"
                    )
                    if is_agreed != agreed:
                        continue
                geom = rec.geometry
                if geom is None or geom.is_empty or not geom.intersects(clip):
                    continue
                clipped = geom.intersection(clip)
                if not clipped.is_empty:
                    parts.extend(getattr(clipped, "geoms", [clipped]))
        geoms += [shapely.transform(g, lambda xy, d=shift: xy + [d, 0.0]) for g in parts]
    return geoms


def _bundled_country_lines(clip):
    """Country outlines from the Natural Earth extract bundled with core."""
    import shapely
    from shapely.geometry import shape

    raw = json.loads(files("weather_skills_core.data").joinpath("countries.geojson").read_text())
    geoms = []
    for feat in raw.get("features") or []:
        if not feat.get("geometry"):
            continue
        poly = shape(feat["geometry"])
        if not poly.intersects(clip):
            continue
        for part in getattr(poly.intersection(clip), "geoms", [poly.intersection(clip)]):
            if part.geom_type in ("Polygon", "MultiPolygon") and not part.is_empty:
                geoms.append(shapely.boundary(part))
    return geoms


def load_geojson(path):
    """Every geometry in a GeoJSON file (FeatureCollection, Feature or bare geometry)."""
    from shapely.geometry import shape

    try:
        raw = json.loads(open(path).read())
    except (OSError, ValueError) as exc:
        raise UsageError(f"GeoJSON input {path}: {exc}") from None
    if raw.get("type") == "FeatureCollection":
        items = [f.get("geometry") for f in raw.get("features") or []]
    elif raw.get("type") == "Feature":
        items = [raw.get("geometry")]
    else:
        items = [raw]
    return [shape(g) for g in items if g]


def geoms_to_xy(geoms):
    """NaN-separated x / y arrays tracing every line and polygon ring in ``geoms``."""
    import shapely

    xs, ys = [], []
    # get_parts splits multi-part shapes and collections into single shapes.
    for geom in geoms:
        for part in shapely.get_parts(shapely.get_parts(geom)):
            if part.geom_type == "Polygon":
                rings = [part.exterior, *part.interiors]
            elif part.geom_type in ("LineString", "LinearRing"):
                rings = [part]
            else:
                continue
            for ring in rings:
                x, y = ring.xy
                xs += [*x, np.nan]
                ys += [*y, np.nan]
    return np.array(xs, dtype=float), np.array(ys, dtype=float)
