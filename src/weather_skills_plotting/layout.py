"""Plotly templates and the map panel grid.

Map panels are lon/lat axes locked to equal degrees (PlateCarree). Plotly's
own ``layout.grid`` gives equal cells but does not reserve room for panel
titles or place colorbars, so map figures get explicit axis domains, a
canvas sized from the map aspect, and colorbar positions computed here.
Charts keep Plotly's automatic layout.
"""

from __future__ import annotations

import copy

from weather_skills_core.errors import UsageError

from weather_skills_plotting.palettes import COLORBLIND, DEEP

DEFAULT_TEMPLATE = "weather_skills"
DEFAULT_FONTSIZE = 16
DEFAULT_MAX_COLUMNS = 4
CHART_SIZE = (1000, 600)


def _template_layout(colorway) -> dict:
    return {
        "font": {
            "size": DEFAULT_FONTSIZE,
            "family": "Helvetica, Arial, sans-serif",
            "color": "#222",
        },
        "colorway": colorway,
        "title": {"x": 0.5, "xanchor": "center"},
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "xaxis": {
            "showline": True,
            "linecolor": "#444",
            "ticks": "outside",
            "zeroline": False,
            "automargin": True,
            "title": {"standoff": 8},
        },
        "yaxis": {
            "showline": True,
            "linecolor": "#444",
            "ticks": "outside",
            "zeroline": False,
            "automargin": True,
            "title": {"standoff": 8},
        },
        "legend": {"bgcolor": "rgba(255,255,255,0.8)"},
        "colorscale": {"sequential": None},
    }


def register_templates(user_template: dict | None = None) -> None:
    """Register ``weather_skills`` and ``colorblind`` (plus a theme-file overlay)."""
    import plotly.graph_objects as go
    import plotly.io as pio

    for name, colorway in (("weather_skills", DEEP), ("colorblind", COLORBLIND)):
        base = copy.deepcopy(pio.templates["simple_white"])
        layout = _template_layout(colorway)
        layout.pop("colorscale")
        base.update(layout=layout)
        if user_template:
            try:
                base.update(go.layout.Template(user_template))
            except ValueError as exc:
                from weather_skills_plotting.spec import plotly_error

                raise plotly_error(exc, "theme file template") from None
        pio.templates[name] = base


def grid_shape(n, rows=None, columns=None, *, max_columns=DEFAULT_MAX_COLUMNS):
    """``(rows, columns)`` for ``n`` panels; unset sides fill in, leftover cells stay blank."""
    for value, name in ((rows, "rows"), (columns, "columns")):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise UsageError(f"layout.grid.{name} must be an integer >= 1; got {value!r}")
    if rows is None and columns is None:
        columns = min(max_columns, max(n, 1))
        return (n + columns - 1) // columns or 1, columns
    if rows is not None and columns is not None:
        if rows * columns < n:
            raise UsageError(
                f"layout.grid {rows} rows × {columns} columns holds {rows * columns} panels, "
                f"but the figure has {n}"
            )
        return rows, columns
    if columns is not None:
        return (n + columns - 1) // columns or 1, columns
    return rows, (n + rows - 1) // rows or 1


def axis_suffix(p: int) -> str:
    """Plotly axis suffix for 0-based panel ``p`` (``""``, ``"2"``, …)."""
    return "" if p == 0 else str(p + 1)


def map_grid(
    n: int,
    rows: int,
    cols: int,
    aspect: float,
    *,
    font: float,
    has_title: bool,
    has_panel_titles: bool,
    right_bars: list,
    bottom_bars: int,
    width=None,
    height=None,
    xgap=None,
    ygap=None,
):
    """Canvas size, margins, per-panel domains, and colorbar anchors.

    ``right_bars[p]`` counts colorbars drawn to the right of panel ``p``;
    ``bottom_bars`` counts shared horizontal bars under the grid. ``xgap`` /
    ``ygap`` are extra space between panels as a fraction of a panel, like
    Plotly's ``layout.grid``.
    """
    aspect = min(max(aspect, 0.3), 4.0)
    est_h = 430 if n == 1 else (340 if rows == 1 else 280)
    est_w = min(max(est_h * aspect, 200), 700)
    bar_w = 95
    title_h = font * 1.5 + 6 if has_panel_titles else 0
    per_col_bars = [
        max((right_bars[r * cols + c] for r in range(rows) if r * cols + c < n), default=0)
        for c in range(cols)
    ]
    gap_x = [(20 + (xgap or 0) * est_w) + per_col_bars[c] * bar_w for c in range(cols - 1)]
    gap_y = 10 + (ygap or 0) * est_h + title_h
    margin = {
        "l": 14,
        "r": 14 + per_col_bars[-1] * bar_w,
        "t": 14 + title_h + (font * 2.6 if has_title else 0),
        "b": 14 + bottom_bars * (font * 3.2 + 30),
        "pad": 0,
    }
    if width is None or height is None:
        panel_h = 430 if n == 1 else (340 if rows == 1 else 280)
        panel_w = panel_h * aspect
        if panel_w > 700:
            panel_w, panel_h = 700, 700 / aspect
        if panel_w < 200:
            panel_w, panel_h = 200, 200 / aspect
        if width is not None:
            avail = width - margin["l"] - margin["r"] - sum(gap_x)
            panel_w = avail / cols
            panel_h = panel_w / aspect
        if height is not None:
            avail = height - margin["t"] - margin["b"] - gap_y * (rows - 1)
            panel_h = avail / rows
            if width is None:
                panel_w = panel_h * aspect
        width = width or round(margin["l"] + margin["r"] + cols * panel_w + sum(gap_x))
        height = height or round(margin["t"] + margin["b"] + rows * panel_h + gap_y * (rows - 1))
    plot_w = width - margin["l"] - margin["r"]
    plot_h = height - margin["t"] - margin["b"]
    if plot_w <= 50 or plot_h <= 50:
        raise UsageError(
            f"layout width {width} × height {height} leaves no room for the map panels"
        )
    panel_w = (plot_w - sum(gap_x)) / cols
    panel_h = (plot_h - gap_y * (rows - 1)) / rows
    domains = []
    for p in range(n):
        r, c = divmod(p, cols)
        x0 = c * panel_w + sum(gap_x[:c])
        y1 = plot_h - r * (panel_h + gap_y)
        domains.append(
            (
                [max(0.0, x0 / plot_w), min(1.0, (x0 + panel_w) / plot_w)],
                [max(0.0, (y1 - panel_h) / plot_h), min(1.0, y1 / plot_h)],
            )
        )
    return {
        "width": int(width),
        "height": int(height),
        "margin": margin,
        "domains": domains,
        "px": (plot_w, plot_h),
        "bar_w": bar_w,
        "font": font,
    }


def colorbar_right_of(grid: dict, p: int, slot: int) -> dict:
    """Vertical colorbar beside panel ``p`` (``slot`` stacks a second one further out)."""
    (x0, x1), (y0, y1) = grid["domains"][p]
    plot_w, _ = grid["px"]
    return {
        "orientation": "v",
        "x": x1 + (8 + slot * grid["bar_w"]) / plot_w,
        "xanchor": "left",
        "xref": "paper",
        "y": (y0 + y1) / 2,
        "yanchor": "middle",
        "yref": "paper",
        "len": (y1 - y0) * 0.92,
        "lenmode": "fraction",
        "thickness": 14,
        "title": {"side": "right"},
    }


def colorbar_bottom(grid: dict, slot: int) -> dict:
    """Horizontal colorbar under the grid (``slot`` stacks further down)."""
    _, plot_h = grid["px"]
    step = grid["font"] * 3.2 + 30
    return {
        "orientation": "h",
        "x": 0.5,
        "xanchor": "center",
        "y": -(10 + slot * step) / plot_h,
        "yanchor": "top",
        "len": 0.7,
        "thickness": 16,
        "title": {"side": "bottom"},
    }


def map_axes(grid: dict, p: int, extent) -> tuple[dict, dict]:
    """Equal-degree lon/lat axes for panel ``p`` (no ticks, framed)."""
    s = axis_suffix(p)
    xd, yd = grid["domains"][p]
    frame = {
        "showgrid": False,
        "zeroline": False,
        "showticklabels": False,
        "ticks": "",
        "showline": True,
        "mirror": True,
        "linecolor": "black",
        "linewidth": 1,
        "constrain": "domain",
        "fixedrange": False,
        "automargin": False,
    }
    xaxis = {**frame, "domain": xd, "range": [extent[0], extent[1]], "anchor": f"y{s}"}
    yaxis = {
        **frame,
        "domain": yd,
        "range": [extent[2], extent[3]],
        "anchor": f"x{s}",
        "scaleanchor": f"x{s}",
        "scaleratio": 1,
    }
    return xaxis, yaxis


def panel_title(p: int, text: str, font: float) -> dict:
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
        "yshift": 3,
        "showarrow": False,
        "font": {"size": round(font * 0.95)},
    }
