"""Repo-wide test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_natural_earth(monkeypatch, request):
    """NE layers download Natural Earth; tests stub them unless marked ``overlays``."""
    if request.node.get_closest_marker("overlays"):
        return
    from shapely.geometry import LineString

    from weather_skills_plotting import geodata

    def fake(layer, scale, n, w, s, e):
        return [LineString([(w, s), (e, n)])]

    monkeypatch.setattr(geodata, "load_ne_layer", fake)
