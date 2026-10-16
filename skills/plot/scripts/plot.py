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
"""Render a map, time series, xy scatter, or wind rose from weather-skills Zarrs as PNG or HTML."""

import argparse
from pathlib import Path

from weather_skills_core import UsageError, weather_skill
from weather_skills_core.cf import cf_dim

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import (
    input_ids,
    parse_input,
    run,
    skeleton,
    spec_datasets,
    split_name,
)
from weather_skills_plotting.geodata import point_dim
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.2"

LAYER_KINDS = ("heatmap", "contour", "scatter", "quiver", "outline", "mask")
_ZARR_LAYERS = frozenset({"heatmap", "contour", "scatter", "quiver"})


class LayerArg:
    """``--layer KIND:PATH[=NAME]``. The decorator opens Zarr layers (``.ds``)."""

    def __init__(self, kind: str, path: str, name: str | None):
        self.kind, self.path, self.name, self.ds = kind, path, name, None

    def zarr_paths(self):
        return [Path(self.path)] if self.kind in _ZARR_LAYERS else []

    def __str__(self):
        # Provenance records str(); keep the flag's own form.
        return f"{self.kind}:{self.path}" + (f"={self.name}" if self.name else "")


def parse_layer(value):
    kind, sep, path = str(value).partition(":")
    kind = kind.strip().lower()
    if not sep or not path.strip() or kind not in LAYER_KINDS:
        raise argparse.ArgumentTypeError(
            f"--layer expects KIND:PATH[=NAME] with KIND one of {', '.join(LAYER_KINDS)}; "
            f"got {value!r}"
        )
    return LayerArg(kind, *split_name(path.strip(), "--layer"))


def _default_trace(uid: str, ds, *, xaxis=None) -> dict:
    """Heatmap for a lat/lon grid, station markers for points, else a line."""
    source = {"input": uid}
    lat, lon = cf_dim(ds, "latitude"), cf_dim(ds, "longitude")
    if point_dim(ds) is not None:
        trace = {"type": "scatter", "meta": {"bind": "points", "source": source}}
    elif lat in ds.dims and lon in ds.dims:
        trace = {"type": "heatmap", "meta": {"source": source}}
    else:
        trace = {"type": "scatter", "meta": {"source": source}}
    trace["uid"] = uid
    if xaxis:
        trace.update(xaxis=xaxis, yaxis="y" + xaxis[1:])
    return trace


def _layer_traces(layers):
    data, datasets, mask = [], {}, None
    for uid, layer in zip(input_ids([x.name for x in layers]), layers, strict=True):
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
    dest="inputs",
    type=parse_input,
    action="append",
    help="Input Zarr as PATH or PATH=NAME. Repeat for side-by-side maps, one panel per file on "
    "its own grid. In --spec the input is uid NAME, else its position: 0, 1, …. Exclusive with "
    "data layers.",
)
@weather_skill.argument(
    "--layer",
    action="append",
    type=parse_layer,
    help="KIND:PATH or KIND:PATH=NAME layer drawn on one shared map; repeat to stack, bottom "
    "first. Kinds: heatmap, contour, scatter (stations), quiver (u/v), outline (GeoJSON), mask "
    "(GeoJSON). In --spec the layer is uid NAME, else its position: 0, 1, ….",
)
@weather_skill.argument("--spec", type=parse_spec_arg, help=SPEC_ARGUMENT_HELP)
@weather_skill.argument(
    "--theme-file",
    help="Theme JSON/TOML: {template: <Plotly template>, palettes: {name: {colors, bounds}}}.",
)
@weather_skill.argument("--dump-spec", nargs="?", const="-", probe=True, help=DUMP_SPEC_HELP)
def plot(
    inputs,
    output,
    layer,
    spec,
    theme_file,
    dump_spec,
    **kwargs,
):
    """Render a map, time series, xy scatter, or wind rose from weather-skills Zarrs."""
    inputs = list(inputs or [])
    files = [x.ds for x in inputs]
    layers = list(layer or [])
    # Boundaries and masks go on -i maps too: an outline on every panel.
    shapes = [x for x in layers if x.kind in ("outline", "mask")] if files else []
    if shapes and len(shapes) == len(layers):
        layers = []
    if files and layers:
        raise UsageError(
            "pass -i/--input or --layer, not both (-i takes only outline: and mask: layers)"
        )
    layout = {}
    if layers:
        data, datasets, mask = _layer_traces(layers)
        if mask:
            layout["meta"] = {"geo": {"mask_geojson": mask}}
    else:
        datasets = dict(zip(input_ids([x.name for x in inputs]), files, strict=True))
        data = [
            _default_trace(key, d, xaxis=None if i == 0 else f"x{i + 1}")
            for i, (key, d) in enumerate(datasets.items())
        ]
        for j, shape in enumerate(shapes):
            if shape.kind == "mask":
                layout["meta"] = {"geo": {"mask_geojson": shape.path}}
                continue
            for i in range(len(datasets)):
                outline = {
                    "uid": f"outline{j + 1}" + (f"-{i + 1}" if i else ""),
                    "type": "scatter",
                    "meta": {"bind": "geojson", "source": {"geojson": shape.path}},
                }
                if i:
                    outline.update(xaxis=f"x{i + 1}", yaxis=f"y{i + 1}")
                data.append(outline)
    datasets = spec_datasets(spec, datasets)
    if not datasets and not any((t.get("meta") or {}).get("bind") == "geojson" for t in data):
        if spec is None or not (spec.data.get("data")):
            raise UsageError(
                "pass -i/--input, --layer, or a --spec with data and layout.meta.inputs"
            )
    base = skeleton("plot", datasets, data)
    if layout.get("meta"):
        base["layout"]["meta"].update(layout["meta"])
    return run(base, spec, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot)

if __name__ == "__main__":
    plot()
