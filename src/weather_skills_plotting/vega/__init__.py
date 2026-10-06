"""Vega-Lite rendering for weather-skills Zarrs (the ``plot-vega`` skill).

A spec is plain Vega-Lite 6. The skill adds three things on top:

1. **Data bindings.** An entry under the top-level ``datasets`` may be a binding
   object (``{"zarr": NAME, "fields": {...}}``, ``{"geojson": NAME}``,
   ``{"naturalearth": LAYER}``) instead of rows. :func:`bind_all` replaces it
   with rows.
2. **Defaults** for what the spec leaves unset, from the bound data: the
   weather colour scale, ``long_name [units]`` titles, ``projection.fit`` and
   the base-map clip box (:func:`apply_defaults`).
3. **Weather palette names** as ``scale.scheme`` values (``"ppt_week"``).

:func:`render` runs the whole pipeline: bind, defaults, lint, validate,
compile to Vega, patch cell seams and classed legends, write PNG/JPEG/HTML.
"""

from __future__ import annotations

import os

# vl-convert's JS runtime parses ISO datetimes in local time; pin UTC before it starts.
os.environ.setdefault("TZ", "UTC")

from weather_skills_plotting.vega.bind import bind_all  # noqa: E402
from weather_skills_plotting.vega.defaults import (  # noqa: E402
    PALETTE_NAMES,
    apply_defaults,
    palette_scale,
)
from weather_skills_plotting.vega.describe import describe_bindings, describe_inputs  # noqa: E402
from weather_skills_plotting.vega.errors import SpecError  # noqa: E402
from weather_skills_plotting.vega.render import (  # noqa: E402
    MAX_ROWS,
    OUTPUT_SUFFIXES,
    Prepared,
    prepare,
    render,
    to_vega,
    truncate_rows,
    write,
)

__all__ = [
    "MAX_ROWS",
    "OUTPUT_SUFFIXES",
    "PALETTE_NAMES",
    "Prepared",
    "SpecError",
    "apply_defaults",
    "bind_all",
    "describe_bindings",
    "describe_inputs",
    "palette_scale",
    "prepare",
    "render",
    "to_vega",
    "truncate_rows",
    "write",
]
