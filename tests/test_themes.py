"""Plot themes: default.json, shipped themes, and --theme-file layering."""

import json
from pathlib import Path

import pytest
from weather_skills_core.errors import UsageError

from conftest import make_gridded
from weather_skills_plotting.palettes import default_palette, parse_palette
from weather_skills_plotting.themes import DEFAULT_THEME_FILE, default_theme, load_theme


@pytest.mark.parametrize("name", sorted(default_theme()["palettes"]))
def test_standard_palettes_pass_theme_file_checks(name):
    # A standard palette copied into a --theme-file must load: right color count for its bounds.
    parse_palette(default_theme()["palettes"][name], loc=name, registry={})


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
    # The shipped file loads as a --theme-file, layered on itself it changes nothing.
    assert load_theme(Path(str(DEFAULT_THEME_FILE))) == default_theme()
    theme = default_theme()
    assert theme["defaults"]["precip"] == "default_precip"
    assert theme["overlays"]["lakes"]["fill"] == "toself"
    assert "rocket" in theme["palettes"]  # listed in default.json
    assert "ppt_week" in theme["palettes"]  # computed in palettes.py


def test_shipped_theme_by_name():
    theme = load_theme("tropical_tidbits")
    assert theme["defaults"]["precip"] == "tt_precip_total"
    assert theme["defaults"]["wind_speed"] == "tt_wind"
    # Layered on the standard look: what it leaves out is unchanged.
    assert theme["overlays"]["lakes"]["fill"] == "toself"
    for name in ("tt_precip_rate", "tt_precip_total", "tt_pwat", "tt_wind", "tt_z500"):
        assert name in theme["palettes"]


def test_theme_file_mistakes_are_usage_errors(tmp_path):
    with pytest.raises(UsageError, match="shipped: tropical_tidbits"):
        load_theme("tropical")
    bad = tmp_path / "bad.json"
    bad.write_text("{bad")
    with pytest.raises(UsageError, match="not valid JSON/TOML"):
        load_theme(bad)


def test_theme_styles_merge_and_reach_the_figure(tmp_path):
    from weather_skills_plotting import compile

    path = tmp_path / "theme.json"
    path.write_text(
        '{"styles": {"maps": {"plot_bgcolor": "#000000"}, "isobars": {"line": {"width": 3}}}}'
    )
    theme = load_theme(path)
    assert theme["styles"]["isobars"]["line"] == {"color": "black", "width": 3}
    ds = make_gridded(n_time=1)
    fig = compile(
        {"data": [{"uid": "a", "type": "heatmap", "meta": {"source": {"input": "a"}}}]},
        {"a": ds},
        theme=theme,
    )
    assert fig.layout.plot_bgcolor == "#000000"
    path.write_text('{"styles": {"halo": {"opacity": 1}}}')
    with pytest.raises(UsageError, match="styles.halo must be one of"):
        load_theme(path)


def test_replacing_a_master_recolors_its_windows(tmp_path):
    master = default_theme()["palettes"]["ppt_master"]
    colors = ["#000000", *master["colors"][1:]]
    path = tmp_path / "theme.json"
    path.write_text(json.dumps({"palettes": {"ppt_master": {**master, "colors": colors}}}))
    palettes = load_theme(path)["palettes"]
    assert palettes["ppt_week"]["colors"][0] == "#000000"
    assert palettes["ppt_season"]["colors"][0] == "#000000"
