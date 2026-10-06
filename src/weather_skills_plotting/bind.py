"""Fill Plotly traces from weather-skills datasets.

A spec trace names its data in ``meta`` (``source``, ``bind``, ``facet``, …).
Each binder turns one such trace into concrete Plotly traces, grouped into
panels (one per facet value, or a single panel), and reports what the figure
needs to know: whether it is a map, its lon/lat extent, the values that drive
its color scale, and default axis / panel titles. Binders never style beyond a
sensible default; the user's own trace keys are merged on afterwards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from weather_skills_core.cf import auto_variable, cf_dim
from weather_skills_core.errors import UsageError
from weather_skills_core.standard_utils import ensure_normalized_longitude, polygon_from_geojson
from weather_skills_core.units import (
    precip_for_display,
    to_standard_units,
    units_equal,
    variable_label_for_display,
    variable_units,
)

from weather_skills_plotting.geodata import (
    extent_from_da,
    plain,
    point_dim,
    subset_points,
    subset_spatial,
)
from weather_skills_plotting.labels import (
    axis_label,
    format_plot_date,
    format_step,
    is_datetime_axis,
    panel_title,
    timeseries_axis,
)
from weather_skills_plotting.palettes import (
    along_dim,
    along_member_label,
    continuous_colorscale,
    parse_palette,
)
from weather_skills_plotting.spec import DEFAULT_BIND
from weather_skills_plotting.wind import (
    WIND_ROSE_SECTORS,
    WIND_SPEED_COLORS,
    _calendar_year,  # noqa: F401 — re-exported for tests
    flat_numeric,
    is_sample_dim,
    native_spacing_deg,
    pair_xy,
    quiver_step,
    resolve_uv,
    speed_bin_labels,
    speed_edges,
    speed_units_display,
    subsample_quiver,
    uv_to_speed_fromdir,
    wind_rose_hist,
    wind_speed_cbar_label,
    wind_speed_da,
)

FACET_DIMS = ("step", "time", "valid_time")
ARROW_LEN_SPACING = 1.5
ARROW_KEY_SPEED = 10.0


@dataclass
class Panel:
    """Concrete traces for one panel; ``title`` is the default panel title."""

    traces: list
    title: str | None = None
    key: object = None


@dataclass
class Bound:
    """What one spec trace became."""

    panels: list
    is_map: bool = False
    static: bool = False
    extent: list | None = None
    # Color-scaled traces: the raw values, where they live in each concrete
    # trace ("z" or "marker.color"), a sample DataArray for palette detection,
    # and the colorbar title.
    color_values: list = field(default_factory=list)
    color_key: str | None = None
    color_da: object = None
    color_title: str | None = None
    default_colorscale: object = None
    axis_titles: dict = field(default_factory=dict)
    title: str | None = None
    layout: dict = field(default_factory=dict)
    x_is_date: bool = False
    x_tickformat: str | None = None


@dataclass
class Context:
    datasets: dict
    palettes: dict
    bbox: tuple | None = None
    polygon: object = None
    point: dict | None = None


def bind_of(trace: dict) -> str | None:
    """The trace's bind mode, or ``None`` for a plain Plotly trace."""
    meta = trace.get("meta") or {}
    if meta.get("bind"):
        return meta["bind"]
    if not any(meta.get(k) for k in ("source", "x", "y")):
        return None
    return DEFAULT_BIND.get(trace.get("type") or "scatter", "series")


# ------------------------------------------------------------------- selection


def _dataset(ctx: Context, source: dict, loc: str):
    input_id = source.get("input")
    if input_id is None:
        if len(ctx.datasets) != 1:
            raise UsageError(
                f"{loc}.input is required when there are several inputs "
                f"(have {', '.join(ctx.datasets) or 'none'})"
            )
        input_id = next(iter(ctx.datasets))
    ds = ctx.datasets.get(str(input_id))
    if ds is None:
        raise UsageError(
            f"{loc}.input {input_id!r} is not an input (have {', '.join(ctx.datasets) or 'none'}); "
            "pass the file with -i or list it in layout.meta.inputs"
        )
    return ds


def _display(ds, variable):
    try:
        ds = to_standard_units(ds, variables=[variable])
    except UsageError:
        # Totals or anomalies can carry a rate/temperature standard_name that
        # the standard-units table would force into an incompatible target.
        pass
    return precip_for_display(ds, variable)


def _variable(ds, name, loc):
    variable = name or auto_variable(ds)
    if not variable or variable not in ds:
        raise UsageError(
            f"{loc}.variable {variable!r} is not in the data; available: {', '.join(ds.data_vars)}"
        )
    return variable


def _sel(da, source: dict, loc: str):
    """Apply ``isel`` (positions) then ``sel`` (labels, nearest for numbers/dates)."""
    for dim, idx in (source.get("isel") or {}).items():
        if dim not in da.dims:
            raise UsageError(
                f"{loc}.isel dimension {dim!r} is not in the data (dims: {list(da.dims)})"
            )
        size = da.sizes[dim]
        for pos in idx if isinstance(idx, list) else [idx]:
            if isinstance(pos, bool) or not isinstance(pos, int) or not -size <= pos < size:
                raise UsageError(f"{loc}.isel {dim}={pos!r} is out of range (size {size})")
        da = da.isel({dim: idx})
    for dim, value in (source.get("sel") or {}).items():
        if dim not in da.dims:
            raise UsageError(
                f"{loc}.sel dimension {dim!r} is not in the data (dims: {list(da.dims)})"
            )
        coord = da[dim].values
        kind = getattr(coord.dtype, "kind", "O")
        try:
            if kind == "M":
                target = (
                    np.datetime64(value)
                    if not isinstance(value, list)
                    else [np.datetime64(v) for v in value]
                )
                da = da.sel({dim: target}, method="nearest")
            elif kind == "m":
                target = (
                    np.timedelta64(int(value), "D") if isinstance(value, (int, float)) else value
                )
                da = da.sel({dim: target})
            elif kind in "iuf":
                da = da.sel({dim: value}, method="nearest")
            else:
                da = da.sel({dim: value})
        except (KeyError, ValueError, TypeError) as exc:
            raise UsageError(
                f"{loc}.sel {dim}={value!r} does not match the coordinate ({exc})"
            ) from None
    return da


def _polygon(ctx: Context, source: dict):
    path = source.get("mask_geojson")
    return polygon_from_geojson(path) if path else ctx.polygon


def select(ctx: Context, source: dict, loc: str, *, variable=None):
    """The source's variable after units, ``isel``/``sel`` and the geo subset."""
    ds = _dataset(ctx, source, loc)
    name = _variable(ds, variable or source.get("variable"), loc)
    ds = _display(ds, name)
    da = _sel(plain(ds[name]), source, loc)
    return _subset(ctx, source, da), ds


def _subset(ctx: Context, source: dict, da):
    polygon = _polygon(ctx, source)
    if ctx.bbox is None and polygon is None:
        return da
    lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
    if lat in da.dims and lon in da.dims:
        da, _ = subset_spatial(da, lat, lon, ctx.bbox, polygon, None)
        if da.sizes[lat] == 0 or da.sizes[lon] == 0:
            raise UsageError(
                "no grid cells remain after layout.meta.geo.bbox / mask_geojson; nothing to plot"
            )
    elif lat and lon:
        da = subset_points(da, ctx.bbox, polygon)
    return da


def _reduce(da, source: dict):
    dims = [d for d in (source.get("reduce") or []) if d in da.dims]
    return da.mean(dims, keep_attrs=True) if dims else da


def _facet_dim(meta: dict, da, keep: tuple, loc: str):
    """The dim that becomes one panel per value, or ``None``."""
    facet = meta.get("facet")
    if facet is False:
        return None
    if isinstance(facet, str):
        if facet not in da.dims:
            raise UsageError(f"{loc}.facet {facet!r} is not a dimension (dims: {list(da.dims)})")
        return facet
    for name in FACET_DIMS:
        if name in da.dims and name not in keep:
            return name
    cf = cf_dim(da, "time")
    return cf if cf in da.dims and cf not in keep else None


def _leftover_error(da, allowed, what, loc):
    extra = [d for d in da.dims if d not in allowed]
    if extra:
        raise UsageError(
            f"dimension {extra[0]!r} remains for {what}; select a position with "
            f"{loc}.source.isel / sel, average it with {loc}.source.reduce, or panel it "
            f"with {loc}.facet. Side-by-side maps are separate inputs on separate axes, "
            f"not one dataset concatenated along {extra[0]!r}"
        )


def _lonlat(da, what):
    lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
    if lat is None or lon is None or lat not in da.dims or lon not in da.dims:
        raise UsageError(
            f"{what} needs latitude/longitude dimensions; got {list(da.dims)}. "
            'Station data draws as a scatter trace with meta.bind "points"'
        )
    return lat, lon


def _wrapped(ctx):
    return ctx.bbox is not None and ctx.bbox[1] > ctx.bbox[3]


def _map_field(ctx, da, meta, loc, what):
    """Grid field ready to panel: subset, ensemble-mean, transposed."""
    lat, lon = _lonlat(da, what)
    if not _wrapped(ctx):
        da = ensure_normalized_longitude(da, lon)
    fdim = _facet_dim(meta, da, (lat, lon), loc)
    if "number" in da.dims and fdim != "number":
        da = da.mean("number", keep_attrs=True)
    _leftover_error(da, {lat, lon, fdim}, what, loc)
    order = ([fdim] if fdim else []) + [lat, lon]
    return da.transpose(*order), lat, lon, fdim


def _slices(da, fdim):
    """``[(key, title, slice)]`` along the facet dim (one ``None`` slice without)."""
    if fdim is None:
        return [(None, None, da)]
    values = list(da[fdim].values)
    return [(v, panel_title(da, fdim, v, values), da.isel({fdim: i})) for i, v in enumerate(values)]


# --------------------------------------------------------------------- binders


def bind_field(trace, meta, ctx, loc, *, speed=False):
    source = meta.get("source") or {}
    if speed:
        ds = _dataset(ctx, source, f"{loc}.source")
        u_name, v_name = resolve_uv(ds, source.get("u"), source.get("v"))
        ds = to_standard_units(ds, variables=[u_name, v_name])
        u_da = _subset(ctx, source, _sel(plain(ds[u_name]), source, f"{loc}.source"))
        v_da = _subset(ctx, source, _sel(plain(ds[v_name]), source, f"{loc}.source"))
        da = wind_speed_da(u_da, v_da)
        title = wind_speed_cbar_label(u_da)
    else:
        da, _ = select(ctx, source, f"{loc}.source")
        da = _reduce(da, source)
        title = variable_label_for_display(da)
    da, lat, lon, fdim = _map_field(ctx, da, meta, loc, "a map")
    x, y = da[lon].values, da[lat].values
    panels, values = [], []
    hover = "%{x:.2f}°, %{y:.2f}°: %{customdata:.4g}<extra></extra>"
    for key, ptitle, part in _slices(da, fdim):
        z = np.asarray(part.values, dtype=float)
        values.append(z)
        panels.append(
            Panel([{"x": x, "y": y, "z": z, "customdata": z, "hovertemplate": hover}], ptitle, key)
        )
    return Bound(
        panels,
        is_map=True,
        extent=extent_from_da(da, lat, lon, ctx.bbox),
        color_values=values,
        color_key="z",
        color_da=None if speed else da,
        color_title=title,
        default_colorscale="YlGn" if speed else None,
    )


def _arrow_segments(lon, lat, u, v, scale):
    """Shaft plus a two-stroke head per arrow, as one None-separated polyline."""
    xs, ys = [], []
    for x0, y0, du, dv in zip(lon.ravel(), lat.ravel(), u.ravel(), v.ravel(), strict=True):
        if not (np.isfinite(du) and np.isfinite(dv)) or (du == 0 and dv == 0):
            continue
        x1, y1 = x0 + du * scale, y0 + dv * scale
        ang = np.arctan2(dv, du)
        head = 0.3 * np.hypot(du, dv) * scale
        xs += [x0, x1, None]
        ys += [y0, y1, None]
        for side in (+1, -1):
            a = ang + np.pi - side * np.radians(25)
            xs += [x1, x1 + head * np.cos(a), None]
            ys += [y1, y1 + head * np.sin(a), None]
    return xs, ys


def bind_arrows(trace, meta, ctx, loc):
    source = meta.get("source") or {}
    opts = meta.get("arrows") or {}
    ds = _dataset(ctx, source, f"{loc}.source")
    u_name, v_name = resolve_uv(ds, source.get("u"), source.get("v"))
    ds = to_standard_units(ds, variables=[u_name, v_name])
    u_units, v_units = variable_units(ds[u_name]), variable_units(ds[v_name])
    if u_units and v_units and not units_equal(u_units, v_units):
        raise UsageError(f"u units {u_units!r} do not match v units {v_units!r}")
    u_da = _subset(ctx, source, _sel(plain(ds[u_name]), source, f"{loc}.source"))
    v_da = _subset(ctx, source, _sel(plain(ds[v_name]), source, f"{loc}.source"))
    u_da, lat, lon, fdim = _map_field(ctx, u_da, meta, loc, "wind arrows")
    v_da, *_ = _map_field(ctx, v_da, meta, loc, "wind arrows")
    step = quiver_step(u_da[lat].values, u_da[lon].values, opts.get("step"))
    scale = opts.get("scale")
    if scale is None:
        spacing = (native_spacing_deg(u_da[lat].values, u_da[lon].values) or 1.0) * step
        speed = np.hypot(np.asarray(u_da.values, float), np.asarray(v_da.values, float))
        typical = float(np.nanpercentile(speed, 95)) if np.isfinite(speed).any() else 0.0
        scale = ARROW_LEN_SPACING * spacing / typical if typical > 0 else 0.1
    elif scale <= 0:
        raise UsageError(f"{loc}.arrows.scale must be > 0 (degrees of arrow per unit of speed)")
    extent = extent_from_da(u_da, lat, lon, ctx.bbox)
    units = speed_units_display(ds[u_name])
    panels = []
    for (key, ptitle, u_part), (_, _, v_part) in zip(
        _slices(u_da, fdim), _slices(v_da, fdim), strict=True
    ):
        lon_q, lat_q, uq, vq = subsample_quiver(
            u_part[lon].values, u_part[lat].values, u_part.values, v_part.values, step
        )
        xs, ys = _arrow_segments(lon_q, lat_q, uq, vq, scale)
        span_x, span_y = extent[1] - extent[0], extent[3] - extent[2]
        kx, ky = extent[1] - 0.04 * span_x - ARROW_KEY_SPEED * scale, extent[2] + 0.04 * span_y
        kxs, kys = _arrow_segments(
            np.array([kx]), np.array([ky]), np.array([ARROW_KEY_SPEED]), np.array([0.0]), scale
        )
        arrows = {
            "mode": "lines",
            "x": xs,
            "y": ys,
            "hoverinfo": "skip",
            "showlegend": False,
            "line": {"color": "black", "width": 1},
        }
        key_trace = {
            "type": "scatter",
            "mode": "lines+text",
            "x": kxs + [kx - 0.01 * span_x],
            "y": kys + [ky],
            "text": [""] * len(kxs) + [f"{ARROW_KEY_SPEED:g} {units}"],
            "textposition": "middle left",
            "hoverinfo": "skip",
            "showlegend": False,
            "line": {"color": "black", "width": 1.5},
            "textfont": {"size": 13},
            "uid_suffix": "key",
        }
        panels.append(Panel([arrows, key_trace], ptitle, key))
    return Bound(panels, is_map=True, extent=extent)


def _points_extent(da):
    lat_name, lon_name = cf_dim(da, "latitude"), cf_dim(da, "longitude")
    lat = np.asarray(da[lat_name].values, dtype=float)
    lon = np.asarray(da[lon_name].values, dtype=float)
    pad_lat = max(0.5, 0.1 * float(np.nanmax(lat) - np.nanmin(lat)))
    pad_lon = max(0.5, 0.1 * float(np.nanmax(lon) - np.nanmin(lon)))
    return [
        float(np.nanmin(lon)) - pad_lon,
        float(np.nanmax(lon)) + pad_lon,
        float(np.nanmin(lat)) - pad_lat,
        float(np.nanmax(lat)) + pad_lat,
    ]


def bind_points(trace, meta, ctx, loc):
    source = meta.get("source") or {}
    da, ds = select(ctx, source, f"{loc}.source")
    pdim = point_dim(ds)
    if pdim is None or pdim not in da.dims:
        raise UsageError(
            f'{loc}: meta.bind "points" needs a station_id or point_id dimension '
            f"(dims: {list(da.dims)})"
        )
    if da.sizes[pdim] == 0:
        raise UsageError(
            f"{loc}: no stations remain after layout.meta.geo.bbox / mask_geojson; nothing to plot"
        )
    da = _reduce(da, source)
    fdim = _facet_dim(meta, da, (pdim,), loc)
    if "number" in da.dims and fdim != "number":
        da = da.mean("number", keep_attrs=True)
    _leftover_error(da, {pdim, fdim}, "station points", loc)
    if fdim:
        da = da.transpose(fdim, pdim)
    lat = np.asarray(da[cf_dim(da, "latitude")].values, dtype=float)
    lon = np.asarray(da[cf_dim(da, "longitude")].values, dtype=float)
    names = [str(v) for v in da[pdim].values]
    panels, values = [], []
    for key, ptitle, part in _slices(da, fdim):
        vals = np.asarray(part.values, dtype=float)
        values.append(vals)
        panels.append(
            Panel(
                [
                    {
                        "mode": "markers",
                        "x": lon,
                        "y": lat,
                        "text": names,
                        "customdata": vals,
                        "marker": {
                            "color": vals,
                            "size": 11,
                            "line": {"color": "black", "width": 0.6},
                        },
                        "hovertemplate": "%{text}: %{customdata:.4g}<extra></extra>",
                        "showlegend": False,
                    }
                ],
                ptitle,
                key,
            )
        )
    extent = (
        [ctx.bbox[1], ctx.bbox[3], ctx.bbox[2], ctx.bbox[0]] if ctx.bbox else _points_extent(da)
    )
    return Bound(
        panels,
        is_map=True,
        extent=extent,
        color_values=values,
        color_key="marker.color",
        color_da=da,
        color_title=variable_label_for_display(da),
    )


def _geojson_lines(path):
    import shapely
    from shapely.geometry import shape

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read GeoJSON {path}: {exc}") from None
    feats = raw.get("features") or ([raw] if raw.get("type") == "Feature" else [{"geometry": raw}])
    xs, ys, geoms = [], [], []
    for feat in feats:
        geom = shape(feat.get("geometry") or {})
        geoms.append(geom)
        boundary = shapely.boundary(geom) if geom.geom_type.endswith("Polygon") else geom
        for part in getattr(boundary, "geoms", [boundary]):
            x, y = part.xy
            xs += list(x) + [None]
            ys += list(y) + [None]
    union = shapely.union_all(geoms)
    return xs, ys, union.bounds


def bind_geojson(trace, meta, ctx, loc):
    path = (meta.get("source") or {}).get("geojson")
    if not path:
        raise UsageError(f'{loc}: meta.bind "geojson" needs meta.source.geojson (a file path)')
    xs, ys, (w, s, e, n) = _geojson_lines(path)
    line = {
        "mode": "lines",
        "x": xs,
        "y": ys,
        "hoverinfo": "skip",
        "showlegend": False,
        "line": {"color": "black", "width": 1.6},
    }
    return Bound([Panel([line])], is_map=True, static=True, extent=[w, e, s, n])


def _color_name(trace, color):
    return (
        (trace.get("line") or {}).get("color") or (trace.get("marker") or {}).get("color") or color
    )


def _rgba(color, alpha):
    from plotly.colors import hex_to_rgb, unlabel_rgb

    if isinstance(color, str) and color.startswith("#"):
        r, g, b = hex_to_rgb(color)
    elif isinstance(color, str) and color.startswith("rgb"):
        r, g, b = unlabel_rgb(color)[:3]
    else:
        return color
    return f"rgba({int(r)}, {int(g)}, {int(b)}, {alpha})"


def bind_series(trace, meta, ctx, loc, *, color=None):
    source = meta.get("source") or {}
    da, _ = select(ctx, source, f"{loc}.source")
    da = _reduce(da, source)
    sdim = "step" if "step" in da.dims else cf_dim(da, "time")
    if sdim is None or sdim not in da.dims:
        if da.ndim == 1:
            sdim = da.dims[0]
        else:
            raise UsageError(f"{loc}: a series needs a step or time axis; got {list(da.dims)}")
    along = along_dim(da, meta.get("along"))
    if meta.get("along") and along is None:
        raise UsageError(
            f"{loc}.along {meta['along']!r} is not a dimension (dims: {list(da.dims)})"
        )
    if along == sdim:
        raise UsageError(
            f"{loc}.along is the time axis {sdim!r}; pass a non-time dim such as number"
        )
    extra = [d for d in da.dims if d not in (sdim, along)]
    if extra:
        raise UsageError(
            f"{loc}: dims {extra} remain besides {sdim!r}. Add them to {loc}.source.reduce "
            f"(averaged), or set {loc}.along {extra[0]!r} for one line per value. Nothing is "
            "averaged silently"
        )
    x, xname = timeseries_axis(da, sdim)
    x = np.asarray(x)
    aligned = meta.get("align") == "dayofyear"
    if aligned:
        x = seasonal_dates(da[sdim], loc)
    if x.dtype.kind == "m":
        x = x / np.timedelta64(1, "D")
        xname = "Lead (days)"
    is_date = is_datetime_axis(x)
    xs = list(x.astype("datetime64[ms]").astype(str)) if x.dtype.kind == "M" else list(x)
    label = trace.get("name") or variable_label_for_display(da, include_units=False)
    ttype = trace.get("type") or "scatter"
    base = {"name": label}
    if ttype == "scatter":
        base["mode"] = "lines+markers"
    traces = []
    if along is None:
        traces.append({**base, "x": xs, "y": np.asarray(da.values, dtype=float)})
    else:
        da = da.transpose(sdim, along)
        y = np.asarray(da.values, dtype=float)
        members = [along_member_label(v) for v in da[along].values]
        band = meta.get("band")
        if band is not None:
            col = _color_name(trace, color)
            lo, hi = np.nanpercentile(y, band[0], axis=1), np.nanpercentile(y, band[1], axis=1)
            common = {
                "type": "scatter",
                "x": xs,
                "mode": "lines",
                "line": {"width": 0},
                "showlegend": False,
                "hoverinfo": "skip",
                "legendgroup": label,
            }
            traces += [
                {**common, "y": lo, "uid_suffix": "band-low"},
                {
                    **common,
                    "y": hi,
                    "fill": "tonexty",
                    "fillcolor": _rgba(col, 0.25),
                    "uid_suffix": "band-high",
                },
                {
                    **base,
                    "x": xs,
                    "y": np.nanmean(y, axis=1),
                    "mode": "lines",
                    "line": {"color": col, "width": 2},
                },
            ]
        elif meta.get("along_color") == "cycle":
            if (trace.get("line") or {}).get("color"):
                raise UsageError(
                    f"{loc}: along_color cycle gives each member its own color; drop line.color"
                )
            for j, member in enumerate(members):
                traces.append(
                    {
                        **base,
                        "x": xs,
                        "y": y[:, j],
                        "name": member,
                        "mode": "lines",
                        "uid_suffix": f"{along}={member}",
                    }
                )
        else:
            gx, gy = [], []
            for j in range(y.shape[1]):
                gx += xs + [None]
                gy += list(y[:, j]) + [None]
            traces.append(
                {
                    **base,
                    "x": gx,
                    "y": gy,
                    "mode": "lines",
                    "opacity": 0.45,
                    "line": {"width": 1, "color": _color_name(trace, color)},
                }
            )
    titles = {"x": "" if is_date else axis_label(xname), "y": variable_label_for_display(da)}
    return Bound(
        [Panel(traces)],
        axis_titles=titles,
        x_is_date=is_date,
        x_tickformat=SEASONAL_TICKFORMAT if aligned else None,
    )


# align "dayofyear" puts every year on this non-leap year, so 1 Oct lines up
# whether or not the data year was a leap year.
SEASONAL_YEAR = 2001
SEASONAL_TICKFORMAT = "%-d %b"


def seasonal_dates(coord, loc):
    """Each date moved to ``SEASONAL_YEAR`` (29 Feb folds onto 28 Feb), as datetime64."""
    try:
        month, day = coord.dt.month.values, coord.dt.day.values
    except (TypeError, AttributeError):
        raise UsageError(f"{loc}.align dayofyear needs a calendar-date time axis") from None
    day = np.where((month == 2) & (day == 29), 28, day)
    text = [f"{SEASONAL_YEAR}-{m:02d}-{d:02d}" for m, d in zip(month, day, strict=True)]
    return np.array(text, dtype="datetime64[D]").astype("datetime64[ns]")


def _xy_series(ctx, source, loc):
    da, _ = select(ctx, source, loc)
    sdim = "step" if "step" in da.dims else cf_dim(da, "time")
    if sdim is None or sdim not in da.dims:
        if da.ndim != 1:
            raise UsageError(
                f"{loc} needs a time or step axis to pair samples; got {list(da.dims)}"
            )
        sdim = da.dims[0]
    rest = [d for d in da.dims if d != sdim]
    reduced = da.mean(rest, keep_attrs=True) if rest else da
    axis, _ = timeseries_axis(reduced, sdim)
    return reduced, np.asarray(axis), np.asarray(reduced.values, dtype=float)


def bind_pair(trace, meta, ctx, loc):
    pair_on = meta.get("pair_on") or "time"
    if not meta.get("x") or not meta.get("y"):
        raise UsageError(f'{loc}: meta.bind "pair" needs meta.x and meta.y sources')
    x_da, x_axis, x_raw = _xy_series(ctx, meta["x"], f"{loc}.x")
    y_da, y_axis, y_raw = _xy_series(ctx, meta["y"], f"{loc}.y")
    xv, yv, keys = pair_xy(x_axis, x_raw, y_axis, y_raw, pair_on)
    keep = np.isfinite(xv) & np.isfinite(yv)
    xv, yv = xv[keep], yv[keep]
    keys = [k for k, ok in zip(keys, keep, strict=True) if ok]
    if xv.size == 0:
        raise UsageError(f"{loc}: no finite paired samples to plot")
    labelled = pair_on == "year" or (pair_on == "time" and xv.size <= 25)
    out = {
        "mode": "markers+text" if labelled else "markers",
        "x": xv,
        "y": yv,
        "marker": {"size": 10},
        "showlegend": False,
    }
    if labelled:
        out.update(
            text=[format_plot_date(k) if pair_on == "time" else str(k) for k in keys],
            textposition="top right",
            textfont={"size": 11},
        )
    x_qty = variable_label_for_display(x_da, include_units=False)
    y_qty = variable_label_for_display(y_da, include_units=False)
    return Bound(
        [Panel([out])],
        axis_titles={"x": variable_label_for_display(x_da), "y": variable_label_for_display(y_da)},
        title=f"{y_qty} vs {x_qty}",
    )


def bind_samples(trace, meta, ctx, loc):
    """Box of every sample per category (box), or the category mean (scatter)."""
    source = meta.get("source") or {}
    da, _ = select(ctx, source, f"{loc}.source")
    point = source.get("point") or ctx.point
    lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
    if point is not None:
        if lat not in da.dims or lon not in da.dims:
            raise UsageError(
                f"{loc}.source.point needs latitude/longitude dims; got {list(da.dims)}"
            )
        da = da.sel({lat: point["lat"], lon: point["lon"]}, method="nearest")
    elif lat in da.dims or lon in da.dims:
        raise UsageError(
            f'{loc}.source.point or layout.meta.geo.point ({{"lat": …, "lon": …}}) is '
            "required to take samples at a point"
        )
    da = _reduce(da, source)
    cat = "step" if "step" in da.dims else cf_dim(da, "time")
    if cat is None or cat not in da.dims:
        raise UsageError(f"{loc}: samples need a step or time axis for the categories")
    rest = [d for d in da.dims if d != cat]
    da = da.transpose(cat, *rest)
    labels = [format_step(v) for v in da[cat].values]
    vals = np.asarray(da.values, dtype=float).reshape(len(labels), -1)
    if (trace.get("type") or "box") == "box":
        out = {"x": np.repeat(labels, vals.shape[1]), "y": vals.ravel()}
    else:
        out = {"mode": "lines+markers", "x": labels, "y": np.nanmean(vals, axis=1)}
    return Bound([Panel([out])], axis_titles={"y": variable_label_for_display(da)})


def bind_windrose(trace, meta, ctx, loc):
    source = meta.get("source") or {}
    ds = _dataset(ctx, source, f"{loc}.source")
    u_name, v_name = resolve_uv(ds, source.get("u"), source.get("v"))
    ds = to_standard_units(ds, variables=[u_name, v_name])
    u_da = _subset(ctx, source, _sel(plain(ds[u_name]), source, f"{loc}.source"))
    v_da = _subset(ctx, source, _sel(plain(ds[v_name]), source, f"{loc}.source"))
    extra = [d for d in u_da.dims if not is_sample_dim(u_da, d)]
    if extra:
        raise UsageError(
            f"dimension {extra[0]!r} remains; a wind rose pools space, time and ensemble into "
            f"samples — select a position with {loc}.source.isel"
        )
    u, v = flat_numeric(u_da), flat_numeric(v_da)
    if u.size != v.size:
        raise UsageError(f"u {u_name!r} and v {v_name!r} have different sizes after selection")
    ok = np.isfinite(u) & np.isfinite(v)
    u, v = u[ok], v[ok]
    if u.size == 0:
        raise UsageError("wind rose has no finite u/v samples to plot")
    speed, direction = uv_to_speed_fromdir(u, v)
    edges = speed_edges(speed, variable_units(u_da))
    hist = wind_rose_hist(speed, direction, edges, nsector=WIND_ROSE_SECTORS)
    while hist.shape[1] > 1 and float(hist[:, -1].sum()) == 0:
        hist, edges = hist[:, :-1], edges[:-1]
    freq = 100.0 * hist / float(hist.sum())
    n = freq.shape[1]
    palette = meta.get("palette")
    colors = (
        parse_palette(palette, loc=f"{loc}.palette", registry=ctx.palettes)["colors"]
        if palette
        else WIND_SPEED_COLORS
    )
    from plotly.colors import sample_colorscale

    colors = sample_colorscale(continuous_colorscale(colors), [i / max(n - 1, 1) for i in range(n)])
    units = speed_units_display(u_da)
    theta = [i * 360.0 / WIND_ROSE_SECTORS for i in range(WIND_ROSE_SECTORS)]
    traces = [
        {
            "r": freq[:, i],
            "theta": theta,
            "name": f"{label} {units}",
            "uid_suffix": f"bin{i}",
            "marker": {"color": colors[i], "line": {"color": "white", "width": 0.6}},
        }
        for i, label in enumerate(speed_bin_labels(edges))
    ]
    compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    layout = {
        "polar": {
            "angularaxis": {
                "rotation": 90,
                "direction": "clockwise",
                "tickvals": [i * 45 for i in range(8)],
                "ticktext": compass,
            },
            "radialaxis": {"ticksuffix": "%", "angle": 90, "tickangle": 90},
        },
        "legend": {"title": {"text": "Wind speed"}},
        "barmode": "stack",
    }
    return Bound([Panel(traces)], layout=layout)


BINDERS = {
    "field": bind_field,
    "speed": lambda t, m, c, loc: bind_field(t, m, c, loc, speed=True),
    "arrows": bind_arrows,
    "points": bind_points,
    "geojson": bind_geojson,
    "series": bind_series,
    "pair": bind_pair,
    "samples": bind_samples,
    "windrose": bind_windrose,
}

_TYPES_FOR_BIND = {
    "field": {"heatmap", "contour"},
    "speed": {"heatmap", "contour"},
    "arrows": {"scatter", "scattergl"},
    "points": {"scatter", "scattergl"},
    "geojson": {"scatter", "scattergl"},
    "series": {"scatter", "scattergl", "bar"},
    "pair": {"scatter", "scattergl"},
    "samples": {"box", "scatter", "violin"},
    "windrose": {"barpolar"},
}


def bind_trace(trace: dict, ctx: Context, loc: str, *, color=None) -> Bound:
    bind = bind_of(trace)
    ttype = trace.get("type") or "scatter"
    allowed = _TYPES_FOR_BIND[bind]
    if ttype not in allowed:
        raise UsageError(
            f"{loc}: meta.bind {bind!r} draws as type {' or '.join(sorted(allowed))}, "
            f"not {ttype!r}"
            + (
                '; for a 1-D series of a gridded field set meta.bind "series" and '
                "average lat/lon with meta.source.reduce"
                if bind == "field"
                else ""
            )
        )
    if bind == "series":
        return bind_series(trace, trace.get("meta") or {}, ctx, loc, color=color)
    return BINDERS[bind](trace, trace.get("meta") or {}, ctx, loc)
