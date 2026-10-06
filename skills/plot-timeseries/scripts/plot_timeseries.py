# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "weather-skills-plotting",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
#   "cf-xarray",
#   "cftime",
#   "numpy",
#   "xarray",
#   "zarr",
#   "pint-xarray>=0.6",
# ]
#
# [tool.uv.sources]
# weather-skills-plotting = { path = "../../..", editable = true }
# ///
"""Overlay one series per input Zarr on a shared time axis, as PNG or HTML."""

import copy
from pathlib import Path

from weather_skills_core import Dataset, UsageError, weather_skill
from weather_skills_core.cf import auto_variable
from weather_skills_core.display_labels import dataset_display_label
from weather_skills_core.units import units_equal, variable_units

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import input_path, letter, run, skeleton, spec_datasets, warn
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP, merge_spec

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.2"

MAX_INPUTS = 26
# meta keys a later trace takes from data[0] when it leaves them unset.
INHERITED_META = ("along", "along_color", "band", "align")
INHERITED_SOURCE = ("variable", "reduce")


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


def inherit_from_first(spec: dict) -> dict:
    """Series settings on data[0] apply to every series that does not set its own."""
    data = spec.get("data") or []
    if len(data) < 2:
        return spec
    first = data[0].get("meta") or {}
    for trace in data[1:]:
        meta = trace.setdefault("meta", {})
        for key in INHERITED_META:
            if key in first and key not in meta:
                meta[key] = copy.deepcopy(first[key])
        source = meta.setdefault("source", {})
        for key in INHERITED_SOURCE:
            if key in (first.get("source") or {}) and key not in source:
                source[key] = copy.deepcopy(first["source"][key])
    return spec


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
        if units:
            by_axis.setdefault(trace.get("yaxis") or "y", []).append((trace.get("uid"), units))
    for axis, items in by_axis.items():
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
    type=Dataset("any"),
    action="append",
    required=False,
    help="Input Zarr; repeat once per series (legend order; trace uids a, b, …).",
)
@weather_skill.argument("--spec", default=None, type=parse_spec_arg, help=SPEC_ARGUMENT_HELP)
@weather_skill.argument(
    "--theme-file",
    default=None,
    help="Theme JSON/TOML: {template: <Plotly template>, palettes: {…}}.",
)
@weather_skill.argument(
    "--dump-spec", nargs="?", const="-", default=None, probe=True, help=DUMP_SPEC_HELP
)
def plot_timeseries(ds, output, spec=None, theme_file=None, dump_spec=None, **kwargs):
    """Overlay one series per input Zarr on a shared time axis."""
    files = [d for d in (ds or []) if d is not None]
    if len(files) > MAX_INPUTS:
        raise UsageError(
            f"--input may be passed at most {MAX_INPUTS} times; got {len(files)}. "
            'For ensemble members use meta.along "number" on one input'
        )
    datasets = spec_datasets(spec, {letter(i): d for i, d in enumerate(files)})
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
    merged = inherit_from_first(merge_spec(base, user))
    warn_mixed_units(merged, datasets)
    return run(merged, None, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot_timeseries)

if __name__ == "__main__":
    plot_timeseries()
