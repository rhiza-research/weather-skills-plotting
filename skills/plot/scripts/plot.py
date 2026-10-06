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
"""Render a map, time series, xy scatter, or wind rose from weather-skills Zarrs as PNG or HTML."""

import argparse
from pathlib import Path

from weather_skills_core import Dataset, UsageError, weather_skill
from weather_skills_core.cf import cf_dim

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import letter, run, skeleton, spec_datasets
from weather_skills_plotting.geodata import point_dim
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.2"

LAYER_KINDS = ("heatmap", "contour", "scatter", "quiver", "outline", "mask")
_ZARR_LAYERS = frozenset({"heatmap", "contour", "scatter", "quiver"})


class LayerArg:
    """``--layer KIND:PATH``. The decorator opens Zarr layers (``.ds``)."""

    def __init__(self, kind: str, path: str):
        self.kind, self.path, self.ds = kind, path, None

    def zarr_paths(self):
        return [Path(self.path)] if self.kind in _ZARR_LAYERS else []


def parse_layer(value):
    kind, sep, path = str(value).partition(":")
    kind = kind.strip().lower()
    if not sep or not path.strip() or kind not in LAYER_KINDS:
        raise argparse.ArgumentTypeError(
            f"--layer expects KIND:PATH with KIND one of {', '.join(LAYER_KINDS)}; got {value!r}. "
            "Style a layer in --spec on the data[] entry with uid a, b, … (in --layer order)"
        )
    return LayerArg(kind, path.strip())


def _default_trace(uid: str, ds, *, xaxis=None) -> dict:
    """Heatmap for a lat/lon grid, station markers for points, else a line."""
    source = {"input": uid}
    lat, lon = cf_dim(ds, "latitude"), cf_dim(ds, "longitude")
    if point_dim(ds) is not None:
        trace = {"type": "scatter", "meta": {"bind": "points", "source": source}}
    elif lat in ds.dims and lon in ds.dims:
        trace = {"type": "heatmap", "meta": {"source": source}}
    else:
        trace = {"type": "scatter", "meta": {"bind": "series", "source": source}}
    trace["uid"] = uid
    if xaxis:
        trace.update(xaxis=xaxis, yaxis="y" + xaxis[1:])
    return trace


def _layer_traces(layers):
    data, datasets, mask = [], {}, None
    for i, layer in enumerate(layers):
        uid = letter(i)
        if layer.kind == "mask":
            mask = layer.path
            continue
        if layer.kind == "outline":
            data.append(
                {
                    "uid": uid,
                    "type": "scatter",
                    "meta": {"bind": "geojson", "source": {"geojson": layer.path}},
                }
            )
            continue
        datasets[uid] = layer.ds
        source = {"input": uid}
        if layer.kind in ("heatmap", "contour"):
            data.append({"uid": uid, "type": layer.kind, "meta": {"source": source}})
        elif layer.kind == "scatter":
            data.append(
                {"uid": uid, "type": "scatter", "meta": {"bind": "points", "source": source}}
            )
        else:
            data.append(
                {"uid": uid, "type": "heatmap", "meta": {"bind": "speed", "source": source}}
            )
            data.append(
                {
                    "uid": f"{uid}-arrows",
                    "type": "scatter",
                    "meta": {"bind": "arrows", "source": source},
                }
            )
    return data, datasets, mask


@weather_skill(name="plot", version=_SKILL_VERSION)
@weather_skill.argument(
    "-i",
    "--input",
    type=Dataset("any"),
    action="append",
    required=False,
    help="Input Zarr. Repeat for side-by-side maps, one panel per file on its own grid "
    "(input ids a, b, … in order). Exclusive with --layer and --x/--y.",
)
@weather_skill.argument(
    "--x",
    dest="x_ds",
    type=Dataset("any"),
    required=False,
    default=None,
    help="X series Zarr for an xy scatter (input id x).",
)
@weather_skill.argument(
    "--y",
    dest="y_ds",
    type=Dataset("any"),
    required=False,
    default=None,
    help="Y series Zarr for an xy scatter (input id y).",
)
@weather_skill.argument(
    "--layer",
    action="append",
    default=None,
    type=parse_layer,
    help="KIND:PATH layer drawn on one shared map; repeat to stack. Kinds: heatmap, contour, "
    "scatter (stations), quiver (u/v), outline (GeoJSON), mask (GeoJSON). Trace uids are a, b, … "
    "in order.",
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
def plot(
    ds,
    output,
    layer=None,
    x_ds=None,
    y_ds=None,
    spec=None,
    theme_file=None,
    dump_spec=None,
    **kwargs,
):
    """Render a map, time series, xy scatter, or wind rose from weather-skills Zarrs."""
    files = [d for d in (ds or []) if d is not None]
    layers = list(layer or [])
    if sum(bool(x) for x in (files, layers, x_ds is not None or y_ds is not None)) > 1:
        raise UsageError("pass one of -i/--input, --layer, or --x/--y")
    if (x_ds is None) != (y_ds is None):
        raise UsageError("an xy scatter needs both --x and --y")
    layout = {}
    if layers:
        data, datasets, mask = _layer_traces(layers)
        if mask:
            layout["meta"] = {"geo": {"mask_geojson": mask}}
    elif x_ds is not None:
        datasets = {"x": x_ds, "y": y_ds}
        data = [
            {
                "uid": "xy",
                "type": "scatter",
                "meta": {"bind": "pair", "x": {"input": "x"}, "y": {"input": "y"}},
            }
        ]
    else:
        datasets = {letter(i): d for i, d in enumerate(files)}
        data = [
            _default_trace(key, d, xaxis=None if i == 0 else f"x{i + 1}")
            for i, (key, d) in enumerate(datasets.items())
        ]
    datasets = spec_datasets(spec, datasets)
    if not datasets and not any((t.get("meta") or {}).get("bind") == "geojson" for t in data):
        if spec is None or not (spec.data.get("data")):
            raise UsageError(
                "pass -i/--input, --layer, --x/--y, or a --spec with data and layout.meta.inputs"
            )
    base = skeleton("plot", datasets, data)
    if layout.get("meta"):
        base["layout"]["meta"].update(layout["meta"])
    return run(base, spec, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot)

if __name__ == "__main__":
    plot()
