"""Stdout QA for a written plot: image hash + whether the plotted data is finite."""

from __future__ import annotations

import hashlib
import sys

import numpy as np


def hash_png_pixels(path) -> str:
    """sha256 of RGB pixels (of the first frame for a GIF). Provenance metadata does not change it."""
    from PIL import Image

    with Image.open(path) as img:
        payload = img.convert("RGB").tobytes()
    return hashlib.sha256(payload).hexdigest()


def figure_counts(fig) -> list[tuple[str, int, int]]:
    """``(trace, n_finite, n)`` per trace name: its ``z``, marker colors, ``y`` or ``r``.

    Base-map lines (``ws.basemap``, uids ``basemap-…``) are left out.
    """
    rows: dict[str, list[int]] = {}
    # A frame's traces count under the base trace they update.
    traces = [(tr.uid or tr.name or f"data[{i}]", tr) for i, tr in enumerate(fig.data)]
    for frame in fig.frames or []:
        targets = frame.traces or range(len(frame.data))
        for k, tr in zip(targets, frame.data, strict=False):
            traces.append((traces[k][0] if k < len(fig.data) else f"data[{k}]", tr))
    for name, tr in traces:
        if str(tr.uid or "").startswith("basemap-"):
            continue
        raw = None
        color = getattr(getattr(tr, "marker", None), "color", None)
        for value in (
            getattr(tr, "z", None),
            None if isinstance(color, str) else color,
            getattr(tr, "y", None),
            getattr(tr, "r", None),
        ):
            if value is not None:
                raw = value
                break
        try:
            values = np.asarray(raw, dtype=float).ravel()
        except (TypeError, ValueError):
            # Names on y (a dot chart): the values are on x.
            try:
                values = np.asarray(getattr(tr, "x", None), dtype=float).ravel()
            except (TypeError, ValueError):
                continue
        if raw is None or values.size == 0:
            continue
        # Traces sharing a name (one per ensemble member) count as one row.
        count = rows.setdefault(name, [0, 0])
        count[0] += int(np.isfinite(values).sum())
        count[1] += values.size
    return [(name, finite, n) for name, (finite, n) in rows.items()]


def report_figure(path, fig, *, digest=None, file=None) -> str:
    """Print ``plot hash`` and ``data:`` lines. Returns the hash."""
    dest = sys.stdout if file is None else file
    if digest is None:
        digest = hash_png_pixels(path)
    rows = figure_counts(fig)
    detail = (
        ", ".join(f"{name} {finite}/{n} finite" for name, finite, n in rows) or "no data traces"
    )
    status = "not null" if any(finite for _, finite, _ in rows) else "NULL"
    print(f"plot hash: {digest}", file=dest)
    print(f"data: {status} ({detail})", file=dest)
    if status == "NULL" and rows:
        print(
            "data is all NaN — inspect-zarr the input before treating this figure as valid",
            file=dest,
        )
    elif rows:
        for name, finite, n in rows:
            if n and not finite:
                print(f"data: {name} is all NaN and draws nothing", file=dest)
    return digest
