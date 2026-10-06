# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3",
#   "vl-convert-python>=1.9",
#   "numpy",
#   "pandas",
#   "xarray",
#   "zarr>=3",
#   "shapely>=2.1",
#   "contourpy>=1.3",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""Prototype of the planned ``plot`` CLI (see ../DESIGN.md, Command line). No provenance stamp or QA lines yet.

uv run plot.py -i obs=/tmp/week.zarr --geojson region=/tmp/KEN.geojson --spec map.json -o map.png
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402


def named(values, flag):
    out = {}
    for v in values or []:
        name, sep, path = v.partition("=")
        if not sep:
            if flag == "-i" and len(values) == 1:
                name, path = "data", v
            else:
                sys.exit(f"{flag} {v!r}: expected NAME=PATH")
        out[name] = Path(path)
    return out


def load_spec(arg):
    if arg == "-":
        return json.load(sys.stdin)
    if arg.lstrip().startswith("{"):
        return json.loads(arg)
    return json.loads(Path(arg).read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-i", "--input", action="append", help="NAME=PATH input Zarr (repeatable)")
    p.add_argument("--geojson", action="append", help="NAME=PATH vector layer (repeatable)")
    p.add_argument("--spec", required=True, help="Vega-Lite spec with bindings: JSON, a file, or -")
    p.add_argument("-o", "--output", type=Path, help="PNG path")
    p.add_argument("--scale", type=float, default=2.0)
    p.add_argument(
        "--dump-spec",
        help="write the bound + defaulted Vega-Lite here (- for stdout) and skip the PNG",
    )
    a = p.parse_args()

    spec = load_spec(a.spec)
    inputs = vlbind.open_inputs(named(a.input, "-i"))
    geojsons = named(a.geojson, "--geojson")
    try:
        if a.dump_spec:
            notes = []
            bound, meta = vlbind.bind_all(spec, inputs, geojsons, notes)
            vlbind.apply_defaults(bound, meta, notes)
            text = json.dumps(bound, indent=2)
            sys.stdout.write(text + "\n") if a.dump_spec == "-" else Path(a.dump_spec).write_text(
                text
            )
            for note in notes:
                print(f"default {note}", file=sys.stderr)
            return
        if not a.output:
            p.error("-o is required unless --dump-spec is given")
        stats = vlbind.render(spec, inputs, a.output, geojsons=geojsons, scale=a.scale)
    except vlbind.SpecError as exc:
        sys.exit(f"spec error: {exc}")
    for note in stats.pop("defaults"):
        print(f"default {note}")
    print(f"rows {stats['rows']}  render {stats['render_s']}s  spec {stats['json_mb']} MB")
    print(f"Wrote: {a.output}")


if __name__ == "__main__":
    main()
