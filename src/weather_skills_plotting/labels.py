"""Human labels: ``14 Sept '26`` dates, panel titles, axis labels."""

from __future__ import annotations

import numpy as np
from weather_skills_core.errors import UsageError
from weather_skills_core.units import DATA_INTERVAL_ATTR, parse_aggregation_period

from weather_skills_plotting.geodata import is_cftime_axis
from weather_skills_plotting.palettes import aggregation_days

# Sept not Sep — the usual meteorological short form.
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sept",
    "Oct",
    "Nov",
    "Dec",
)


def _ymd(value):
    """Return ``(year, month, day)`` from a datetime-like, or None."""
    if value is None:
        return None
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            year, month, day = int(value.year), int(value.month), int(value.day)
            if 1 <= month <= 12 and 1 <= day <= 31:
                return year, month, day
        except (TypeError, ValueError):
            pass
    try:
        import numpy as np

        arr = np.asarray(value)
        if arr.dtype.kind == "M":
            sample = np.asarray(arr.reshape(-1)[0]).astype("datetime64[D]")
            text = str(np.datetime_as_string(sample, unit="D"))
            return int(text[0:4]), int(text[5:7]), int(text[8:10])
    except (TypeError, ValueError, IndexError):
        pass
    text = str(value)
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        try:
            return int(text[0:4]), int(text[5:7]), int(text[8:10])
        except ValueError:
            return None
    return None


def format_plot_date(value, *, year=True):
    """Figure date: ``14 Sept '26``. Set ``year=False`` for day-of-year ticks."""
    ymd = _ymd(value)
    if ymd is None:
        return str(value)
    y, month, day = ymd
    mon = _MONTHS[month - 1]
    if not year:
        return f"{day} {mon}"
    return f"{day} {mon} '{y % 100:02d}"


def axis_label(text):
    """Sentence-case an axis label; map lon/lat shorthand to Longitude/Latitude."""
    if text is None:
        return text
    s = str(text).strip()
    if not s:
        return s
    known = {
        "lon": "Longitude",
        "lat": "Latitude",
        "longitude": "Longitude",
        "latitude": "Latitude",
        "valid time": "Valid time",
        "calendar day": "Calendar day",
        "time": "Time",
        "step": "Step",
        "forecast step": "Forecast step",
    }
    key = s.lower()
    if key in known:
        return known[key]
    if s[:1].islower():
        return s[:1].upper() + s[1:]
    return s


def resolve_axis_label(override, default):
    """Use ``override`` verbatim when set; otherwise sentence-case ``default``."""
    if override is not None and str(override).strip() != "":
        return str(override)
    return axis_label(default)


def is_datetime_axis(values):
    """True when ``values`` are calendar dates (datetime64 or cftime)."""
    import numpy as np

    arr = np.asarray(values)
    if arr.dtype.kind == "M":
        return True
    if arr.size == 0:
        return False
    first = arr.reshape(-1)[0]
    return hasattr(first, "year") and hasattr(first, "month")


def format_plot_date_range(start, end):
    """Inclusive range: ``1–7 Sept '26``, ``28 Aug–3 Sept '26``, ``28 Dec '25–3 Jan '26``."""
    a = _ymd(start)
    b = _ymd(end)
    if a is None or b is None:
        return f"{format_plot_date(start)}–{format_plot_date(end)}"
    ay, am, ad = a
    by, bm, bd = b
    a_mon, b_mon = _MONTHS[am - 1], _MONTHS[bm - 1]
    a_yr, b_yr = f"'{ay % 100:02d}", f"'{by % 100:02d}"
    if ay == by and am == bm:
        return f"{ad}–{bd} {a_mon} {a_yr}"
    if ay == by:
        return f"{ad} {a_mon}–{bd} {b_mon} {b_yr}"
    return f"{ad} {a_mon} {a_yr}–{bd} {b_mon} {b_yr}"


def format_step(value):
    """Lead-time or calendar label: ``+3d`` or ``1 Jan '26``."""
    arr = np.asarray(value)
    if arr.dtype.kind == "M":
        return format_plot_date(value)
    if arr.dtype.kind == "m":
        days = int(arr.astype("timedelta64[D]").astype("int64").reshape(-1)[0])
        return f"+{days}d"
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return format_plot_date(value)
    return str(value)


def calendar_bin_width(da, all_steps):
    """Days in a left-labeled multi-day calendar bin, or None for a single date."""
    days = aggregation_days(da)
    if days is not None and days >= 2:
        return float(days)
    arr = np.asarray(all_steps)
    if arr.size < 2:
        return None
    if arr.dtype.kind == "M":
        try:
            diffs = np.diff(arr.astype("datetime64[ns]").astype("int64"))
        except (TypeError, ValueError):
            return None
        positive = diffs[diffs > 0]
        if positive.size == 0:
            return None
        median_ns = float(np.median(positive))
        if median_ns < 2 * 86_400_000_000_000:
            return None
        return median_ns / 86_400_000_000_000
    if is_cftime_axis(arr):
        ordered = np.sort(arr)
        deltas = [
            abs((ordered[i + 1] - ordered[i]).total_seconds()) for i in range(ordered.size - 1)
        ]
        if not deltas:
            return None
        seconds = float(np.median(deltas))
        if seconds < 2 * 86_400:
            return None
        return seconds / 86_400
    return None


def format_calendar_panel(value, bin_width=None):
    """``14 Sept '26``, or ``4–10 Aug '26`` for multi-day left-edge bins."""
    import datetime as _dt

    if bin_width is None:
        return format_plot_date(value)
    try:
        if hasattr(bin_width, "to"):
            days = float(bin_width.to("day").magnitude)
        elif hasattr(bin_width, "total_seconds"):
            days = float(bin_width.total_seconds()) / 86_400
        else:
            days = float(bin_width)
    except (TypeError, ValueError, AttributeError):
        return format_plot_date(value)
    if days <= 1.5:
        return format_plot_date(value)

    offset_days = int(round(days)) - 1
    if hasattr(value, "calendar"):
        try:
            end = value + _dt.timedelta(days=offset_days)
        except (TypeError, ValueError):
            return format_plot_date(value)
        return format_plot_date_range(value, end)

    try:
        start = np.asarray(value, dtype="datetime64[D]")
        end = start + np.timedelta64(offset_days, "D")
        return format_plot_date_range(start, end)
    except (TypeError, ValueError):
        return format_step(value)


def panel_title(da, sdim, step_value, all_steps):
    """Human panel label: calendar range, forecast valid window, or ``<sdim>=…``."""
    step_arr = np.asarray(all_steps)
    value_arr = np.asarray(step_value)
    if step_arr.dtype.kind == "m" and "time" in da.coords and getattr(da["time"], "ndim", 1) == 0:
        fallback = f"{sdim}={format_step(step_value)}"
        try:
            time_val = np.asarray(da["time"].values)
            start = time_val + np.asarray(step_value)
            dt = None
            interval = da.attrs.get(DATA_INTERVAL_ATTR)
            if isinstance(interval, str) and interval.strip():
                try:
                    seconds = float(parse_aggregation_period(interval).to("second").magnitude)
                    dt = np.timedelta64(int(round(seconds)), "s")
                except (TypeError, ValueError, UsageError):
                    dt = None
            if dt is None:
                dt = step_arr[1] - step_arr[0] if step_arr.size > 1 else np.timedelta64(1, "D")
            end = start + dt
            return f"{format_plot_date(start)} until {format_plot_date(end)}"
        except Exception:  # noqa: BLE001
            return fallback
    if value_arr.dtype.kind == "M" or hasattr(step_value, "calendar"):
        return format_calendar_panel(step_value, calendar_bin_width(da, all_steps))
    return f"{sdim}={format_step(step_value)}"


def timeseries_axis(da, sdim):
    """X coord and xlabel. Forecast ``step`` + scalar init → valid times."""
    if sdim != "step" or "time" not in da.coords:
        return da[sdim].values, sdim
    time_coord = da["time"]
    if getattr(time_coord, "ndim", 1) != 0:
        return da[sdim].values, sdim
    steps = np.asarray(da["step"].values)
    if steps.dtype.kind != "m":
        return da[sdim].values, sdim
    init = np.asarray(time_coord.values)
    if init.dtype.kind != "M":
        return da[sdim].values, sdim
    return (init + steps).astype("datetime64[ns]"), "Valid time"
