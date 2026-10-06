"""End-to-end tests for plot-verify."""

import json

import numpy as np
import pytest
from skill_conftest import load_skill, make_gridded, run_skill, write_zarr

mod = load_skill("plot-verify", "plot_verify")


@pytest.fixture(scope="module")
def ver_fn():
    return mod.plot_verify


def _week(fill, name="precip"):
    ds = make_gridded(n_time=1, name=name, fill=fill)
    ds[name].attrs.update(units="mm", aggregation_period="7 day")
    return ds


def _verify(metric="hits"):
    ds = make_gridded(n_time=1, name={"hits": "event_hit", "bias": "bias", "mae": "mae"}[metric])
    var = list(ds.data_vars)[0]
    ds[var].values[:] = np.resize([-1.0, 0.0, 1.0], ds[var].shape)
    ds[var].attrs = {}
    ds.attrs.update(verify_metric=metric, verify_score_summary="score 0.5")
    return ds


@pytest.fixture
def files(tmp_path):
    return {
        "obs": str(write_zarr(_week(10.0), tmp_path / "obs.zarr")),
        "fc": [str(write_zarr(_week(5.0 + i), tmp_path / f"fc{i}.zarr")) for i in (1, 2)],
        "ver": [str(write_zarr(_verify(), tmp_path / f"v{i}.zarr")) for i in (1, 2)],
    }


def _argv(files):
    argv = ["--obs", files["obs"]]
    for fc, v in zip(files["fc"], files["ver"], strict=True):
        argv += ["--forecast", fc, "--verify", v]
    return argv


def test_grid_spec(files, ver_fn, capsys):
    run_skill(ver_fn, *_argv(files), "--dump-spec", "-")
    out = capsys.readouterr().out
    spec = json.loads(out[out.index("{") :])
    uids = [(t["uid"], t.get("xaxis", "x"), t["coloraxis"]) for t in spec["data"]]
    assert uids == [
        ("obs", "x", "coloraxis"),
        ("forecast1", "x2", "coloraxis"),
        ("forecast2", "x3", "coloraxis"),
        ("verify1", "x5", "coloraxis2"),
        ("verify2", "x6", "coloraxis2"),
    ]
    assert spec["layout"]["grid"] == {"rows": 2, "columns": 3}
    assert spec["data"][0]["meta"]["palette"] == "ppt_week"
    assert spec["layout"]["title"]["text"] == "1–7 Jan '26"
    assert spec["layout"]["coloraxis2"]["colorbar"]["ticktext"] == ["disagree", "below", "hit"]


def test_renders_and_prints_scores(files, ver_fn, tmp_path, capsys):
    out = tmp_path / "v.png"
    run_skill(
        ver_fn, *_argv(files), "-o", str(out), "--spec", '{"layout": {"title": {"text": "Kenya"}}}'
    )
    text = capsys.readouterr().out
    assert "1-week lead  score 0.5" in text
    assert out.is_file()


def test_needs_one_verify_per_forecast(files, ver_fn, capsys):
    with pytest.raises(SystemExit):
        run_skill(ver_fn, "--obs", files["obs"], "--forecast", files["fc"][0], "-o", "x.png")
    assert "one --verify per --forecast" in capsys.readouterr().err


def test_multi_time_obs_rejected(tmp_path, files, ver_fn, capsys):
    obs = write_zarr(make_gridded(n_time=2), tmp_path / "obs2.zarr")
    with pytest.raises(SystemExit):
        run_skill(
            ver_fn,
            "--obs",
            str(obs),
            "--forecast",
            files["fc"][0],
            "--verify",
            files["ver"][0],
            "-o",
            "x.png",
        )
    assert "select the verifying week" in capsys.readouterr().err


def test_grid_mismatch_rejected(tmp_path, files, ver_fn, capsys):
    coarse = make_gridded(n_time=1, lats=(1.0, 3.0), lons=(10.0, 12.0))
    obs = write_zarr(coarse, tmp_path / "coarse.zarr")
    with pytest.raises(SystemExit):
        run_skill(
            ver_fn,
            "--obs",
            str(obs),
            "--forecast",
            files["fc"][0],
            "--verify",
            files["ver"][0],
            "-o",
            "x.png",
        )
    assert "coarsen --obs onto the forecast" in capsys.readouterr().err
