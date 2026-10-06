"""Correctness tests for plot-vega: every recipe renders, plus the CLI contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from skill_conftest import SKILLS_ROOT, load_skill, run_skill
from vega_data import NE_FIXTURES, RECIPE_INPUTS, write_all
from weather_skills_core.provenance import load_figure_history

RECIPES = SKILLS_ROOT / "plot-vega" / "recipes"


@pytest.fixture(autouse=True)
def _ne_fixtures(monkeypatch):
    monkeypatch.setenv("WS_NE_CACHE", str(NE_FIXTURES))


@pytest.fixture(scope="module")
def plot_vega():
    return load_skill("plot-vega", "plot_vega").plot_vega


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    return write_all(tmp_path_factory.mktemp("vega_inputs"))


def _inputs(data, mapping):
    args = []
    for name, fixture in mapping.items():
        args += ["-i", f"{name}={data[fixture]}"]
    return args


def test_every_recipe_has_inputs_and_a_description():
    names = {p.stem for p in RECIPES.glob("*.json")}
    assert names == set(RECIPE_INPUTS)
    for path in RECIPES.glob("*.json"):
        spec = json.loads(path.read_text())
        assert "Inputs: -i" in spec["description"], path.name


@pytest.mark.parametrize("recipe", sorted(RECIPE_INPUTS))
def test_recipe_renders(recipe, tmp_path, data, plot_vega, capsys):
    out = tmp_path / f"{recipe}.png"
    run_skill(
        plot_vega,
        *_inputs(data, RECIPE_INPUTS[recipe]),
        "--spec",
        str(RECIPES / f"{recipe}.json"),
        "-o",
        str(out),
    )
    assert out.stat().st_size > 5000
    stdout = capsys.readouterr().out
    assert "bound " in stdout
    assert "plot hash:" in stdout
    assert "data: NULL" not in stdout


def test_describe_without_spec(data, plot_vega, capsys):
    run_skill(plot_vega, "--describe", "-i", f"fcst={data['fcst_weekly_mean']}")
    out = capsys.readouterr().out
    assert "input fcst: zarr  dims {'step': 4, 'latitude': 23, 'longitude': 19}" in out
    assert "long_name='Total precipitation'" in out
    assert "derived fields sources" in out and "valid_time" in out


def test_describe_with_spec_lists_bindings_and_defaults(tmp_path, data, plot_vega, capsys):
    run_skill(
        plot_vega,
        "--describe",
        *_inputs(data, RECIPE_INPUTS["map_heatmap_stations"]),
        "--spec",
        str(RECIPES / "map_heatmap_stations.json"),
    )
    out = capsys.readouterr().out
    assert "bound obs: 8500 rows (lon, lon2, lat, lat2, precip)" in out
    assert "bound stations: 8 rows (lon, lat, name, precip)" in out
    assert "default spec.layer[0].encoding.color.scale <- ppt_week" in out
    assert not list(tmp_path.iterdir())


def test_dump_spec_is_plain_vega_lite(tmp_path, data, plot_vega):
    dump = tmp_path / "final.vl.json"
    run_skill(
        plot_vega,
        *_inputs(data, RECIPE_INPUTS["map_contours"]),
        "--spec",
        str(RECIPES / "map_contours.json"),
        "--dump-spec",
        str(dump),
        "--dump-spec-rows",
        "2",
    )
    spec = json.loads(dump.read_text())
    assert spec["$schema"].endswith("vega-lite/v6.json")
    assert all(isinstance(rows, list) and len(rows) <= 2 for rows in spec["datasets"].values())
    assert spec["projection"]["fit"]["geometry"]["type"] == "MultiPoint"
    assert spec["layer"][0]["encoding"]["color"]["scale"]["type"] == "threshold"


def test_dump_spec_stdout(data, plot_vega, capsys):
    run_skill(
        plot_vega,
        *_inputs(data, RECIPE_INPUTS["timeseries_weekly_line"]),
        "--spec",
        str(RECIPES / "timeseries_weekly_line.json"),
        "--dump-spec",
    )
    captured = capsys.readouterr()
    spec = json.loads(captured.out)
    assert len(spec["datasets"]["weekly"]) == 52
    assert "bound weekly: 52 rows" in captured.err


def test_html_and_jpeg_outputs_carry_provenance(tmp_path, data, plot_vega):
    for suffix in (".html", ".jpg"):
        out = tmp_path / f"bars{suffix}"
        run_skill(
            plot_vega,
            *_inputs(data, RECIPE_INPUTS["bar_weekly_totals"]),
            "--spec",
            str(RECIPES / "bar_weekly_totals.json"),
            "-o",
            str(out),
        )
        history = load_figure_history(out)
        assert history and history[-1]["skill"] == "plot-vega"
    assert "weather_skills_history" in (tmp_path / "bars.html").read_text()


def test_provenance_records_original_spec_and_inputs(tmp_path, data, plot_vega):
    out = tmp_path / "region.png"
    run_skill(
        plot_vega,
        *_inputs(data, RECIPE_INPUTS["map_region_outline"]),
        "--spec",
        str(RECIPES / "map_region_outline.json"),
        "-o",
        str(out),
    )
    args = load_figure_history(out)[-1]["args"]
    original = json.loads((RECIPES / "map_region_outline.json").read_text())
    assert args["spec"] == original
    kinds = {i["name"]: i["kind"] for i in args["inputs"]}
    assert kinds == {"obs": "zarr", "region": "geojson"}
    region = next(i for i in args["inputs"] if i["name"] == "region")
    assert len(region["sha256"]) == 64


def test_bare_path_is_named_data(tmp_path, data, plot_vega):
    out = tmp_path / "line.png"
    spec = json.loads((RECIPES / "timeseries_weekly_line.json").read_text())
    spec["datasets"]["weekly"]["zarr"] = "data"
    run_skill(
        plot_vega, "-i", str(data["imerg_weekly"]), "--spec", json.dumps(spec), "-o", str(out)
    )
    assert out.exists()


def _fails(plot_vega, capsys, *argv):
    with pytest.raises(SystemExit) as exc:
        run_skill(plot_vega, *argv)
    return exc.value.code, capsys.readouterr().err


def test_usage_errors_exit_2(tmp_path, data, plot_vega, capsys):
    fcst = f"fcst={data['fcst_weekly_mean']}"
    out = str(tmp_path / "x.png")
    spec = {
        "datasets": {"f": {"zarr": "fcst", "fields": {"lon": "longitude", "tp": "tp"}}},
        "data": {"name": "f"},
        "mark": "circle",
        "encoding": {"x": {"field": "lon", "type": "quantitative"}},
    }
    code, err = _fails(plot_vega, capsys, "-i", fcst, "--spec", json.dumps(spec), "-o", out)
    assert code == 2 and "not columns in fields" in err

    code, err = _fails(plot_vega, capsys, "-i", fcst, "-i", fcst, "--spec", "{}", "-o", out)
    assert code == 2 and "given twice" in err

    code, err = _fails(plot_vega, capsys, "-i", fcst, "-o", out)
    assert code == 2 and "--spec is required" in err

    spec["datasets"]["f"]["sel"] = {"step": "7D", "latitude": 0}
    code, err = _fails(
        plot_vega, capsys, "-i", fcst, "--spec", json.dumps(spec), "-o", str(tmp_path / "x.svg")
    )
    assert code == 2 and "use one of" in err

    code, err = _fails(plot_vega, capsys, "-i", fcst, "--spec", json.dumps(spec))
    assert code == 2 and "-o/--output" in err
    assert not list(Path(tmp_path).iterdir())


def test_help_mentions_vega_lite(plot_vega, capsys):
    with pytest.raises(SystemExit) as exc:
        run_skill(plot_vega, "--help")
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "Vega-Lite" in text and "--describe" in text and "--dump-spec" in text
