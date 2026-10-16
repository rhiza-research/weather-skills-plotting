"""Weather palettes (CHC precipitation classes, rank) and their Plotly form.

The class palettes are data: ``{colors, bounds}`` with ``colors`` packed as
under + classes + over. Fixed tables (SPI, percent of normal, rocket) live in
``themes/default.json``; this module keeps the palettes that are computed: the
precip windows cropped from one master, and rank classes sized to the record. ``discretize`` turns a field into class indices plus a
stepped Plotly colorscale so uneven bounds (0, 1, 2, 5, 10 … mm) get equal
colorbar slots, which a linear Plotly colorscale cannot do on raw values.
"""

from __future__ import annotations

import numpy as np
from weather_skills_core.errors import UsageError
from weather_skills_core.units import parse_aggregation_period, ureg, variable_units


def _rgb(*rows: tuple[int, int, int]) -> list[str]:
    """``(r, g, b)`` 0–255 → ``#rrggbb``. Source values are CHC IDL palettes."""
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in rows]


# CHC ``ppt_total_cmap.pro`` (Will Turner, 6 Feb 2018). 17 colors / 16 interior
# breaks: null/negative white, 0–2 mm white, then the published classes;
# over (>2500 mm) is pale pink. Data-dependent IDL min/max ends are under/over.
PRECIP_COLORS = _rgb(
    (255, 255, 255),  # null / negative
    (255, 255, 255),  # 0–2 mm
    (200, 255, 190),
    (120, 245, 115),
    (30, 180, 30),
    (180, 240, 250),
    (80, 165, 245),
    (30, 110, 235),
    (220, 220, 255),
    (160, 140, 255),
    (112, 96, 220),
    (255, 250, 170),
    (255, 160, 0),
    (255, 20, 0),
    (165, 0, 0),
    (230, 140, 140),
    (255, 230, 230),
)


PRECIP_BOUNDS = [0, 2, 5, 10, 25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2500]


# Nested absolute-mm default: one color per millimetre class; colorbars crop
# this master (same color = same millimetres on every window). Hues follow CHC
# ``ppt_total`` — white, beige, light / mid / dark green, blue, purple,
# yellow, orange, red — so adjacent classes stay distinct. 0–1 mm is white,
# matching CHC's 0–2 mm class; 1–2 and 2–5 mm are beige so green starts at
# 5 mm. CHC's pale cyan and pale lavender are skipped. Overflow above 1000 mm
# is a darker maroon than the last class, not CHC's pale pink.
PRECIP_BEIGE_TRACE = "#f6e8c3"  # 1–2 mm


PRECIP_BEIGE_LIGHT = "#e8d4a0"  # 2–5 mm


PRECIP_MASTER_BOUNDS = [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 400, 700, 1000]


PRECIP_MASTER_COLORS = [
    PRECIP_COLORS[1],  # 0–1 mm white
    PRECIP_BEIGE_TRACE,  # 1–2 mm pale beige
    PRECIP_BEIGE_LIGHT,  # 2–5 mm tan beige
    PRECIP_COLORS[2],  # 5–10 mm light green
    PRECIP_COLORS[3],  # 10–15 mm mid green
    PRECIP_COLORS[4],  # 15–20 mm dark green
    PRECIP_COLORS[6],  # 20–30 mm sky blue
    PRECIP_COLORS[7],  # 30–40 mm blue
    *PRECIP_COLORS[9:16],  # 40–700 mm purple … salmon (skip pale lavender)
    "#7a0000",  # 700–1000 mm
]


PRECIP_UNDER = "#ffffff"


PRECIP_OVER = "#5a0000"


PRECIP_WINDOW_ORDER = ("ppt_daily", "ppt_week", "ppt_month", "ppt_season")


PRECIP_WINDOW_VMAX = {
    "ppt_daily": 50.0,
    "ppt_week": 200.0,
    "ppt_month": 400.0,
    "ppt_season": 1000.0,
}


# CHC ``ppt_anomaly_cmap.pro`` (Will Turner, 8 Feb 2018).
PRECIP_ANOMALY_COLORS = _rgb(
    (192, 0, 0),
    (255, 50, 0),
    (255, 160, 0),
    (255, 232, 120),
    (120, 80, 70),
    (180, 140, 130),
    (240, 220, 210),
    (255, 255, 255),
    (200, 255, 190),
    (120, 245, 115),
    (30, 180, 30),
    (150, 210, 250),
    (40, 130, 240),
    (220, 220, 255),
    (128, 112, 235),
)


PRECIP_ANOMALY_BOUNDS = [-500, -300, -200, -100, -50, -25, -10, 10, 25, 50, 100, 200, 300, 500]


# Packed CHC list is under + 13 classes + over. Nested windows crop this master
# the same way totals crop PRECIP_MASTER_* (same colour = same millimetres).
PRECIP_ANOMALY_UNDER = PRECIP_ANOMALY_COLORS[0]


PRECIP_ANOMALY_OVER = PRECIP_ANOMALY_COLORS[-1]


PRECIP_ANOMALY_MASTER_COLORS = PRECIP_ANOMALY_COLORS[1:-1]


PRECIP_ANOMALY_WINDOW_ORDER = (
    "ppt_anom_daily",
    "ppt_anom_week",
    "ppt_anom_month",
    "ppt_anom_season",
)


# CHC ``rank_cmap.pro`` (missing gray omitted; bounds depend on ``n_seasons``).
RANK_COLORS = _rgb(
    (115, 0, 0),
    (231, 0, 0),
    (255, 170, 0),
    (255, 255, 255),
    (189, 235, 255),
    (0, 113, 255),
    (0, 0, 85),
)


def precip_window_name(days: float | None) -> str:
    """Pick a nested precip colorbar window from ``aggregation_period`` days."""
    if days is None:
        return "ppt_week"
    if days < 2:
        return "ppt_daily"
    if days <= 10:
        # A dekad is the week window, as chc-plot-theme picks it.
        return "ppt_week"
    if days < 40:
        return "ppt_month"
    return "ppt_season"


def precip_anomaly_window_name(days: float | None) -> str:
    """Nested anomaly window matching ``precip_window_name`` (same day cuts)."""
    return "ppt_anom_" + precip_window_name(days).removeprefix("ppt_")


def widest_precip_window(*days: float | None) -> str:
    """Window that covers every aggregation in ``days`` (highest vmax)."""
    return max((precip_window_name(d) for d in days), key=PRECIP_WINDOW_ORDER.index)


def widest_precip_anomaly_window(*days: float | None) -> str:
    """Anomaly window that covers every aggregation in ``days``."""
    return "ppt_anom_" + widest_precip_window(*days).removeprefix("ppt_")


def default_precip_window(*days: float | None, anomaly: bool = False) -> str:
    """Totals or anomaly nested window covering every aggregation in ``days``."""
    if anomaly:
        return widest_precip_anomaly_window(*days)
    return widest_precip_window(*days)


# Palette names that follow the field's ``aggregation_period`` like the
# automatic precip default, but skip detection (so an all-positive anomaly
# still gets the diverging scale). Value: whether it is the anomaly scale.
DEFAULT_PRECIP_PALETTES = {"default_precip": False, "default_precip_anom": True}


def precip_nested_palette(name: str) -> dict:
    """Packed under + master prefix + next-class over for a window name."""
    if name not in PRECIP_WINDOW_VMAX:
        raise UsageError(f"unknown precip window {name!r}")
    vmax = PRECIP_WINDOW_VMAX[name]
    bounds = [b for b in PRECIP_MASTER_BOUNDS if b <= vmax]
    n_bins = len(bounds) - 1
    classes = PRECIP_MASTER_COLORS[:n_bins]
    over = PRECIP_MASTER_COLORS[n_bins] if n_bins < len(PRECIP_MASTER_COLORS) else PRECIP_OVER
    return {"colors": [PRECIP_UNDER, *classes, over], "bounds": list(bounds)}


def precip_nested_anomaly_palette(name: str) -> dict:
    """Crop the CHC anomaly master to ± the matching totals window.

    Same colour is always the same millimetres. Stops are the CHC edges whose
    absolute value is ≤ the totals ``vmax`` (month 400 mm → ±300 mm; season
    1000 mm → ±500 mm). Overflow uses the next master class.
    """
    if name not in PRECIP_ANOMALY_WINDOW_ORDER:
        raise UsageError(f"unknown precip anomaly window {name!r}")
    totals = "ppt_" + name.removeprefix("ppt_anom_")
    vmax = PRECIP_WINDOW_VMAX[totals]
    bounds = [b for b in PRECIP_ANOMALY_BOUNDS if abs(b) <= vmax]
    if len(bounds) < 2:
        raise UsageError(f"precip anomaly window {name!r} has no classes at ±{vmax:g} mm")
    i0 = PRECIP_ANOMALY_BOUNDS.index(bounds[0])
    i1 = PRECIP_ANOMALY_BOUNDS.index(bounds[-1])
    classes = PRECIP_ANOMALY_MASTER_COLORS[i0:i1]
    under = PRECIP_ANOMALY_MASTER_COLORS[i0 - 1] if i0 > 0 else PRECIP_ANOMALY_UNDER
    over = (
        PRECIP_ANOMALY_MASTER_COLORS[i1]
        if i1 < len(PRECIP_ANOMALY_MASTER_COLORS)
        else PRECIP_ANOMALY_OVER
    )
    return {"colors": [under, *classes, over], "bounds": list(bounds)}


def aggregation_days(da) -> float | None:
    """Return stamped ``aggregation_period`` in days, or None."""
    period = da.attrs.get("aggregation_period")
    if not (isinstance(period, str) and period.strip()):
        return None
    try:
        return float(parse_aggregation_period(period).to("day").magnitude)
    except UsageError:
        return None


def is_precip(da) -> bool:
    from weather_skills_core.units import classify_variable

    kind = classify_variable(
        da.name or "",
        units=variable_units(da),
        standard_name=da.attrs.get("standard_name"),
    )
    return kind in ("precip", "precip_amount")


def is_precip_anomaly(da) -> bool:

    if not is_precip(da):
        return False
    name = f"{da.name or ''} {da.attrs.get('long_name') or ''}".lower()
    if "anomal" in name:
        return True
    values = da.data
    values = getattr(values, "magnitude", values)  # a pint quantity: its numbers
    sample = np.asarray(values, dtype=float).ravel()
    finite = sample[np.isfinite(sample)]
    # Real negatives, not the -1e-6 rounding a deaccumulated total can carry.
    return bool(finite.size) and bool(np.nanmin(finite) < -0.01)


def is_precip_poa(da) -> bool:
    """Percent-of-normal precip (CHC ``ppt_poa``)."""
    name = f"{da.name or ''} {da.attrs.get('long_name') or ''}".lower()
    tokens = name.replace("_", " ").replace("-", " ").split()
    if "percent of" in name or "pct of" in name or "poa" in tokens:
        return True
    units = (variable_units(da) or "").strip().lower()
    return units in {"%", "percent"}


def is_temperature(da) -> bool:
    """Air, surface or sea temperature (not an anomaly): drawn cool to warm."""
    text = " ".join(str(da.attrs.get(k) or "") for k in ("standard_name", "long_name")).lower()
    return "temperature" in text and "anomal" not in text and "anomal" not in str(da.name).lower()


# Standard-atmosphere sea-level pressure: the white middle of the pressure scale.
STANDARD_SEA_LEVEL_PRESSURE_HPA = 1013.25


def is_sea_level_pressure(da) -> bool:
    """Sea-level pressure in pressure units (not surface pressure, not an anomaly)."""
    from weather_skills_core.units import classify_variable

    standard_name = da.attrs.get("standard_name")
    kind = classify_variable(da.name or "", units=variable_units(da), standard_name=standard_name)
    surface = standard_name == "surface_air_pressure" or "surface" in str(da.name).lower()
    return kind == "pressure" and not surface and "anomal" not in str(da.name).lower()


def is_statistic(da) -> bool:
    """A spread or variance (``cell_methods`` from summarize-dim): not a precip amount."""
    methods = str(da.attrs.get("cell_methods") or "")
    return "standard_deviation" in methods or "variance" in methods


def is_spi(da) -> bool:
    name = f"{da.name or ''} {da.attrs.get('long_name') or ''}".lower()
    tokens = name.replace("_", " ").replace("-", " ").split()
    return "spi" in tokens or "standardized precipitation" in name


def default_kind(da, *, diverging: bool = False) -> str:
    """The field kind whose ``theme["defaults"]`` entry colors ``da``.

    Precipitation kinds and wind speed (CF ``standard_name: wind_speed``) come
    from the field itself. Other fields are ``diverging`` (the color range
    straddles zero), sea-level pressure, temperature, or ``sequential``. A
    spread or variance is never a precip amount.
    """
    if da is not None and da.attrs.get("standard_name") == "wind_speed":
        return "wind_speed"
    if da is not None and not is_statistic(da):
        if is_spi(da):
            return "spi"
        if is_precip_poa(da):
            return "precip_poa"
        if is_precip_anomaly(da):
            return "precip_anomaly"
        if is_precip(da):
            return "precip"
    if diverging:
        return "diverging"
    if da is not None and not is_statistic(da) and is_sea_level_pressure(da):
        return "sea_level_pressure"
    if da is not None and is_temperature(da):
        return "temperature"
    return "sequential"


def rank_colorscale(n_seasons: int) -> dict:
    """CHC ``rank_cmap.pro`` classes for a climatology of ``n_seasons`` years."""
    n = int(n_seasons)
    if n < 4:
        raise UsageError("--colormap ppt_rank needs n_seasons ≥ 4")
    bounds = [-0.5, 1.5, 2.5, 3.5, n - 2.5, n - 1.5, n - 0.5, n + 0.5]
    return {
        "name": "ppt_rank",
        "colors": list(RANK_COLORS),
        "bounds": bounds,
        "cmin": bounds[0],
        "cmax": bounds[-1],
    }


def along_dim(da, along: str | None) -> str | None:
    """Resolve ``along`` to a dim on ``da``, including ontology aliases (member/number)."""
    from weather_skills_core.standard_dataset import ALIASES, names_for

    if not along:
        return None
    if along in da.dims:
        return along
    preferred = ALIASES.get(along, along)
    return next((name for name in names_for(preferred) if name in da.dims), None)


ALONG_COLOR_SAME = "same"


ALONG_COLOR_CYCLE = "cycle"


_ALONG_COLOR_ALIASES = {
    "same": ALONG_COLOR_SAME,
    "shared": ALONG_COLOR_SAME,
    "cycle": ALONG_COLOR_CYCLE,
    "distinct": ALONG_COLOR_CYCLE,
}


def parse_along_color(value) -> str:
    """``traces[].along_color``: ``same`` (default) or ``cycle``."""
    if value is None or value is False or value == "":
        return ALONG_COLOR_SAME
    raw = str(value).strip().lower().replace("_", "-")
    if raw in _ALONG_COLOR_ALIASES:
        return _ALONG_COLOR_ALIASES[raw]
    raise UsageError(
        "traces[].along_color must be 'same' (one color for every along member) "
        f"or 'cycle' (a distinct color per value); got {value!r}."
    )


def along_member_label(value) -> str:
    """Short legend label for one coordinate along ``traces[].along``."""

    if value is None:
        return ""
    arr = np.asarray(value)
    item = arr.reshape(-1)[0] if arr.size else value
    kind = np.asarray(item).dtype.kind
    if kind == "M" or isinstance(item, np.datetime64):
        try:
            return str(np.datetime_as_string(np.asarray(item, dtype="datetime64[ns]"), unit="D"))
        except (TypeError, ValueError):
            return str(item).strip()
    if isinstance(item, (np.integer, int)) and not isinstance(item, bool):
        return str(int(item))
    if isinstance(item, (np.floating, float)):
        num = float(item)
        return str(int(num)) if num.is_integer() else str(num)
    return str(item).strip()


def parse_band(value) -> tuple[float, float] | None:
    """Parse ``--band`` / spec ``band`` as two percentiles, default ``10,90``."""
    if value is None or value is False or value == "":
        return None
    if value is True:
        return (10.0, 90.0)
    if isinstance(value, dict):
        q = value.get("q") or value.get("percentiles")
        if q is None:
            lo = value.get("low", 10)
            hi = value.get("high", 90)
            value = (lo, hi)
        else:
            value = q
    if isinstance(value, (list, tuple)):
        if len(value) != 2:
            raise UsageError("traces[].band must be two percentiles, e.g. [10, 90]")
        lo, hi = float(value[0]), float(value[1])
    else:
        raw = str(value).strip().lower().replace("q", "")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) != 2:
            raise UsageError("traces[].band must be two percentiles, e.g. [10, 90]")
        lo, hi = float(parts[0]), float(parts[1])
    if not 0 <= lo < hi <= 100:
        raise UsageError(
            f"traces[].band percentiles must satisfy 0 ≤ low < high ≤ 100; got {lo},{hi}"
        )
    return (lo, hi)


def check_color_bound_counts(colors, bounds, under=None, over=None, *, loc="palette"):
    """``colors`` is one per class, or under+classes+over packed in one list."""
    n_bins = len(bounds) - 1
    if n_bins < 1:
        raise UsageError(f"{loc}.bounds needs at least two strictly increasing stops")
    n_colors = len(colors)
    if under is not None or over is not None:
        if n_colors != n_bins:
            raise UsageError(
                f"{loc}.colors must have {n_bins} class colors when under/over are set "
                f"(one per interval between {len(bounds)} bounds); got {n_colors}"
            )
        return
    if n_colors == n_bins or n_colors == n_bins + 2:
        return
    raise UsageError(
        f"{loc}.colors must have {n_bins} class colors, or {n_bins + 2} "
        f"(under + classes + over); got {n_colors} colors and {len(bounds)} bounds"
    )


PALETTE_KEYS = frozenset({"colors", "bounds", "under", "over", "labels"})


def builtin_palettes() -> dict:
    """Named palettes built here rather than listed in ``themes/default.json``."""
    return {
        **{name: precip_nested_palette(name) for name in PRECIP_WINDOW_ORDER},
        **{name: precip_nested_anomaly_palette(name) for name in PRECIP_ANOMALY_WINDOW_ORDER},
        "ppt_total": {"colors": PRECIP_COLORS, "bounds": PRECIP_BOUNDS},
    }


def parse_palette(value, *, registry: dict, loc="meta.palette") -> dict:
    """A palette name, a list of colors, or ``{colors, bounds, under, over}``.

    ``registry`` is the theme's palettes (``load_theme``) that names resolve in.
    """
    palettes = registry
    if isinstance(value, str):
        key = next((k for k in palettes if k.lower() == value.lower()), None)
        if key is None:
            raise UsageError(
                f"{loc} {value!r} is not a known palette; known: "
                f"{', '.join(sorted({*palettes, *DEFAULT_PRECIP_PALETTES}))}. "
                "For a Plotly colorscale name (Viridis, RdBu, YlGn, …) set the trace's "
                "colorscale instead; a palette from a theme file needs that --theme-file"
            )
        return {"name": key, **parse_palette(palettes[key], loc=f"{loc} {key!r}", registry={})}
    if isinstance(value, list):
        value = {"colors": value}
    if not isinstance(value, dict):
        raise UsageError(f"{loc} must be a palette name, a color list, or an object")
    unknown = sorted(set(value) - PALETTE_KEYS - {"name"})
    if unknown:
        raise UsageError(
            f"{loc}: unknown keys {', '.join(unknown)}; allowed: {', '.join(sorted(PALETTE_KEYS))}"
        )
    colors = value.get("colors")
    if not isinstance(colors, list) or len(colors) < 2:
        raise UsageError(f"{loc}.colors must list at least two colors")
    out = {"colors": [str(c) for c in colors]}
    bounds = value.get("bounds")
    if bounds is not None:
        try:
            nums = [float(b) for b in bounds]
        except (TypeError, ValueError) as exc:
            raise UsageError(f"{loc}.bounds must be numbers") from exc
        if len(nums) < 2 or any(a >= b for a, b in zip(nums, nums[1:], strict=False)):
            raise UsageError(f"{loc}.bounds needs at least two strictly increasing numbers")
        check_color_bound_counts(
            out["colors"], nums, value.get("under"), value.get("over"), loc=loc
        )
        out["bounds"] = nums
    for key in ("under", "over"):
        if value.get(key) is not None:
            out[key] = str(value[key])
    labels = value.get("labels")
    if labels is not None:
        n_classes = len(out.get("bounds") or []) - 1
        if not isinstance(labels, list) or len(labels) != n_classes:
            raise UsageError(f"{loc}.labels needs one label per class ({n_classes}) and bounds")
        out["labels"] = [str(label) for label in labels]
    if value.get("name"):
        out["name"] = str(value["name"])
    return out


# A three-flag field (verify's disagree / below / hit) reads red / grey / green.
FLAG3_COLORS = ["#d73027", "#f0f0f0", "#1a9850"]


def flag_palette(da, colorway: list) -> dict | None:
    """One class per CF ``flag_values`` entry, labelled with ``flag_meanings``.

    Three flags read red / grey / green; any other count takes ``colorway`` in order.
    """
    raw = da.attrs.get("flag_values")
    if raw is None:
        return None
    values = np.asarray(raw, dtype=float).ravel()
    if values.size < 2:
        return None
    order = np.argsort(values)
    values = values[order]
    meanings = str(da.attrs.get("flag_meanings") or "").split()
    if len(meanings) == values.size:
        labels = [meanings[i].replace("_", " ") for i in order]
    else:
        labels = [f"{v:g}" for v in values]
    colors = (
        FLAG3_COLORS
        if values.size == 3
        else [colorway[i % len(colorway)] for i in range(values.size)]
    )
    mids = ((values[:-1] + values[1:]) / 2).tolist()
    bounds = [values[0] - 0.5, *mids, values[-1] + 0.5]
    return {"name": "flags", "colors": colors, "bounds": bounds, "labels": labels}


def default_palette(da, *others, theme: dict, diverging: bool = False) -> dict:
    """The palette ``da`` gets when the spec names none.

    CF flags get one class per flag. Every other field gets the theme's
    ``defaults`` entry for its kind (``default_kind``). ``default_precip`` /
    ``default_precip_anom`` pick the window that covers the period of ``da``
    and ``others`` (the fields sharing its colorbar). A Plotly colorscale name
    comes back as ``{"name", "colorscale"}``.
    """
    colorway = theme["template"]["layout"]["colorway"]
    flags = flag_palette(da, colorway) if da is not None else None
    if flags is not None:
        return flags
    kind = default_kind(da, diverging=diverging)
    if kind == "precip_anomaly" and theme["defaults"][kind] == "default_precip_anom":
        from weather_skills_core.units import classify_variable

        rate = classify_variable(
            da.name or "", units=variable_units(da), standard_name=da.attrs.get("standard_name")
        )
        if rate == "precip" and not aggregation_days(da):
            # A change in rate (a CMIP6 future-minus-historical, mm/day) is not a period
            # total: the mm anomaly classes would leave it all in the white ±10 class.
            return {"name": "BrBG", "colorscale": "BrBG"}
    value = theme["defaults"][kind]
    palettes = theme["palettes"]
    key = value.lower() if isinstance(value, str) else None
    if key in DEFAULT_PRECIP_PALETTES and not any(k.lower() == key for k in palettes):
        # A --theme-file entry of the same name wins over the window-following default.
        # A rate with no period is an amount per its unit's time step: mm/day is a
        # daily amount, mm/h an hourly one (still the daily window, not the weekly).
        days = []
        for d in (da, *others):
            if d is None:
                continue
            step = None
            try:
                step = (
                    (ureg.Quantity(1, "mm") / ureg.Quantity(1, variable_units(d)))
                    .to("day")
                    .magnitude
                )
            except Exception:  # noqa: BLE001 — not a length-per-time rate
                pass
            days.append(aggregation_days(d) or step)
        value = default_precip_window(*(days or [None]), anomaly=DEFAULT_PRECIP_PALETTES[key])
    if isinstance(value, str) and not any(k.lower() == value.lower() for k in palettes):
        return {"name": value, "colorscale": value}
    return parse_palette(value, registry=palettes)


def continuous_colorscale(colors) -> list:
    """Evenly spaced Plotly colorscale through ``colors``."""
    colors = list(colors)
    n = len(colors) - 1
    return [[i / n, c] for i, c in enumerate(colors)]


def _class_slots(palette: dict):
    """``(under, classes, over)`` from packed or explicit under/over colors."""
    colors, bounds = palette["colors"], palette["bounds"]
    n_classes = len(bounds) - 1
    if len(colors) == n_classes + 2 and "under" not in palette and "over" not in palette:
        return colors[0], colors[1:-1], colors[-1]
    return palette.get("under"), colors[:n_classes], palette.get("over")


def discretize(values, palette: dict):
    """Map values onto class slots for a bounded palette.

    Returns ``(slots, scale)`` where ``slots`` is a float array of slot indices
    (NaN stays NaN) and ``scale`` holds ``colorscale``, ``cmin``, ``cmax`` and
    the colorbar ``tickvals`` / ``ticktext`` at the class edges.
    """
    bounds = palette["bounds"]
    under, classes, over = _class_slots(palette)
    m = len(bounds)
    offset = 1 if under else 0
    z = np.asarray(values, dtype=float)
    k = np.digitize(z, bounds)
    slots = offset + np.clip(k, 1, m - 1) - 1.0
    if under:
        slots = np.where(k == 0, 0.0, slots)
    if over:
        slots = np.where(k == m, offset + m - 1.0, slots)
    slots = np.where(np.isfinite(z), slots, np.nan)
    colors = ([under] if under else []) + list(classes) + ([over] if over else [])
    n = len(colors)
    colorscale = []
    for i, color in enumerate(colors):
        colorscale += [[i / n, color], [(i + 1) / n, color]]
    scale = {
        "colorscale": colorscale,
        "cmin": -0.5,
        "cmax": n - 0.5,
        "tickvals": [offset + j - 0.5 for j in range(m)],
        "ticktext": [f"{b:g}" for b in bounds],
    }
    if palette.get("labels"):
        # Named classes (CF flags): label each class at its centre, not the edges.
        scale["tickvals"] = [offset + i for i in range(len(classes))]
        scale["ticktext"] = list(palette["labels"])
    return slots, scale
