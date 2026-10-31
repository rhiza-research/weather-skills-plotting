"""Repo-wide test setup."""

import pytest


@pytest.fixture(autouse=True)
def no_natural_earth(monkeypatch, request):
    """NE layers download Natural Earth; tests stub them unless marked ``overlays``."""
    if request.node.get_closest_marker("overlays"):
        return
    from shapely.geometry import LineString

    from weather_skills_plotting import bind

    def fake(layer, scale, n, w, s, e):
        return [LineString([(w, s), (e, n)])]

    monkeypatch.setattr(bind, "load_ne_layer", fake)


@pytest.fixture(scope="session", autouse=True)
def kaleido_server():
    """One headless Chrome for every image a test writes (each write starts one otherwise)."""
    import kaleido

    kaleido.start_sync_server(silence_warnings=True)
    yield
    kaleido.stop_sync_server(silence_warnings=True)
