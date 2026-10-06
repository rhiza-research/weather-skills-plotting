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
"""ECMWF-style mediogram: forecast vs m-climate ensemble boxes at one point, as PNG or HTML."""

from weather_skills_core import Dataset, UsageError, weather_skill
from weather_skills_core.cf import auto_variable, cf_dim
from weather_skills_core.units import variable_label_for_display

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import run, skeleton
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP, merge_spec

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.2"

MAX_STEPS = 6
FORECAST_COLOR = "cyan"
MCLIMATE_COLOR = "red"


def _box(uid, name, color, source):
    return {
        "uid": uid,
        "type": "box",
        "name": name,
        "fillcolor": color,
        "line": {"color": "black"},
        "marker": {"color": "black"},
        "meta": {"bind": "samples", "source": source},
    }


def _variable(ds, user, uid):
    trace = next((t for t in user.get("data") or [] if t.get("uid") == uid), {})
    return ((trace.get("meta") or {}).get("source") or {}).get("variable") or auto_variable(ds)


@weather_skill(name="plot-mediogram", version=_SKILL_VERSION)
@weather_skill.argument(
    "-i",
    "--input",
    type=Dataset("any"),
    action="append",
    required=False,
    help="Pass twice: the forecast Zarr, then the m-climate Zarr (input ids forecast, mclimate).",
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
def plot_mediogram(ds, output, spec=None, theme_file=None, dump_spec=None, **kwargs):
    """ECMWF-style mediogram: forecast vs m-climate ensemble distributions at a point."""
    files = [d for d in (ds or []) if d is not None]
    if not files and spec is not None:
        opened = spec.opened()
        files = [opened.get("forecast"), opened.get("mclimate")]
    if len(files) != 2 or any(f is None for f in files):
        raise UsageError(
            "pass -i twice (forecast, then m-climate), or a --spec whose layout.meta.inputs "
            "names forecast and mclimate"
        )
    datasets = {"forecast": files[0], "mclimate": files[1]}
    user = spec.data if spec is not None else {}
    point = (((user.get("layout") or {}).get("meta") or {}).get("geo") or {}).get("point")
    if point is None:
        raise UsageError(
            'set the point in --spec: {"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}'
        )
    das = {}
    for key, d in datasets.items():
        var = _variable(d, user, key)
        if var not in d:
            raise UsageError(f"{key} has no variable {var!r}; available: {', '.join(d.data_vars)}")
        da = d[var]
        if "number" not in da.dims or "step" not in da.dims:
            raise UsageError(f"{key} input needs 'number' and 'step' dims; got {list(da.dims)}")
        das[key] = da
    n_steps = min(das["forecast"].sizes["step"], das["mclimate"].sizes["step"], MAX_STEPS)
    steps = {"step": list(range(n_steps))}
    fc = {"input": "forecast", "isel": steps}
    data = [
        _box("forecast", "forecast", FORECAST_COLOR, fc),
        _box("mclimate", "m-climate", MCLIMATE_COLOR, {"input": "mclimate", "isel": steps}),
        {
            "uid": "forecast-mean",
            "type": "scatter",
            "name": "forecast mean",
            "line": {"color": "black"},
            "marker": {"color": "black"},
            "meta": {"bind": "samples", "source": fc},
        },
    ]
    da = das["forecast"]
    lat, lon = cf_dim(da, "latitude"), cf_dim(da, "longitude")
    snapped = da.sel({lat: point["lat"], lon: point["lon"]}, method="nearest")
    qty = variable_label_for_display(da, include_units=False)
    title = f"Mediogram: {qty} at lat={float(snapped[lat]):g}, lon={float(snapped[lon]):g}"
    layout = {
        "title": {"text": title},
        "boxmode": "group",
        "xaxis": {"title": {"text": "Forecast step"}},
    }
    base = skeleton("plot-mediogram", datasets, data, layout)
    return run(merge_spec(base, user), None, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot_mediogram)

if __name__ == "__main__":
    plot_mediogram()
