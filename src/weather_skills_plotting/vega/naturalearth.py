"""Natural Earth base-map layers: pinned download, cache, clip, d3 ring orientation."""

from __future__ import annotations

import functools
import json
import os
import urllib.request
from pathlib import Path

from weather_skills_plotting.vega.errors import DataError, SpecError

NE_VERSION = "v5.1.2"
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{NE_VERSION}/geojson/ne_{{scale}}_{{name}}.geojson"
)
NE_LAYERS = {
    "countries": "admin_0_countries",
    "borders": "admin_0_boundary_lines_land",
    "coastline": "coastline",
    "lakes": "lakes",
    "rivers": "rivers_lake_centerlines",
    "admin1": "admin_1_states_provinces_lines",
    "ocean": "ocean",
    "land": "land",
}
NE_SCALES = ("10m", "50m", "110m")
DEFAULT_SCALE = "50m"
CLIP_PAD_DEG = 1.0


def cache_dir() -> Path:
    """``$WS_NE_CACHE``, else ``~/.cache/weather-skills/naturalearth``."""
    env = os.environ.get("WS_NE_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "weather-skills" / "naturalearth"


def layer_path(layer: str, scale: str) -> Path:
    """Local path of one layer file, downloading it into the cache on first use."""
    name = f"ne_{scale}_{NE_LAYERS[layer]}.geojson"
    path = cache_dir() / name
    if path.exists():
        return path
    url = NE_URL.format(scale=scale, name=NE_LAYERS[layer])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            tmp.write_bytes(resp.read())
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise DataError(
            f"could not download Natural Earth {name} ({exc}). Each layer file is fetched once "
            f"from {url} into {path.parent}; with no network, copy the file there or set "
            "WS_NE_CACHE to a directory that has it."
        ) from exc
    os.replace(tmp, path)
    return path


@functools.lru_cache(maxsize=16)
def _features(path: str, mtime: float) -> tuple[dict, ...]:
    return tuple(json.loads(Path(path).read_text())["features"])


def load_features(layer: str, scale: str) -> list[dict]:
    path = layer_path(layer, scale)
    return list(_features(str(path), path.stat().st_mtime))


def clip_features(features, bbox, pad: float = CLIP_PAD_DEG) -> list[dict]:
    """Features cut to ``bbox`` (``[N, W, S, E]``) plus ``pad`` degrees; new dicts, inputs untouched."""
    from shapely.geometry import box, mapping, shape

    n, w, s, e = bbox
    clip = box(w - pad, s - pad, e + pad, n + pad)
    out = []
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        g = shape(geom)
        if not g.intersects(clip):
            continue
        g = g.intersection(clip)
        if g.is_empty:
            continue
        out.append(
            {"type": "Feature", "properties": feat.get("properties") or {}, "geometry": mapping(g)}
        )
    return out


def orient_for_d3(features) -> list[dict]:
    """d3-geo reads a counter-clockwise ring as "the whole globe except this", so make them clockwise."""
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
    from shapely.geometry.polygon import orient

    def fix(g):
        if isinstance(g, Polygon):
            return orient(g, sign=-1.0)
        if isinstance(g, MultiPolygon):
            return MultiPolygon([orient(p, sign=-1.0) for p in g.geoms])
        if isinstance(g, GeometryCollection):
            return GeometryCollection([fix(p) for p in g.geoms])
        return g

    out = []
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        out.append({**feat, "geometry": mapping(fix(shape(geom)))})
    return out


def check_bbox(bbox, loc: str) -> list[float]:
    if (
        not isinstance(bbox, (list, tuple))
        or len(bbox) != 4
        or not all(isinstance(v, (int, float)) for v in bbox)
    ):
        raise SpecError(f"{loc}.bbox must be [N, W, S, E] in degrees, got {json.dumps(bbox)}")
    n, w, s, e = (float(v) for v in bbox)
    if n <= s:
        raise SpecError(f"{loc}.bbox is [N, W, S, E]: north {n} must be greater than south {s}")
    return [n, w, s, e]


def bind_naturalearth(name: str, binding: dict) -> list[dict]:
    loc = f"datasets.{name}"
    layer = binding["naturalearth"]
    if layer not in NE_LAYERS:
        raise SpecError(f"{loc}.naturalearth {layer!r}: choose one of {sorted(NE_LAYERS)}")
    scale = binding.get("scale", DEFAULT_SCALE)
    if scale not in NE_SCALES:
        raise SpecError(f"{loc}.scale {scale!r}: choose one of {list(NE_SCALES)}")
    features = load_features(layer, scale)
    if binding.get("bbox") is not None:
        features = clip_features(features, check_bbox(binding["bbox"], loc))
    keep = binding.get("properties", ["name"])
    if not isinstance(keep, list) or not all(isinstance(k, str) for k in keep):
        raise SpecError(f"{loc}.properties must be a list of property names, got {keep!r}")
    keep = {k.lower() for k in keep}
    features = [
        {
            **feat,
            "properties": {
                k: v for k, v in (feat.get("properties") or {}).items() if k.lower() in keep
            },
        }
        for feat in features
    ]
    return orient_for_d3(features)
