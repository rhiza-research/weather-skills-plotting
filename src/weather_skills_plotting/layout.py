"""Plotly templates and map-panel helpers.

Layout is left to Plotly wherever it has a default: map panels sit in
Plotly's ``layout.grid``, a lone colorbar keeps Plotly's position, and fonts,
margins and gaps come from Plotly's ``seaborn`` template. This module only adds what Plotly cannot
know: equal-degree lon/lat axes, a canvas shaped like the map, panel titles,
and where several colorbars go (side by side along the bottom).
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


def map_axes(p: int, extent) -> tuple[dict, dict]:
    """Lon/lat axes for panel ``p`` over ``extent``, one degree the same length on both."""
    xaxis = {"range": [extent[0], extent[1]], "constrain": "domain"}
    yaxis = {
        "range": [extent[2], extent[3]],
        "constrain": "domain",
        "scaleanchor": f"x{axis_suffix(p)}",
        "scaleratio": 1,
    }
    return xaxis, yaxis


def stacked_colorbars(k: int) -> list[dict]:
    """Positions for ``k`` colorbars: one keeps Plotly's place, several sit side by side.

    Several bars turn horizontal and share the bottom edge of the figure, each
    taking an equal slice of the width; Plotly's automatic margins make room.
    """
    if k <= 1:
        return [{}] * k
    return [
        {
            "orientation": "h",
            "len": 1 / k,
            "x": (i + 0.5) / k,
            "xanchor": "center",
            "y": 0,
            "yref": "container",
            "yanchor": "bottom",
            # Below the bar: beside it squeezes the bar, above it overlaps it.
            "title": {"side": "bottom"},
        }
        for i in range(k)
    ]


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
