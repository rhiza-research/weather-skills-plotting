"""End-to-end tests for plot-timeseries."""

import json

import pytest
from skill_conftest import load_skill, make_forecast, make_gridded, run_skill, write_zarr

mod = load_skill("plot-timeseries", "plot_timeseries")


@pytest.fixture(scope="module")
def ts_fn():
    return mod.plot_timeseries


def _dump(fn, capsys, *argv):
    run_skill(fn, *argv, "--dump-spec", "-")
    return json.loads(capsys.readouterr().out)


def test_one_series_per_input_named_by_file(tmp_path, ts_fn, capsys):
    a = write_zarr(make_gridded(n_time=3), tmp_path / "chirps.zarr")
    b = write_zarr(make_gridded(n_time=3, fill=2.0), tmp_path / "imerg.zarr")
    spec = _dump(ts_fn, capsys, "-i", str(a), "-i", str(b))
    assert [(t["uid"], t["name"]) for t in spec["data"]] == [("a", "chirps"), ("b", "imerg")]
    assert all(t["meta"]["bind"] == "series" for t in spec["data"])


def test_first_trace_settings_apply_to_the_rest(tmp_path, ts_fn, capsys):
    a = write_zarr(make_gridded(n_time=3), tmp_path / "a.zarr")
    b = write_zarr(make_gridded(n_time=3), tmp_path / "b.zarr")
    user = {
        "data": [
            {"uid": "a", "meta": {"source": {"reduce": ["latitude", "longitude"]}}},
            {"uid": "b", "type": "bar"},
        ]
    }
    spec = _dump(ts_fn, capsys, "-i", str(a), "-i", str(b), "--spec", json.dumps(user))
    assert spec["data"][1]["meta"]["source"]["reduce"] == ["latitude", "longitude"]
    assert spec["data"][1]["type"] == "bar"
    run_skill(
        ts_fn,
        "-i",
        str(a),
        "-i",
        str(b),
        "-o",
        str(tmp_path / "ts.png"),
        "--spec",
        json.dumps(user),
    )


def test_spaghetti_html(tmp_path, ts_fn):
    fc = write_zarr(make_forecast(members=4), tmp_path / "fc.zarr")
    out = tmp_path / "ens.html"
    user = {
        "data": [
            {
                "uid": "a",
                "meta": {"along": "number", "source": {"reduce": ["latitude", "longitude"]}},
            }
        ]
    }
    run_skill(ts_fn, "-i", str(fc), "-o", str(out), "--spec", json.dumps(user))
    assert "Plotly.newPlot" in out.read_text()


def test_mixed_units_warns(tmp_path, ts_fn, capsys):
    a = make_gridded(n_time=2)
    b = make_gridded(n_time=2)
    b["precip"].attrs["units"] = "mm"
    pa, pb = write_zarr(a, tmp_path / "a.zarr"), write_zarr(b, tmp_path / "b.zarr")
    user = {"data": [{"uid": "a", "meta": {"source": {"reduce": ["latitude", "longitude"]}}}]}
    run_skill(ts_fn, "-i", str(pa), "-i", str(pb), "--spec", json.dumps(user), "--dump-spec", "-")
    assert "different units" in capsys.readouterr().err


def test_leftover_dims_error(tmp_path, ts_fn, capsys):
    a = write_zarr(make_gridded(n_time=2), tmp_path / "a.zarr")
    with pytest.raises(SystemExit):
        run_skill(ts_fn, "-i", str(a), "-o", str(tmp_path / "x.png"))
    assert "Nothing is averaged silently" in capsys.readouterr().err
