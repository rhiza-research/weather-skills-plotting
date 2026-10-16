"""Class palettes and their Plotly stepped colorscales."""

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from conftest import make_gridded
from weather_skills_plotting.palettes import (
    default_palette,
    discretize,
    parse_palette,
    precip_nested_palette,
)
from weather_skills_plotting.themes import default_theme

THEME = default_theme()
PALETTES = THEME["palettes"]


def test_discretize_packed_under_classes_over():
    pal = precip_nested_palette("ppt_daily")  # bounds 0,1,2,5,…,50; under + 9 classes + over
    slots, scale = discretize(np.array([-1, 0, 0.5, 1, 4, 49, 50, 51, np.nan]), pal)
    assert slots[:8].tolist() == [0, 1, 1, 2, 3, 9, 10, 10]
    assert np.isnan(slots[8])
    n = len(pal["colors"])
    assert (scale["cmin"], scale["cmax"]) == (-0.5, n - 0.5)
    assert scale["ticktext"] == [f"{b:g}" for b in pal["bounds"]]
    assert scale["tickvals"][0] == 0.5  # first bound sits between under and class 1
    assert len(scale["colorscale"]) == 2 * n


def test_discretize_without_under_over_clamps():
    pal = {"colors": ["red", "white", "green"], "bounds": [-1.5, -0.5, 0.5, 1.5]}
    slots, scale = discretize(np.array([-5, -1, 0, 1, 5]), pal)
    assert slots.tolist() == [0, 0, 1, 2, 2]
    assert scale["tickvals"] == [-0.5, 0.5, 1.5, 2.5]


def test_parse_palette_forms():
    assert parse_palette("PPT_WEEK", registry=PALETTES)["name"] == "ppt_week"
    assert parse_palette(["#fff", "#000"], registry=PALETTES) == {"colors": ["#fff", "#000"]}
    with pytest.raises(UsageError, match="Plotly colorscale name"):
        parse_palette("Viridis", registry=PALETTES)
    with pytest.raises(UsageError, match="strictly increasing"):
        parse_palette({"colors": ["a", "b"], "bounds": [2, 1]}, registry=PALETTES)


def test_default_palette_follows_aggregation_period():
    da = make_gridded(n_time=1)["precip"]
    da.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        aggregation_period="7 day",
    )
    assert default_palette(da, theme=THEME)["name"] == "ppt_week"
    da.attrs["aggregation_period"] = "1 day"
    assert default_palette(da, theme=THEME)["name"] == "ppt_daily"
    temp = make_gridded(n_time=1, name="t2m", units="degree_Celsius")["t2m"]
    temp.attrs["standard_name"] = "air_temperature"
    assert default_palette(temp, theme=THEME) == {"name": "RdYlBu_r", "colorscale": "RdYlBu_r"}
    assert default_palette(temp, theme=THEME, diverging=True)["colorscale"] == "RdBu_r"
    speed = make_gridded(n_time=1, name="ws", units="m s-1")["ws"]
    speed.attrs["standard_name"] = "wind_speed"
    assert default_palette(speed, theme=THEME)["colorscale"] == "YlGn"
    msl = make_gridded(n_time=1, name="msl", units="hPa")["msl"]
    msl.attrs["standard_name"] = "air_pressure_at_mean_sea_level"
    assert default_palette(msl, theme=THEME)["colorscale"] == "RdBu_r"
    sp = make_gridded(n_time=1, name="sp", units="hPa")["sp"]
    sp.attrs["standard_name"] = "surface_air_pressure"
    assert default_palette(sp, theme=THEME)["name"] == "rocket"


def test_reference_recipes_are_json():
    import json

    from weather_skills_plotting.reference import _RECIPES

    for _, example in _RECIPES:
        json.loads(example)


def test_a_dekad_uses_the_week_window():
    from weather_skills_plotting.palettes import precip_window_name

    assert precip_window_name(10.0) == "ppt_week"
    assert precip_window_name(11.0) == "ppt_month"


def test_named_default_precip_follows_the_rate_step_like_the_theme_default():
    """meta.palette default_precip and the theme's precip default pick the same window."""
    from weather_skills_plotting.palettes import resolve_default_precip

    hourly = make_gridded(units="mm h-1")["precip"]
    assert resolve_default_precip("default_precip", [hourly], PALETTES) == "ppt_daily"
    assert resolve_default_precip("default_precip_anom", [hourly], PALETTES) == "ppt_anom_daily"
    assert default_palette(hourly, theme=THEME)["name"] == "ppt_daily"
    weekly = make_gridded(units="mm")["precip"]
    weekly.attrs["aggregation_period"] = "7 day"
    assert resolve_default_precip("default_precip", [hourly, weekly], PALETTES) == "ppt_week"
    # Anything else, or a theme palette of that name, is left alone.
    assert resolve_default_precip("ppt_month", [hourly], PALETTES) == "ppt_month"
    assert (
        resolve_default_precip("default_precip", [hourly], {"default_precip": {}})
        == "default_precip"
    )
