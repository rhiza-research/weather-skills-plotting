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

from weather_skills_core.errors import UsageError

from weather_skills_plotting.palettes import COLORBLIND, DEEP

DEFAULT_TEMPLATE = "weather_skills"


def register_templates(user_template: dict | None = None) -> None:
    """``weather_skills`` and ``colorblind``: Plotly's ``seaborn`` template with a colorway.

    A theme file's ``template`` is layered on top of both.
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    for name, colorway in (("weather_skills", DEEP), ("colorblind", COLORBLIND)):
        base = copy.deepcopy(pio.templates["seaborn"])
        base.layout.colorway = colorway
        if user_template:
            try:
                base.update(go.layout.Template(user_template))
            except ValueError as exc:
                from weather_skills_plotting.spec import plotly_error

                raise plotly_error(exc, "theme file template") from None
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
MAP_BOX_PANEL = (340, 340)  # largest map area per panel in a grid
MAX_PLOT_WIDTH = 1400  # panels shrink so the panel area fits this width
TICK_LEFT = 46  # y tick labels left of each map
TICK_BELOW = 24  # x tick labels under each map
PANEL_TITLE = 24  # panel title above each map
FIGURE_TITLE = 50
COLORBAR_RIGHT = 110  # a vertical colorbar with its title turned along it
COLORBAR_BELOW = 80  # a row of horizontal colorbars


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
    box_w, box_h = MAP_BOX_SINGLE if rows * cols == 1 else MAP_BOX_PANEL
    w = min(box_w, box_h * aspect)
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


def map_size(rows: int, cols: int, aspect: float, width=None, height=None) -> tuple[int, int]:
    """Canvas for a map grid: Plotly's default width per pair of columns, height from the aspect.

    ``aspect`` is a panel's lon span over its lat span. A side the user set is
    kept and the other follows from it. Plotly's margins and grid gaps are not
    counted, so the panels (constrained to equal degrees) may leave a little
    white space rather than be squeezed.
    """
    import plotly.io as pio

    shape = rows / (cols * aspect)
    if width is None and height is not None:
        width = height / shape
    if width is None:
        width = pio.defaults.default_width * max(1.0, cols / 2)
    if height is None:
        height = width * shape
    return round(width), round(height)


def map_axes(p: int, extent, domain=None) -> tuple[dict, dict]:
    """Lon/lat axes for panel ``p`` over ``extent``, one degree the same length on both."""
    common = {"constrain": "domain", "showgrid": False, "ticksuffix": "°", "ticks": "outside"}
    s = axis_suffix(p)
    xaxis = {"range": [extent[0], extent[1]], **common, "anchor": f"y{s}"}
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
            bar.update(len=(x1 - x0) * 0.9, x=(x0 + x1) / 2, xanchor="center")
        else:
            bar.update(len=0.9 / k, x=(i + 0.5) / k, xanchor="center")
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
