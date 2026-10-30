"""Plotly figures from weather-skills Zarrs.

The spec is Jsonnet that evaluates to a standard Plotly figure. Where Plotly
expects data, a string starting with ``@`` names it: ``"@OBS.precip.isel(time=0)"``.

=====================  ========================================================
Module                 Role
=====================  ========================================================
:mod:`.spec`           Evaluate the Jsonnet, input metadata, Plotly validation
:mod:`.refs`           Parse, check and resolve ``@`` references
:mod:`.geodata`        Natural Earth (``NE``) and GeoJSON lines
:mod:`.qa`             Pixel hash + finite-data report printed after export
``lib/``               ``ws.libsonnet`` helpers, palettes and themes
=====================  ========================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUTPUT_SUFFIXES = (".png", ".jpg", ".jpeg", ".pdf", ".svg", ".html", ".htm", ".gif")

# A GIF frame lasts this long (ms) unless the figure's play button sets a duration.
DEFAULT_DURATION_MS = 500

# Many chat clients and slide tools show images only up to about this size inline.
LARGE_GIF_BYTES = 8 * 1024 * 1024


def export(fig, output, *, scale=1):
    """Write ``output`` (.png, .jpg, .pdf, .svg, .html or .gif) and print QA lines for images.

    HTML embeds plotly.js so the file works offline. A GIF plays the figure's frames.
    """
    from weather_skills_core.errors import UsageError

    output = Path(output)
    suffix = output.suffix.lower()
    if suffix not in OUTPUT_SUFFIXES:
        raise UsageError(
            f"output {output.name!r} must end in .png, .jpg, .pdf, .svg, .html or .gif "
            f"(got {suffix or 'no suffix'})"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    import plotly.io as pio

    from weather_skills_plotting.qa import report_figure

    spec = _float32(fig.to_plotly_json())
    if suffix in (".html", ".htm"):
        # An animation opens paused on its first frame; the viewer presses Play.
        pio.write_html(
            spec,
            output,
            include_plotlyjs=True,
            full_html=True,
            auto_play=False,
            config={
                "responsive": True,
                "scrollZoom": True,
                "showSendToCloud": False,
                "displaylogo": False,
            },
        )
        import hashlib

        # An HTML page has no pixels to hash; hash the figure JSON it embeds.
        report_figure(output, fig, digest=hashlib.sha256(json.dumps(spec).encode()).hexdigest())
        return output
    if suffix == ".gif":
        if not spec.get("frames"):
            raise UsageError(
                f"output {output.name!r}: a GIF plays the figure's frames, and this spec has "
                "none; add frames, or write a still image to .png"
            )
        write_gif(spec, output, scale=scale)
        size = output.stat().st_size
        print(f"gif: {len(spec['frames'])} frames, {size / 1e6:.1f} MB", file=sys.stderr)
        if size > LARGE_GIF_BYTES:
            print(
                f"Warning: {output.name} is {size / 1e6:.1f} MB; many chat clients and slide "
                f"tools show images only up to about {LARGE_GIF_BYTES / 1e6:.0f} MB inline. Use "
                "fewer frames, a smaller width / height, sparser markers or a smaller window",
                file=sys.stderr,
            )
        report_figure(output, fig)
        return output
    pio.write_image(spec, output, scale=scale, validate=False)
    digest = None
    if suffix in (".pdf", ".svg"):
        import hashlib

        # A vector file's bytes carry a creation time; hash the figure JSON instead.
        digest = hashlib.sha256(pio.to_json(spec, validate=False).encode()).hexdigest()
    report_figure(output, fig, digest=digest)
    return output


def write_gif(spec: dict, output, *, scale=1):
    """Write a figure's frames as a looping GIF.

    Each frame is drawn as a PNG by kaleido, then Pillow joins them on one
    shared 256-colour palette. A frame lasts as long as the play button's
    ``frame.duration`` (``ws.player``), else DEFAULT_DURATION_MS.
    """
    import tempfile

    import plotly.io as pio
    from PIL import Image

    duration = DEFAULT_DURATION_MS
    for menu in spec["layout"].get("updatemenus") or []:
        for button in menu.get("buttons") or []:
            args = button.get("args") or []
            if len(args) > 1 and isinstance(args[1], dict) and "frame" in args[1]:
                duration = args[1]["frame"].get("duration") or duration
                break
    layout = {k: v for k, v in spec["layout"].items() if k not in ("updatemenus", "sliders")}
    stills = []
    for frame in spec["frames"]:
        # Plotly merges a frame's traces into the base traces it names, else by position.
        data = list(spec["data"])
        targets = frame.get("traces") or range(len(frame.get("data") or []))
        for i, trace in zip(targets, frame.get("data") or [], strict=True):
            data[i] = {**data[i], **trace}
        stills.append({"data": data, "layout": {**layout, **(frame.get("layout") or {})}})
    with tempfile.TemporaryDirectory() as tmp:
        paths = [Path(tmp) / f"{i}.png" for i in range(len(stills))]
        # kaleido draws at 700 x 500 unless each image is given the layout's own size.
        widths = [still["layout"].get("width") or 700 for still in stills]
        heights = [still["layout"].get("height") or 500 for still in stills]
        pio.write_images(stills, paths, scale=scale, width=widths, height=heights, validate=False)
        images = [Image.open(p).convert("RGB") for p in paths]
    # One palette picked from all frames stacked, so a colorbar bands the same in every frame.
    w, h = images[0].size
    stack = Image.new("RGB", (w, h * len(images)))
    for i, im in enumerate(images):
        stack.paste(im, (0, h * i))
    palette = stack.quantize(256, dither=Image.Dither.NONE)
    images = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    images[0].save(output, save_all=True, append_images=images[1:], duration=duration, loop=0)
    return output


def _float32(obj):
    """Copy of a figure dict with its float64 arrays stored as float32.

    Plotly writes each array as base64 ``{"dtype": "f8", "bdata": ...}``; 32-bit
    floats halve an HTML file and keep finer detail than any plot shows.
    """
    import base64

    import numpy as np

    if isinstance(obj, dict) and obj.get("dtype") == "f8" and "bdata" in obj:
        values = np.frombuffer(base64.b64decode(obj["bdata"]), dtype="<f8").astype("<f4")
        return {**obj, "dtype": "f4", "bdata": base64.b64encode(values.tobytes()).decode()}
    if isinstance(obj, dict):
        return {k: _float32(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_float32(v) for v in obj]
    return obj
