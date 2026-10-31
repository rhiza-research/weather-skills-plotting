"""GeoJSON inputs and Natural Earth layers (with the download stubbed offline)."""

import json

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from weather_skills_plotting import geodata

RING = [[10, 1], [13, 1], [13, 3], [10, 3], [10, 1]]


@pytest.mark.parametrize(
    "doc",
    [
        {"type": "Polygon", "coordinates": [RING]},
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [RING]}},
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [RING]}},
                {"type": "Feature", "geometry": None},
            ],
        },
    ],
)
def test_geojson_wrappers_give_the_same_lines(tmp_path, doc):
    path = tmp_path / "a.geojson"
    path.write_text(json.dumps(doc))
    x, y = geodata.geoms_to_xy(geodata.load_geojson(path))
    assert x[:5].tolist() == [10, 13, 13, 10, 10] and np.isnan(x[5])


def test_unreadable_geojson_is_a_usage_error(tmp_path):
    path = tmp_path / "bad.geojson"
    path.write_text("{not json")
    with pytest.raises(UsageError, match="GeoJSON input"):
        geodata.load_geojson(path)


def test_window_parts_split_at_the_dateline():
    assert geodata.window_parts(170, -175) == [(170, 180, 0.0), (-180, -175, 360.0)]
    assert geodata.window_parts(170, 195) == [(170, 180, 0.0), (-180, -165, 360.0)]


@pytest.mark.overlays
def test_offline_natural_earth_falls_back_to_bundled_outlines(monkeypatch, capsys):
    import cartopy.io.shapereader as shpreader

    def offline(**kwargs):
        raise OSError("no network")

    monkeypatch.setattr(shpreader, "natural_earth", offline)
    lines = geodata.load_ne_layer("coastline", "50m", 5, 30, -5, 45)
    assert lines and "drawing the bundled country outlines" in capsys.readouterr().err
    assert geodata.load_ne_layer("rivers", "50m", 5, 30, -5, 45) == []
    assert "NE.rivers unavailable" in capsys.readouterr().err
