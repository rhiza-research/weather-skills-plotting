"""Validate, compile and render: Vega-Lite (with bindings) -> Vega -> PNG / JPEG / HTML."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from weather_skills_plotting.vega.bind import bind_all
from weather_skills_plotting.vega.defaults import apply_defaults, derived_names, iter_views
from weather_skills_plotting.vega.errors import DataError, SpecError

VL_VERSION = "6.4"
VL_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"
COMPOSITION_KEYS = ("layer", "hconcat", "vconcat", "concat", "facet", "repeat", "mark")
OUTPUT_SUFFIXES = (".png", ".jpg", ".jpeg", ".html", ".htm")
WARN_ROWS = 150_000
MAX_ROWS = 500_000
USERMETA_KEYS = ("defaults", "classed_legend", "seal_cells")


@dataclass
class Prepared:
    """A spec after binding, defaults, lint and validation: plain Vega-Lite with rows inlined."""

    spec: dict
    meta: dict
    notes: list[str] = field(default_factory=list)
    classed: dict = field(default_factory=dict)
    usermeta: dict = field(default_factory=dict)

    @property
    def rows(self) -> dict[str, int]:
        return {k: m["rows"] for k, m in self.meta.items()}

    def bound_datasets(self) -> dict:
        """Name -> the xarray Dataset each Zarr binding drew from (after bbox/sel)."""
        return {k: m["ds"] for k, m in self.meta.items() if "ds" in m}


def _usermeta(spec: dict) -> dict:
    um = spec.get("usermeta") or {}
    if not isinstance(um, dict):
        raise SpecError("usermeta must be an object")
    for key in USERMETA_KEYS:
        if key in um and not isinstance(um[key], bool):
            raise SpecError(f"usermeta.{key} must be true or false, got {json.dumps(um[key])}")
    return um


def chart_class(spec: dict):
    """The Altair class for the spec's top-level composition key."""
    import altair as alt

    present = [k for k in COMPOSITION_KEYS if k in spec]
    if "facet" in present or "repeat" in present:
        if "spec" not in spec:
            raise SpecError(
                f"top-level {present[0]!r} needs a 'spec' (the chart drawn in each panel)"
            )
        return alt.FacetChart if "facet" in present else alt.RepeatChart
    if len(present) != 1:
        raise SpecError(
            "the top level needs exactly one of mark (single view), layer, hconcat, vconcat, "
            f"concat, facet+spec, repeat+spec; found {present or 'none'}"
        )
    return {
        "layer": alt.LayerChart,
        "hconcat": alt.HConcatChart,
        "vconcat": alt.VConcatChart,
        "concat": alt.ConcatChart,
        "mark": alt.Chart,
    }[present[0]]


def lint(spec: dict, meta: dict) -> list[str]:
    """Problems Vega-Lite itself would draw silently (an empty layer, a blank axis)."""
    problems = []
    known = set((spec.get("datasets") or {}).keys())
    for node, data_name, derived, path in iter_views(spec):
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            if data["name"] not in known:
                problems.append(
                    f"{path}.data.name {data['name']!r} is not a dataset "
                    f"(datasets: {sorted(known)})"
                )
                continue
        if data_name not in meta or "*pivot*" in derived:
            continue
        cols = set(meta[data_name]["columns"]) | derived
        for ch, enc in (node.get("encoding") or {}).items():
            encs = enc if isinstance(enc, list) else [enc]
            for item in encs:
                fld = item.get("field") if isinstance(item, dict) else None
                if not isinstance(fld, str):
                    continue
                if fld not in cols and fld.split(".")[0] not in cols:
                    problems.append(
                        f"{path}.encoding.{ch}.field {fld!r} is not a column of {data_name!r} "
                        f"(columns: {sorted(cols)})"
                    )
    return problems


def validate(spec: dict) -> None:
    """Vega-Lite schema check through Altair, on a copy with each dataset cut to 3 rows."""
    from altair.utils.schemapi import SchemaValidationError

    stub = copy.deepcopy({k: v for k, v in spec.items() if k != "datasets"})
    if "datasets" in spec:
        stub["datasets"] = {k: v[:3] for k, v in spec["datasets"].items()}
    cls = chart_class(spec)
    try:
        cls.from_dict(stub)
    except SchemaValidationError as exc:
        raise SpecError(f"not valid Vega-Lite {VL_VERSION}: {exc}") from None


def seal_cells(vega: dict) -> int:
    """Stroke scale-filled ``rect`` marks with their own fill so abutting cells show no seams.

    Only Vega-Lite ``rect`` marks whose fill comes from a scale and that set no
    stroke are touched; bars, geoshapes and anything with an explicit stroke are
    left alone. Patching the compiled Vega avoids knowing scale names
    (``color`` vs ``concat_0_color``) and leaves legends untouched.
    """
    count = 0

    def walk(marks):
        nonlocal count
        for mark in marks:
            if mark.get("type") == "group":
                walk(mark.get("marks", []))
                continue
            style = mark.get("style") or []
            style = [style] if isinstance(style, str) else style
            update = mark.get("encode", {}).get("update", {})
            fill = update.get("fill")
            if (
                mark.get("type") == "rect"
                and "rect" in style
                and isinstance(fill, dict)
                and "scale" in fill
                and "stroke" not in update
            ):
                update["stroke"] = copy.deepcopy(fill)
                update.setdefault("strokeWidth", {"value": 0.5})
                count += 1

    walk(vega.get("marks", []))
    return count


def classed_legends(vega: dict, classed: dict) -> int:
    """Turn threshold-scale legends into one equal-size swatch per class.

    Vega-Lite draws a threshold legend as a gradient sized by value, so narrow
    classes (0–1 mm beside 200–400 mm) vanish, and it ignores ``legend.type``
    for these scales. The compiled Vega legend accepts ``type: symbol``, which
    labels each class with its range. The under entry (``< 0``) is dropped when
    no plotted value falls below the first bound.
    """
    count = 0

    def walk(node, scales):
        nonlocal count
        scales = {**scales, **{s["name"]: s for s in node.get("scales") or []}}
        for lg in node.get("legends") or []:
            sc = scales.get(lg.get("fill") or lg.get("stroke"))
            if not sc or sc.get("type") != "threshold":
                continue
            for key in ("gradientLength", "gradientThickness", "gradientStrokeWidth"):
                lg.pop(key, None)
            lg["type"] = "symbol"
            lg.setdefault("symbolType", "square")
            lg.setdefault("symbolSize", 196)
            lg.setdefault("symbolStrokeColor", "#888")
            lg.setdefault("symbolStrokeWidth", 0.5)
            domain = sc.get("domain")
            if (
                "values" not in lg
                and isinstance(domain, list)
                and not classed.get(tuple(domain), True)
            ):
                lg["values"] = domain
            count += 1
        for mark in node.get("marks") or []:
            if mark.get("type") == "group":
                walk(mark, scales)

    walk(vega, {})
    return count


def _row_guard(meta: dict, max_rows: int) -> None:
    bound = {k: m["rows"] for k, m in meta.items() if m.get("kind") in ("zarr", "contours")}
    total = sum(bound.values())
    advice = (
        'Crop with the binding\'s bbox, thin with isel (e.g. {"latitude": {"step": 2}}), '
        "or coarsen upstream. Every row is a mark the renderer draws one by one."
    )
    if total > max_rows:
        raise SpecError(
            f"datasets: {total} bound rows {bound} is over the {max_rows} row limit. {advice} "
            "To render anyway, pass --max-rows."
        )
    if total > WARN_ROWS:
        print(
            f"Warning: {total} bound rows {bound}; expect a slow render. {advice}", file=sys.stderr
        )


def prepare(spec_in: dict, inputs: dict, *, max_rows: int = MAX_ROWS) -> Prepared:
    """Bind, fill defaults, lint and validate. Nothing is rendered."""
    if not isinstance(spec_in, dict):
        raise SpecError("the spec must be a JSON object (a Vega-Lite top-level spec)")
    usermeta = _usermeta(spec_in)
    use_defaults = usermeta.get("defaults", True)
    notes: list[str] = []
    spec, meta = bind_all(spec_in, inputs, notes, defaults=use_defaults)
    _row_guard(meta, max_rows)
    classed = apply_defaults(spec, meta, notes, defaults=use_defaults)
    spec.setdefault("$schema", VL_SCHEMA)
    problems = lint(spec, meta)
    if problems:
        raise SpecError("\n".join(problems))
    validate(spec)
    return Prepared(spec, meta, notes, classed, usermeta)


def to_vega(prep: Prepared) -> dict:
    """Compile to Vega and apply the seam and classed-legend patches."""
    import vl_convert as vlc

    try:
        vega = vlc.vegalite_to_vega(prep.spec, vl_version=VL_VERSION)
    except ValueError as exc:
        raise SpecError(f"Vega-Lite could not compile the spec: {_first_lines(exc)}") from None
    vega = json.loads(vega) if isinstance(vega, str) else vega
    if prep.usermeta.get("seal_cells", True):
        seal_cells(vega)
    if prep.usermeta.get("defaults", True) and prep.usermeta.get("classed_legend", True):
        classed_legends(vega, prep.classed)
    return vega


def _first_lines(exc, n=6) -> str:
    return "\n".join(str(exc).strip().splitlines()[:n])


def write(vega: dict, out: Path, *, scale: float = 2.0) -> Path:
    """Render compiled Vega to ``out`` (``.png``, ``.jpg``/``.jpeg`` or ``.html``)."""
    import vl_convert as vlc

    out = Path(out)
    suffix = out.suffix.lower()
    if suffix not in OUTPUT_SUFFIXES:
        raise SpecError(f"output {out.name}: use one of {list(OUTPUT_SUFFIXES)}")
    try:
        if suffix == ".png":
            out.write_bytes(vlc.vega_to_png(vega, scale=scale))
        elif suffix in (".jpg", ".jpeg"):
            out.write_bytes(vlc.vega_to_jpeg(vega, scale=scale))
        else:
            out.write_text(vlc.vega_to_html(vega, bundle=True), encoding="utf-8")
    except ValueError as exc:
        raise DataError(f"rendering failed: {_first_lines(exc)}") from None
    return out


def render(spec_in: dict, inputs: dict, out: Path, *, scale: float = 2.0, max_rows: int = MAX_ROWS):
    """Bind, default, validate, compile and write ``out``. Returns the :class:`Prepared` spec."""
    prep = prepare(spec_in, inputs, max_rows=max_rows)
    write(to_vega(prep), out, scale=scale)
    return prep


def truncate_rows(spec: dict, n: int | None) -> dict:
    """A copy with each dataset cut to ``n`` rows (for reading a dumped spec)."""
    if n is None:
        return spec
    out = dict(spec)
    out["datasets"] = {k: v[:n] for k, v in (spec.get("datasets") or {}).items()}
    return out


__all__ = [
    "MAX_ROWS",
    "OUTPUT_SUFFIXES",
    "Prepared",
    "chart_class",
    "classed_legends",
    "derived_names",
    "lint",
    "prepare",
    "render",
    "seal_cells",
    "to_vega",
    "truncate_rows",
    "validate",
    "write",
]
