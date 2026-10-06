"""The spec reference printed after the flags in ``--help``.

Every key outside ``meta`` is standard Plotly and documented at
https://plotly.com/python/reference/. This page covers the ``meta`` keys
(generated from the validator's key lists) and recipes for common edits.
"""

from __future__ import annotations

import argparse

from weather_skills_plotting import spec

_BINDS = {
    "field": "lat/lon grid → z of a heatmap or contour (default for those types); panels the time/step dim",
    "speed": "wind speed from u/v → heatmap or contour (pair with an arrows trace for a quiver map)",
    "arrows": "u/v wind arrows on a map → scatter lines; meta.arrows.step / .scale",
    "points": "station_id / point_id values → colored scatter markers on a map",
    "geojson": "GeoJSON boundary → scatter lines (meta.source.geojson); repeats on every panel",
    "series": "1-D along time or step → scatter / bar (default for those types)",
    "pair": "one series against another → scatter (meta.x, meta.y, meta.pair_on)",
    "samples": "values at a point per step → box (all samples) or scatter (the mean)",
    "windrose": "u/v pooled into a polar wind rose → barpolar (default for that type)",
}

_META = {
    "bind": "how the trace's arrays are filled; see BINDS",
    "source": "the data: {input, variable, isel, sel, reduce, u, v, geojson, mask_geojson, point}",
    "x / y": "pair only: a source each for the x and the y series",
    "pair_on": "pair only: time (default), year, or index",
    "facet": "dim to panel (default: step or time when present); false for none",
    "along": "series: dim drawn as one line per value (e.g. number for spaghetti)",
    "along_color": "same (default; one color, one legend entry) or cycle",
    "band": "series with along: percentile pair such as [10, 90], shaded with the mean",
    "align": "series: dayofyear overlays years on one seasonal axis",
    "palette": "class palette name (ppt_week, ppt_anom_month, spi, …), color list, or "
    "{colors, bounds, under, over}; precipitation gets one automatically",
    "arrows": "arrows only: {step: thin to every Nth cell, scale: degrees per unit speed}",
}

_SOURCE = {
    "input": "input id: a, b, … in -i order (x / y for --x / --y; obs, forecast1 … for plot-verify)",
    "variable": "data variable (default: auto-detected)",
    "isel": 'positions to select, e.g. {"number": 0, "step": [0, 1]}',
    "sel": 'labels to select (nearest for numbers and dates), e.g. {"time": "2026-09-21"}',
    "reduce": 'dims to average, e.g. ["latitude", "longitude"]; nothing is averaged silently',
    "u / v": "wind component variables (default: auto-detected u10/v10, eastward/northward …)",
    "geojson": "geojson bind: path to the boundary file",
    "mask_geojson": "blank cells outside this polygon for this trace only",
    "point": 'samples bind: {"lat": …, "lon": …}, nearest grid cell',
}

_LAYOUT_META = {
    "inputs": "{id: path} — opened when no file flag is passed (written by --dump-spec)",
    "geo.bbox": "[N, W, S, E] map window; subsets every input. Named places: run resolve-region",
    "geo.mask_geojson": "blank every map cell outside this polygon (does not draw it)",
    "geo.point": '{"lat": …, "lon": …} for samples traces (plot-mediogram); nearest cell',
    "overlays": "true, false, or {coastline|borders|lakes|rivers|admin1: false or a scatter "
    'style such as {"line": {"width": 2}}}',
    "export.scale": "PNG/JPG pixel multiplier (default 2)",
    "version / skill": "leave as dumped",
}

_RECIPES = [
    ("Title and font size", '{"layout": {"title": {"text": "Week 1"}, "font": {"size": 20}}}'),
    ("Contour instead of heatmap", '{"data": [{"uid": "a", "type": "contour"}]}'),
    (
        "Color limits and colorscale (continuous)",
        '{"data": [{"uid": "a", "zmin": 0, "zmax": 50, "colorscale": "YlGnBu"}]}',
    ),
    ("Class palette", '{"data": [{"uid": "a", "meta": {"palette": "ppt_month"}}]}'),
    (
        "Colorbar label and ticks",
        '{"layout": {"coloraxis": {"colorbar": {"title": {"text": "Rain [mm]"}, "len": 0.5}}}}',
    ),
    (
        "Grid shape and extra gaps (fractions of a panel)",
        '{"layout": {"grid": {"rows": 2, "columns": 3, "xgap": 0.3, "ygap": 0.2}}}',
    ),
    ("Rename panel 2", '{"layout": {"annotations": [{"name": "panel-title-2", "text": "ECMWF"}]}}'),
    ("Map window", '{"layout": {"meta": {"geo": {"bbox": [5, 33.5, -5, 42]}}}}'),
    ("Base-map layers", '{"layout": {"meta": {"overlays": {"rivers": false, "admin1": true}}}}'),
    (
        "One shared colorbar for two side-by-side maps",
        '{"data": [{"uid": "a", "coloraxis": "coloraxis"}, {"uid": "b", "coloraxis": "coloraxis"}]}',
    ),
    (
        "Boundary outline",
        '{"data": [{"uid": "kenya", "type": "scatter", "meta": {"bind": "geojson", '
        '"source": {"geojson": "kenya.geojson"}}, "line": {"width": 3}}]}',
    ),
    (
        "City markers (a plain Plotly trace; repeats on every map panel)",
        '{"data": [{"uid": "cities", "type": "scatter", "mode": "markers+text", "x": [36.82], '
        '"y": [-1.29], "text": ["Nairobi"], "textposition": "top right"}]}',
    ),
    (
        "Box outline on the map",
        '{"data": [{"uid": "box", "type": "scatter", "mode": "lines", "x": [34, 42, 42, 34, 34], '
        '"y": [-5, -5, 5, 5, -5], "line": {"color": "red"}}]}',
    ),
    (
        "Wind quiver map",
        '{"data": [{"uid": "a", "meta": {"bind": "speed"}}, {"uid": "wind", "type": "scatter", '
        '"meta": {"bind": "arrows", "source": {"input": "a"}, "arrows": {"step": 2}}}]}',
    ),
    ("Wind rose", '{"data": [{"uid": "a", "type": "barpolar"}]}'),
    (
        "Area-mean time series of a grid",
        '{"data": [{"uid": "a", "type": "scatter", "meta": {"bind": "series", '
        '"source": {"reduce": ["latitude", "longitude"]}}}]}',
    ),
    (
        "Ensemble spaghetti with a 10–90% band",
        '{"data": [{"uid": "a", "meta": {"along": "number", "band": [10, 90]}}]}',
    ),
    (
        "Bars instead of lines; stacked",
        '{"data": [{"uid": "a", "type": "bar"}], "layout": {"barmode": "stack"}}',
    ),
    (
        "Second series on a right-hand axis",
        '{"data": [{"uid": "b", "yaxis": "y2"}], "layout": {"yaxis2": {"overlaying": "y", "side": "right"}}}',
    ),
    (
        "One stacked panel per series",
        '{"layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}',
    ),
    (
        "Text label on panel 1",
        '{"layout": {"annotations": [{"text": "Onset", "xref": "x domain", "yref": "y domain", '
        '"x": 0.5, "y": 0.03, "showarrow": false, "bgcolor": "white"}]}}',
    ),
    (
        "Shaded period on a time axis",
        '{"layout": {"shapes": [{"type": "rect", "xref": "x", "yref": "y domain", '
        '"x0": "2026-10-01", "x1": "2026-10-10", "y0": 0, "y1": 1, "fillcolor": "grey", '
        '"opacity": 0.2, "line": {"width": 0}}]}}',
    ),
]


def _block(title: str, rows: dict) -> str:
    width = max(len(k) for k in rows) + 2
    lines = [title]
    lines += [f"  {k.ljust(width)}{v}" for k, v in rows.items()]
    return "\n".join(lines)


def spec_reference() -> str:
    """Plain-text reference appended to ``--help``."""
    parts = [
        "PLOT SPEC (--spec)",
        '  A standard Plotly figure: {"data": [traces], "layout": {…}}. Every key is Plotly\'s',
        "  (https://plotly.com/python/reference/) except meta, which holds the dataset bindings.",
        "  --spec is merged onto the figure the command builds from its files: data[] by uid",
        "  (else position; a new uid adds a trace), layout.annotations / shapes by name, and",
        "  everything else deep-merged. Run with --dump-spec - to see that figure, edit, pass back.",
        "  Output by -o suffix: .png, .jpg, or .html (interactive, works offline).",
        "",
        "  Panels: map traces on the same xaxis stack as layers; traces on x, x2, … sit side by",
        "  side, each on its own lat/lon grid (do not coarsen to plot). One trace with a time or",
        "  step dim gets one panel per value. Panel titles are annotations named panel-title-N.",
        "",
        _block("BINDS (data[].meta.bind)", _BINDS),
        "",
        _block("data[].meta", {**{k: _META[k] for k in _META}}),
        "  (keys: " + ", ".join(sorted(spec.TRACE_META_KEYS)) + ")",
        "",
        _block("data[].meta.source", _SOURCE),
        "",
        _block("layout.meta", _LAYOUT_META),
        "",
        "RECIPES (each is a complete --spec)",
    ]
    for title, example in _RECIPES:
        parts += [f"  {title}:", f"    {example}"]
    return "\n".join(parts)


def install_spec_help(skill) -> None:
    """Append the spec reference to a skill's ``--help``."""
    parser = skill.parser
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = f"{spec_reference()}\n\n{parser.epilog or ''}".rstrip()
