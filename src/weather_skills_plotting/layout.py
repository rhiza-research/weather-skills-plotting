"""Plotly templates and map-panel helpers.

Charts keep Plotly's layout. Maps size the canvas from the map's lon/lat
aspect, so equal-degree maps fill it, and place every panel with an explicit
axis domain. Plotly still grows the margins to fit tick labels, titles and
colorbars.
"""

from __future__ import annotations

import copy
import math

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


# Largest map area, in pixels, for one panel alone and per panel in a grid.
MAP_BOX_SINGLE = (760, 560)
MAP_BOX_PANEL = (340, 340)
MAX_PLOT_WIDTH = 1400  # panels shrink so the panel area fits this width
# Room around map panels, in multiples of the font size. This only sizes the
# canvas and the gaps between panels: Plotly grows the outer margins itself
# (autoexpand) when tick labels, titles or colorbars need more.
TICK_ROOM = 4  # y tick labels left of a map, such as "-10°"
LINE = 2  # one line of text: x tick labels, a panel title, the figure title
COLORBAR_ROOM = 8  # a colorbar with its title


def font_size(user: dict | None) -> float:
    """The figure's font size: the spec's, else the template's, else Plotly's 12."""
    import plotly.io as pio

    user = user or {}
    size = (user.get("font") or {}).get("size")
    template = user.get("template", DEFAULT_TEMPLATE)
    if size is None and isinstance(template, str) and template in pio.templates:
        size = pio.templates[template].layout.font.size
    elif size is None and isinstance(template, dict):
        size = ((template.get("layout") or {}).get("font") or {}).get("size")
    return float(size or 12)


def map_layout(
    rows, cols, aspect, *, titled, panel_titles, right=False, below=False, below_lines=0, user=None
) -> tuple[dict, list[tuple[float, float, float, float]]]:
    """Canvas, margins and per-panel ``(x0, x1, y0, y1)`` domains for a map grid.

    ``right`` / ``below`` say a colorbar stands there; ``below_lines`` is more
    room under the maps, in lines of text. ``user`` is the spec layout: its
    ``width`` / ``height`` fix the canvas (maps shrink to fit), and
    ``grid.xgap`` / ``grid.ygap`` are gaps as a fraction of a panel.
    """
    user = user or {}
    grid = user.get("grid") or {}
    em = font_size(user)
    box_w, box_h = MAP_BOX_SINGLE if rows * cols == 1 else MAP_BOX_PANEL
    w = min(box_w, box_h * aspect)
    h = w / aspect
    title_lines = LINE if panel_titles else 0
    ml = TICK_ROOM * em
    mr = (COLORBAR_ROOM if right else 1) * em
    mt = ((LINE if titled else 0) + title_lines + 1) * em
    mb = (LINE + (COLORBAR_ROOM if below else 0) + below_lines) * em

    def gaps(w, h):
        gx = grid["xgap"] * w if grid.get("xgap") is not None else (TICK_ROOM + 1) * em
        gy = grid["ygap"] * h if grid.get("ygap") is not None else (LINE + title_lines + 1) * em
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
        "margin": {"l": round(ml), "r": round(mr), "t": round(mt), "b": round(mb)},
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
        # Tick labels push the figure margin rather than being clipped.
        "automargin": True,
    }
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
