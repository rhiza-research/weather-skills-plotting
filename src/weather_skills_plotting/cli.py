"""Shared skill flow: skeleton + ``--spec`` → dump, or compile and export."""

from __future__ import annotations

import sys
from pathlib import Path

from weather_skills_core.errors import UsageError

from weather_skills_plotting.spec import (
    SPEC_VERSION,
    dump_spec,
    dump_spec_dest,
    merge_spec,
    validate,
)


def input_path(ds) -> str | None:
    from weather_skills_core.decorator import INPUT_PATH_ATTR

    return None if ds is None else ds.attrs.get(INPUT_PATH_ATTR)


def letter(i: int) -> str:
    return chr(ord("a") + i) if i < 26 else f"i{i}"


def skeleton(skill: str, datasets: dict, data: list, layout: dict | None = None) -> dict:
    """The spec a skill builds from its files, before ``--spec`` is merged on."""
    inputs = {key: str(input_path(ds)) for key, ds in datasets.items() if input_path(ds)}
    meta = {"version": SPEC_VERSION, "skill": skill}
    if inputs:
        meta["inputs"] = inputs
    return {"data": data, "layout": {**(layout or {}), "meta": meta}}


def spec_datasets(spec_arg, cli: dict) -> dict:
    """Datasets named on the command line, else those listed in ``layout.meta.inputs``."""
    if cli:
        return cli
    return spec_arg.opened() if spec_arg is not None else {}


def run(skill_spec: dict, user_spec, datasets: dict, output, dump, *, theme_file=None, scale=None):
    """Merge, then either dump the spec or draw it. Returns the output path or ``None``."""
    from weather_skills_plotting import SpecArg, compile, export
    from weather_skills_plotting.palettes import load_theme

    user = user_spec.data if isinstance(user_spec, SpecArg) else (user_spec or {})
    merged = merge_spec(skill_spec, user)
    validate(merged)
    dest = dump_spec_dest(dump)
    if dest is not None:
        dump_spec(merged, dest)
        return None
    if output is None:
        raise UsageError("--output is required unless --dump-spec is set")
    theme = load_theme(theme_file)
    fig = compile(merged, datasets, theme=theme)
    export_meta = ((merged.get("layout") or {}).get("meta") or {}).get("export") or {}
    return export(fig, Path(output), datasets=datasets, scale=scale or export_meta.get("scale"))


def warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)
