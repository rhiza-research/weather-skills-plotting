"""Map canvas and margins (layout.map_layout)."""

from weather_skills_plotting.layout import map_axes, map_layout, register_templates
from weather_skills_plotting.themes import default_theme


def test_plotly_grows_margins_and_tick_labels_push_them():
    register_templates(default_theme())
    layout, _ = map_layout(1, 1, 1.2, titled=True, panel_titles=True, right=True)
    # Margins are a starting size; Plotly may grow them to fit labels and colorbars.
    assert layout["margin"].get("autoexpand", True) is True
    xaxis, yaxis = map_axes(0, (30, 52, -5, 15))
    assert xaxis["automargin"] is True and yaxis["automargin"] is True


def test_room_around_maps_scales_with_the_font():
    register_templates(default_theme())
    small, _ = map_layout(2, 2, 1.2, titled=True, panel_titles=True, right=True)
    big, _ = map_layout(
        2, 2, 1.2, titled=True, panel_titles=True, right=True, user={"font": {"size": 24}}
    )
    for side in ("l", "r", "t", "b"):
        assert big["margin"][side] == 2 * small["margin"][side]
    assert big["width"] > small["width"] and big["height"] > small["height"]
