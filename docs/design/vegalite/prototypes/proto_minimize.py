# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "altair>=6.3",
#   "vl-convert-python>=1.9",
#   "numpy",
#   "pandas",
#   "pillow",
#   "xarray",
#   "zarr>=3",
#   "shapely>=2.1",
#   "contourpy>=1.3",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
# ]
# ///
"""How much of a spec can go and still render the same PNG?

uv run proto_minimize.py --spec map.json -i obs=/tmp/week.zarr --out /tmp/min/map

1. Ablation: drop each key of the full spec on its own; report identical / changed / error.
2. Greedy: walk the spec top-down, dropping every key whose removal leaves the PNG
   pixel-identical (descending into a key only when dropping it whole changes the output).
Writes the minimal spec, the baseline PNG, and one PNG per changing ablation to --out.
"""

import argparse
import copy
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import vlbind  # noqa: E402


def size(spec) -> int:
    return len(json.dumps(spec, separators=(",", ":")))


def get(node, path):
    for p in path:
        node = node[p]
    return node


def without(spec, path):
    out = copy.deepcopy(spec)
    del get(out, path[:-1])[path[-1]]
    return out


def key_paths(node, path=()):
    """Every dict key, parents before children; list items are walked, not removed."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield (*path, k)
            yield from key_paths(v, (*path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from key_paths(v, (*path, i))


def label(path) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")


class Renderer:
    def __init__(self, inputs, out: Path, scale: float):
        self.inputs, self.tmp, self.scale = inputs, out / "_trial.png", scale

    def __call__(self, spec):
        """``(pixels, None)`` or ``(None, error message)``."""
        try:
            vlbind.render(spec, self.inputs, self.tmp, scale=self.scale)
        except Exception as exc:  # noqa: BLE001
            return None, f"{type(exc).__name__}: {str(exc).splitlines()[0][:140]}"
        return np.asarray(Image.open(io.BytesIO(self.tmp.read_bytes())).convert("RGBA")), None


def compare(base, img) -> str:
    if img.shape != base.shape:
        return f"size {base.shape[1]}x{base.shape[0]} -> {img.shape[1]}x{img.shape[0]}"
    n = int(np.any(img != base, axis=-1).sum())
    return "identical" if n == 0 else f"{n} px ({100 * n / base[..., 0].size:.2f}%) differ"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("-i", "--input", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    spec = json.loads(args.spec.read_text())
    inputs = vlbind.open_inputs(dict(kv.split("=", 1) for kv in args.input))
    render = Renderer(inputs, args.out, args.scale)

    base, err = render(spec)
    if err:
        raise SystemExit(err)
    again, _ = render(spec)
    assert np.array_equal(base, again), "render is not deterministic"
    Image.fromarray(base).save(args.out / "baseline.png")

    print(f"== ablation ({size(spec)} bytes compact)")
    for path in key_paths(spec):
        img, err = render(without(spec, path))
        what = err or compare(base, img)
        print(f"  {label(path):60s} {what}")
        if img is not None and what != "identical":
            Image.fromarray(img).save(args.out / f"drop_{label(path).replace('/', '_')}.png")

    print("== greedy")
    cur = copy.deepcopy(spec)

    def visit(path):
        nonlocal cur
        node = get(cur, path)
        keys = list(node) if isinstance(node, dict) else list(range(len(node)))
        for k in keys:
            child_path = (*path, k)
            if isinstance(node, dict):
                trial = without(cur, child_path)
                img, err = render(trial)
                if err is None and np.array_equal(img, base):
                    cur = trial
                    print(f"  drop {label(child_path)}")
                    continue
            if isinstance(get(cur, child_path), (dict, list)):
                visit(child_path)

    visit(())
    final, _ = render(cur)
    assert np.array_equal(final, base)
    (args.out / "minimal.json").write_text(json.dumps(cur, indent=2) + "\n")
    print(f"== {size(spec)} -> {size(cur)} bytes compact ({100 * size(cur) / size(spec):.0f}%)")
    print(json.dumps(cur, indent=2))


if __name__ == "__main__":
    main()
