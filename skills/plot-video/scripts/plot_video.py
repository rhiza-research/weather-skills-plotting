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
"""Animate a gridded Zarr through time (or forecast step) as an interactive HTML map."""

from weather_skills_core import Dataset, UsageError, weather_skill
from weather_skills_core.cf import cf_dim

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import run, skeleton, spec_datasets
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.1"


@weather_skill(name="plot-video", version=_SKILL_VERSION)
@weather_skill.argument(
    "-i",
    "--input",
    type=Dataset("spatial"),
    required=False,
    help="Gridded Zarr with a time or step dim (input id a). Each value becomes one frame.",
)
@weather_skill.argument("--spec", default=None, type=parse_spec_arg, help=SPEC_ARGUMENT_HELP)
@weather_skill.argument(
    "--theme-file",
    default=None,
    help="Theme JSON/TOML: {template: <Plotly template>, palettes: {name: {colors, bounds}}}.",
)
@weather_skill.argument(
    "--dump-spec", nargs="?", const="-", default=None, probe=True, help=DUMP_SPEC_HELP
)
def plot_video(ds, output, spec=None, theme_file=None, dump_spec=None, **kwargs):
    """Animate a gridded Zarr through time (or forecast step) as an interactive HTML map."""
    datasets = spec_datasets(spec, {"a": ds} if ds is not None else {})
    if not datasets:
        raise UsageError("pass -i/--input, or a --spec with layout.meta.inputs")
    if len(datasets) > 1:
        raise UsageError("plot-video animates one gridded input; got several in layout.meta.inputs")
    grid = next(iter(datasets.values()))
    lat, lon = cf_dim(grid, "latitude"), cf_dim(grid, "longitude")
    if lat not in grid.dims or lon not in grid.dims:
        raise UsageError(
            f"plot-video needs a latitude/longitude grid; got dims {list(grid.dims)}. "
            "For station or 1-D data use plot or plot-timeseries"
        )
    data = [{"uid": "a", "type": "heatmap", "meta": {"source": {"input": "a"}}}]
    base = skeleton("plot-video", datasets, data)
    return run(base, spec, datasets, output, dump_spec, theme_file=theme_file, animate=True)


install_spec_help(plot_video)

if __name__ == "__main__":
    plot_video()
