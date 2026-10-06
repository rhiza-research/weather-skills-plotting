"""Plotly figures from weather-skills standard dataset Zarrs.

The spec is a standard Plotly figure; weather-skills bindings live in each
trace's ``meta`` and in ``layout.meta``.

=====================  ========================================================
Module                 Role
=====================  ========================================================
:mod:`.spec`           Load, merge (by uid / name), validate, dump the spec
:mod:`.bind`           Fill traces from datasets (``meta.bind`` modes)
:mod:`.figure`         Panels, color axes, overlays → ``go.Figure``
:mod:`.layout`         Templates and the map panel grid
:mod:`.palettes`       CHC precipitation / SPI class palettes, theme files
:mod:`.geodata`        Natural Earth overlays, spatial subsets, extents
:mod:`.labels`         Date and panel labels
:mod:`.wind`           u/v detection, arrows, wind-rose histograms, xy pairing
:mod:`.qa`             Pixel hash + finite-data report printed by ``export()``
=====================  ========================================================
"""

from __future__ import annotations

from pathlib import Path

from weather_skills_plotting.spec import SPEC_VERSION, dump_spec, load_spec, merge_spec, validate

__all__ = [
    "SPEC_VERSION",
    "SpecArg",
    "compile",
    "dump_spec",
    "export",
    "load_spec",
    "merge_spec",
    "validate",
]

OUTPUT_SUFFIXES = (".png", ".jpg", ".jpeg", ".html", ".htm")


class SpecArg:
    """A parsed ``--spec``. The skill decorator opens the Zarrs it lists.

    ``layout.meta.inputs`` maps input ids to paths; those are opened only
    when the command line names no dataset files.
    """

    def __init__(self, data: dict):
        self.data = data
        self.ds = None
        self.datasets = None

    def to_dict(self) -> dict:
        """What provenance records for ``--spec``: the spec itself, not an object repr."""
        return self.data

    def input_paths(self) -> dict:
        return dict(((self.data.get("layout") or {}).get("meta") or {}).get("inputs") or {})

    def zarr_paths(self):
        return [Path(p) for p in self.input_paths().values()]

    def opened(self) -> dict:
        """``{input id: Dataset}`` for the paths in ``layout.meta.inputs``."""
        opened = list(self.datasets or ([self.ds] if self.ds is not None else []))
        return dict(zip(self.input_paths(), opened, strict=False))


def parse_spec_arg(value):
    """Argparse converter for ``--spec`` → :class:`SpecArg`."""
    from weather_skills_plotting.spec import parse_plot_spec

    return SpecArg(parse_plot_spec(value))


def compile(spec, datasets, *, theme=None):
    """Compile a spec against ``{input id: Dataset}`` into a Plotly figure."""
    from weather_skills_plotting.figure import compile_figure

    if isinstance(spec, SpecArg):
        spec = spec.data
    return compile_figure(spec, datasets, theme=theme)


def export(fig, output, *, datasets=None, scale=None):
    """Write ``output`` (.png, .jpg or .html) and print the QA lines for images.

    Images print a pixel ``plot hash`` and whether the plotted data is all-NaN.
    HTML embeds plotly.js so the file works offline.
    """
    from weather_skills_core.errors import UsageError

    output = Path(output)
    suffix = output.suffix.lower()
    if suffix not in OUTPUT_SUFFIXES:
        raise UsageError(
            f"output {output.name!r} must end in .png, .jpg or .html (got {suffix or 'no suffix'})"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix in (".html", ".htm"):
        fig.write_html(output, include_plotlyjs=True, full_html=True)
        return output
    fig.write_image(output, scale=scale)
    from weather_skills_plotting.qa import report_figure

    report_figure(output, datasets)
    return output
