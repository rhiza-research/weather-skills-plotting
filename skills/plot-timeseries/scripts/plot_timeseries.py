# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "weather-skills-plotting",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
#
# [tool.uv.sources]
# weather-skills-plotting = { path = "../../..", editable = true }
# ///
"""Overlay one series per input Zarr on a shared time axis, as PNG or HTML."""

import copy
from pathlib import Path

from weather_skills_core import UsageError, weather_skill
from weather_skills_core.cf import auto_variable
from weather_skills_core.units import (
    AGGREGATION_PERIOD_ATTR,
    to_standard_units,
    units_equal,
    variable_units,
)

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import (
    input_ids,
    input_path,
    parse_input,
    run,
    skeleton,
    spec_datasets,
    warn,
)
from weather_skills_plotting.display import dataset_display_label, precip_for_display
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP, merge_spec

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.2"

MAX_INPUTS = 26
# meta keys a later trace takes from data[0] when it leaves them unset.
INHERITED_META = ("along", "along_color", "band", "members", "align")
INHERITED_SOURCE = ("variable",)


def _size1(ds, *names):
    for name in names:
        if name in ds.coords and ds[name].size == 1:
            text = str(ds[name].values.reshape(-1)[0]).strip()
            if text:
                return text
    return None


def trace_label(ds, idx: int) -> str:
    """Legend label: station id (and name), file stem, else the dataset's display label."""
    station = _size1(ds, "station_id", "point_id")
    if station:
        name = _size1(ds, "name")
        return f"{station} {name}" if name and name.casefold() != station.casefold() else station
    path = input_path(ds)
    if path:
        return Path(path).stem
    return dataset_display_label(ds, f"input {idx + 1}")


def inherit_from_first(spec: dict, datasets: dict | None = None) -> dict:
    """Series settings on data[0] apply to every series that does not set its own.

    ``along`` (and its band and colours) passes on only to an input that has
    that dim: an ensemble's spread does not apply to a climatology line.
    """
    data = spec.get("data") or []
    if len(data) < 2:
        return spec
    first = data[0].get("meta") or {}
    for trace in data[1:]:
        meta = trace.setdefault("meta", {})
        source = meta.get("source") or {}
        ds = (datasets or {}).get(str(source.get("input")))
        along = first.get("along")
        # The dims of the variable this trace draws, not of the whole file.
        var = source.get("variable") or (first.get("source") or {}).get("variable")
        dims = ds[var].dims if ds is not None and var in ds else getattr(ds, "dims", ())
        lacks_along = along and ds is not None and along not in dims
        for key in INHERITED_META:
            if lacks_along and key in ("along", "along_color", "band", "members"):
                continue
            if key in first and key not in meta:
                meta[key] = copy.deepcopy(first[key])
        source = meta.setdefault("source", {})
        for key in INHERITED_SOURCE:
            if key in (first.get("source") or {}) and key not in source:
                source[key] = copy.deepcopy(first["source"][key])
    return spec


def keep_mixed_precip_as_rates(spec: dict, datasets: dict) -> dict:
    """Draw every precip series on a y-axis as a rate unless all become totals.

    Series with an ``aggregation_period`` are drawn as period totals (mm);
    one without stays a rate (mm/day). Mixed on one axis, a weekly 35 mm
    total would read as 35 mm/day, so drop the period from those inputs.
    """
    by_axis = {}
    for trace in spec.get("data") or []:
        source = (trace.get("meta") or {}).get("source") or {}
        key = str(source.get("input"))
        ds = datasets.get(key)
        if ds is None:
            continue
        var = source.get("variable") or auto_variable(ds)
        if var not in ds:
            continue
        try:
            rate = to_standard_units(ds, variables=[var])
        except UsageError:
            rate = ds
        converted = precip_for_display(rate, var) is not rate
        by_axis.setdefault(trace.get("yaxis") or "y", []).append((key, var, converted))
    out = dict(datasets)
    for items in by_axis.values():
        converted = [c for _, _, c in items]
        if not any(converted) or all(converted):
            continue
        for key, var, c in items:
            if c:
                ds = out[key].copy(deep=False)
                ds[var] = ds[var].copy(deep=False)
                ds[var].attrs.pop(AGGREGATION_PERIOD_ATTR, None)
                out[key] = ds
        warn(
            "some precip inputs have no aggregation_period, so every series on a shared "
            "y-axis is drawn as a rate (mm/day). Run aggregate-temporal on all inputs to "
            'plot totals, or give each its own axis (yaxis "y2", or layout.grid).'
        )
    return out


def warn_disjoint_dates(spec: dict, datasets: dict) -> None:
    """Overlaid series whose dates never overlap are rarely what was meant; say so."""
    spans = {}
    for trace in spec.get("data") or []:
        if (trace.get("meta") or {}).get("align"):
            continue  # seasonal overlays put different years on one axis on purpose
        key = str(((trace.get("meta") or {}).get("source") or {}).get("input"))
        ds = datasets.get(key)
        if ds is None or "time" not in ds.coords or ds["time"].ndim != 1:
            continue
        times = ds["time"].values
        if times.dtype.kind == "M" and times.size:
            spans[trace.get("uid") or key] = (times.min(), times.max())
    items = list(spans.items())
    for i, (a, (a0, a1)) in enumerate(items):
        for b, (b0, b1) in items[i + 1 :]:
            if a1 < b0 or b1 < a0:
                warn(
                    f"series {a} ({str(a0)[:10]}–{str(a1)[:10]}) and {b} "
                    f"({str(b0)[:10]}–{str(b1)[:10]}) share no dates"
                )


def warn_mixed_units(spec: dict, datasets: dict) -> None:
    """Series on one y-axis in different units are drawn on one scale; say so."""
    by_axis = {}
    for trace in spec.get("data") or []:
        source = (trace.get("meta") or {}).get("source") or {}
        ds = datasets.get(str(source.get("input")))
        if ds is None:
            continue
        var = source.get("variable") or auto_variable(ds)
        units = variable_units(ds[var]) if var in ds else None
        by_axis.setdefault(trace.get("yaxis") or "y", []).append((trace.get("uid"), units))
    for axis, items in by_axis.items():
        unknown = [str(uid) for uid, u in items if not u]
        items = [(uid, u) for uid, u in items if u]
        if items and unknown:
            warn(
                f"series {', '.join(unknown)} on {axis} have no units attr but share an axis "
                f"labelled in {items[0][1]!r}; check they are the same quantity"
            )
        if any(not units_equal(items[0][1], u) for _, u in items[1:]):
            detail = ", ".join(f"{uid} units={u!r}" for uid, u in items)
            warn(
                f"series on {axis} have different units ({detail}) but share one y-axis. "
                'Give each its own panel with layout.grid {"rows": N, "columns": 1, '
                '"pattern": "coupled"}, or a second axis with yaxis "y2"'
            )


@weather_skill(name="plot-timeseries", version=_SKILL_VERSION)
@weather_skill.argument(
    "-i",
    "--input",
    dest="inputs",
    type=parse_input,
    action="append",
    help="Input Zarr as PATH or PATH=NAME; repeat once per series, in legend order. In --spec "
    "the series is uid NAME, else its position: 0, 1, ….",
)
@weather_skill.argument("--spec", type=parse_spec_arg, help=SPEC_ARGUMENT_HELP)
@weather_skill.argument(
    "--theme-file",
    help="Theme JSON/TOML: {template: <Plotly template>, palettes: {…}}.",
)
@weather_skill.argument("--dump-spec", nargs="?", const="-", probe=True, help=DUMP_SPEC_HELP)
def plot_timeseries(inputs, output, spec, theme_file, dump_spec, **kwargs):
    """Overlay one series per input Zarr on a shared time axis."""
    inputs = list(inputs or [])
    files = [x.ds for x in inputs]
    if len(files) > MAX_INPUTS:
        raise UsageError(
            f"--input may be passed at most {MAX_INPUTS} times; got {len(files)}. "
            'For ensemble members use meta.along "number" on one input'
        )
    datasets = spec_datasets(
        spec, dict(zip(input_ids([x.name for x in inputs]), files, strict=True))
    )
    if not datasets:
        raise UsageError("pass -i/--input, or a --spec with layout.meta.inputs")
    data = [
        {
            "uid": key,
            "type": "scatter",
            "name": trace_label(d, i),
            "meta": {"bind": "series", "source": {"input": key}},
        }
        for i, (key, d) in enumerate(datasets.items())
    ]
    base = skeleton("plot-timeseries", datasets, data)
    user = spec.data if spec is not None else {}
    merged = inherit_from_first(merge_spec(base, user), datasets)
    datasets = keep_mixed_precip_as_rates(merged, datasets)
    warn_mixed_units(merged, datasets)
    warn_disjoint_dates(merged, datasets)
    return run(merged, None, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot_timeseries)

if __name__ == "__main__":
    plot_timeseries()
