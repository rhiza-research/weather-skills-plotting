"""Defaults for what the agent leaves unset, derived from the bound data.

Everything here only fills a gap: a key the agent wrote is never changed. Each
default appends one ``"<json path> <- <value>"`` line to ``notes``.
"""

from __future__ import annotations

import functools

import numpy as np

from weather_skills_plotting import theme as THEME
from weather_skills_plotting.vega.errors import SpecError

COLOR_CHANNELS = ("color", "fill", "stroke")
TITLE_CHANNELS = ("x", "y", "color", "fill", "stroke", "size", "opacity", "theta", "radius")
# Any of these in a colour scale means the agent chose the scale; the skill leaves it alone.
SCALE_CHOICE_KEYS = ("type", "scheme", "range", "domain", "domainMid", "domainMin", "domainMax")
FIT_KEYS = ("fit", "scale", "translate")
VIEW_CHILD_KEYS = ("layer", "hconcat", "vconcat", "concat")


# --------------------------------------------------------------------------- palettes


def _palette_names() -> frozenset[str]:
    named = [k for k, v in THEME.default_theme()["colormaps"].items() if v.get("bounds")]
    return frozenset(k.lower() for k in (*THEME.DEFAULT_PRECIP_PALETTES, *named))


PALETTE_NAMES = _palette_names()


@functools.cache
def vega_scheme_names() -> frozenset[str]:
    """Every built-in Vega colour scheme name, from the Vega-Lite schema Altair ships."""
    from altair.vegalite.v6.schema.core import load_schema

    defs = load_schema()["definitions"]
    groups = ("Categorical", "SequentialSingleHue", "SequentialMultiHue", "Diverging", "Cyclical")
    return frozenset(name for g in groups for name in defs.get(g, {}).get("enum", []))


def _threshold(entry: dict) -> tuple[list, list]:
    """Vega threshold ``(domain, range)``: range is under + one colour per class + over."""
    colors, bounds = list(entry["colors"]), list(entry["bounds"])
    n_bins = len(bounds) - 1
    if len(colors) == n_bins:
        colors = [entry.get("under", colors[0]), *colors, entry.get("over", colors[-1])]
    elif len(colors) > n_bins + 2:
        # Dev's packing rule: first is under, last is over, classes follow the under.
        colors = [colors[0], *colors[1 : 1 + n_bins], colors[-1]]
    elif len(colors) != n_bins + 2:
        raise SpecError(f"palette has {len(colors)} colours for {n_bins} classes")
    return bounds, colors


def palette_scale(name: str, da=None) -> tuple[str, list, list]:
    """``(resolved name, class edges, colours)`` for one of our palette names."""
    key = name.lower()
    if key in THEME.DEFAULT_PRECIP_PALETTES:
        window = THEME.default_precip_scale_name(key, da)
        build = (
            THEME.precip_nested_anomaly_palette
            if THEME.DEFAULT_PRECIP_PALETTES[key]
            else THEME.precip_nested_palette
        )
        return (window, *_threshold(build(window)))
    entry, _ = THEME._palette_entry(THEME.default_theme()["colormaps"], key)
    return (key, *_threshold(entry))


def detected_palette(da):
    """Dev's automatic choice: precip totals / anomalies by window, SPI, percent of normal."""
    if not (THEME.is_precip(da) or THEME.is_spi(da) or THEME.is_precip_poa(da)):
        return None
    name, colors, bounds = THEME.named_precip_scale(da)
    return (name, *_threshold({"colors": colors, "bounds": bounds}))


def label(da) -> str:
    """``long_name [display units]``, the default axis and legend title."""
    from weather_skills_core.units import format_units_for_display

    name = da.attrs.get("long_name") or da.name
    units = da.attrs.get("units")
    return f"{name} [{format_units_for_display(units)}]" if units else str(name)


# --------------------------------------------------------------------------- spec walking


def derived_names(transforms) -> set[str]:
    """Columns that transforms create or overwrite (no longer the raw bound variable)."""
    out = set()
    for t in transforms or []:
        if not isinstance(t, dict):
            continue
        v = t.get("as")
        if isinstance(v, str):
            out.add(v)
        elif isinstance(v, list):
            out.update(x for x in v if isinstance(x, str))
        for key in ("aggregate", "window", "joinaggregate"):
            for item in t.get(key) or []:
                if isinstance(item, dict) and item.get("as"):
                    out.add(item["as"])
        if "lookup" in t:
            out.update((t.get("from") or {}).get("fields") or [])
        if "pivot" in t:
            out.add("*pivot*")
        if "fold" in t and "as" not in t:
            out.update(["key", "value"])
        if "quantile" in t and "as" not in t:
            out.update(["prob", "value"])
        if "density" in t and "as" not in t:
            out.update(["value", "density"])
        if "regression" in t or "loess" in t:
            out.update(x for x in (t.get("regression"), t.get("loess"), t.get("on")) if x)
    return out


def iter_views(node, data_name=None, derived=frozenset(), path="spec"):
    """Yield ``(view, data name, derived columns, JSON path)`` for every view, with inheritance."""
    if not isinstance(node, dict):
        return
    data = node.get("data")
    if isinstance(data, dict) and "name" in data:
        data_name = data["name"]
    elif isinstance(data, dict) and data:
        data_name = None
    derived = derived | derived_names(node.get("transform"))
    yield node, data_name, derived, path
    for key in VIEW_CHILD_KEYS:
        for i, child in enumerate(node.get(key) or []):
            yield from iter_views(child, data_name, derived, f"{path}.{key}[{i}]")
    yield from iter_views(node.get("spec"), data_name, derived, f"{path}.spec")


def data_names(node) -> set[str]:
    """Every ``data.name`` referenced in ``node`` (outside the top-level ``datasets``)."""
    out = set()
    if isinstance(node, dict):
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            out.add(data["name"])
        for key, value in node.items():
            if key != "datasets":
                out |= data_names(value)
    elif isinstance(node, list):
        for value in node:
            out |= data_names(value)
    return out


def _bound_da(field, data_name, derived, meta):
    if not isinstance(field, str) or field in derived:
        return None
    src = (meta.get(data_name) or {}).get("var_cols", {}).get(field)
    return meta[data_name]["ds"][src] if src else None


def _shared_da(node, channel, field, derived, meta):
    """The variable behind an encoding set on a layer parent and inherited by every child.

    Only when each inheriting child binds ``field`` to a variable with the same
    ``long_name [units]`` (two products of the same quantity, for example).
    """
    das = []
    for child in node.get("layer") or []:
        enc = (child.get("encoding") or {}).get(channel)
        if isinstance(enc, dict) and "field" in enc:
            continue
        data = child.get("data")
        name = data.get("name") if isinstance(data, dict) else None
        if name is None:
            return None
        da = _bound_da(field, name, derived | derived_names(child.get("transform")), meta)
        if da is None:
            return None
        das.append(da)
    if not das or len({label(d) for d in das}) != 1:
        return None
    return das[0]


# --------------------------------------------------------------------------- defaults


def _fit_default(node, data_name, meta, path, notes):
    proj = node.get("projection")
    if not isinstance(proj, dict) or any(k in proj for k in FIT_KEYS):
        return
    names = ({data_name} if data_name else set()) | data_names(node)
    from weather_skills_plotting.vega.bind import union

    ext = union(meta.get(n, {}).get("extent") for n in sorted(names))
    if not ext:
        return
    n, w, s, e = (round(v, 4) for v in ext)
    # Two corner points: no ring, so no d3 winding to get wrong.
    proj["fit"] = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "MultiPoint", "coordinates": [[w, s], [e, n]]},
    }
    notes.append(f"{path}.projection.fit <- extent of the bound data [{n}, {w}, {s}, {e}]")


def _check_scheme(scheme, loc):
    name = scheme.get("name") if isinstance(scheme, dict) else scheme
    if not isinstance(name, str):
        return
    if name.lower() in PALETTE_NAMES or name in vega_scheme_names():
        return
    raise SpecError(
        f"{loc}.scale.scheme {name!r} is not a palette. Weather palettes: "
        f"{sorted(PALETTE_NAMES)}. Or any Vega scheme "
        "(https://vega.github.io/vega/docs/schemes/), e.g. 'viridis', 'blues', 'redblue', "
        "'brownbluegreen'."
    )


def _color_scale(enc, da, loc, notes, classed, *, defaults):
    scale = enc.get("scale")
    if scale is None and "scale" in enc:
        return
    scale = scale or {}
    scheme = scale.get("scheme")
    if scheme is not None:
        _check_scheme(scheme, loc)
    if enc.get("type") != "quantitative":
        return
    if isinstance(scheme, str) and scheme.lower() in PALETTE_NAMES:
        name, bounds, colors = palette_scale(scheme, da)
        how = f"scheme {scheme!r}"
    elif not defaults or da is None or any(k in scale for k in SCALE_CHOICE_KEYS):
        return
    else:
        found = detected_palette(da)
        if not found:
            return
        name, bounds, colors = found
        how = "default for this variable"
    rest = {k: v for k, v in scale.items() if k != "scheme"}
    enc["scale"] = {**rest, "type": "threshold", "domain": bounds, "range": colors}
    values = np.asarray(da.values, dtype=float) if da is not None else np.array([])
    finite = values[np.isfinite(values)]
    below = finite.size == 0 or bool(finite.min() < bounds[0])
    classed[tuple(bounds)] = classed.get(tuple(bounds), False) or below
    notes.append(f"{loc}.scale <- {name} ({how}; {len(bounds) - 1} classes)")


def apply_defaults(spec: dict, meta: dict, notes: list, *, defaults: bool = True) -> dict:
    """Fill what the agent left unset from the bound data. Mutates ``spec``.

    Our palette names in ``scale.scheme`` are resolved even with ``defaults=False``
    (they are an explicit choice). Returns ``{class edges: show_under_entry}`` for
    the classed-legend patch.
    """
    classed: dict[tuple, bool] = {}
    titles = {}  # id(encoding) -> (encoding, loc, label)
    for node, data_name, derived, path in iter_views(spec):
        if defaults:
            _fit_default(node, data_name, meta, path, notes)
        for ch, enc in (node.get("encoding") or {}).items():
            if not isinstance(enc, dict):
                continue
            field = enc.get("field")
            if data_name is not None:
                da = _bound_da(field, data_name, derived, meta)
            elif isinstance(field, str) and node.get("layer"):
                da = _shared_da(node, ch, field, derived, meta)
            else:
                da = None
            loc = f"{path}.encoding.{ch}"
            if defaults and da is not None and ch in TITLE_CHANNELS and "title" not in enc:
                titles[id(enc)] = (enc, loc, label(da))
            if ch in COLOR_CHANNELS:
                _color_scale(enc, da, loc, notes, classed, defaults=defaults)
    # Layers share axes and legends, and Vega-Lite joins differing layer titles with
    # commas. Only the first layer that has a title for a channel keeps it.
    for node, *_ in iter_views(spec):
        for ch in TITLE_CHANNELS:
            encs = [
                child["encoding"][ch]
                for child in node.get("layer") or []
                if isinstance((child.get("encoding") or {}).get(ch), dict)
            ]
            owners = [e for e in encs if "title" in e or id(e) in titles]
            for enc in owners[1:]:
                titles.pop(id(enc), None)
    for enc, loc, text in titles.values():
        enc["title"] = text
        notes.append(f"{loc}.title <- {text!r}")
    return classed
