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
    assert traces[-1]["x"] == "@NE.coastline_10m.clip(5, 33, -5, 42).x"
    assert traces[0]["xaxis"] == "x3"
    wide = ev("ws.basemap({n: 40, w: -20, s: -40, e: 60})")
    assert wide[0]["name"] == "rivers" and "_50m" in wide[0]["x"]
