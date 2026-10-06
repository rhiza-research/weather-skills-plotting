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
"""Render a plain Vega-Lite 6 spec to PNG/JPEG/HTML, with weather-skills Zarrs and GeoJSON bound in as data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from weather_skills_core import UsageError, weather_skill

from weather_skills_plotting import vega
from weather_skills_plotting.qa import report_figure

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.1"

GEOJSON_SUFFIXES = (".geojson", ".json")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class Input:
    """One ``-i NAME=PATH``. The decorator opens Zarr paths (``zarr_paths``) and sets ``.ds``."""

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.kind = "geojson" if path.suffix.lower() in GEOJSON_SUFFIXES else "zarr"
        self.ds = None
        self.geojson = None
        if self.kind == "geojson":
            if not path.is_file():
                raise argparse.ArgumentTypeError(f"GeoJSON input not found: {path}")
            raw = path.read_bytes()
            self.sha256 = hashlib.sha256(raw).hexdigest()
            try:
                self.geojson = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise argparse.ArgumentTypeError(f"{path} is not valid JSON: {exc}") from exc
            if not isinstance(self.geojson, dict) or "type" not in self.geojson:
                raise argparse.ArgumentTypeError(f"{path} is not a GeoJSON object")

    def zarr_paths(self):
        return [self.path] if self.kind == "zarr" else []

    def value(self):
        return self.geojson if self.kind == "geojson" else self.ds

    def to_dict(self):
        out = {"name": self.name, "path": str(self.path), "kind": self.kind}
        if self.kind == "geojson":
            out["sha256"] = self.sha256
        return out

    def __repr__(self):
        return f"{self.name}={self.path}"


def parse_input(text: str) -> Input:
    """``NAME=PATH`` (or a bare ``PATH``, named ``data``)."""
    name, sep, path = text.partition("=")
    if not sep:
        name, path = "data", text
    if not _NAME_RE.match(name):
        raise argparse.ArgumentTypeError(
            f"-i {text!r}: NAME must start with a letter or _ and use letters, digits, _ or -"
        )
    if not path:
        raise argparse.ArgumentTypeError(f"-i {text!r}: missing PATH after {name}=")
    return Input(name, Path(path))


def parse_spec(text: str) -> dict:
    """Inline JSON, a path to a JSON file, or ``-`` for stdin."""
    if text == "-":
        raw, where = sys.stdin.read(), "stdin"
    elif text.lstrip().startswith("{"):
        raw, where = text, "--spec"
    else:
        path = Path(text)
        if not path.is_file():
            raise argparse.ArgumentTypeError(
                f"--spec {text!r} is neither a JSON object nor an existing file"
            )
        raw, where = path.read_text(encoding="utf-8"), str(path)
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{where} is not valid JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise argparse.ArgumentTypeError(f"{where} must be a JSON object (a Vega-Lite spec)")
    return spec


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or more")
    return value


def _named(inputs) -> dict:
    named = {}
    for item in inputs or []:
        if item.name in named:
            raise UsageError(f"-i name {item.name!r} is given twice; each input needs its own NAME")
        named[item.name] = item.value()
    return named


def _emit(lines, file=sys.stdout):
    for line in lines:
        print(line, file=file)


@weather_skill(name="plot-vega", version=_SKILL_VERSION)
@weather_skill.argument(
    "-i",
    "--input",
    dest="inputs",
    action="append",
    type=parse_input,
    default=None,
    metavar="NAME=PATH",
    help=(
        "Named input, repeatable. A Zarr, or a .geojson/.json file (e.g. from resolve-region). "
        'Bind it in the spec with {"zarr": NAME} or {"geojson": NAME} under datasets. '
        "A single bare PATH is named data."
    ),
)
@weather_skill.argument(
    "--spec",
    type=parse_spec,
    default=None,
    help=(
        "The Vega-Lite 6 spec with data bindings: inline JSON, a file path, or - for stdin. "
        "Required except with --describe."
    ),
)
@weather_skill.argument(
    "--scale",
    type=float,
    default=2.0,
    help="Pixel ratio for PNG/JPEG (default 2: a 600-px-wide view gives a 1200-px image).",
)
@weather_skill.argument(
    "--describe",
    action="store_true",
    probe=True,
    help=(
        "Print each input's dims, coords, variables (long_name, units, aggregation_period) and "
        "derived field sources; with --spec also the rows each binding produces and every "
        "default that would apply. Renders nothing."
    ),
)
@weather_skill.argument(
    "--dump-spec",
    nargs="?",
    const="-",
    default=None,
    metavar="PATH",
    probe=True,
    help=(
        "Write the final Vega-Lite (rows inlined, every default written out) to PATH or "
        "stdout (-) and skip rendering. Pastes into https://vega.github.io/editor/ as-is."
    ),
)
@weather_skill.argument(
    "--dump-spec-rows",
    type=_positive_int,
    default=None,
    metavar="N",
    help="With --dump-spec, keep only the first N rows of each dataset (for reading).",
)
@weather_skill.argument(
    "--max-rows",
    type=_positive_int,
    default=vega.MAX_ROWS,
    metavar="N",
    help=f"Fail when the bindings produce more than N rows in total (default {vega.MAX_ROWS}).",
)
def plot_vega(
    output,
    inputs=None,
    spec=None,
    scale=2.0,
    describe=False,
    dump_spec=None,
    dump_spec_rows=None,
    max_rows=vega.MAX_ROWS,
    **kwargs,
):
    """Render a plain Vega-Lite 6 spec to PNG/JPEG/HTML, binding weather-skills Zarrs and GeoJSON as data."""
    named = _named(inputs)
    if describe:
        _emit(vega.describe_inputs(named))
        if spec is not None:
            _emit(vega.describe_bindings(vega.prepare(spec, named, max_rows=max_rows)))
        return None
    if spec is None:
        raise UsageError("--spec is required (inline JSON, a file path, or - for stdin)")
    if dump_spec is not None:
        prep = vega.prepare(spec, named, max_rows=max_rows)
        _emit(vega.describe_bindings(prep), file=sys.stderr)
        text = json.dumps(vega.truncate_rows(prep.spec, dump_spec_rows), indent=2)
        if dump_spec == "-":
            print(text)
        else:
            Path(dump_spec).write_text(text + "\n", encoding="utf-8")
            print(f"Wrote: {dump_spec}", file=sys.stderr)
        return None
    if output is None:
        raise UsageError("--output is required unless --describe or --dump-spec is set")
    if Path(output).suffix.lower() not in vega.OUTPUT_SUFFIXES:
        raise UsageError(f"--output {output}: use one of {list(vega.OUTPUT_SUFFIXES)}")
    prep = vega.render(spec, named, Path(output), scale=scale, max_rows=max_rows)
    _emit(vega.describe_bindings(prep))
    if Path(output).suffix.lower() in (".png", ".jpg", ".jpeg"):
        report_figure(output, prep.bound_datasets())
    return Path(output)


if __name__ == "__main__":
    plot_vega()
