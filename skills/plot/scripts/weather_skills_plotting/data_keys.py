"""List every Plotly figure JSON key that holds data, for every trace type and layout.

Reads the attribute definitions plotly.py generates from the plotly.js schema
(``plotly/validators/_validators.json``, an internal file) and sorts each leaf key:

- ``always``: a data array (plotly.js ``valType: data_array``), e.g. ``x``,
  ``z``, ``dimensions[].values``. Always one value per point/cell.
- ``array_settings``: also typed ``data_array``, but a list of axis ticks,
  categories or formats rather than plotted values (hand-picked below).
- ``may``: a scalar setting that also accepts a per-point array (plotly.js
  ``arrayOk: true``), e.g. ``marker.color``, ``text``. Data only when the value
  given is an array.
- ``schema_silent``: keys the schema types as plain values that still carry
  data in practice (hand-picked below, with reasons).

The same key can sort differently by trace type (``text`` is a data array on
``heatmap`` but ``arrayOk`` on ``scatter``), so ``any_trace`` lists such keys
under ``may``: look up ``traces[type]`` when the type is known.

Paths are relative to a trace object (``data[i]``) or to ``layout``. ``[]``
marks an array of objects (``dimensions[].values``) and ``*`` a numbered
subplot key (``xaxis*`` = ``xaxis``, ``xaxis2``, ...).

Regenerate the listing:  python -m weather_skills_plotting.data_keys [out.json]
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import plotly
import plotly.graph_objects as go

VALIDATORS = Path(plotly.__file__).parent / "validators" / "_validators.json"

COMPOUND = {"CompoundValidator", "TitleValidator"}
CATEGORIES = ("always", "array_settings", "may", "schema_silent")

# data_array keys that list axis ticks, categories or formats, not plotted values.
ARRAY_SETTING_NAMES = {"tickvals", "ticktext", "categoryarray"}
ARRAY_SETTING_PATHS = {
    "hiddenlabels",  # layout: pie/funnelarea labels hidden from the legend
    "map.layers[].line.dash",  # layout: dash pattern of a map layer's lines
    "columnorder",  # table: display order of columns
    "cells.format",  # table: d3 format string per column
    "header.format",
}

# Typed as strings, indices or free-form values, so neither data_array nor
# arrayOk flags them, but they carry data rather than styling.
SCHEMA_SILENT = {
    "geojson": "GeoJSON object (or URL) holding the shapes being plotted",
    "selectedpoints": "array of point indices selected in this trace",
    "source": "image trace: the image itself as a data URI",
    "node.groups": "sankey: arrays of node indices grouped together",
    "images[].source": "layout: an image as a data URI or URL",
    "map.layers[].source": "layout: GeoJSON or tile source drawn as a map layer",
}


def load_validators():
    """Return ``{parent class path: {validator key: spec}}``."""
    by_parent = defaultdict(dict)
    for key, spec in json.loads(VALIDATORS.read_text()).items():
        by_parent[spec["params"]["parent_name"]][key] = spec
    return by_parent


def trace_types(by_parent):
    return sorted(
        key
        for key, spec in by_parent[""].items()
        if spec["superclass"] == "CompoundValidator" and key != "layout"
    )


def item_class(spec):
    """Class path of one item in a CompoundArrayValidator (``dimensions`` -> ``parcoords.dimension``)."""
    params = spec["params"]
    return f"{params['parent_name']}.{params['data_class_str'].lower()}"


def leaf_category(path, spec):
    """Category of a leaf key at ``path`` (relative, ``[]`` for array items), or None for plain settings."""
    if spec["superclass"] == "DataArrayValidator":
        is_setting = path.rpartition(".")[2] in ARRAY_SETTING_NAMES or path in ARRAY_SETTING_PATHS
        return "array_settings" if is_setting else "always"
    if spec["params"].get("array_ok"):
        return "may"
    if path in SCHEMA_SILENT:
        return "schema_silent"
    return None


def walk(by_parent, class_path, prefix, out):
    for key, spec in by_parent[class_path].items():
        kind = spec["superclass"]
        path = prefix + spec["params"]["plotly_name"]
        if kind in COMPOUND:
            walk(by_parent, key, path + ".", out)
        elif kind == "CompoundArrayValidator":
            walk(by_parent, item_class(spec), path + "[].", out)
        elif category := leaf_category(path, spec):
            out[category].append(path)


def classify(by_parent, root, subplot_keys=()):
    out = {k: [] for k in CATEGORIES}
    walk(by_parent, root, "", out)

    def star(path):
        head, dot, rest = path.partition(".")
        return f"{head}*{dot}{rest}" if head in subplot_keys else path

    return {k: sorted(star(p) for p in v) for k, v in out.items()}


def main(out_path):
    by_parent = load_validators()
    traces = {t: classify(by_parent, t) for t in trace_types(by_parent)}
    # layout.template only holds per-trace-type style defaults; skip it.
    by_parent["layout"].pop("layout.template", None)
    layout = classify(by_parent, "layout", go.Layout._subplotid_prop_names)

    union = {k: {p for t in traces.values() for p in t[k]} for k in CATEGORIES}
    mixed = union["always"] & union["may"]
    union["always"] -= mixed
    union = {k: sorted(v) for k, v in union.items()}
    result = {
        "plotly_version": plotly.__version__,
        "notes": {
            "always": "data_array: always per-point data",
            "array_settings": "data_array-typed lists of ticks, categories or formats, not plotted values",
            "may": "arrayOk: data only when the value is an array",
            "any_trace": f"keys that are data_array on some trace types and arrayOk on others are under 'may': {sorted(mixed)}",
            "schema_silent": SCHEMA_SILENT,
            "encoding": "plotly.py may write 'always' arrays as {dtype, bdata, shape} base64 objects instead of lists",
            "nesting": "frames[].data[] and frames[].layout follow the same rules as data[] and layout",
        },
        "any_trace": union,
        "traces": traces,
        "layout": layout,
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n")

    print(f"plotly {plotly.__version__}: {len(traces)} trace types -> {out_path}")
    for k in CATEGORIES:
        per_trace = sum(len(t[k]) for t in traces.values())
        print(
            f"  {k:14} {per_trace:5} trace keys ({len(union[k])} distinct), {len(layout[k])} layout keys"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "plotly_data_keys.json")
