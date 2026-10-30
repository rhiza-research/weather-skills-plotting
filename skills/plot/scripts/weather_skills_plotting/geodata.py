"""Lines for maps: Natural Earth layers (the built-in ``NE`` input) and GeoJSON inputs."""

from __future__ import annotations

import json
import sys
from importlib.resources import files

import numpy as np
from weather_skills_core.errors import UsageError

# NE layer name → (Natural Earth category, shapefile name, agreed-boundary filter).
# ``borders`` is agreed international boundaries; ``disputed`` is every other land
# line (disputed, indefinite, line of control). ``admin1`` exists only at 10m.
NE_LAYERS = {
    "admin1": ("cultural", "admin_1_states_provinces", None),
    "rivers": ("physical", "rivers_lake_centerlines", None),
    "lakes": ("physical", "lakes", None),
    "borders": ("cultural", "admin_0_boundary_lines_land", True),
    "disputed": ("cultural", "admin_0_boundary_lines_land", False),
    "coastline": ("physical", "coastline", None),
}


def clip_box(n, w, s, e):
    """Shapely box for a bbox; one that crosses the dateline (w > e) is two boxes."""
    from shapely.geometry import box

    if w > e:
        return box(w, s, 180.0, n).union(box(-180.0, s, e, n))
    return box(w, s, e, n)


def load_ne_layer(layer: str, scale: str, n, w, s, e):
    """A Natural Earth layer's shapes clipped to the bbox (downloaded once by cartopy).

    If borders or coastline can't be fetched, the country outlines bundled with
    core stand in for both, with a warning; other layers are left out.
    """
    category, name, agreed = NE_LAYERS[layer]
    clip = clip_box(n, w, s, e)
    try:
        import cartopy.io.shapereader as shpreader

        path = shpreader.natural_earth(resolution=scale, category=category, name=name)
        records = list(shpreader.Reader(path, bbox=clip.bounds).records())
    except Exception as exc:  # noqa: BLE001 — offline, or cartopy missing
        if layer not in ("borders", "coastline"):
            print(f"Warning: NE.{layer} unavailable ({exc}); not drawn.", file=sys.stderr)
            return []
        print(
            f"Warning: NE.{layer} unavailable ({exc}); drawing the bundled country outlines.",
            file=sys.stderr,
        )
        return _bundled_country_lines(clip)
    geoms = []
    for rec in records:
        if agreed is not None:
            is_agreed = str(rec.attributes.get("FEATURECLA", "")).startswith(
                "International boundary"
            )
            if is_agreed != agreed:
                continue
        geom = rec.geometry
        if geom is None or geom.is_empty or not geom.intersects(clip):
            continue
        clipped = geom.intersection(clip)
        if not clipped.is_empty:
            geoms.extend(getattr(clipped, "geoms", [clipped]))
    return geoms


def _bundled_country_lines(clip):
    """Country outlines from the Natural Earth extract bundled with core."""
    import shapely
    from shapely.geometry import shape

    raw = json.loads(files("weather_skills_core.data").joinpath("countries.geojson").read_text())
    geoms = []
    for feat in raw.get("features") or []:
        if not feat.get("geometry"):
            continue
        poly = shape(feat["geometry"])
        if not poly.intersects(clip):
            continue
        for part in getattr(poly.intersection(clip), "geoms", [poly.intersection(clip)]):
            if part.geom_type in ("Polygon", "MultiPolygon") and not part.is_empty:
                geoms.append(shapely.boundary(part))
    return geoms


def load_geojson(path):
    """Every geometry in a GeoJSON file (FeatureCollection, Feature or bare geometry)."""
    from shapely.geometry import shape

    try:
        raw = json.loads(open(path).read())
    except (OSError, ValueError) as exc:
        raise UsageError(f"GeoJSON input {path}: {exc}") from None
    if raw.get("type") == "FeatureCollection":
        items = [f.get("geometry") for f in raw.get("features") or []]
    elif raw.get("type") == "Feature":
        items = [raw.get("geometry")]
    else:
        items = [raw]
    return [shape(g) for g in items if g]


def geoms_to_xy(geoms):
    """NaN-separated x / y arrays tracing every line and polygon ring in ``geoms``."""
    import shapely

    xs, ys = [], []
    # get_parts splits multi-part shapes and collections into single shapes.
    for geom in geoms:
        for part in shapely.get_parts(shapely.get_parts(geom)):
            if part.geom_type == "Polygon":
                rings = [part.exterior, *part.interiors]
            elif part.geom_type in ("LineString", "LinearRing"):
                rings = [part]
            else:
                continue
            for ring in rings:
                x, y = ring.xy
                xs += [*x, np.nan]
                ys += [*y, np.nan]
    return np.array(xs, dtype=float), np.array(ys, dtype=float)
