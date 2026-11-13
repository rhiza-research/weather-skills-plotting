"""ws.libsonnet: the helpers return plain Plotly JSON."""

import json

import _gojsonnet
import plotly.graph_objects as go
import pytest

from weather_skills_plotting.render import LIB_DIR

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


@pytest.mark.parametrize("name", ["ppt_day", "ppt_week", "ppt_anom_month", "spi", "hits", "bias"])
def test_every_palette_makes_a_valid_coloraxis(name):
    go.Figure(layout={"coloraxis": ev(f"ws.stepped(ws.palettes.{name})")})


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
        "admin",
        "rivers",
        "lakes",
        "borders",
        "disputed",
        "coastline",
    ]
    assert traces[-1]["x"] == "@NE.coastline_10m.clip(5.3, 32.7, -5.3, 42.3).x"
    assert traces[0]["x"] == "@GB.admin1.clip(5.3, 32.7, -5.3, 42.3).x"
    assert ev(f"ws.basemap({BBOX}, admin=2)")[0]["x"].startswith("@GB.admin2.clip(")
    with pytest.raises(Exception, match="admin is 1, 2, false or 'auto'"):
        ev(f"ws.basemap({BBOX}, admin=3)")
    assert traces[0]["xaxis"] == "x3"
    wide = ev("ws.basemap({n: 40, w: -20, s: -40, e: 60})")
    assert wide[0]["name"] == "rivers" and "_50m" in wide[0]["x"]


def test_class_bar_draws_equal_bands_labelled_at_the_bounds():
    layout = ev("ws.classBar(ws.palettes.ppt_day, 'mm')")
    go.Figure(layout=layout)
    assert layout["coloraxis"]["showscale"] is False
    rects = [s for s in layout["shapes"] if s["type"] == "rect"]
    heights = {round(s["y1"] - s["y0"], 9) for s in rects}
    assert len(rects) == 9 and len(heights) == 1  # nine classes, one height
    assert [s["type"] for s in layout["shapes"][-2:]] == ["path", "path"]  # under / over
    texts = [a["text"] for a in layout["annotations"]]
    assert texts == ["0", "1", "2", "5", "10", "15", "20", "30", "40", "50", "mm"]


def test_class_bar_names_classes_when_the_palette_has_labels():
    layout = ev("ws.classBar(ws.palettes.hits, coloraxis='coloraxis2')")
    assert [a["text"] for a in layout["annotations"]] == ["Disagree", "Both below", "Hit"]
    assert "coloraxis2" in layout


def test_class_bar_labels_one_per_class_or_one_per_color():
    palette = "{colors: ['#0', '#1', '#2', '#3'], bounds: [1, 10, 20]"
    inner = ev(f"ws.classBar({palette}, labels: ['a', 'b']}})")
    assert [a["text"] for a in inner["annotations"]] == ["a", "b"]
    every = ev(f"ws.classBar({palette}, labels: ['<1', 'a', 'b', '>20']}})")
    texts = {a["text"]: a["y"] for a in every["annotations"]}
    # The under label sits below the first band, the over label above the last.
    assert list(texts) == ["a", "b", "<1", ">20"]
    assert texts["<1"] < 0.05 < texts["a"] < texts["b"] < 0.9 < texts[">20"]
    with pytest.raises(Exception, match=r"3 labels for 2 classes.*\(2\).*\(4\)"):
        ev(f"ws.classBar({palette}, labels: ['a', 'b', 'c']}})")


def test_class_bar_formats_bounds_with_a_jsonnet_code_only():
    palette = "{colors: ['#0', '#1', '#2'], bounds: [25, 50]}"
    bar = ev(f"ws.classBar({palette}, format='%d%%')")
    assert [a["text"] for a in bar["annotations"]] == ["25%", "50%"]
    with pytest.raises(Exception, match=r"Jsonnet % code.*not a d3 format like \".0%\""):
        ev(f"ws.classBar({palette}, format='.0%')")


def test_class_bar_triangles_stay_short_in_a_tall_figure():
    layout = ev(
        "ws.grid({n: 5, w: 33, s: -5, e: 42}, rows=4, cols=3) + ws.classBar(ws.palettes.ppt_day)"
    )
    plot_h = layout["height"] - layout["margin"]["t"] - layout["margin"]["b"]
    tip = [
        s for s in layout["shapes"] if s.get("name") == "classBar-coloraxis" and s["type"] == "path"
    ][0]["path"]
    # "M x,y L x,y L x,y Z": the first pair is on the base, the last is the tip.
    base, point = (float(tip.split()[i].split(",")[1]) for i in (1, 5))
    assert 0 < (base - point) * plot_h <= 24.01


def test_class_bar_replaces_its_own_axis_bar_only():
    daily = ev("ws.classBar(ws.palettes.ppt_day, 'mm')")
    swapped = ev(
        "{annotations: [{text: 'mine'}]} + ws.classBar(ws.palettes.ppt_week, 'mm')"
        " + ws.classBar(ws.palettes.ppt_day, 'mm')"
    )
    assert swapped["shapes"] == daily["shapes"]
    assert swapped["annotations"] == [{"text": "mine"}] + daily["annotations"]
    two = ev(
        "ws.classBar(ws.palettes.ppt_day, 'mm') + ws.classBar(ws.palettes.hits, coloraxis='coloraxis2')"
    )
    assert {s["name"] for s in two["shapes"]} == {"classBar-coloraxis", "classBar-coloraxis2"}


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


def test_maps_fill_the_sea_under_the_data():
    seas = lambda layout: [s for s in layout["shapes"] if s["name"].startswith("basemap-sea")]  # noqa: E731
    sea = seas(ev(f"ws.map({BBOX})"))
    assert len(sea) == 1 and sea[0]["layer"] == "below" and sea[0]["path"].startswith("@NE.ocean_")
    assert seas(ev(f"ws.map({BBOX}, sea=null)")) == []
    # In either order with a classBar, both keep their shapes; a second map's sea replaces the first.
    bar = ev(f"ws.classBar(ws.palettes.ppt_day) + ws.map({BBOX}) + ws.map({BBOX}, sea='red')")
    assert [s["fillcolor"] for s in seas(bar)] == ["red"] and len(bar["shapes"]) > 1
    grid = ev(f"ws.grid({BBOX}, rows=2, cols=2, empty=[3])")
    assert [s["xref"] for s in seas(grid)] == ["x", "x2", "x3"]


def test_basemap_view_reaches_only_the_border_layers():
    refs = {t["name"]: t["x"] for t in ev(f"ws.basemap({BBOX}, view='KEN')")}
    assert all(('view="KEN"' in x) == (name in ("borders", "disputed")) for name, x in refs.items())


def test_basemap_layers_are_on_unless_switched_off():
    names = lambda e: [t["name"] for t in ev(e)]  # noqa: E731
    assert names(f"ws.basemap({BBOX})") == [
        "admin",
        "rivers",
        "lakes",
        "borders",
        "disputed",
        "coastline",
    ]
    assert names(f"ws.basemap({BBOX}, lakes=false)") == [
        "admin",
        "rivers",
        "borders",
        "disputed",
        "coastline",
    ]
    assert "admin" not in names("ws.basemap({n: 20, w: 20, s: -20, e: 60})")
    assert "admin" in names("ws.basemap({n: 20, w: 20, s: -20, e: 60}, admin=2)")
    assert names(f"ws.basemap({BBOX}, disputed=false, rivers=false, admin=false)") == [
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


@pytest.mark.parametrize(
    "name", __import__("weather_skills_plotting.render", fromlist=["x"]).palette_names()
)
def test_every_named_palette_is_a_valid_coloraxis(name):
    go.Figure(layout={"coloraxis": ev(f"ws.stepped(ws.palettes.{name})")})


def test_continuous_palette_has_no_bounds_ticks():
    axis = ev("ws.stepped({colors: ['#000', '#888', '#fff']})")
    assert axis["colorscale"] == [[0, "#000"], [0.5, "#888"], [1, "#fff"]] and "cmin" not in axis


def test_a_dateline_window_reads_east_and_west():
    axis = ev("ws.map({n: 10, w: 170, s: -10, e: -170}, pad=0).xaxis")
    assert axis["range"] == [170, 190]
    assert axis["ticktext"] == ["170°E", "175°E", "180°", "175°W", "170°W"]
    assert "ticktext" not in ev(f"ws.map({BBOX}).xaxis")


def test_class_bar_without_under_and_over_has_no_triangles():
    layout = ev("ws.classBar({colors: ['#a', '#b'], bounds: [0, 1, 2]})")
    assert all(s["type"] == "rect" for s in layout["shapes"])


def test_unknown_parameter_lists_the_called_functions_parameters():
    from weather_skills_core.errors import UsageError

    from weather_skills_plotting.render import SpecArg, evaluate

    spec = f"local ws = import 'ws.libsonnet'; {{layout: ws.map({BBOX}) + ws.classBar(ws.palettes.ppt_day, axis='c')}}"
    with pytest.raises(
        UsageError, match=r"ws\.classBar\(p, title='', coloraxis='coloraxis'"
    ) as err:
        evaluate(SpecArg(spec), {}, {})
    assert "ws.basemap" not in str(err.value)
