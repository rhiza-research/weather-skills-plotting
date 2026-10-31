"""The ``--spec``: Jsonnet that evaluates to a Plotly figure, checked by Plotly itself."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

import numpy as np
from weather_skills_core.cf import cf_dim
from weather_skills_core.errors import UsageError

LIB_DIR = Path(__file__).parent / "lib"
# skills/plot/recipes, beside the skill's scripts/ folder.
RECIPES_DIR = Path(__file__).parents[2] / "recipes"

# 1-D coordinates up to this long are listed in std.extVar('inputs') with their values.
MAX_LISTED_COORD = 400

# Plotly keys a scatter takes under ``marker``, not at the top of the trace.
MARKER_KEYS = frozenset({"showscale", "colorscale", "colorbar", "cmin", "cmax", "reversescale"})


class SpecArg:
    """A ``--spec`` value: a Jsonnet file path, a recipe name, or Jsonnet / JSON text."""

    def __init__(self, value: str):
        self.value = value
        self.path = None
        text = value.strip()
        # One line ending in .jsonnet / .json, or a bare name, is a file; anything else is text.
        looks_like_name = "\n" not in text and (
            text.endswith((".jsonnet", ".json")) or text.isidentifier()
        )
        if looks_like_name:
            text = os.path.expandvars(text)
        name = Path(text).name if looks_like_name else ""
        own = RECIPES_DIR / (name if name.endswith(".jsonnet") else f"{name}.jsonnet")
        # A recipe by name (map, map.jsonnet), or a path to one that does not exist here
        # (an unexpanded ${CLAUDE_SKILL_DIR}/recipes/map.jsonnet), is the skill's own.
        if name and not Path(text).is_file() and own.is_file():
            self.path = own
        # Any other file name ends in .jsonnet / .json; anything else is Jsonnet text.
        elif looks_like_name and text.endswith((".jsonnet", ".json")):
            self.path = Path(text)
            if not self.path.is_file():
                raise argparse.ArgumentTypeError(
                    f"--spec {value}: no such file; recipes are {', '.join(recipe_names())} "
                    "(pass one by name, e.g. --spec map)"
                )
        self.evaluated = None

    def to_dict(self) -> dict:
        """What provenance records: the evaluated figure, which replays as --spec on its own."""
        return self.evaluated if self.evaluated is not None else {"jsonnet": self.value}


def recipe_names() -> list[str]:
    return sorted(p.stem for p in RECIPES_DIR.glob("*.jsonnet"))


def recipe_text(name: str | None) -> str:
    """``--recipe``: every recipe with its first line, or one recipe's Jsonnet."""
    if not name:
        lines = []
        for stem in recipe_names():
            first = (RECIPES_DIR / f"{stem}.jsonnet").read_text().splitlines()[0]
            lines.append(f"{stem:15} {first.lstrip('/ ')}")
        return "\n".join(lines)
    path = RECIPES_DIR / f"{Path(name).stem}.jsonnet"
    if not path.is_file():
        raise UsageError(
            f"--recipe {name}: no such recipe; recipes are {', '.join(recipe_names())}"
        )
    return path.read_text()


def _plain(value):
    """A coordinate value as JSON: ISO date, lead days, number (None for NaN) or string."""
    if isinstance(value, np.timedelta64):
        # A lead time, in days.
        return float(value / np.timedelta64(1, "D"))
    if isinstance(value, np.datetime64):
        text = np.datetime_as_string(value, unit="s")
        return text[:10] if text.endswith("T00:00:00") else text
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(value) else None
    return str(value)


def input_metadata(value) -> dict:
    """What std.extVar('inputs').NAME holds for one input, read without loading data chunks."""
    if isinstance(value, list):
        # A GeoJSON input: its shapes.
        import shapely

        w, s, e, n = shapely.GeometryCollection(value).bounds
        return {"kind": "geojson", "bbox": {"n": n, "w": w, "s": s, "e": e}}
    ds = value
    meta = {
        "kind": "zarr",
        "dims": {str(d): int(n) for d, n in ds.sizes.items()},
        "vars": {
            str(name): {
                "dims": [str(d) for d in da.dims],
                "units": str(da.attrs.get("units", "")),
                "long_name": str(da.attrs.get("long_name", "")),
            }
            for name, da in ds.data_vars.items()
        },
        "coords": {},
        "attrs": {
            str(k): v if isinstance(v, (int, float)) else str(v)
            for k, v in ds.attrs.items()
            if k != "weather_skills_history" and len(str(v)) <= 200
        },
    }
    for name, coord in ds.coords.items():
        if coord.ndim == 0:
            meta["coords"][str(name)] = _plain(coord.values[()])
        elif coord.ndim == 1 and coord.size <= MAX_LISTED_COORD:
            meta["coords"][str(name)] = [_plain(v) for v in coord.values]
    # CF-tagged coordinates, else the usual names.
    lat = cf_dim(ds, "latitude") or next((n for n in ("latitude", "lat") if n in ds.coords), None)
    lon = cf_dim(ds, "longitude") or next((n for n in ("longitude", "lon") if n in ds.coords), None)
    if lat and lon:
        lats = np.asarray(ds[lat].values, float)
        lons = np.unique(np.asarray(ds[lon].values, float) % 360)
        # The window is the circle of longitudes minus its widest gap, so a grid across
        # the dateline (150..179, -180..-150) is 150 to 210, not -180 to 179.
        gaps = np.diff(np.append(lons, lons[0] + 360))
        k = int(np.argmax(gaps))
        west = lons[(k + 1) % lons.size]
        east = lons[k] + (360 if k + 1 < lons.size else 0)
        if west >= 180:
            west, east = west - 360, east - 360
        meta["bbox"] = {
            "n": float(np.nanmax(lats)),
            "w": float(west),
            "s": float(np.nanmin(lats)),
            "e": float(east),
        }
    return meta


def evaluate(spec: SpecArg, inputs_meta: dict, *, ext_strs=()) -> dict:
    """Evaluate the Jsonnet to a figure dict, with std.extVar('inputs') and --ext-str set."""
    import _gojsonnet

    # Recipes import by name too: importstr 'map.jsonnet' reads one.
    # Imports are found beside the spec file, in the working folder (a palettes file
    # written there, such as chc_palettes.libsonnet), in the library and in the recipes.
    jpathdir = [str(Path.cwd()), str(LIB_DIR), str(RECIPES_DIR)]
    ext_vars = dict(ext_strs)
    ext_codes = {"inputs": json.dumps(inputs_meta)}
    try:
        if spec.path is not None:
            text = _gojsonnet.evaluate_file(
                str(spec.path), jpathdir=jpathdir, ext_vars=ext_vars, ext_codes=ext_codes
            )
        else:
            text = _gojsonnet.evaluate_snippet(
                "--spec", spec.value, jpathdir=jpathdir, ext_vars=ext_vars, ext_codes=ext_codes
            )
    except RuntimeError as exc:
        message = str(exc).strip()
        missing = re.search(r"Field does not exist: (\w+)", message)
        if missing:
            name = missing.group(1)
            message += (
                f"\nIf {name} is an input, pass it with -i FILE={name} (inputs given: "
                f"{', '.join(inputs_meta) or 'none'}). If it is a palette, ws.palettes has "
                f"{', '.join(palette_names())}, or write one inline: {{colors: [...], bounds: "
                "[...]}. std.extVar('inputs').NAME.coords lists only coordinates up to "
                f"{MAX_LISTED_COORD} long, and bbox needs lat / lon coordinates."
            )
        if missing and missing.group(1) == "coloraxis":
            message += (
                " ws.stepped(p) is the coloraxis itself (coloraxis: ws.stepped(p)); "
                "ws.classBar(p) is layout keys (layout: ws.map(b) + ws.classBar(p))."
            )
        if "function has no parameter layers" in message:
            message += (
                "\nws.basemap switches layers by name: coastline=, borders=, disputed=, "
                "lakes=, rivers= (true / false) and admin1= ('auto', true, false)"
            )
        elif "function has no parameter" in message:
            message += "\nSKILL.md lists each ws.libsonnet function's parameters"
        if "couldn't open import" in message:
            message += (
                "\nImports found by name: ws.libsonnet, palettes.libsonnet, "
                "themes/tropical_tidbits.libsonnet, and the recipes "
                f"({', '.join(n + '.jsonnet' for n in recipe_names())}); "
                "and any .libsonnet beside the spec or in the working folder"
            )
        raise UsageError(f"--spec: {message}") from None
    fig = json.loads(text)
    if not isinstance(fig, dict):
        raise UsageError("--spec must evaluate to an object: {data: [...], layout: {...}}")
    return fig


def palette_names() -> list[str]:
    import _gojsonnet

    text = _gojsonnet.evaluate_snippet(
        "palettes", "std.objectFields(import 'palettes.libsonnet')", jpathdir=[str(LIB_DIR)]
    )
    return json.loads(text)


def validate(fig: dict):
    """A ``go.Figure`` from the resolved spec; Plotly's own checks, naming the trace."""
    import plotly.graph_objects as go

    for i, trace in enumerate(fig.get("data") or []):
        if not isinstance(trace, dict):
            raise UsageError(f"data[{i}] must be an object (a Plotly trace)")
        try:
            go.Figure(data=[trace])
        except ValueError as exc:
            raise UsageError(f"data[{i}]: {_explain(exc)}") from None
    try:
        return go.Figure(fig)
    except ValueError as exc:
        raise UsageError(f"--spec: {_explain(exc)}") from None


def key_hint(kind: str, key: str) -> str:
    """What to do about ``key``, which a ``kind`` trace (or layout object) doesn't have."""
    import plotly.graph_objects as go

    if key in ("animation", "animation_frame", "animation_group"):
        return (
            " animation_frame / animation_group are Plotly Express arguments, not figure "
            "keys; animate with frames (--recipe animation)."
        )
    if kind in ("scatter", "scattergl") and key in MARKER_KEYS | {"zmin", "zmax", "zmid"}:
        under = {"zmin": "cmin", "zmax": "cmax", "zmid": "cmid"}.get(key, key)
        return f' On a {kind} it goes under marker: {{"marker": {{"{under}": …}}}}.'
    if kind == "heatmap" and key in ("line", "marker", "mode", "text"):
        return " Outlines, markers and labels are scatter traces of their own."
    if kind == "bar" and key == "mode":
        return " Remove it: bars have no mode."
    trace_class = getattr(go, kind.capitalize(), None) or next(
        (getattr(go, n) for n in dir(go) if n.lower() == kind), None
    )
    names = sorted(getattr(trace_class(), "_valid_props", [])) if trace_class else []
    return f" Its properties: {', '.join(names)}." if names else ""


def _explain(exc) -> str:
    """Plotly's error in one or two lines, with what to do for the usual mix-ups.

    Plotly's own "Did you mean" guesses are dropped: they are often wrong
    (zmin → line, mode → base).
    """

    text = str(exc).strip()
    reference = "\nKeys are standard Plotly: https://plotly.com/python/reference/"
    bad_key = re.search(r"object of type plotly\.graph_objs\.([\w.]+): '(\w+)'", text)
    if bad_key:
        kind, key = bad_key.group(1).split(".")[-1].lower(), bad_key.group(2)
        return f"a {kind} has no property {key!r}.{key_hint(kind, key)}" + reference
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    message = " ".join(lines[:2])
    if re.search(r"for the '[xy]' property", text) and "Received value: '" in text:
        message += (
            " x and y take arrays; one value (a scalar coordinate such as a forecast's init "
            "time, or a single picked position) is not an axis. For a forecast, run "
            "step-to-time and use the valid times."
        )
    if "'colorscale' property" in text:
        message += (
            f" A colorscale is a Plotly name (Viridis, RdBu, YlGnBu, …) or a list of "
            f"[position, color]; a class palette goes through ws.classBar / ws.stepped "
            f"(ws.palettes has {', '.join(palette_names())})."
        )
    return message + reference
