"""Class palettes and their Plotly stepped colorscales."""

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from conftest import make_gridded
from weather_skills_plotting.palettes import (
    default_palette,
    discretize,
    load_theme,
    parse_palette,
    precip_nested_palette,
)


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
    assert parse_palette("PPT_WEEK")["name"] == "ppt_week"
    assert parse_palette(["#fff", "#000"]) == {"colors": ["#fff", "#000"]}
    with pytest.raises(UsageError, match="Plotly colorscale name"):
        parse_palette("Viridis")
    with pytest.raises(UsageError, match="strictly increasing"):
        parse_palette({"colors": ["a", "b"], "bounds": [2, 1]})


def test_default_palette_follows_aggregation_period():
    da = make_gridded(n_time=1)["precip"]
    da.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        aggregation_period="7 day",
    )
    assert default_palette(da)["name"] == "ppt_week"
    da.attrs["aggregation_period"] = "1 day"
    assert default_palette(da)["name"] == "ppt_daily"
    temp = make_gridded(n_time=1, name="t2m", units="degree_Celsius")["t2m"]
    assert default_palette(temp) is None


def test_theme_file(tmp_path):
    path = tmp_path / "theme.json"
    path.write_text(
        '{"template": {"layout": {"font": {"size": 22}}}, '
        '"palettes": {"drought": {"colors": ["#a00", "#fff", "#00a"], "bounds": [0, 1, 2, 3]}}}'
    )
    theme = load_theme(path)
    assert theme["template"]["layout"]["font"]["size"] == 22
    assert parse_palette("drought", registry=theme["palettes"])["bounds"] == [0, 1, 2, 3]
    path.write_text('{"colormap": "x"}')
    with pytest.raises(UsageError, match="unknown keys colormap"):
        load_theme(path)
