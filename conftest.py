"""Repo-wide test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_natural_earth(monkeypatch, request):
    """Base-map overlays download Natural Earth; tests stub them unless marked ``overlays``."""
    if request.node.get_closest_marker("overlays"):
        return
    from shapely.geometry import LineString

    from weather_skills_plotting import figure

    def fake(extent, settings):
        line = LineString([(extent[0], extent[2]), (extent[1], extent[3])])
        return [
            (name, [line]) for name in ("borders", "coastline") if settings.get(name) is not False
        ]

    monkeypatch.setattr(figure, "overlay_geoms", fake)
