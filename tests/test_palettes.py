"""Class palettes and their Plotly stepped colorscales."""

import numpy as np
import pytest
from weather_skills_core.errors import UsageError

from conftest import make_gridded
from weather_skills_plotting.palettes import (
    builtin_palettes,
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


@pytest.mark.parametrize("name", sorted(builtin_palettes()))
def test_builtin_palettes_pass_theme_file_checks(name):
    # A built-in copied into a --theme-file must load: right color count for its bounds.
    parse_palette(builtin_palettes()[name], loc=name)


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
    temp.attrs["standard_name"] = "air_temperature"
    assert default_palette(temp) == {"name": "RdYlBu_r", "colorscale": "RdYlBu_r"}
    assert default_palette(temp, diverging=True)["colorscale"] == "RdBu_r"
    speed = make_gridded(n_time=1, name="ws", units="m s-1")["ws"]
    speed.attrs["standard_name"] = "wind_speed"
    assert default_palette(speed)["colorscale"] == "YlGn"


def test_theme_defaults_replace_kind_colors(tmp_path):
    da = make_gridded(n_time=1)["precip"]
    da.attrs.update(units="mm", aggregation_period="7 day")
    path = tmp_path / "theme.json"
    path.write_text(
        '{"palettes": {"agency": {"colors": ["#fff", "#cfc", "#0a0", "#00f"], '
        '"bounds": [0, 1, 10]}}, "defaults": {"precip": "agency", "temperature": "Viridis"}}'
    )
    theme = load_theme(path)
    assert default_palette(da, theme=theme)["name"] == "agency"
    assert theme["defaults"]["precip_anomaly"] == "default_precip_anom"  # untouched kinds stay
    path.write_text('{"defaults": {"rain": "agency"}}')
    with pytest.raises(UsageError, match="defaults.rain is not a field kind"):
        load_theme(path)
    path.write_text('{"defaults": {"precip": "no_such"}}')
    with pytest.raises(UsageError, match="neither a palette"):
        load_theme(path)


def test_theme_overlays_merge_into_standard_lines(tmp_path):
    path = tmp_path / "theme.json"
    path.write_text('{"overlays": {"borders": {"line": {"color": "#ff0000"}}}}')
    overlays = load_theme(path)["overlays"]
    assert overlays["borders"]["line"] == {"color": "#ff0000", "width": 1.2}
    assert overlays["lakes"]["fillcolor"] == "#708090"
    path.write_text('{"overlays": {"roads": {"line": {"color": "red"}}}}')
    with pytest.raises(UsageError, match="overlays.roads must be one of"):
        load_theme(path)
    path.write_text('{"overlays": {"borders": {"color": "red"}}}')
    with pytest.raises(UsageError, match=r"theme\.json: overlays\.borders: Invalid property"):
        load_theme(path)


def test_theme_default_precip_palette_replaces_the_window_default(tmp_path):
    da = make_gridded(n_time=1)["precip"]
    da.attrs.update(units="mm", aggregation_period="7 day")
    path = tmp_path / "theme.json"
    path.write_text(
        '{"palettes": {"default_precip": {"colors": ["#fff", "#0a0", "#00f"], "bounds": [0, 3]}}}'
    )
    palette = default_palette(da, theme=load_theme(path))
    assert palette["bounds"] == [0.0, 3.0]


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


def test_default_theme_file_is_a_theme_file_and_is_the_standard_look():
    from pathlib import Path

    from weather_skills_plotting.palettes import DEFAULT_THEME_FILE, default_theme

    # The shipped file loads as a --theme-file, layered on itself it changes nothing.
    assert load_theme(Path(str(DEFAULT_THEME_FILE))) == default_theme()
    theme = default_theme()
    assert theme["defaults"]["precip"] == "default_precip"
    assert theme["overlays"]["lakes"]["fill"] == "toself"
    assert "rocket" in theme["palettes"]
