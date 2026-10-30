"""ws.libsonnet: the helpers return plain Plotly JSON."""

import json

import _gojsonnet
import plotly.graph_objects as go
import pytest

from weather_skills_plotting.spec import LIB_DIR

BBOX = "{n: 5, w: 33, s: -5, e: 42}"


def ev(expr):
    src = f"local ws = import 'ws.libsonnet'; {expr}"
    return json.loads(_gojsonnet.evaluate_snippet("t", src, jpathdir=[str(LIB_DIR)]))


def test_stepped_puts_steps_at_the_bounds():
    axis = ev("ws.stepped({colors: ['#a', '#b', '#c'], bounds: [0, 10, 40, 100]})")
    assert axis["cmin"] == 0 and axis["cmax"] == 100
    assert axis["colorscale"] == [
        [0, "#a"],
        [0.1, "#a"],
        [0.1, "#b"],
        [0.4, "#b"],
        [0.4, "#c"],
        [1, "#c"],
    ]
    assert axis["colorbar"]["tickvals"] == [0, 10, 40, 100]


def test_stepped_under_and_over_get_a_class_width_each():
    axis = ev("ws.stepped({colors: ['u', 'a', 'o'], bounds: [10, 20]})")
    assert (axis["cmin"], axis["cmax"]) == (0, 30)
    assert [c for _, c in axis["colorscale"]] == ["u", "u", "a", "a", "o", "o"]


@pytest.mark.parametrize("name", ["ppt_daily", "ppt_week", "ppt_anom_month", "spi", "hits", "bias"])
def test_every_palette_makes_a_valid_coloraxis(name):
    go.Figure(layout={"coloraxis": ev(f"ws.stepped(ws.palettes.{name})")})


def test_tropical_tidbits_palettes():
    axis = ev("local tt = import 'themes/tropical_tidbits.libsonnet'; ws.stepped(tt.tt_wind)")
    go.Figure(layout={"coloraxis": axis})


def test_map_grid_and_titles_are_valid_plotly():
    layout = ev(
        f"ws.grid({BBOX}, 2, 3) + {{annotations: [ws.panelTitle(i, 'p') for i in std.range(0, 5)]}}"
    )
    go.Figure(layout=layout)
    assert layout["yaxis6"]["scaleanchor"] == "x6"
    assert layout["xaxis4"]["showticklabels"] and not layout["xaxis"]["showticklabels"]
    assert layout["yaxis4"]["showticklabels"] and not layout["yaxis5"]["showticklabels"]
    go.Figure(layout=ev(f"ws.map({BBOX}) + ws.player(['a', 'b'])"))


def test_basemap_traces_reference_natural_earth():
    traces = ev(f"ws.basemap({BBOX}, 2)")
    assert [t["name"] for t in traces] == [
        "admin1",
        "rivers",
        "lakes",
        "borders",
        "disputed",
        "coastline",
    ]
    assert traces[-1]["x"] == "@NE.coastline_10m.clip(5.3, 32.7, -5.3, 42.3).x"
    assert traces[0]["xaxis"] == "x3"
    wide = ev("ws.basemap({n: 40, w: -20, s: -40, e: 60})")
    assert wide[0]["name"] == "rivers" and "_50m" in wide[0]["x"]


def test_class_bar_draws_equal_bands_labelled_at_the_bounds():
    layout = ev("ws.classBar(ws.palettes.ppt_daily, 'mm')")
    go.Figure(layout=layout)
    assert layout["coloraxis"]["showscale"] is False
    rects = [s for s in layout["shapes"] if s["type"] == "rect"]
    heights = {round(s["y1"] - s["y0"], 9) for s in rects}
    assert len(rects) == 9 and len(heights) == 1  # nine classes, one height
    assert [s["type"] for s in layout["shapes"][-2:]] == ["path", "path"]  # under / over
    texts = [a["text"] for a in layout["annotations"]]
    assert texts == ["0", "1", "2", "5", "10", "15", "20", "30", "40", "50", "mm"]


def test_class_bar_names_classes_when_the_palette_has_labels():
    layout = ev("ws.classBar(ws.palettes.hits, axis='coloraxis2')")
    assert [a["text"] for a in layout["annotations"]] == ["Disagree", "Both below", "Hit"]
    assert "coloraxis2" in layout


def test_dates_and_day_of_year_ticks():
    assert ev("ws.date('2026-10-26')") == "26 Oct 2026"
    assert ev("ws.date('2026-10-30T12:00:00', year=false)") == "30 Oct 12 UTC"
    ticks = ev("ws.dayOfYearTicks")
    assert ticks["tickvals"][7] == 213 and ticks["ticktext"][7] == "1 Aug"


def test_a_palette_with_the_wrong_number_of_colors_says_so():
    with pytest.raises(RuntimeError, match="3 colors for 5 bounds"):
        ev("ws.stepped({colors: ['a', 'b', 'c'], bounds: [0, 1, 2, 3, 4]})")


def test_maps_pad_the_bbox_unless_pad_is_zero():
    assert ev(f"ws.map({BBOX}).yaxis.range[1]") > 5
    assert ev(f"ws.map({BBOX}).xaxis.range[0]") < 33
    assert ev(f"ws.map({BBOX}, pad=0).yaxis.range") == [-5, 5]
    assert ev(f"ws.grid({BBOX}, 1, 2).xaxis2.range[1]") > 42
    assert "clip(5.3, 32.7, -5.3, 42.3)" in ev(f"ws.basemap({BBOX})[0].x")


def test_basemap_layers_are_on_unless_switched_off():
    names = lambda e: [t["name"] for t in ev(e)]  # noqa: E731
    assert names(f"ws.basemap({BBOX})") == [
        "admin1",
        "rivers",
        "lakes",
        "borders",
        "disputed",
        "coastline",
    ]
    assert names(f"ws.basemap({BBOX}, lakes=false)") == [
        "admin1",
        "rivers",
        "borders",
        "disputed",
        "coastline",
    ]
    assert "admin1" not in names("ws.basemap({n: 20, w: 20, s: -20, e: 60})")
    assert "admin1" in names("ws.basemap({n: 20, w: 20, s: -20, e: 60}, admin1=true)")
    assert names(f"ws.basemap({BBOX}, disputed=false, rivers=false, admin1=false)") == [
        "lakes",
        "borders",
        "coastline",
    ]


def test_a_ragged_grid_labels_its_filled_edges():
    layout = ev(f"ws.grid({BBOX}, 3, 4, empty=[8, 9])")
    go.Figure(layout=layout)
    assert layout["xaxis5"]["showticklabels"]  # above an empty cell
    assert not layout["xaxis9"]["visible"] and not layout["yaxis10"]["visible"]
    assert layout["yaxis11"]["showticklabels"]  # first filled panel of its row
    assert layout["xaxis11"]["showticklabels"] and not layout["xaxis7"]["showticklabels"]
    go.Figure(layout={**layout, "annotations": [ev("ws.rowTitle(4, 'GEFS')")]})
