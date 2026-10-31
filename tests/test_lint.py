"""check_bindings: figures that bind every data value pass; each other way of putting data in fails."""

import re
from pathlib import Path

import _gojsonnet
import pytest

from weather_skills_plotting.lint import UnboundDataError, check_bindings
from weather_skills_plotting.render import LIB_DIR

HERE = Path(__file__).parent / "data"


def problems(fig):
    with pytest.raises(UnboundDataError) as caught:
        check_bindings(fig)
    return caught.value.problems


def scatter(**kw):
    return {"data": [{"type": "scatter", "x": "@t", "y": "@v", **kw}]}


def test_example_passes():
    check_bindings(_gojsonnet.evaluate_file(str(HERE / "lint_example.jsonnet")))  # JSON text


def test_house_template_and_helpers_pass():
    # ws.template's shapedefaults take the class of one shape, layout.shape.
    src = (
        "local ws = import 'ws.libsonnet'; local b = {n: 5, w: 33, s: -5, e: 42};"
        "{data: ws.basemap(b), layout: ws.map(b) + ws.classBar(ws.palettes.ppt_week, 'mm')"
        " + ws.player(['a']) + {template: ws.template, annotations+: [ws.panelTitle(0, 'A')]}}"
    )
    check_bindings(_gojsonnet.evaluate_snippet("t", src, jpathdir=[str(LIB_DIR)]))


@pytest.mark.parametrize(
    "fig",
    [
        scatter(),
        scatter(x=["@a", "@b"]),  # a list made only of bindings
        scatter(marker={"color": "#2a78d6", "size": 8}),  # one value per key is styling
        scatter(marker={"color": "@v"}),
        {"data": [{"type": "heatmap", "z": "@grid"}], "layout": {"xaxis": {"ticktext": "@labels"}}},
        {
            "data": [
                {"type": "bar", "x": "@t", "y": "@v", "error_y": {"type": "data", "array": "@err"}}
            ]
        },
        {"data": [{"y": "@v"}]},  # typeless trace is scatter
        {
            "layout": {
                "shapes": [
                    {
                        "type": "rect",
                        "xref": "paper",
                        "yref": "paper",
                        "x0": 0,
                        "x1": 1,
                        "y0": 0,
                        "y1": 0.1,
                    }
                ]
            }
        },
        {
            "layout": {
                "annotations": [
                    {"text": "Panel A", "xref": "paper", "yref": "paper", "x": 0, "y": 1}
                ]
            }
        },
        {
            "layout": {
                "updatemenus": [
                    {"buttons": [{"method": "restyle", "args": [{"visible": [True, False]}]}]}
                ]
            }
        },
        {
            "layout": {
                "updatemenus": [{"buttons": [{"method": "restyle", "args": [{"y": ["@other"]}]}]}]
            }
        },
        {
            "layout": {
                "xaxis2": {"title": {"text": "Lead time"}},
                "template": {"data": {"scatter": [{"mode": "lines"}]}},
            }
        },
        {
            "data": [{"type": "bar", "x": "@t", "y": "@v"}],
            "frames": [{"name": "f1", "data": [{"y": "@v_next"}]}],
        },
    ],
)
def test_bound_figures_pass(fig):
    check_bindings(fig)


@pytest.mark.parametrize(
    "fig, path, words",
    [
        (scatter(y=[1, 2, 3]), "data[0].y", "data key"),
        (scatter(x=["@a", 5]), "data[0].x", "data key"),
        (scatter(y={"dtype": "f8", "bdata": "AAAAAAAA8D8="}), "data[0].y", "data key"),
        (scatter(y="@@1"), "data[0].y", "data key"),  # @@ starts literal text, not a reference
        (scatter(customdata=[[1], [2]]), "data[0].customdata", "data key"),
        (scatter(marker={"size": [4, 9, 30]}), "data[0].marker.size", "per point"),
        (scatter(text=["12 °C", "40 °C"]), "data[0].text", "per point"),
        (
            {"data": [{"type": "heatmap", "z": "@grid", "text": [["hot"]]}]},
            "data[0].text",
            "data key",
        ),
        (
            {"data": [{"type": "scatter", "y": "@v", "x0": "2026-01-01", "dx": 86400000}]},
            "data[0].x0",
            "generates",
        ),
        (
            {"data": [{"type": "bar", "x": "@t", "y": "@v", "base": 100}]},
            "data[0].base",
            "generates",
        ),
        ({"data": [{"type": "box", "y": "@v", "x0": "Group A"}]}, "data[0].x0", "generates"),
        (scatter(error_y={"visible": True}), "data[0].error_y", "default 10"),
        (scatter(error_y={"type": "constant", "value": 2}), "data[0].error_y.value", "generates"),
        (
            {"data": [{"type": "image", "source": "data:image/png;base64,iVBORw0KGgo="}]},
            "data[0].source",
            "data key",
        ),
        (
            {
                "data": [
                    {
                        "type": "choropleth",
                        "locations": "@iso",
                        "z": "@v",
                        "geojson": {"type": "FeatureCollection"},
                    }
                ]
            },
            "data[0].geojson",
            "data key",
        ),
        (
            {"layout": {"shapes": [{"type": "path", "path": "M 0 0 L 1 5 L 2 3"}]}},
            "layout.shapes[0].path",
            "data axis",
        ),
        (
            {
                "layout": {
                    "shapes": [
                        {
                            "type": "line",
                            "xref": "paper",
                            "yref": "y2",
                            "x0": 0,
                            "x1": 1,
                            "y0": 30,
                            "y1": 30,
                        }
                    ]
                }
            },
            "layout.shapes[0].y0",
            "data axis",
        ),
        (
            {"layout": {"annotations": [{"text": "record high", "x": "2026-03-01", "y": 41}]}},
            "layout.annotations[0].x",
            "data axis",
        ),
        (
            {
                "layout": {
                    "images": [
                        {
                            "source": "data:image/png;base64,iVBORw0KGgo=",
                            "xref": "paper",
                            "yref": "paper",
                        }
                    ]
                }
            },
            "layout.images[0].source",
            "data key",
        ),
        ({"layout": {"meta": [1, 2, 3]}}, "layout.meta", "per point"),
        (
            {
                "layout": {
                    "updatemenus": [
                        {"buttons": [{"method": "restyle", "args": [{"y": [[1, 2, 3]]}]}]}
                    ]
                }
            },
            "layout.updatemenus[0].buttons[0].args.y",
            "restyled data key",
        ),
        (
            {
                "layout": {
                    "updatemenus": [
                        {
                            "buttons": [
                                {"method": "update", "args": [{"marker": {"size": [[5, 50]]}}, {}]}
                            ]
                        }
                    ]
                }
            },
            "layout.updatemenus[0].buttons[0].args.marker.size",
            "per point",
        ),
        (
            {
                "layout": {
                    "sliders": [{"steps": [{"method": "relayout", "args": [{"shapes[0].y0": 30}]}]}]
                }
            },
            "layout.sliders[0].steps[0].args.shapes[0].y0",
            "place shapes",
        ),
        (
            {
                "layout": {
                    "updatemenus": [
                        {"buttons": [{"method": "animate", "args": [[{"data": [{"y": [1, 2]}]}]]}]}
                    ]
                }
            },
            "layout.updatemenus[0].buttons[0].args.data.y",
            "inline",
        ),
        (
            {
                "data": [{"type": "bar", "x": "@t", "y": "@v"}],
                "frames": [{"data": [{"y": [5, 6]}]}],
            },
            "frames[0].data[0].y",
            "data key",
        ),
        (
            {"layout": {"template": {"data": {"bar": [{"y": [1, 2]}]}}}},
            "layout.template.data.bar[0].y",
            "data key",
        ),
        (
            {"layout": {"template": {"layout": {"annotations": [{"x": 1, "y": 2, "text": "x"}]}}}},
            "layout.template.layout.annotations[0].x",
            "data axis",
        ),
        (scatter(marker={"colour": "red"}), "data[0].marker.colour", "unknown key"),
        ({**scatter(), "config": {"x": [1]}}, "config", "unknown top-level"),
        ({"data": [{"type": "sparkline", "y": "@v"}]}, "data[0].type", "unknown trace type"),
    ],
)
def test_unbound_data_raises(fig, path, words):
    found = problems(fig)
    assert any(p == path and words in message for p, message in found), found


def test_error_lists_every_problem():
    with pytest.raises(UnboundDataError) as caught:
        check_bindings('{"data": [{"type": "scatter", "y": [1, 2], "marker": {"size": [3, 4]}}]}')
    message = str(caught.value)
    assert message.startswith("figure has 2 binding problem(s):")
    assert "data[0].y: data key needs an @binding, found 1" in message
    assert (
        "data[0].marker.size: 'marker.size' given per point needs an @binding, found 3" in message
    )


def test_custom_binding_pattern():
    fig = {"data": [{"type": "scatter", "x": "$t", "y": "$v"}]}
    check_bindings(fig, pattern=re.compile(r"^\$\w+$"))
    assert [p for p, _ in problems(fig)] == ["data[0].x", "data[0].y"]


def test_template_defaults_are_checked():
    found = problems({"layout": {"template": {"layout": {"shapedefaults": {"y0": 30, "y1": 30}}}}})
    assert any(p.endswith("shapedefaults.y0") and "data axis" in m for p, m in found), found
    found = problems({"layout": {"shapedefaults": {"colour": "red"}}})
    assert any("colour" in p and "unknown key" in m for p, m in found), found
