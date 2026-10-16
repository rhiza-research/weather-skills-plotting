"""Figure-facing helpers: dataset labels, variable labels, unit spellings,
which variable each input uses, and precip totals for display.

Moved from weather-skills-core, which keeps the on-disk contract; these only
shape what a figure shows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from weather_skills_core.cf import auto_variable
from weather_skills_core.errors import UsageError
from weather_skills_core.provenance import HISTORY_ATTR, SOURCE_ATTR, origin_skill
from weather_skills_core.units import (
    AGGREGATION_PERIOD_ATTR,
    PRECIP_AMOUNT_LONG_NAME,
    STANDARD,
    assert_nonoverlapping_intervals,
    classify_variable,
    format_cell_methods,
    looks_like_rate_display_name,
    parse_aggregation_period,
    rate_to_total,
    units_equal,
    ureg,
    variable_units,
)

_DATE_TAIL = re.compile(r"[_-]\d{4}-\d{2}-\d{2}(?:[_-]\d{2}-\d{2}-\d{2})?$")
_VAR_TAIL = re.compile(r"[_-](?:precip|tp)$", re.I)
_ACRONYMS = frozenset(
    {
        "ecmwf",
        "s2s",
        "ghcn",
        "cmip6",
        "gefs",
        "oisst",
        "imerg",
        "smap",
        "chirps",
        "nasa",
        "noaa",
        "ifs",
        "ens",
        "aifs",
        "gfs",
        "era5",
        "arco",
        "ucsb",
        "chc",
        "icon",
        "eu",
        "mrms",
        "kmsa",
        "tahmo",
        "gsmap",
        "jaxa",
        "hres",
        "er",
    }
)


def _prettify_token(text: str) -> str:
    parts = [p for p in re.split(r"[_-]+", text.strip()) if p]
    return " ".join(p.upper() if p.lower() in _ACRONYMS else p.capitalize() for p in parts) or text


def label_from_history(ds) -> str | None:
    raw = ds.attrs.get(HISTORY_ATTR)
    if not raw:
        return None
    try:
        history = json.loads(raw) if isinstance(raw, str) else list(raw)
    except (TypeError, ValueError):
        return None
    skill = origin_skill(history)
    return _prettify_token(skill.removesuffix("-fetch")) if skill else None


# Words a catalog id carries that a panel title does not need.
_ID_NOISE = re.compile(r"[-_](forecast|analysis)(?=[-_]|$)|[-_]\d+[-_](day|hour)s?.*$", re.I)


def label_from_source_token(token: str) -> str:
    """Product name from a source token: ``scheme:product/…``, a path, or a bare id."""
    text = token.strip()
    if ":" in text:
        head, _, tail = text.partition(":")
        # The product id is the first path segment after the scheme.
        text = re.split(r"[/\\]", (tail or head).strip())[0].removesuffix(".zarr")
    elif "/" in text or "\\" in text or text.endswith(".zarr"):
        text = Path(text).stem
    text = _VAR_TAIL.sub("", _DATE_TAIL.sub("", text))
    # nasa-imerg-analysis-late → NASA IMERG Late; ecmwf-ifs-ens-forecast-15-day-0-25-degree → ECMWF IFS ENS
    text = _ID_NOISE.sub("", text) or text
    return _prettify_token(text)


def dataset_display_label(ds, fallback) -> str:
    """Short product name from ``weather_skills_source``, provenance, or ``fallback``."""
    for token in (ds.attrs.get(SOURCE_ATTR), ds.encoding.get("source")):
        if isinstance(token, str) and (label := label_from_source_token(token)):
            return label
    return label_from_history(ds) or (fallback() if callable(fallback) else str(fallback))


def resolve_input_labels(
    labels: list[str] | None,
    n: int,
    *,
    input_flag: str = "--input",
) -> list[str | None]:
    """Map optional ``--label`` values to *n* inputs; ``None`` slots use auto labels."""
    if not labels or all(label is None for label in labels):
        return [None] * n
    if len(labels) != n:
        raise UsageError(f"expected {n} --label values (one per {input_flag}), got {len(labels)}")
    return list(labels)


def combine_display_labels(labels: list[str]) -> str:
    """Join unique labels for a shared row title (e.g. one forecast row)."""
    return " / ".join(dict.fromkeys(label for label in labels if label))


def resolve_input_variable(inputs, ds, *, id=None, index=None):
    """This input's own ``variable``, else ``inputs[0].variable``, else auto-detect on ``ds``.

    Match the input by ``id`` (preferred) or list ``index``. This is the one
    place "which variable does this dataset use" is resolved, so every
    plot-* skill treats a per-input override, and the ``inputs[0]`` fallback,
    the same way — a spec key set on one dataset never leaks onto another
    dataset that has its own name for the same field.
    """
    items = [item for item in (inputs or []) if isinstance(item, dict)]
    own = None
    if id is not None:
        own = next((item.get("variable") for item in items if str(item.get("id")) == str(id)), None)
    elif index is not None and index < len(items):
        own = items[index].get("variable")
    if own:
        return own
    fallback = items[0].get("variable") if items else None
    if fallback:
        return fallback
    return auto_variable(ds)


def format_units_for_display(units: str | None) -> str:
    """Short figure-label spelling. On-disk attrs stay CF; colorbars do not.

    ``mm day-1`` / ``millimeter / day`` → ``mm/day``; ``degree_Celsius`` →
    ``°C``; other pint-parseable strings use CF compact form.
    """
    if not isinstance(units, str) or not units.strip() or units.strip() == "1":
        return ""
    raw = units.strip()
    if raw.lower() in ("delta_degc", "delta_degree_celsius", "delta_degree_c"):
        return "°C"
    for kind, nice in (("precip", "mm/day"), ("precip_amount", "mm"), ("temp", "°C")):
        if units_equal(raw, STANDARD[kind]["units"]):
            return nice
    try:
        text = format(ureg.Unit(raw), "cf").replace(" d-1", "/day").replace(" h-1", "/h")
    except Exception:  # noqa: BLE001 — leave unparseable strings alone
        return raw
    if text == "1":
        # Dimensionless: a ratio of like units (m3 m-3) says what it is; a bare 1 says nothing.
        return "" if raw.lower() in ("1", "dimensionless") else raw
    return text


_LABEL_NOISE = (
    (re.compile(r"^(daily|hourly|weekly|monthly)\s+", re.I), ""),
    (re.compile(r"^mean\s+", re.I), ""),
    (re.compile(r"\s+in the (last|previous) \d+ hours?$", re.I), ""),
    (re.compile(r"\s+at 2 met(re|er)s?", re.I), " (2 m)"),
    (re.compile(r"\s+at 10 met(re|er)s?", re.I), " (10 m)"),
)


def short_label(label: str) -> str:
    """Drop aggregation words a colorbar does not need ("Daily", "in the last 24 hours")."""
    out = label
    for pattern, repl in _LABEL_NOISE:
        out = pattern.sub(repl, out)
    out = out.strip()
    if not out or out == label:
        return label
    return out[:1].upper() + out[1:]


def variable_label_for_display(
    da, *, fallback: str | None = None, include_units: bool = True
) -> str:
    """Colorbar / axis label: ``long_name``, then ``GRIB_name``, then the name.

    Leftover rate-like names on precip amounts become ``Total precipitation``.
    Units are appended in display form (``mm/day``, ``°C``) when present.
    """
    label = None
    for key in ("long_name", "GRIB_name"):
        val = da.attrs.get(key)
        if isinstance(val, str) and val.strip():
            label = val.strip()
            break
    if label is None:
        name = da.name if isinstance(da.name, str) and da.name.strip() else None
        label = fallback or name or "value"
    kind = classify_variable(
        da.name or "",
        units=variable_units(da),
        standard_name=da.attrs.get("standard_name"),
    )
    if kind == "precip_amount" and looks_like_rate_display_name(label):
        label = PRECIP_AMOUNT_LONG_NAME
    label = short_label(label)
    if kind in ("precip", "precip_amount") and label.lower() == "total precipitation":
        label = "Precipitation"
    from weather_skills_plotting.palettes import is_precip_anomaly, is_statistic

    if is_statistic(da):
        # summarize-dim writes "Standard deviation of Total precipitation across number".
        m = re.match(r"standard deviation of (.+?)(?: across (.+))?$", label, re.I)
        if m:
            what = short_label(m.group(1))
            if what.lower() == "total precipitation":
                what = "Precipitation"
            label = f"{what} std. dev." + (f" ({m.group(2)})" if m.group(2) else "")
        elif "std" not in label.lower() and "deviation" not in label.lower():
            label = f"{label} std. dev."
    elif "anomal" not in label.lower() and (
        "anomal" in str(da.name).lower() or is_precip_anomaly(da)
    ):
        label = f"{label} anomaly"
    if not include_units:
        return label
    units = format_units_for_display(variable_units(da))
    if units:
        return f"{label} [{units}]"
    return label


def precip_for_display(ds, name: str):
    """In-memory precip rate → period total for plotting.

    Uses stamped ``aggregation_period`` (from ``aggregate-temporal``). No-op
    when the variable is not a precip rate, has no period or a sub-daily one, or the time axis
    would overlap (same gates as convert-to-totals). Plotters call this so
    precip defaults to ``mm`` totals without a separate Zarr. The period attr
    is kept so colormap selection can stay period-aware.
    """
    if name not in ds.data_vars:
        return ds
    da = ds[name]
    units = variable_units(da) or da.attrs.get("units")
    kind = classify_variable(name, units=units, standard_name=da.attrs.get("standard_name"))
    if kind != "precip":
        return ds
    period = da.attrs.get(AGGREGATION_PERIOD_ATTR)
    if not (isinstance(period, str) and period.strip()):
        return ds
    try:
        days = float(parse_aggregation_period(period).to("day").magnitude)
    except Exception:  # noqa: BLE001 — calendar periods (1 month, 1 dekad) are a day or more
        days = None
    if days is not None and days < 1:
        # Sub-daily means (a 6 hour rate) read as rates, the way forecast charts show them.
        return ds
    dim = "step" if "step" in da.dims else "time" if "time" in da.dims else None
    if dim is None:
        return ds
    try:
        assert_nonoverlapping_intervals(ds, dim, period)
        total = rate_to_total(da, period)
    except UsageError:
        return ds
    plain = total.pint.dequantify() if total.pint.units is not None else total
    attrs = {**da.attrs, **plain.attrs}
    attrs["units"] = STANDARD["precip_amount"]["units"]
    attrs["standard_name"] = STANDARD["precip_amount"]["standard_name"]
    attrs["long_name"] = PRECIP_AMOUNT_LONG_NAME
    if looks_like_rate_display_name(attrs.get("GRIB_name")):
        attrs["GRIB_name"] = PRECIP_AMOUNT_LONG_NAME
    attrs["cell_methods"] = format_cell_methods(dim, "sum")
    # Keep aggregation_period so plotters can crop the nested precip palette.
    out = ds.copy(deep=False)
    out[name] = plain
    out[name].attrs = attrs
    return out
