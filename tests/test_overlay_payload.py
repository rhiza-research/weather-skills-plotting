"""Overlay polylines and animation frame comparison stay compact and exact."""

import numpy as np
import pytest
from shapely.geometry import LineString

from weather_skills_plotting.animate import _content
from weather_skills_plotting.geodata import geoms_to_xy


def test_geoms_to_xy_is_nan_separated_float32():
    xs, ys = geoms_to_xy([LineString([(0, 0), (1, 1)]), LineString([(2, 2), (3, 3)])])
    assert xs.dtype == np.float32 and ys.dtype == np.float32
    assert np.isnan(xs[2]) and np.isnan(xs[-1])
    assert list(xs[~np.isnan(xs)]) == [0, 1, 2, 3]


def test_geoms_to_xy_drops_points_below_tolerance():
    wiggle = LineString([(x / 100, 0.001 * (-1) ** x) for x in range(101)])
    xs, _ = geoms_to_xy([wiggle], tolerance=0.01)
    assert np.count_nonzero(~np.isnan(xs)) == 2


def test_content_tells_apart_arrays_that_differ_inside():
    # str() of a large array shows only its corners, which match here.
    a = np.full((300, 321), np.nan)
    b = a.copy()
    b[150, 150] = 5.0
    assert _content({"type": "heatmap", "z": a}) != _content({"type": "heatmap", "z": b})
    assert _content({"type": "heatmap", "z": a}) == _content({"type": "heatmap", "z": a.copy()})


@pytest.mark.overlays
def test_disputed_lines_split_from_borders():
    from shapely.geometry import box

    from weather_skills_plotting.geodata import overlay_geoms

    names = dict(overlay_geoms((32.5, 43.5, -5.5, 6.5), {"admin1": False}))
    ilemi = box(34.5, 4.7, 35.5, 5.1)
    assert any(g.intersects(ilemi) for g in names["disputed"])
    assert not any(g.intersects(ilemi) for g in names["borders"])


@pytest.mark.overlays
def test_admin1_lines_stop_along_disputed_borders():
    from shapely.geometry import Point

    from weather_skills_plotting.geodata import overlay_geoms

    names = dict(overlay_geoms((32.5, 43.5, -5.5, 6.5), {"admin1": True}))
    # A point on the Ilemi edge: the dashed line is there, no province line on top of it.
    on_edge = Point(35.09, 4.92).buffer(0.01)
    assert any(g.intersects(on_edge) for g in names["disputed"])
    assert not any(g.intersects(on_edge) for g in names["admin1"])
