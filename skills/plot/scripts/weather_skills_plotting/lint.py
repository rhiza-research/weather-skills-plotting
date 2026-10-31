"""Check that a Plotly figure carries data only as @bindings.

    from weather_skills_plotting.lint import UnboundDataError, check_bindings

    check_bindings(figure)  # a dict or JSON text; raises UnboundDataError

The spec styles a figure in Jsonnet and binds its data with @references that
refs.resolve fills in from the inputs. plot runs this on the rendered figure,
before binding: it raises if anything that can put data on the chart holds
something other than bindings.

- data keys (``x``, ``z``, ``dimensions[].values``, ...): a binding, or a list
  made only of bindings.
- per-point keys (``marker.color``, ``text``, ...): one value is styling, but
  a list must be bindings.
- generator keys (``x0``/``dx``, ``base``, error-bar ``value``, ...): scalars
  that make up a value for every point. Error bars that would fall back to
  Plotly's default ±10 also fail.
- shapes, annotations, images and selections on a data axis: their coordinates.
- menu and slider ``args``: may not set data keys or coordinates to literals,
  or carry inline frames.
- unknown keys, since only keys Plotly defines can be checked.

It checks bindings only; validate the filled figure with plotly afterwards.
"""

import functools
import json
import re
from dataclasses import dataclass

import plotly.graph_objects as go

from weather_skills_plotting import data_keys as keys

# A reference: a string that starts with one @ ('@@' starts literal text).
BINDING = re.compile(r"^@[^@]", re.S)
AXIS_REF = re.compile(r"^[xy]\d*$")  # a data axis; 'paper' and 'x domain' are not
SUBPLOT_KEY = re.compile(rf"^({'|'.join(go.Layout._subplotid_prop_names)})\d+$")

# Scalars from which Plotly makes up coordinates or offsets for every point.
GENERATORS = {
    "x0",
    "dx",
    "y0",
    "dy",
    "a0",
    "da",
    "b0",
    "db",
    "r0",
    "dr",
    "theta0",
    "dtheta",
    "base",
    "delta.reference",
    "gauge.threshold.value",
    *(f"error_{axis}.{k}" for axis in "xyz" for k in ("value", "valueminus")),
}

# Layout collections drawn in data coordinates when anchored to an axis: (x keys, y keys).
ANCHORED = {
    "shapes": ({"x0", "x1", "xanchor", "path"}, {"y0", "y1", "yanchor", "path"}),
    "selections": ({"x0", "x1", "path"}, {"y0", "y1", "path"}),
    "annotations": ({"x"}, {"y"}),
    "images": ({"x", "sizex"}, {"y", "sizey"}),
}
MENU_ARGS = {
    "updatemenus[].buttons[].args",
    "updatemenus[].buttons[].args2",
    "sliders[].steps[].args",
}
FRAME_KEYS = {"data", "layout", "name", "group", "traces", "baseframe"}


class UnboundDataError(ValueError):
    """Raised when part of a figure that can hold data holds something other than @bindings."""

    def __init__(self, problems):
        self.problems = problems  # [(path, message), ...]
        listing = "\n".join(f"  {path}: {message}" for path, message in problems)
        super().__init__(f"figure has {len(problems)} binding problem(s):\n{listing}")


def check_bindings(figure, pattern=BINDING):
    """Raise UnboundDataError unless every data-carrying key in ``figure`` holds @bindings.

    ``figure`` is a Plotly figure as a dict or JSON text; ``pattern`` is the regex a
    binding must match. Every problem is collected before raising, so one error lists
    them all.
    """
    if isinstance(figure, (str, bytes)):
        figure = json.loads(figure)
    problems = _Checker(pattern).check(figure)
    if problems:
        raise UnboundDataError(problems)


@dataclass(frozen=True)
class _Schema:
    children: dict  # class path -> {key name: (validator key, spec)}
    trace_types: frozenset
    trace_data: frozenset  # trace paths whose values must be bindings
    trace_may: frozenset  # trace paths whose lists must be bindings


@functools.cache
def _schema():
    by_parent = keys.load_validators()
    trace_types = frozenset(keys.trace_types(by_parent))
    sets = [keys.classify(by_parent, t) for t in trace_types]
    trace_data = frozenset(p for s in sets for p in s["always"] + s["schema_silent"]) | GENERATORS
    return _Schema(
        children={
            parent: {spec["params"]["plotly_name"]: (key, spec) for key, spec in specs.items()}
            for parent, specs in by_parent.items()
        },
        trace_types=trace_types,
        trace_data=trace_data,
        trace_may=frozenset(p for s in sets for p in s["may"]) - trace_data,
    )


def leaves(value):
    if isinstance(value, list):
        for item in value:
            yield from leaves(item)
    else:
        yield value


def has_dict(value):
    return isinstance(value, dict) or (isinstance(value, list) and any(map(has_dict, value)))


def flatten(value, prefix=""):
    """Dotted (key, value) pairs of nested dicts, e.g. a restyle payload."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(value, list) and has_dict(value):
        for v in value:
            yield from flatten(v, prefix)
    elif prefix:
        yield prefix, value


def on_axis(ref):
    """Whether an xref/yref places coordinates on a data axis (Plotly's default when unset)."""
    if ref is None:
        return True
    if isinstance(ref, list):
        return any(on_axis(r) for r in ref)
    return isinstance(ref, str) and bool(AXIS_REF.match(ref))


class _Checker:
    def __init__(self, pattern):
        self.pattern = pattern
        self.schema = _schema()
        self.problems = []

    def is_binding(self, value):
        return isinstance(value, str) and bool(self.pattern.match(value))

    def problem(self, path, message):
        self.problems.append((path, message))

    def require(self, value, path, what):
        bad = next((v for v in leaves(value) if not self.is_binding(v)), None)
        if bad is not None or value == []:
            shown = json.dumps(bad, ensure_ascii=False)[:60] if bad is not None else "[]"
            self.problem(path, f"{what} needs an @binding, found {shown}")

    def require_if_list(self, value, path, what):
        if isinstance(value, (list, dict)):
            self.require(value, path, f"{what} given per point")

    # ---- figure structure -------------------------------------------------

    def check(self, fig):
        if not isinstance(fig, dict):
            self.problem("<figure>", "expected a JSON object with data/layout/frames")
            return self.problems
        for key in fig.keys() - {"data", "layout", "frames"}:
            self.problem(key, "unknown top-level key, so it can't be checked for data")
        for i, trace in enumerate(fig.get("data", [])):
            self.check_trace(trace, f"data[{i}]")
        if "layout" in fig:
            self.walk(fig["layout"], "layout", "", "layout", "layout")
        for i, frame in enumerate(fig.get("frames", [])):
            self.check_frame(frame, f"frames[{i}]")
        return self.problems

    def check_trace(self, trace, path, trace_type=None):
        if not isinstance(trace, dict):
            return self.problem(path, "expected a trace object")
        trace_type = trace_type or trace.get("type", "scatter")
        if trace_type not in self.schema.trace_types:
            return self.problem(f"{path}.type", f"unknown trace type {trace_type!r}")
        self.walk({k: v for k, v in trace.items() if k != "type"}, trace_type, "", path, "trace")
        self.check_error_bars(trace, path)

    def check_frame(self, frame, path):
        if not isinstance(frame, dict):
            return self.problem(path, "expected a frame object")
        for key in frame.keys() - FRAME_KEYS:
            self.problem(f"{path}.{key}", "unknown frame key, so it can't be checked for data")
        for i, trace in enumerate(frame.get("data", [])):
            self.check_trace(trace, f"{path}.data[{i}]")
        if "layout" in frame:
            self.walk(frame["layout"], "layout", "", f"{path}.layout", "layout")

    def check_template(self, template, path):
        if not isinstance(template, dict):
            return self.problem(path, "expected a template object")
        for key in template.keys() - {"data", "layout"}:
            self.problem(f"{path}.{key}", "unknown template key, so it can't be checked for data")
        for trace_type, traces in template.get("data", {}).items():
            for i, trace in enumerate(traces):
                self.check_trace(trace, f"{path}.data.{trace_type}[{i}]", trace_type)
        if "layout" in template:
            self.walk(template["layout"], "layout", "", f"{path}.layout", "layout")

    def walk(self, obj, class_path, rel, path, context):
        """Check every key of ``obj`` against the schema class at ``class_path``."""
        if not isinstance(obj, dict):
            return self.problem(path, "expected an object")
        children = self.schema.children.get(class_path, {})
        for name, value in obj.items():
            child_path = f"{path}.{name}"
            match = SUBPLOT_KEY.match(name) if class_path == "layout" else None
            lookup = match[1] if match else name
            if lookup not in children:
                self.problem(
                    child_path, f"unknown key for {class_path}, so it can't be checked for data"
                )
                continue
            key, spec = children[lookup]
            kind, child_rel = spec["superclass"], rel + lookup
            if kind in keys.COMPOUND:
                # *defaults keys (shapedefaults, annotationdefaults) have no class of their
                # own: they take the class of one item (layout.shape).
                child_class = key if key in self.schema.children else keys.item_class(spec)
                self.walk(value, child_class, child_rel + ".", child_path, context)
                # A default applies to every shape / annotation / image, so its coordinates
                # on a data axis are checked like an item's.
                collection = child_rel.removesuffix("defaults") + "s"
                if (
                    context == "layout"
                    and child_rel.endswith("defaults")
                    and collection in ANCHORED
                ):
                    self.check_anchored(value, collection, child_path)
            elif kind == "CompoundArrayValidator":
                if not isinstance(value, list):
                    self.problem(child_path, "expected a list")
                    continue
                for i, item in enumerate(value):
                    self.walk(
                        item,
                        keys.item_class(spec),
                        child_rel + "[].",
                        f"{child_path}[{i}]",
                        context,
                    )
                    if context == "layout" and child_rel in ANCHORED:
                        self.check_anchored(item, child_rel, f"{child_path}[{i}]")
            elif kind == "BaseTemplateValidator":
                self.check_template(value, child_path)
            else:
                self.check_leaf(value, spec, child_rel, child_path, context)

    # ---- the rules ------------------------------------------------------

    def check_leaf(self, value, spec, rel, path, context):
        category = keys.leaf_category(rel, spec)
        if rel == "meta":
            self.problem(
                path,
                "plot has no meta keys. A palette is layout: ws.classBar(palette, title) "
                "(or a Plotly colorscale); an outline is a scatter with x: '@NAME.x', "
                "y: '@NAME.y'; data is an @ reference in the Plotly attribute itself (see --recipe)",
            )
        elif context == "trace" and rel in GENERATORS:
            self.require(value, path, f"'{rel}' generates a value for every point and")
        elif category in ("always", "schema_silent"):
            self.require(value, path, "data key")
        elif category == "may" and context == "trace":
            self.require_if_list(value, path, f"'{rel}'")
        elif rel in MENU_ARGS:
            self.check_menu_args(value, path)

    def check_error_bars(self, trace, path):
        # Plotly draws ±10 (percent) by default once error bars are visible without data.
        for axis in "xyz":
            bars = trace.get(f"error_{axis}")
            if not isinstance(bars, dict):
                continue
            visible = bars.get("visible", "array" in bars or "value" in bars)
            bar_type = bars.get("type", "data" if "array" in bars else "percent")
            if not visible or bar_type not in ("percent", "constant"):
                continue
            symmetric = bars.get("symmetric", "arrayminus" not in bars and "valueminus" not in bars)
            for k in ["value"] + ([] if symmetric else ["valueminus"]):
                if k not in bars:
                    self.problem(
                        f"{path}.error_{axis}",
                        f"{bar_type} error bars without '{k}' draw Plotly's default 10; "
                        f"give '{k}' an @binding or use type 'data'",
                    )

    def check_anchored(self, item, collection, path):
        if not isinstance(item, dict):
            return
        x_keys, y_keys = ANCHORED[collection]
        coords = (x_keys if on_axis(item.get("xref")) else set()) | (
            y_keys if on_axis(item.get("yref")) else set()
        )
        if collection == "annotations":
            coords |= {k for k in ("ax", "ay") if on_axis(item.get(f"{k}ref", "pixel"))}
        for k in sorted(coords & item.keys()):
            self.require(item[k], f"{path}.{k}", f"'{k}' is on a data axis and")

    def check_menu_args(self, args, path):
        for key, value in flatten(args):
            norm = re.sub(r"\[\d+\]", "[]", key)
            head = norm.split(".")[0].split("[")[0]
            if head in ("data", "layout", "frames"):
                self.problem(
                    f"{path}.{key}",
                    "args may not carry inline traces or frames; reference frames by name",
                )
            elif norm in self.schema.trace_data:
                self.require(value, f"{path}.{key}", "restyled data key")
            elif norm in self.schema.trace_may:
                # Restyle wraps values per trace, so a per-point array sits one list deeper.
                for item in value if isinstance(value, list) else [value]:
                    self.require_if_list(item, f"{path}.{key}", f"restyled '{norm}'")
            elif head in ANCHORED and (
                norm == head or norm.rpartition(".")[2] in set().union(*ANCHORED[head])
            ):
                self.problem(f"{path}.{key}", f"args may not place {head}; draw them in the layout")
