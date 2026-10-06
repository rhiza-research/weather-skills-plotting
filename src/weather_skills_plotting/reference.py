"""The plot-spec reference printed by ``--help``.

``--help`` is where an agent learns what the plotting skills can do;
``--dump-spec`` only shows the spec it is about to draw, so it can be edited.
Every key list below comes from the allowlists in ``spec`` / ``figure`` /
``maps``, so a key added there shows up here without a docs edit. A key with
no entry in ``_DESCRIPTIONS`` is still listed, under "also".
"""

from __future__ import annotations

import argparse
import textwrap

from weather_skills_plotting import figure, spec
from weather_skills_plotting.maps import _OUTLINE_LINE_KWARGS

_WIDTH = 100

# Plot kinds a single `plot` call can draw (traces[0].kind).
_PLOT_KINDS = {
    "heatmap": "lon/lat color map; one panel per time or step (default for gridded data)",
    "contour": "filled-contour map; contour.lines: false drops the isolines",
    "quiver": "wind-speed map with u/v arrows (u_variable / v_variable)",
    "scatter": "stations on a map colored by value (needs station_id or point_id)",
    "timeseries": "1D trace along time; reduce leftover dims with traces[0].reduce",
    "xy": "one 1D series against another (--x/--y, or x_variable / y_variable)",
    "windrose": "polar rose of wind direction stacked by speed",
}

_LAYER_KINDS = {
    "heatmap": "gridded Zarr drawn as a color map",
    "scatter": "station Zarr drawn as colored points",
    "quiver": "u/v Zarr drawn as arrows",
    "outline": "GeoJSON boundary edges; style with layers[].line",
    "mask": "GeoJSON polygon; blanks cells outside it (same as geo.mask_geojson)",
}

_DESCRIPTIONS = {
    # top level
    "top.title": "figure title (wraps automatically)",
    "top.subplot_titles": "list of panel titles, in panel order",
    "top.xlabel": "x-axis label",
    "top.ylabel": "y-axis label",
    "top.cbar_label": "colorbar label (default: variable name and units)",
    "top.legend": "legend location: a matplotlib loc, 'outside right', 'below', or 'none'",
    "top.vmin": "lower color limit for every panel",
    "top.vmax": "upper color limit for every panel",
    "top.inputs": "the datasets; see inputs[]",
    "top.traces": "what to draw from each input; see traces[]",
    "top.layers": "stacked map layers from --layer; see layers[]",
    "top.subplots": "per-cell settings for side-by-side maps; see subplots[]",
    "top.layout": "figure size, panel grid, spacing, colorbar; see layout",
    "top.theme": "colormap, font size, matplotlib rc; see theme",
    "top.geo": "map window, masks, cities, boxes; see geo",
    "top.axes": "per-axes matplotlib settings applied after drawing; see axes",
    "top.annotations": "text labels and arrows; see annotations[]",
    "top.shapes": "rectangles, lines, spans, circles; see shapes[]",
    "top.version": "spec version (leave as dumped)",
    "top.skill": "skill name (leave as dumped)",
    "top.weather_skills_history": "provenance (leave as dumped)",
    # inputs[]
    "inputs.id": "id that traces[].input / layers[].input refer to",
    "inputs.path": "Zarr path (when no -i flag is given)",
    "inputs.variable": "data variable to plot",
    "inputs.index": "select along leftover dims, e.g. {'number': 0}",
    "inputs.label": "panel/legend label for this input",
    "inputs.colormap": "colormap for this input only",
    "inputs.vmin": "lower color limit for this input only",
    "inputs.vmax": "upper color limit for this input only",
    "inputs.cbar_label": "colorbar label for this input only",
    # traces[]
    "traces.kind": "what to draw; see KINDS",
    "traces.input": "which inputs[] id this trace reads",
    "traces.alpha": "opacity, for any map kind",
    "traces.reduce": "dims to collapse (mean) for timeseries / xy",
    "traces.along": "dim to fan out as separate lines (e.g. number for spaghetti)",
    "traces.align": "dayofyear overlays years on one seasonal axis (timeseries)",
    "traces.mark": "line or bar (timeseries)",
    "traces.band": "percentile pair, e.g. [10, 90], shaded across an along fan (timeseries)",
    "traces.pair_on": "time, year, or index (xy)",
    "traces.u_variable": "eastward wind variable (windrose / quiver)",
    "traces.v_variable": "northward wind variable (windrose / quiver)",
    "traces.x_variable": "x series variable (xy)",
    "traces.y_variable": "y series variable (xy)",
    # layers[]
    "layers.id": "a, b, c, ... in --layer order; match this to style a layer",
    "layers.variable": "data variable for this layer",
    "layers.colormap": "colormap for this layer",
    "layers.vmin": "lower color limit for this layer",
    "layers.vmax": "upper color limit for this layer",
    "layers.alpha": "opacity for this layer (any kind, including outline)",
    "layers.line": "outline style: {color, linewidth, linestyle, alpha, zorder}",
    "layers.index": "select along leftover dims for this layer",
    # subplots[]
    "subplots.row": "1-based row of the cell",
    "subplots.col": "1-based column of the cell",
    "subplots.title": "cell title",
    "subplots.layers": "layers stacked in this cell",
    "subplots.colorbar": "colorbar style for this cell (same keys as layout.colorbar)",
    # layout
    "layout.figsize": "[width, height] in inches",
    "layout.dpi": "output resolution",
    "layout.facecolor": "figure background color",
    "layout.facet": "panel grid and spacing; see layout.facet",
    "layout.colorbar": "colorbar styling; see layout.colorbar",
    "layout.suptitle": "{y: height of the figure title}",
    "layout.shared_colorscale": "true = one colorbar for every panel; false = never share",
    "layout.bar_mode": "grouped, stacked, or overlay (timeseries bars)",
    "layout.autosize": "size the canvas from the map extent (default true)",
    # layout.facet
    "facet.rows": "panel rows",
    "facet.columns": "panel columns",
    "facet.max_columns": "wrap panels after this many columns (default 4)",
    "facet.wspace": "horizontal gap between panels, fraction of panel width",
    "facet.hspace": "vertical gap between panels, fraction of panel height",
    "facet.per_trace": "one panel per trace (timeseries)",
    # layout.colorbar
    "colorbar.labelsize": "colorbar label font size",
    "colorbar.ticksize": "colorbar tick-label font size",
    "colorbar.labelpad": "points between ticks and label",
    "colorbar.pad": "gap between the map and the colorbar",
    "colorbar.len": "length as a fraction of the axes",
    "colorbar.shrink": "length as a fraction of the axes",
    "colorbar.thickness": "points (> 1) or fraction (<= 1)",
    "colorbar.location": "right, bottom, left, top",
    "colorbar.orientation": "vertical or horizontal",
    "colorbar.extend": "arrows past the ends: neither, min, max, both",
    "colorbar.ticks": "tick positions",
    "colorbar.labels": "tick text (same count as ticks)",
    "colorbar.format": "tick number format",
    # theme
    "theme.fontsize": "base font size; scales titles, labels, ticks, legend together",
    "theme.colormap": "colormap name (default_precip / default_precip_anom for rainfall totals / anomalies), or {colors, bounds} for classes",
    "theme.template": "weather_skills or colorblind",
    "theme.rc": "matplotlib rcParams, e.g. {'axes.titlesize': 20, 'figure.titlesize': 24}",
    # geo
    "geo.bbox": "[N, W, S, E] map window; subsets the data",
    "geo.extent": "[lon_min, lon_max, lat_min, lat_max] map window",
    "geo.mask_geojson": "GeoJSON file path (string); blanks cells outside the polygon",
    "geo.cities": "{'Nairobi': [lat, lon], ...} (or a JSON file path); marks and labels points",
    "geo.draw_boxes": "list of [N, W, S, E] boxes to outline",
    "geo.lat": "point latitude (mediogram / point extraction)",
    "geo.lon": "point longitude (mediogram / point extraction)",
    "geo.overlays": "base-map layers: false = none, or {coastline, borders, lakes, rivers, admin1: true/false}; admin1 defaults on only for country-scale views",
    # annotations[]
    "annotation.text": "the label text (required)",
    "annotation.x": "x position",
    "annotation.y": "y position",
    "annotation.xy": "[x, y] instead of x and y",
    "annotation.xref": "coordinate system for x/y; see COORDINATES",
    "annotation.yref": "same as xref (must match it)",
    "annotation.xycoords": "same as xref (matplotlib spelling)",
    "annotation.panel": "panel index (0-based) or list of indexes; unset = every panel",
    "annotation.axes": "same as panel",
    "annotation.xytext": "[x, y] text position; draws an arrow from the text to x/y",
    "annotation.textcoords": "coordinate system for xytext (e.g. 'axes fraction')",
    "annotation.arrowprops": "arrow style: {arrowstyle, color, linewidth, ...}",
    "annotation.fontsize": "text size",
    "annotation.fontweight": "normal or bold",
    "annotation.color": "text color",
    "annotation.ha": "horizontal alignment: left, center, right",
    "annotation.va": "vertical alignment: top, center, bottom, baseline",
    "annotation.rotation": "degrees",
    "annotation.bbox": "box behind the text: {facecolor, edgecolor, alpha, boxstyle}",
}

_SHAPES = {
    "rect": "x0, x1, y0, y1 (or xy + width + height); fill, edgecolor, facecolor, linewidth, hatch",
    "hline": "y; line style keys (color, linewidth, linestyle, ...)",
    "vline": "x; line style keys",
    "hspan": "ymin, ymax; facecolor, color, alpha",
    "vspan": "xmin, xmax; facecolor, color, alpha",
    "line": "x: [x0, x1], y: [y0, y1] (or x0/x1/y0/y1); line style keys",
    "circle": "x, y (or xy) + radius; edgecolor, facecolor, fill, linewidth",
    "ellipse": "x, y (or xy) + width, height; same style keys as circle",
}

RECIPES = [
    ("Bigger titles and labels", '{"theme": {"fontsize": 22}}'),
    ("Only the panel titles bigger", '{"theme": {"rc": {"axes.titlesize": 22}}}'),
    (
        "Less space between panels",
        '{"layout": {"facet": {"wspace": 0.02, "hspace": 0.05}}}',
    ),
    ("Panel grid", '{"layout": {"facet": {"rows": 1, "columns": 5}}}'),
    ("Wider figure", '{"layout": {"figsize": [22, 7]}}'),
    ("Fixed color range", '{"vmin": 0, "vmax": 100}'),
    (
        "Colorbar at the bottom, larger text",
        '{"layout": {"colorbar": {"location": "bottom", "labelsize": 16, "ticksize": 14}}}',
    ),
    (
        "Label inside the bottom of panel 1",
        '{"annotations": [{"text": "Start of season", "panel": 1, "x": 0.5, "y": 0.03, '
        '"xref": "axes fraction", "ha": "center", "va": "bottom", "fontsize": 16, '
        '"bbox": {"facecolor": "white", "alpha": 0.8}}]}',
    ),
    (
        "Arrow pointing at a lon/lat on every panel",
        '{"annotations": [{"text": "Nairobi", "x": 36.8, "y": -1.3, "xytext": [0.1, 0.9], '
        '"textcoords": "axes fraction", "bbox": {"facecolor": "white"}, '
        '"arrowprops": {"arrowstyle": "->", "color": "black", "linewidth": 1.5}}]}',
    ),
    (
        "Mask to a region and draw its border in black",
        "--layer heatmap:IN.zarr --layer outline:REGION.geojson --spec "
        '\'{"geo": {"mask_geojson": "REGION.geojson"}, '
        '"layers": [{"id": "b", "line": {"color": "black", "linewidth": 2.5}}]}\'',
    ),
    ("Hide rivers on the base map", '{"geo": {"overlays": {"rivers": false}}}'),
    (
        "Box around an area",
        '{"shapes": [{"type": "rect", "x0": 36, "x1": 38, "y0": -2, "y1": 0, '
        '"edgecolor": "red", "linewidth": 2}]}',
    ),
]


def _wrap(text: str, indent: str = "  ", hang: str = "      ") -> str:
    return textwrap.fill(
        text, width=_WIDTH, initial_indent=indent, subsequent_indent=hang, break_on_hyphens=False
    )


def _section(title: str, keys, prefix: str, intro: str = "") -> list[str]:
    """Described keys one per line, then the rest as an "also" list."""
    lines = ["", title]
    if intro:
        lines.append(_wrap(intro, hang="  "))
    described, rest = [], []
    for key in sorted(keys):
        desc = _DESCRIPTIONS.get(f"{prefix}.{key}")
        (described if desc else rest).append((key, desc))
    width = max((len(k) for k, _ in described), default=0)
    for key, desc in described:
        lines.append(_wrap(f"{key.ljust(width)}  {desc}", hang="  " + " " * (width + 2)))
    if rest:
        lines.append(_wrap("also: " + ", ".join(k for k, _ in rest), hang="        "))
    return lines


def _named(title: str, items: dict, intro: str = "") -> list[str]:
    lines = ["", title]
    if intro:
        lines.append(_wrap(intro, hang="  "))
    width = max(len(k) for k in items)
    for key, desc in items.items():
        lines.append(_wrap(f"{key.ljust(width)}  {desc}", hang="  " + " " * (width + 2)))
    return lines


def spec_reference(*, kinds: bool = True) -> str:
    """Every plot-spec feature, for the end of ``--help``."""
    out = [
        "PLOT SPEC REFERENCE",
        _wrap(
            "Name files on the command line; every other choice is a JSON key in --spec "
            "(inline or a file path), deep-merged onto the defaults. An unknown key is an "
            "error that lists the valid keys at that level. To change an existing figure, "
            "run the same command with --dump-spec - in place of --spec, edit that JSON, "
            "and pass it back as --spec.",
            hang="  ",
        ),
    ]
    if kinds:
        out += _named("KINDS (traces[0].kind)", _PLOT_KINDS)
        out += _named(
            "LAYERS (--layer KIND:PATH)",
            _LAYER_KINDS,
            intro="Stacks several inputs on one map. Style each on the layers[] entry whose "
            "id matches (a, b, c, ... in --layer order).",
        )
    out += _section("TOP-LEVEL KEYS", spec.TOP_KEYS, "top")
    out += _section("inputs[]", spec.INPUT_KEYS, "inputs")
    out += _section(
        "traces[]",
        spec.TRACE_KEYS - spec.ARTIST_BLOCKS,
        "traces",
        intro="Artist blocks (line, mesh, contour, ...) also go here; see ARTIST BLOCKS.",
    )
    out += _section(
        "layers[]",
        spec.LAYER_KEYS - (spec.ARTIST_BLOCKS - {"line"}),
        "layers",
        intro="Other artist blocks (mesh, scatter, quiver, ...) also go here.",
    )
    out += _section("subplots[]", spec.SUBPLOT_KEYS, "subplots")
    out += _section("layout", spec.LAYOUT_KEYS, "layout")
    out += _section("layout.facet", spec.FACET_KEYS, "facet")
    out += _section("layout.colorbar", spec.COLORBAR_KEYS, "colorbar")
    out += _section(
        "theme",
        spec.THEME_KEYS,
        "theme",
        intro="Useful theme.rc keys: axes.titlesize (panel titles), figure.titlesize, "
        "axes.labelsize, xtick.labelsize, ytick.labelsize, legend.fontsize, font.family, "
        "axes.titleweight, axes.titlepad.",
    )
    out += _section(
        "geo",
        spec.GEO_KEYS,
        "geo",
        intro="Coordinates only. For a named country or region, run resolve-region first and "
        "pass its bbox (geo.bbox) or polygon (geo.mask_geojson).",
    )
    out += _section(
        "axes",
        figure.AXES_TEMPLATE,
        "axes",
        intro="An object (every panel) or a list (one per panel). Applied after drawing.",
    )
    out += _section(
        "annotations[]",
        figure.ANNOTATION_KEYS,
        "annotation",
        intro="Text on the figure. Without xytext it is a plain label; with xytext and "
        "arrowprops it is an arrow from the text to x/y.",
    )
    out += [
        "",
        "COORDINATES (annotations xref / yref / xycoords)",
        "  data (default)     x/y in data units; lon/lat on a map",
        "  axes fraction      0-1 across the panel (also: axes, paper, domain)",
        "  figure fraction    0-1 across the whole figure (also: figure)",
    ]
    out += _named(
        "shapes[] (type: ...)",
        _SHAPES,
        intro="Data coordinates (lon/lat on a map). Same panel rule as annotations. Unset type "
        "is rect. Keys not listed for a type are an error.",
    )
    out += ["", "ARTIST BLOCKS (on traces[] or layers[])"]
    blocks = {
        "line": figure.LINE_KEYS,
        "mesh": figure.MESH_KEYS,
        "contour": figure.CONTOUR_KEYS,
        "scatter": figure.SCATTER_KEYS,
        "bar": figure.BAR_KEYS,
        "quiver": figure.QUIVER_KEYS,
        "windrose": figure.WINDROSE_KEYS,
        "fill": figure.FILL_KEYS,
        "box": figure.BOX_KEYS,
    }
    for name, keys in blocks.items():
        out.append(_wrap(f"{name}: " + ", ".join(sorted(keys)), hang="      "))
    out.append(
        _wrap(
            "An outline layer's line block takes only: " + ", ".join(sorted(_OUTLINE_LINE_KWARGS)),
            hang="      ",
        )
    )
    out += ["", "RECIPES (--spec values)"]
    for label, value in RECIPES:
        out.append(f"  {label}:")
        out.append(f"      {value}")
    return "\n".join(out)


def install_spec_help(skill, *, kinds: bool = True) -> None:
    """Append the spec reference to a skill's ``--help`` without rewrapping it."""
    parser = skill.parser
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = f"{spec_reference(kinds=kinds)}\n\n{parser.epilog or ''}".rstrip()
