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

LARGE_HTML_MB = 50


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


def run(
    skill_spec: dict,
    user_spec,
    datasets: dict,
    output,
    dump,
    *,
    theme_file=None,
    scale=None,
    animate=False,
):
    """Merge, then either dump the spec or draw it. Returns the output path or ``None``.

    ``animate`` turns the figure's map panels into frames of one animated panel
    (``plot-video``); the output must then be HTML.
    """
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
    if animate and Path(output).suffix.lower() not in (".html", ".htm"):
        raise UsageError(
            f"output {Path(output).name!r} must end in .html: an animation plays only in a "
            "browser. For a still image of one time, use the plot skill"
        )
    theme = load_theme(theme_file)
    fig = compile(merged, datasets, theme=theme)
    layout_meta = (merged.get("layout") or {}).get("meta") or {}
    if animate:
        from weather_skills_plotting.animate import animate_figure, estimate_html_mb

        fig = animate_figure(
            fig, user_layout=user.get("layout") or {}, animation=layout_meta.get("animation")
        )
        size = estimate_html_mb(fig)
        print(
            f"plot-video: {len(fig.frames)} frames, {size:.1f} MB of figure data",
            file=sys.stderr,
        )
        if size > LARGE_HTML_MB:
            warn(
                f"the HTML will be large (~{size:.0f} MB) and slow to open; select fewer frames "
                "(meta.source.isel / sel) or a smaller layout.meta.geo.bbox"
            )
    export_meta = layout_meta.get("export") or {}
    return export(fig, Path(output), datasets=datasets, scale=scale or export_meta.get("scale"))


def warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)
