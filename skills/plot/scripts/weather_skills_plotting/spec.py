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
    lat, lon = cf_dim(ds, "latitude"), cf_dim(ds, "longitude")
    if lat and lon:
        lats, lons = np.asarray(ds[lat].values, float), np.asarray(ds[lon].values, float)
        meta["bbox"] = {
            "n": float(np.nanmax(lats)),
            "w": float(np.nanmin(lons)),
            "s": float(np.nanmin(lats)),
            "e": float(np.nanmax(lons)),
        }
    return meta


def evaluate(spec: SpecArg, inputs_meta: dict, *, jpath=(), ext_strs=()) -> dict:
    """Evaluate the Jsonnet to a figure dict, with std.extVar('inputs') and --ext-str set."""
    import _gojsonnet

    # Recipes import by name too: importstr 'map.jsonnet' reads one.
    jpathdir = [str(LIB_DIR), str(RECIPES_DIR), *[str(p) for p in jpath]]
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
        if missing and missing.group(1) not in inputs_meta and "extVar" not in missing.group(1):
            message += (
                f"\nIf {missing.group(1)} is an input, pass it with -i FILE={missing.group(1)}; "
                f"inputs given: {', '.join(inputs_meta) or 'none'}"
            )
        raise UsageError(f"--spec: {message}") from None
    fig = json.loads(text)
    if not isinstance(fig, dict):
        raise UsageError("--spec must evaluate to an object: {data: [...], layout: {...}}")
    return fig


def validate(fig: dict):
    """A ``go.Figure`` from the resolved spec; Plotly's own errors, naming the trace."""
    import plotly.graph_objects as go

    for i, trace in enumerate(fig.get("data") or []):
        if not isinstance(trace, dict):
            raise UsageError(f"data[{i}] must be an object (a Plotly trace)")
        try:
            go.Figure(data=[trace])
        except ValueError as exc:
            kind = trace.get("type", "scatter")
            hint = ""
            bad = [k for k in trace if k in MARKER_KEYS]
            if kind in ("scatter", "scattergl") and bad:
                hint = f'\nOn a {kind}, {", ".join(bad)} goes under marker: {{"marker": {{...}}}}'
            raise UsageError(f"data[{i}] ({kind}): {_short(exc)}{hint}") from None
    try:
        return go.Figure(fig)
    except ValueError as exc:
        raise UsageError(f"--spec: {_short(exc)}") from None


def _short(exc) -> str:
    """Plotly's message without its long list of valid properties."""
    lines = [line for line in str(exc).strip().splitlines() if line.strip()]
    keep = [line for line in lines[:3]]
    keep += [line for line in lines[3:] if line.startswith("Did you mean")]
    return "\n".join(keep) + "\nKeys are standard Plotly: https://plotly.com/python/reference/"
