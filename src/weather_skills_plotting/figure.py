"""Assemble a Plotly figure from a spec and its datasets.

1. Bind: every trace with ``meta`` data becomes concrete traces (``bind.py``).
2. Place: map traces group by their ``xaxis`` anchor; a group panels its
   facet values; static layers (outlines, plain traces) repeat on each panel.
3. Color: each color-scaled source trace gets a ``coloraxis`` (shared when
   the user points traces at the same one, or when same-variable layers
   share a panel). Class palettes become stepped colorscales.
4. Defaults (axis titles, panel titles, colorbar titles, sizes) fill only
   what the user's layout leaves unset; the user's layout is merged last.
"""

from __future__ import annotations

import copy
import re

import numpy as np
from weather_skills_core.errors import UsageError
from weather_skills_core.standard_utils import parse_bbox, polygon_from_geojson

from weather_skills_plotting.bind import Context, bind_of, bind_trace
from weather_skills_plotting.geodata import (
    OVERLAY_STYLES,
    geoms_to_xy,
    overlay_geoms,
    overlay_settings,
)
from weather_skills_plotting.layout import (
    CHART_SIZE,
    DEFAULT_FONTSIZE,
    DEFAULT_TEMPLATE,
    axis_suffix,
    colorbar_bottom,
    colorbar_right_of,
    grid_shape,
    map_axes,
    map_grid,
    panel_title,
    register_templates,
)
from weather_skills_plotting.palettes import (
    COLORBLIND,
    DEEP,
    DEFAULT_SEQUENTIAL,
    continuous_colorscale,
    default_palette,
    discretize,
    load_theme,
    parse_palette,
)
from weather_skills_plotting.spec import (
    deep_merge,
    fill_defaults,
    merge_spec,
    plotly_error,
    validate,
)

# Draw order inside a map panel: fields under overlays, then arrows, stations, outlines.
_MAP_RANK = {"field": 0, "speed": 0, "overlay": 1, "arrows": 2, "points": 3, "geojson": 4, None: 5}
_TRACE_COLOR_KEYS = ("colorscale", "reversescale", "showscale", "colorbar")
_TRACE_LIMIT_KEYS = {"zmin": "cmin", "zmax": "cmax", "zmid": "cmid"}
_MARKER_LIMIT_KEYS = {"cmin": "cmin", "cmax": "cmax", "cmid": "cmid"}


def compile_figure(spec: dict, datasets: dict, *, theme: dict | None = None):
    """Return a validated ``plotly.graph_objects.Figure``."""
    import plotly.graph_objects as go

    spec = validate(copy.deepcopy(spec))
    theme = theme or load_theme()
    register_templates(theme.get("template"))
    user_layout = copy.deepcopy(spec.get("layout") or {})
    lmeta = user_layout.pop("meta", None) or {}
    geo = lmeta.get("geo") or {}
    bbox = geo.get("bbox")
    ctx = Context(
        datasets=datasets,
        palettes=theme["palettes"],
        bbox=tuple(parse_bbox(bbox)) if isinstance(bbox, str) else (tuple(bbox) if bbox else None),
        polygon=polygon_from_geojson(geo["mask_geojson"]) if geo.get("mask_geojson") else None,
        point=geo.get("point"),
    )
    template = user_layout.get("template", DEFAULT_TEMPLATE)
    colorway = COLORBLIND if template == "colorblind" else DEEP
    font = float(((user_layout.get("font") or {}).get("size")) or DEFAULT_FONTSIZE)

    items = []
    n_colored = 0
    for i, trace in enumerate(spec.get("data") or []):
        bound = None
        if bind_of(trace):
            bound = bind_trace(trace, ctx, f"data[{i}]", color=colorway[n_colored % len(colorway)])
            n_colored += 1
        items.append((i, trace, bound))
    if not items:
        raise UsageError("plot spec has no traces to draw")

    if any(b is not None and b.is_map for _, _, b in items):
        data, layout = _assemble_map(items, user_layout, lmeta, ctx, font)
    else:
        data, layout = _assemble_chart(items, user_layout, font)
    layout.setdefault("template", DEFAULT_TEMPLATE)
    out_layout = merge_spec({"layout": layout}, {"layout": user_layout})["layout"]
    try:
        return go.Figure({"data": data, "layout": out_layout})
    except ValueError as exc:
        raise plotly_error(exc) from None


# ---------------------------------------------------------------- trace merge


def _concrete(spec_trace: dict, generated: dict, uid: str, *, user_style=True) -> dict:
    """Generated arrays with the user's own trace keys on top (user wins)."""
    gen = dict(generated)
    suffix = gen.pop("uid_suffix", None)
    out = {"type": spec_trace.get("type") or "scatter"}
    if user_style and not str(suffix or "").startswith("band"):
        user = {k: v for k, v in spec_trace.items() if k not in ("meta", "uid", "xaxis", "yaxis")}
        out.update(deep_merge(gen, user))
    else:
        out.update(gen)
    out["uid"] = safe_uid(f"{uid}-{suffix}" if suffix else uid)
    return out


def safe_uid(text) -> str:
    """plotly.js puts uids in CSS selectors: keep letters, digits, ``-`` and ``_``."""
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(text))


def _set_path(obj: dict, path: str, value):
    keys = path.split(".")
    for key in keys[:-1]:
        obj = obj.setdefault(key, {})
    obj[keys[-1]] = value


def _get_path(obj: dict, path: str):
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


# ---------------------------------------------------------------- color axes


def _lift_color(spec_trace: dict, color_key: str) -> dict:
    """Trace-level colorscale / limits / colorbar, moved onto its coloraxis."""
    holder = spec_trace.get("marker") or {} if color_key == "marker.color" else spec_trace
    limits = _MARKER_LIMIT_KEYS if color_key == "marker.color" else _TRACE_LIMIT_KEYS
    out = {k: copy.deepcopy(holder[k]) for k in _TRACE_COLOR_KEYS if k in holder}
    out.update({dst: holder[src] for src, dst in limits.items() if src in holder})
    return out


def _resolve_coloraxis(name, members, user_axis, ctx, *, contour_traces):
    """Fill ``layout.<name>`` for the bound traces in ``members``.

    ``members`` are ``(spec_trace, bound, concrete_traces)``. Returns the
    generated coloraxis dict (the user's own keys are merged later).
    """
    lifted = {}
    for spec_trace, bound, _ in members:
        lifted = deep_merge(lifted, _lift_color(spec_trace, bound.color_key))
    user = deep_merge(lifted, user_axis or {})
    first = members[0][1]
    palette_raw = next(
        (
            (st.get("meta") or {}).get("palette")
            for st, _, _ in members
            if (st.get("meta") or {}).get("palette")
        ),
        None,
    )
    palette = parse_palette(palette_raw, registry=ctx.palettes) if palette_raw else None
    if palette is None and "colorscale" not in user:
        palette = next(
            (default_palette(b.color_da) for _, b, _ in members if b.color_da is not None), None
        )
    values = np.concatenate([np.ravel(v) for _, b, _ in members for v in b.color_values])
    finite = values[np.isfinite(values)]
    stretch = "cmin" in user or "cmax" in user
    axis = {"colorbar": {"title": {"text": first.color_title or ""}}}
    if palette and palette.get("bounds") and not stretch and "colorscale" not in user:
        for _, bound, traces in members:
            for tr in traces:
                raw = _get_path(tr, bound.color_key)
                slots, scale = discretize(raw, palette)
                _set_path(tr, bound.color_key, slots)
        _, scale = discretize(finite, palette)
        axis.update(colorscale=scale["colorscale"], cmin=scale["cmin"], cmax=scale["cmax"])
        axis["colorbar"].update(tickvals=scale["tickvals"], ticktext=scale["ticktext"])
        n_slots = len(scale["colorscale"]) // 2
        for tr in contour_traces:
            tr.setdefault("autocontour", False)
            fill_defaults(tr, {"contours": {"start": 0.5, "end": n_slots - 1.5, "size": 1}})
        return axis
    if palette:
        axis["colorscale"] = continuous_colorscale(palette["colors"])
    elif first.default_colorscale:
        axis["colorscale"] = first.default_colorscale
    lo = float(finite.min()) if finite.size else 0.0
    hi = float(finite.max()) if finite.size else 1.0
    diverging = lo < 0 < hi and not stretch
    if "colorscale" not in axis and "colorscale" not in user:
        axis["colorscale"] = "RdBu_r" if diverging else continuous_colorscale(DEFAULT_SEQUENTIAL)
    if diverging:
        m = max(abs(lo), abs(hi))
        lo, hi = -m, m
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    axis.setdefault("cmin", lo)
    axis.setdefault("cmax", hi)
    return axis


# ------------------------------------------------------------------- map figure


def _anchor(trace: dict) -> int:
    raw = trace.get("xaxis") or "x"
    try:
        return int(raw[1:] or 1)
    except ValueError:
        raise UsageError(f"trace xaxis {raw!r} must look like x, x2, x3 …") from None


def _input_label(ctx, trace):
    from pathlib import Path

    from weather_skills_core.decorator import INPUT_PATH_ATTR

    if trace.get("name"):
        return str(trace["name"])
    source = (trace.get("meta") or {}).get("source") or {}
    ds = ctx.datasets.get(str(source.get("input"))) if source.get("input") else None
    path = getattr(ds, "attrs", {}).get(INPUT_PATH_ATTR) if ds is not None else None
    return Path(path).stem if path else None


def _assemble_map(items, user_layout, lmeta, ctx, font):
    groups: dict[int, list] = {}
    for item in items:
        groups.setdefault(_anchor(item[1]), []).append(item)
    order = sorted(groups)
    plan = []  # per group: list of panel keys (None for an unfaceted group)
    for g in order:
        faceted = [
            b for _, _, b in groups[g] if b is not None and not b.static and len(b.panels) > 1
        ]
        if faceted:
            keys = [p.key for p in faceted[0].panels]
            for b in faceted[1:]:
                have = {_key(p.key) for p in b.panels}
                keys = [k for k in keys if _key(k) in have]
            if not keys:
                raise UsageError(
                    "layered traces share no time/step values to draw together; select one "
                    "time per layer (meta.source.isel / sel), or reduce it (meta.source.reduce)"
                )
            plan.append(keys)
        else:
            plan.append([None])
    if len(order) > 1 and any(len(keys) > 1 for keys in plan):
        raise UsageError(
            "side-by-side map traces (different xaxis) must each already be a single map; "
            "select one time/step per input (meta.source.isel / sel) or aggregate first"
        )
    panels = []  # (group index or None for an empty cell, key)
    if len(order) > 1:
        # Unfaceted side-by-side traces keep their axis number as their cell,
        # so x, x2, x4 leaves cell 3 empty.
        panels = [
            (order.index(a), None) if a in order else (None, None) for a in range(1, order[-1] + 1)
        ]
    else:
        panels = [(0, k) for k in plan[0]]
    n = len(panels)
    grid_in = user_layout.pop("grid", None) or {}
    rows, cols = grid_shape(n, grid_in.get("rows"), grid_in.get("columns"))

    # Bind results per panel.
    panel_traces = [[] for _ in range(n)]  # (rank, trace dict, spec_trace, bound)
    panel_titles = [None] * n
    extents = [None] * n
    for p, (gi, key) in enumerate(panels):
        if gi is None:
            continue
        g = order[gi]
        for i, spec_trace, bound in groups[g]:
            uid = spec_trace.get("uid") or f"trace{i}"
            if bound is None:
                tr = copy.deepcopy(
                    {k: v for k, v in spec_trace.items() if k not in ("xaxis", "yaxis")}
                )
                tr["uid"] = safe_uid(f"{uid}-p{p + 1}" if n > 1 else uid)
                panel_traces[p].append((_MAP_RANK[None], tr, spec_trace, None))
                continue
            if len(bound.panels) == 1:
                part = bound.panels[0]
            else:
                part = next(pp for pp in bound.panels if _key(pp.key) == _key(key))
            if part.title and panel_titles[p] is None:
                panel_titles[p] = part.title
            if not bound.static and bound.extent and extents[p] is None:
                extents[p] = bound.extent
            pid = f"{uid}-p{p + 1}" if n > 1 else uid
            for j, gen in enumerate(part.traces):
                tr = _concrete(spec_trace, gen, pid if j == 0 else f"{pid}-{j}")
                panel_traces[p].append((_MAP_RANK[bind_of(spec_trace)], tr, spec_trace, bound))
        if extents[p] is None:
            extents[p] = next(
                (b.extent for _, _, b in groups[g] if b is not None and b.extent), None
            )
        if extents[p] is None:
            raise UsageError("a map panel has no data extent; set layout.meta.geo.bbox")
    if len(order) > 1:
        # Side by side, a panel is named for its dataset (trace name, else file name).
        for p, (gi, _) in enumerate(panels):
            if gi is None:
                continue
            bound_items = [
                (t, b) for _, t, b in groups[order[gi]] if b is not None and not b.static
            ]
            if bound_items:
                panel_titles[p] = _input_label(ctx, bound_items[0][0]) or panel_titles[p]

    # Color axes: explicit coloraxis wins; else same color title on one group shares.
    axis_of = {}  # id(spec_trace) -> coloraxis name
    axis_members: dict[str, list] = {}
    next_axis = 1
    auto = {}
    for g in order:
        for _, spec_trace, bound in groups[g]:
            if bound is None or not bound.color_values:
                continue
            name = (
                spec_trace.get("coloraxis")
                if bound.color_key == "z"
                else (spec_trace.get("marker") or {}).get("coloraxis")
            )
            if not name:
                key = (g, bound.color_title)
                name = auto.get(key)
                if name is None:
                    name = "coloraxis" if next_axis == 1 else f"coloraxis{next_axis}"
                    next_axis += 1
                    auto[key] = name
            axis_of[id(spec_trace)] = name
    for p in range(n):
        for _, tr, spec_trace, bound in panel_traces[p]:
            if bound is None or id(spec_trace) not in axis_of:
                continue
            name = axis_of[id(spec_trace)]
            if bound.color_key == "z" and "z" in tr:
                tr["coloraxis"] = name
            elif bound.color_key == "marker.color" and "color" in (tr.get("marker") or {}):
                tr["marker"]["coloraxis"] = name
            else:
                continue
            members = axis_members.setdefault(name, [])
            entry = next((m for m in members if m[0] is spec_trace), None)
            if entry is None:
                members.append((spec_trace, bound, [tr]))
            else:
                entry[2].append(tr)
    # Which panels each axis covers, for colorbar placement.
    covers = {
        name: sorted(
            {p for p in range(n) for _, tr, st, _ in panel_traces[p] if axis_of.get(id(st)) == name}
        )
        for name in axis_members
    }
    right_bars = [0] * n
    bottom = []
    placement = {}
    for name in axis_members:
        if (user_layout.get(name) or {}).get("showscale") is False:
            continue
        ps = covers[name]
        # One panel: every colorbar stacks outward on its right. Several panels:
        # a scale shared by all of them goes underneath, the rest beside their panel.
        if len(ps) == n and n > 1:
            placement[name] = ("bottom", len(bottom))
            bottom.append(name)
        else:
            last = ps[-1]
            placement[name] = ("right", last, right_bars[last])
            right_bars[last] += 1
    xgap, ygap = grid_in.get("xgap"), grid_in.get("ygap")
    has_title = bool(
        ((user_layout.get("title") or {}).get("text"))
        if isinstance(user_layout.get("title"), dict)
        else user_layout.get("title")
    )
    user_titles = [
        a
        for a in (user_layout.get("annotations") or [])
        if str(a.get("name", "")).startswith("panel-title-")
    ]
    aspect = float(np.median([(e[1] - e[0]) / max(e[3] - e[2], 1e-6) for e in extents if e]))
    grid = map_grid(
        n,
        rows,
        cols,
        aspect,
        font=font,
        has_title=has_title,
        has_panel_titles=any(panel_titles) or bool(user_titles),
        right_bars=right_bars,
        bottom_bars=len(bottom),
        width=user_layout.get("width"),
        height=user_layout.get("height"),
        xgap=xgap,
        ygap=ygap,
    )
    layout = {
        "width": grid["width"],
        "height": grid["height"],
        "margin": grid["margin"],
        "showlegend": False,
        "annotations": [],
    }
    for p in range(n):
        s = axis_suffix(p)
        if extents[p] is None:
            xd, yd = grid["domains"][p]
            # An empty cell keeps a bare axis so annotations can still target it.
            bare = {
                "showline": False,
                "showgrid": False,
                "zeroline": False,
                "showticklabels": False,
                "ticks": "",
                "fixedrange": True,
            }
            layout[f"xaxis{s}"] = {**bare, "domain": xd, "anchor": f"y{s}"}
            layout[f"yaxis{s}"] = {**bare, "domain": yd, "anchor": f"x{s}"}
            continue
        layout[f"xaxis{s}"], layout[f"yaxis{s}"] = map_axes(grid, p, extents[p])
        if panel_titles[p]:
            layout["annotations"].append(panel_title(p, panel_titles[p], font))
    for name, members in axis_members.items():
        contours = [tr for _, b, trs in members for tr in trs if tr.get("type") == "contour"]
        for tr in contours:
            fill_defaults(
                tr, {"contours": {"coloring": "fill"}, "line": {"color": "black", "width": 0.5}}
            )
        axis = _resolve_coloraxis(
            name, members, user_layout.get(name), ctx, contour_traces=contours
        )
        where = placement.get(name)
        if where is None:
            axis["showscale"] = False
        elif where[0] == "bottom":
            fill_defaults(axis["colorbar"], colorbar_bottom(grid, where[1]))
        else:
            fill_defaults(axis["colorbar"], colorbar_right_of(grid, where[1], where[2]))
        lifted = {}
        for spec_trace, bound, _ in members:
            lifted = deep_merge(lifted, _lift_color(spec_trace, bound.color_key))
        layout[name] = deep_merge(axis, lifted)

    # Overlays, then assemble each panel's traces in draw order.
    settings = overlay_settings(lmeta.get("overlays"))
    data = []
    for p in range(n):
        s = axis_suffix(p)
        if extents[p] is None:
            # plotly.js only builds axes a trace uses; keep the empty cell's axis alive.
            data.append(
                {
                    "type": "scatter",
                    "x": [None],
                    "y": [None],
                    "xaxis": f"x{s}",
                    "yaxis": f"y{s}",
                    "hoverinfo": "skip",
                    "showlegend": False,
                    "uid": f"empty-p{p + 1}",
                }
            )
            continue
        for name, geoms in overlay_geoms(extents[p], settings):
            xs, ys = geoms_to_xy(geoms, rings_only=name == "lakes")
            style = copy.deepcopy(OVERLAY_STYLES[name])
            if isinstance(settings.get(name), dict):
                style = deep_merge(style, settings[name])
            tr = {
                "type": "scatter",
                "mode": "lines",
                "x": xs,
                "y": ys,
                "hoverinfo": "skip",
                "showlegend": False,
                "uid": f"overlay-{name}-{p + 1}",
                **style,
            }
            panel_traces[p].append((_MAP_RANK["overlay"], tr, None, None))
        for _, tr, _, _ in sorted(panel_traces[p], key=lambda item: item[0]):
            tr["xaxis"], tr["yaxis"] = f"x{s}", f"y{s}"
            data.append(tr)
    return data, layout


def _key(value):
    arr = np.asarray(value)
    if arr.dtype.kind in "Mm":
        return int(
            arr.astype("datetime64[ns]" if arr.dtype.kind == "M" else "timedelta64[ns]").astype(
                "int64"
            )
        )
    return str(value)


# ----------------------------------------------------------------- chart figure


def _assemble_chart(items, user_layout, font):
    grid = user_layout.get("grid") or {}
    cells = (grid.get("rows") or 1) * (grid.get("columns") or 1)
    explicit = any(t.get("xaxis") or t.get("yaxis") for _, t, _ in items)
    coupled = grid.get("pattern") == "coupled"
    data = []
    layout = {"width": CHART_SIZE[0], "height": CHART_SIZE[1]}
    axis_titles: dict[str, dict] = {}
    n_legend = 0
    for k, (i, spec_trace, bound) in enumerate(items):
        uid = spec_trace.get("uid") or f"trace{i}"
        xa, ya = spec_trace.get("xaxis") or "x", spec_trace.get("yaxis") or "y"
        if cells > 1 and not explicit and k < cells:
            xa = "x" if coupled and grid.get("columns", 1) == 1 else f"x{axis_suffix(k)}"
            ya = f"y{axis_suffix(k)}"
        if bound is None:
            tr = copy.deepcopy(spec_trace)
            tr["uid"] = safe_uid(uid)
            data.append(tr)
            continue
        for j, gen in enumerate(bound.panels[0].traces):
            tr = _concrete(spec_trace, gen, uid if j == 0 else f"{uid}-{j}")
            if tr.get("type") != "barpolar":
                tr["xaxis"], tr["yaxis"] = xa, ya
            if tr.get("showlegend") is not False:
                n_legend += 1
            data.append(tr)
        layout = deep_merge(layout, bound.layout)
        xs, ys = xa[1:], ya[1:]
        if bound.axis_titles.get("x") is not None:
            axis_titles.setdefault(f"xaxis{xs}", {"title": {"text": bound.axis_titles["x"]}})
        if bound.axis_titles.get("y") is not None:
            axis_titles.setdefault(f"yaxis{ys}", {"title": {"text": bound.axis_titles["y"]}})
        if bound.x_is_date:
            axis_titles.setdefault(f"xaxis{xs}", {}).setdefault("tickformat", "%-d %b '%y")
        if bound.title:
            layout.setdefault("title", {"text": bound.title})
    layout.update(axis_titles)
    if cells > 1 and grid.get("rows", 1) > 1:
        layout["height"] = max(CHART_SIZE[1], 300 * grid["rows"])
    if n_legend > 1 and "polar" not in layout:
        layout["legend"] = {
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": -0.15,
            "yanchor": "top",
        }
    if "polar" in layout:
        layout["width"], layout["height"] = 850, 700
    return data, layout
