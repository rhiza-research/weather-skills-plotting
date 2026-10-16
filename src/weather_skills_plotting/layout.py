"""Plotly templates and map-panel helpers.

Charts keep Plotly's layout. Maps do not: Plotly's default canvas and grid
cells know nothing about a map's shape, so equal-degree maps float small in
mostly empty cells. ``map_layout`` instead sizes each panel from the map's
lon/lat aspect, adds fixed pixel room for titles, tick labels and colorbars,
and places every panel with an explicit axis domain.
"""

from __future__ import annotations

import copy
import math

import numpy as np
from weather_skills_core.errors import UsageError

from weather_skills_plotting.palettes import COLORBLIND, default_theme

DEFAULT_TEMPLATE = "weather_skills"


def register_templates(template: dict | None = None) -> None:
    """``weather_skills`` and ``colorblind``: Plotly's ``seaborn`` with the theme's template.

    ``template`` is the theme's (``themes/default.json`` when None).
    ``colorblind`` keeps its own colorway, since picking it is an accessibility choice.
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    if template is None:
        template = default_theme()["template"]
    for name in ("weather_skills", "colorblind"):
        base = copy.deepcopy(pio.templates["seaborn"])
        try:
            base.update(go.layout.Template(template))
        except ValueError as exc:
            from weather_skills_plotting.spec import plotly_error

            raise plotly_error(exc, "theme file template") from None
        if name == "colorblind":
            base.layout.colorway = COLORBLIND
        pio.templates[name] = base


def grid_shape(n, rows=None, columns=None):
    """``(rows, columns)`` for ``n`` panels: a near-square grid unless the user fixes a side."""
    for value, name in ((rows, "rows"), (columns, "columns")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise UsageError(f"layout.grid.{name} must be an integer >= 1; got {value!r}")
    if rows is None and columns is None:
        columns = math.ceil(math.sqrt(max(n, 1)))
    if rows is not None and columns is not None:
        if rows * columns < n:
            raise UsageError(
                f"layout.grid {rows} rows × {columns} columns holds {rows * columns} panels, "
                f"but the figure has {n}"
            )
        return rows, columns
    if columns is not None:
        return math.ceil(n / columns) or 1, columns
    return rows, math.ceil(n / rows) or 1


def choose_grid(n: int, aspect: float, rows=None, columns=None) -> tuple[int, int]:
    """``(rows, columns)`` for ``n`` map panels of lon/lat ``aspect``.

    Picks the grid whose overall shape is closest to a 1.6:1 landscape page,
    with few empty cells and never a whole empty row. A side the user fixed wins.
    """
    if rows is not None or columns is not None:
        return grid_shape(n, rows, columns)
    best = None
    for cols in range(1, min(n, 6) + 1):
        r = math.ceil(n / cols)
        empty = r * cols - n
        if empty >= cols:
            continue
        cost = abs(math.log(cols * aspect / r / 1.6)) + 0.35 * empty
        if best is None or cost <= best[0]:
            best = (cost, r, cols)
    return best[1], best[2]


# Pixel room around map panels.
MAP_BOX_SINGLE = (760, 560)  # largest map area for a one-panel figure
MAP_BOX_PANEL = (340, 340)  # map area per panel in a grid (width x height of a square map)
PANEL_MAX_H = 420  # tallest grid panel, for maps taller than wide
MAX_PLOT_WIDTH = 1400  # panels shrink so the panel area fits this width
TICK_LEFT = 46  # y tick labels left of each map
TICK_BELOW = 24  # x tick labels under each map
PANEL_TITLE = 24  # panel title above each map
FIGURE_TITLE = 50
COLORBAR_RIGHT = 110  # a vertical colorbar with its title turned along it
COLORBAR_BELOW = 80  # a row of horizontal colorbars
SEAL_CLEAR = 0.88  # horizontal colorbars end left of the provenance seal (plot-width fraction)
SEAL_CLEAR_Y = 0.06  # vertical colorbars start above it (plot-height fraction)
WIDE_MAP = 2.5  # a single map wider than this (lon / lat span) gets its colorbar below


def map_layout(
    rows, cols, aspect, *, titled, panel_titles, right=0, below=0, user=None
) -> tuple[dict, list[tuple[float, float, float, float]]]:
    """Canvas, margins and per-panel ``(x0, x1, y0, y1)`` domains for a map grid.

    ``right`` / ``below`` are extra pixels for colorbars. ``user`` is the
    spec layout: its ``width`` / ``height`` fix the canvas (maps shrink to
    fit), and ``grid.xgap`` / ``grid.ygap`` are gaps as a fraction of a panel.
    """
    user = user or {}
    grid = user.get("grid") or {}
    if rows * cols == 1:
        box_w, box_h = MAP_BOX_SINGLE
        w = min(box_w, box_h * aspect)
    else:
        # Same area per panel whatever its shape: a Pacific strip gets width, not a sliver.
        box_w, box_h = MAP_BOX_PANEL
        w = min(MAP_BOX_SINGLE[0], (box_w * box_h * aspect) ** 0.5, PANEL_MAX_H * aspect)
    h = w / aspect
    title_px = PANEL_TITLE if panel_titles else 0
    ml, mr = TICK_LEFT, 16 + right
    mt = (FIGURE_TITLE if titled else 12) + title_px
    mb = TICK_BELOW + 8 + below

    def gaps(w, h):
        gx = grid["xgap"] * w if grid.get("xgap") is not None else TICK_LEFT + 12
        gy = grid["ygap"] * h if grid.get("ygap") is not None else TICK_BELOW + title_px + 12
        return gx, gy

    gx, gy = gaps(w, h)
    avail = MAX_PLOT_WIDTH - (cols - 1) * gx
    if cols * w > avail:
        w = avail / cols
        h = w / aspect
    width, height = user.get("width"), user.get("height")
    if width is not None:
        w = (width - ml - mr - (cols - 1) * gx) / cols
        h = w / aspect
    if height is not None:
        h_fit = (height - mt - mb - (rows - 1) * gy) / rows
        if width is None or h_fit < h:
            h = h_fit
            w = h * aspect
    if w < 20 or h < 20:
        raise UsageError(
            f"layout width/height {width}x{height} leaves no room for {rows}x{cols} map panels"
        )
    gx, gy = gaps(w, h)
    width = width if width is not None else ml + mr + cols * w + (cols - 1) * gx
    height = height if height is not None else mt + mb + rows * h + (rows - 1) * gy
    pw, ph = width - ml - mr, height - mt - mb
    # Centre the block when a fixed canvas leaves spare room.
    ox = (pw - (cols * w + (cols - 1) * gx)) / 2
    oy = (ph - (rows * h + (rows - 1) * gy)) / 2
    domains = []
    for p in range(rows * cols):
        r, c = divmod(p, cols)
        x0 = (ox + c * (w + gx)) / pw
        top = 1 - (oy + r * (h + gy)) / ph
        domains.append(tuple(min(max(v, 0.0), 1.0) for v in (x0, x0 + w / pw, top - h / ph, top)))
    layout = {
        "width": round(width),
        "height": round(height),
        "margin": {"l": ml, "r": mr, "t": mt, "b": mb, "autoexpand": False},
    }
    return layout, domains


def axis_suffix(p: int) -> str:
    """Plotly axis suffix for 0-based panel ``p`` (``""``, ``"2"``, …)."""
    return "" if p == 0 else str(p + 1)


def map_axes(p: int, extent, domain=None) -> tuple[dict, dict]:
    """Lon/lat axes for panel ``p`` over ``extent``, one degree the same length on both."""
    common = {
        "constrain": "domain",
        "showgrid": False,
        "zeroline": False,
        "ticksuffix": "°",
        "ticks": "outside",
    }
    s = axis_suffix(p)
    xaxis = {"range": [extent[0], extent[1]], **common, "anchor": f"y{s}"}
    if extent[1] > 180:
        # A map across the dateline runs on 0..360: label 200 as -160, like every other map.
        span = extent[1] - extent[0]
        step = next(d for d in (1, 2, 5, 10, 20, 30, 45, 60, 90) if span / d <= 8)
        ticks = np.arange(np.ceil(extent[0] / step) * step, extent[1] + 1e-9, step)
        xaxis.update(
            tickmode="array",
            tickvals=[float(t) for t in ticks],
            ticktext=[f"{180 if t % 360 == 180 else (t + 180) % 360 - 180:g}°" for t in ticks],
        )
    yaxis = {
        "range": [extent[2], extent[3]],
        **common,
        "anchor": f"x{s}",
        "scaleanchor": f"x{s}",
        "scaleratio": 1,
    }
    if domain is not None:
        xaxis["domain"] = [domain[0], domain[1]]
        yaxis["domain"] = [domain[2], domain[3]]
    return xaxis, yaxis


def colorbar_mode(panels_of: dict, cols: int) -> str:
    """Where colorbars go: ``right`` (one bar), ``rows`` / ``columns`` (each bar
    beside the rows or under the columns it colours), else ``below``."""
    if len(panels_of) <= 1:
        return "right"
    for mode, key in (("rows", lambda p: p // cols), ("columns", lambda p: p % cols)):
        seen, ok = set(), True
        for panels in panels_of.values():
            band = sorted({key(p) for p in panels})
            if band != list(range(band[0], band[-1] + 1)) or seen & set(band):
                ok = False
                break
            seen |= set(band)
        if ok:
            return mode
    return "below"


def place_colorbars(mode: str, panels_of: dict, domains) -> dict:
    """Colorbar settings per color axis for ``mode`` (see ``colorbar_mode``)."""
    out = {}
    k = len(panels_of)
    for i, (name, panels) in enumerate(panels_of.items()):
        ds = [domains[p] for p in panels]
        if mode in ("right", "rows"):
            y0, y1 = min(d[2] for d in ds), max(d[3] for d in ds)
            # Clear of the provenance seal in the bottom-right corner.
            y0 = max(y0, SEAL_CLEAR_Y)
            out[name] = {
                "len": y1 - y0,
                "y": (y0 + y1) / 2,
                "yanchor": "middle",
                "thickness": 16,
                # Along the bar: a long title laid flat would eat the map's width.
                "title": {"side": "right"},
            }
            continue
        bar = {
            "orientation": "h",
            "y": 0,
            "yref": "container",
            "yanchor": "bottom",
            "thickness": 14,
            "tickangle": 0,
            # Below the bar: beside it squeezes the bar, above it overlaps it.
            "title": {"side": "bottom"},
        }
        if mode == "columns":
            x0, x1 = min(d[0] for d in ds), max(d[1] for d in ds)
        else:
            x0, x1 = i / k, (i + 1) / k
        # The provenance seal sits in the bottom-right corner: bars and their
        # titles stop short of it.
        x1 = min(x1, SEAL_CLEAR)
        bar.update(len=(x1 - x0) * 0.9, x=(x0 + x1) / 2, xanchor="center")
        out[name] = bar
    return out


def panel_title(p: int, text: str) -> dict:
    """Title annotation centred above panel ``p`` (named so a spec can override it)."""
    s = axis_suffix(p)
    return {
        "name": f"panel-title-{p + 1}",
        "text": text,
        "xref": f"x{s} domain",
        "yref": f"y{s} domain",
        "x": 0.5,
        "y": 1,
        "xanchor": "center",
        "yanchor": "bottom",
        "showarrow": False,
    }
