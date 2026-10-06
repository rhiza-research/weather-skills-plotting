"""End-to-end tests for the plot skill."""

import json

import pytest
from skill_conftest import (
    load_skill,
    make_forecast,
    make_gridded,
    make_point_obs,
    run_skill,
    write_zarr,
)
from weather_skills_core.provenance import load_figure_history

plot_mod = load_skill("plot", "plot")


@pytest.fixture(scope="module")
def plot_fn():
    return plot_mod.plot


def _dump(plot_fn, capsys, *argv):
    run_skill(plot_fn, *argv, "--dump-spec", "-")
    return json.loads(capsys.readouterr().out)


def test_dump_spec_defaults_by_data_shape(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(), tmp_path / "grid.zarr")
    pts = write_zarr(make_point_obs(), tmp_path / "pts.zarr")
    spec = _dump(plot_fn, capsys, "-i", str(grid), "-i", str(pts))
    a, b = spec["data"]
    assert a == {"uid": "a", "type": "heatmap", "meta": {"source": {"input": "a"}}}
    assert b["meta"]["bind"] == "points" and b["xaxis"] == "x2"
    meta = spec["layout"]["meta"]
    assert meta["version"] == 3 and meta["skill"] == "plot"
    assert meta["inputs"] == {"a": str(grid), "b": str(pts)}


def test_dump_merges_user_spec(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(), tmp_path / "grid.zarr")
    user = {"data": [{"uid": "a", "type": "contour"}], "layout": {"title": {"text": "Hi"}}}
    spec = _dump(plot_fn, capsys, "-i", str(grid), "--spec", json.dumps(user))
    assert spec["data"][0]["type"] == "contour"
    assert spec["data"][0]["meta"] == {"source": {"input": "a"}}
    assert spec["layout"]["title"] == {"text": "Hi"}


def test_dumped_spec_replays_without_file_flags(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(n_time=1), tmp_path / "grid.zarr")
    spec = _dump(plot_fn, capsys, "-i", str(grid))
    out = tmp_path / "replay.png"
    run_skill(plot_fn, "--spec", json.dumps(spec), "-o", str(out))
    assert out.is_file()


def test_png_render_with_provenance_and_qa(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(n_time=2), tmp_path / "grid.zarr")
    out = tmp_path / "map.png"
    run_skill(
        plot_fn,
        "-i",
        str(grid),
        "-o",
        str(out),
        "--spec",
        '{"layout": {"title": {"text": "Precip"}}}',
    )
    text = capsys.readouterr().out
    assert "plot hash:" in text and "data: not null (precip 24/24 finite)" in text
    history = load_figure_history(out)
    assert history and history[-1]["skill"] == "plot"


def test_html_output(tmp_path, plot_fn):
    grid = write_zarr(make_gridded(n_time=1), tmp_path / "grid.zarr")
    out = tmp_path / "map.html"
    run_skill(plot_fn, "-i", str(grid), "-o", str(out))
    html = out.read_text()
    assert "weather_skills_history" in html
    assert "Plotly.newPlot" in html


def test_series_of_a_forecast(tmp_path, plot_fn):
    fc = write_zarr(make_forecast(members=3), tmp_path / "fc.zarr")
    out = tmp_path / "ts.png"
    run_skill(
        plot_fn,
        "-i",
        str(fc),
        "-o",
        str(out),
        "--spec",
        json.dumps(
            {
                "data": [
                    {
                        "uid": "a",
                        "type": "scatter",
                        "meta": {
                            "bind": "series",
                            "along": "number",
                            "band": [10, 90],
                            "source": {"reduce": ["latitude", "longitude"]},
                        },
                    }
                ]
            }
        ),
    )
    assert out.is_file()


def test_xy_flags(tmp_path, plot_fn, capsys):
    x = write_zarr(make_gridded(n_time=3), tmp_path / "x.zarr")
    y = write_zarr(make_gridded(n_time=3, fill=2.0), tmp_path / "y.zarr")
    spec = _dump(plot_fn, capsys, "--x", str(x), "--y", str(y))
    assert spec["data"][0]["meta"]["bind"] == "pair"
    run_skill(plot_fn, "--x", str(x), "--y", str(y), "-o", str(tmp_path / "xy.png"))


def test_layers(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(n_time=1), tmp_path / "grid.zarr")
    pts = write_zarr(make_point_obs(n_time=1), tmp_path / "pts.zarr")
    edge = tmp_path / "edge.geojson"
    edge.write_text(
        json.dumps({"type": "Polygon", "coordinates": [[[9, 0], [14, 0], [14, 4], [9, 4], [9, 0]]]})
    )
    argv = [
        "--layer",
        f"heatmap:{grid}",
        "--layer",
        f"scatter:{pts}",
        "--layer",
        f"outline:{edge}",
        "--layer",
        f"mask:{edge}",
    ]
    spec = _dump(plot_fn, capsys, *argv)
    assert [t["uid"] for t in spec["data"]] == ["a", "b", "c"]
    assert spec["layout"]["meta"]["geo"]["mask_geojson"] == str(edge)
    run_skill(plot_fn, *argv, "-o", str(tmp_path / "layers.png"))


@pytest.mark.parametrize(
    "argv, match",
    [
        (["--layer", "heatmap"], "KIND:PATH"),
        (["--layer", "pie:x.zarr"], "KIND:PATH"),
    ],
)
def test_bad_layer_flag(plot_fn, capsys, argv, match):
    with pytest.raises(SystemExit):
        run_skill(plot_fn, *argv, "-o", "x.png")
    assert match in capsys.readouterr().err


def test_errors_are_actionable(tmp_path, plot_fn, capsys):
    grid = write_zarr(make_gridded(n_time=1), tmp_path / "grid.zarr")
    bad = [
        ('{"inputs": [{"variable": "tp"}]}', "retired version-2 spec"),
        ('{"data": [{"uid": "a", "colorscal": "Blues"}]}', "Did you mean"),
        ('{"layout": {"meta": {"geo": {"region": "Kenya"}}}}', "resolve-region"),
    ]
    for spec, match in bad:
        with pytest.raises(SystemExit):
            run_skill(plot_fn, "-i", str(grid), "-o", str(tmp_path / "x.png"), "--spec", spec)
        assert match in capsys.readouterr().err


def test_help_lists_meta_reference(plot_fn, capsys):
    with pytest.raises(SystemExit):
        run_skill(plot_fn, "--help")
    out = capsys.readouterr().out
    for needle in ("BINDS", "data[].meta.source", "layout.meta", "RECIPES", "plotly.com"):
        assert needle in out


def test_mask_removing_every_station(tmp_path, plot_fn, capsys):
    pts = write_zarr(make_point_obs(n_time=1), tmp_path / "pts.zarr")
    far = tmp_path / "far.geojson"
    far.write_text(
        json.dumps({"type": "Polygon", "coordinates": [[[50, 50], [51, 50], [51, 51], [50, 50]]]})
    )
    with pytest.raises(SystemExit):
        run_skill(
            plot_fn,
            "--layer",
            f"scatter:{pts}",
            "--layer",
            f"mask:{far}",
            "-o",
            str(tmp_path / "x.png"),
        )
    assert "no stations remain" in capsys.readouterr().err


def test_provenance_records_spec_and_layers(tmp_path, plot_fn):
    grid = write_zarr(make_gridded(n_time=1), tmp_path / "grid.zarr")
    out = tmp_path / "p.png"
    spec = {"layout": {"title": {"text": "T"}}}
    run_skill(plot_fn, "--layer", f"heatmap:{grid}", "-o", str(out), "--spec", json.dumps(spec))
    args = load_figure_history(out)[-1]["args"]
    assert args["spec"] == spec
    assert args["layer"] == [f"heatmap:{grid}"]
