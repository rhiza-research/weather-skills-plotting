# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3", "vl-convert-python>=1.9", "numpy", "pandas", "xarray", "zarr>=3", "shapely>=2.1",
#   "pillow",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""End-to-end cost of the rect heatmap with two cheap fixes, one subprocess per run.

  uv run --script proto_levers.py [N ...]
  uv run --script proto_levers.py one VARIANT N

today    the skill's path: compile with data inline, stroke seals the cells, vega_to_png
splice   compile with each dataset cut to 3 rows, then put the rows into the compiled Vega
crisp    no stroke; the rect group gets shape-rendering="crispEdges" (no antialias, so no seams)
both     splice + crisp
"""

import json
import resource
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402
from proto_stages import grid, spec_for  # noqa: E402

OUT = Path(__file__).parent / "out"


def one(variant, n):
    import vl_convert as vlc

    vlc.vegalite_to_png(
        {"mark": "point", "data": {"values": [{"a": 1}]}, "encoding": {"x": {"field": "a"}}}
    )
    splice = variant in ("splice", "both")
    crisp = variant in ("crisp", "both")
    ds = grid(n)
    t0 = time.perf_counter()
    spec_in = spec_for("nostroke" if crisp else "base", n)
    notes = []
    spec, meta = vlbind.bind_all(spec_in, {"g": ds}, None, notes)
    classed = vlbind.apply_defaults(spec, meta, notes)
    spec["$schema"] = "https://vega.github.io/schema/vega-lite/v6.json"
    t1 = time.perf_counter()
    if splice:
        rows = spec.pop("datasets")
        spec["datasets"] = {k: v[:3] for k, v in rows.items()}
    vega = vlc.vegalite_to_vega(spec, vl_version="6.4")
    if splice:
        for d in vega["data"]:
            if d["name"] in rows:
                d["values"] = rows[d["name"]]
    if not crisp:
        vlbind.seal_cells(vega)
    vlbind.classed_legends(vega, classed)
    t2 = time.perf_counter()
    if crisp:
        svg = vlc.vega_to_svg(vega)
        svg = svg.replace(
            'class="mark-rect role-mark',
            'shape-rendering="crispEdges" class="mark-rect role-mark',
            1,
        )
        png = vlc.svg_to_png(svg, scale=2)
    else:
        png = vlc.vega_to_png(vega, scale=2)
    t3 = time.perf_counter()
    (OUT / f"levers_{variant}_{n}.png").write_bytes(png)
    print(
        json.dumps(
            {
                "variant": variant,
                "cells": n * n,
                "bind_s": round(t1 - t0, 2),
                "compile_s": round(t2 - t1, 2),
                "render_s": round(t3 - t2, 2),
                "total_s": round(t3 - t0, 2),
                "peak_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2),
            }
        ),
        flush=True,
    )


def sweep(sizes):
    cols = ["bind_s", "compile_s", "render_s", "total_s", "peak_rss_gb"]
    print(f"{'variant':8} {'cells':>7} " + " ".join(f"{c:>12}" for c in cols), flush=True)
    for n in sizes:
        for variant in ("today", "splice", "crisp", "both"):
            res = subprocess.run(
                [sys.executable, __file__, "one", variant, str(n)], capture_output=True, text=True
            )
            if res.returncode:
                tail = (res.stderr.strip().splitlines() or ["?"])[-1]
                print(f"{variant:8} {n * n:>7} FAILED rc={res.returncode}: {tail}", flush=True)
                continue
            r = json.loads(res.stdout.strip().splitlines()[-1])
            print(
                f"{variant:8} {r['cells']:>7} " + " ".join(f"{r[c]:>12}" for c in cols), flush=True
            )


if __name__ == "__main__":
    if sys.argv[1:2] == ["one"]:
        one(sys.argv[2], int(sys.argv[3]))
    else:
        sweep([int(a) for a in sys.argv[1:]] or [200, 450, 630])
