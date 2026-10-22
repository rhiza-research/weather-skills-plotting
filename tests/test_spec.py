"""The plot spec: loading, merging, meta checks, Plotly validation."""

import json

import pytest
from weather_skills_core.errors import UsageError

from weather_skills_plotting.spec import (
    check_meta,
    deep_merge,
    fill_defaults,
    load_spec,
    merge_spec,
    merge_traces,
    validate,
)
from weather_skills_plotting.themes import default_theme

PALETTES = default_theme()["palettes"]


def test_load_inline_and_file(tmp_path):
    spec = {"data": [{"type": "heatmap", "uid": "a"}], "layout": {"title": {"text": "T"}}}
    assert load_spec(json.dumps(spec)) == spec
    path = tmp_path / "s.json"
    path.write_text(json.dumps(spec))
    assert load_spec(str(path)) == spec


def test_load_rejects_non_object_and_bad_json():
    with pytest.raises(UsageError, match="not valid JSON"):
        load_spec("{nope")
    with pytest.raises(UsageError, match="not a file or a JSON object"):
        load_spec("missing.json")


def test_unknown_top_level_key():
    with pytest.raises(UsageError, match="top-level key"):
        load_spec({"data": [], "frames": []})


def test_merge_traces_by_uid_position_and_append():
    base = [
        {"uid": "a", "type": "heatmap", "meta": {"source": {"input": "a"}}},
        {"uid": "b", "type": "heatmap"},
    ]
    out = merge_traces(base, [{"uid": "b", "type": "contour"}, {"uid": "new", "type": "scatter"}])
    assert [t["uid"] for t in out] == ["a", "b", "new"]
    assert out[1]["type"] == "contour"
    out = merge_traces(base, [{"zmax": 5, "meta": {"source": {"variable": "tp"}}}])
    assert out[0]["zmax"] == 5
    assert out[0]["meta"]["source"] == {"input": "a", "variable": "tp"}


def test_merge_traces_new_bound_trace_without_input_names_the_input_uids():
    base = [
        {"uid": "West", "type": "scatter", "meta": {"source": {"input": "West"}}},
        {"uid": "East", "type": "scatter", "meta": {"source": {"input": "East"}}},
    ]
    xy = {"uid": "0", "type": "scatter", "meta": {"x": "precip_7d", "y": "county"}}
    with pytest.raises(UsageError, match="uids 'West', 'East'.*set meta.source.input"):
        merge_traces(base, [xy])
    # Naming the input, or adding a trace that reads no input, is fine.
    ok = merge_traces(base, [{**xy, "meta": {**xy["meta"], "source": {"input": "East"}}}])
    assert ok[2]["meta"]["source"] == {"input": "East"}
    edge = {
        "uid": "edge",
        "type": "scatter",
        "meta": {"bind": "geojson", "source": {"geojson": "a"}},
    }
    assert len(merge_traces(base, [edge, {"uid": "city", "type": "scatter", "x": [1]}])) == 4
    # One input: the trace falls back to it, as before.
    assert len(merge_traces(base[:1], [xy])) == 2


def test_merge_traces_position_past_end_errors():
    with pytest.raises(UsageError, match="give a new trace a uid"):
        merge_traces([{"uid": "a"}], [{}, {"type": "bar"}])


def test_merge_layout_named_annotations():
    base = {"layout": {"annotations": [{"name": "panel-title-1", "text": "auto", "x": 0.5}]}}
    out = merge_spec(
        base,
        {"layout": {"annotations": [{"name": "panel-title-1", "text": "Mine"}, {"text": "extra"}]}},
    )
    anns = out["layout"]["annotations"]
    assert anns[0] == {"name": "panel-title-1", "text": "Mine", "x": 0.5}
    assert anns[1] == {"text": "extra"}


def test_merge_layout_deep():
    out = merge_spec(
        {"layout": {"xaxis": {"range": [0, 1], "title": {"text": "x"}}}},
        {"layout": {"xaxis": {"title": {"text": "y"}}}},
    )
    assert out["layout"]["xaxis"] == {"range": [0, 1], "title": {"text": "y"}}


def test_deep_merge_and_fill_defaults():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}
    target = {"a": {"b": 1}}
    fill_defaults(target, {"a": {"b": 9, "c": 2}, "d": 4})
    assert target == {"a": {"b": 1, "c": 2}, "d": 4}


@pytest.mark.parametrize(
    "meta, match",
    [
        ({"bnd": "field"}, "data\\[0\\].meta.bnd is not a known key"),
        ({"bind": "grid"}, "bind 'grid' must be one of"),
        ({"source": {"inptu": "a"}}, "meta.source.inptu is not a known key"),
        ({"source": {"reduce": ["latitude"]}}, "meta.source.reduce is not a known key"),
        ({"band": [10, 90]}, "band was removed.*summarize-dim --method quantile"),
        ({"along_color": "cycle"}, "along_color was removed.*style one by its uid"),
        ({"members": False}, "members was removed.*visible"),
        ({"source": {"point": {"lat": 0, "lon": 0}}}, "point was removed.*point-value"),
        ({"source": {"mask_geojson": "k.geojson"}}, "mask_geojson was removed.*clip-region"),
        ({"arrows": {"step": 2}}, "step was removed.*isel range steps"),
        ({"x": "dmi"}, "needs both x and y"),
        ({"x": {"input": "a"}, "y": "precip"}, "x must be a variable name"),
        ({"palette": "no_such"}, "not a known palette"),
        ({"palette": {"colors": ["#fff", "#000"], "bounds": [0, 1, 2, 3]}}, "colors must have"),
    ],
)
def test_trace_meta_errors(meta, match):
    with pytest.raises(UsageError, match=match):
        check_meta({"data": [{"type": "heatmap", "meta": meta}]}, PALETTES)


@pytest.mark.parametrize(
    "meta, match",
    [
        ({"geo": {"bbox": [1, 2, 3, 4]}}, "geo was removed.*clip-region.*xaxis.range"),
        ({"overlays": False}, "overlays was removed.*uids coastline"),
        ({"export": {"scale": 2}}, "export was removed.*--scale"),
        ({"animation": {"duration": 300}}, "animation was removed.*updatemenus"),
        ({"version": 3}, "version 3 is not supported"),
    ],
)
def test_layout_meta_errors(meta, match):
    with pytest.raises(UsageError, match=match):
        check_meta({"layout": {"meta": meta}}, PALETTES)


def test_duplicate_uid():
    with pytest.raises(UsageError, match="more than once"):
        check_meta({"data": [{"uid": "a"}, {"uid": "a"}]}, PALETTES)


def test_plotly_validates_everything_else():
    with pytest.raises(UsageError, match="(?s)'colorscal'.*Did you mean \"colorscale\""):
        validate({"data": [{"type": "heatmap", "colorscal": "Blues"}]})
    with pytest.raises(UsageError, match="'rnage'"):
        validate({"layout": {"xaxis": {"rnage": [0, 1]}}})
    good = {
        "data": [{"type": "heatmap", "uid": "a", "meta": {"source": {"input": "a"}}}],
        "layout": {"meta": {"version": 4}, "title": {"text": "ok"}},
    }
    assert validate(good) is good


@pytest.mark.parametrize("name", ["weather_skills", "colorblind", "plotly_white+presentation"])
def test_named_templates_validate(name):
    assert validate({"layout": {"template": name}})


def test_hints_for_common_misplaced_keys():
    with pytest.raises(UsageError, match='nested path: write {"source": {"variable"'):
        check_meta({"data": [{"meta": {"source.variable": "tp"}}]}, PALETTES)
    with pytest.raises(UsageError, match="plain x/y axes"):
        check_meta({"data": [{"type": "scattermap"}]}, PALETTES)
    with pytest.raises(UsageError, match="coloraxis"):
        validate({"layout": {"colorbar": {}}})
