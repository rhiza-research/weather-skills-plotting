"""Plot PNG hash and plotted-data null check."""

import numpy as np
import pytest
from PIL import Image

from conftest import make_gridded
from weather_skills_plotting.qa import data_status, hash_png_pixels, report_figure


def test_hash_png_pixels_is_stable_and_changes_with_pixels(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(a)
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(b)
    Image.new("RGB", (8, 8), color=(11, 20, 30)).save(tmp_path / "c.png")
    assert hash_png_pixels(a) == hash_png_pixels(b)
    assert hash_png_pixels(a) != hash_png_pixels(tmp_path / "c.png")


def test_data_status_not_null():
    status, detail = data_status({"a": make_gridded(n_time=1)})
    assert status == "not null"
    assert "precip 12/12 finite" in detail


def test_data_status_null():
    status, detail = data_status({"a": make_gridded(n_time=1, fill=np.nan)})
    assert status == "NULL"
    assert "precip 0/12 finite" in detail


def test_data_status_no_datasets():
    assert data_status(None) == ("not checked", "no numeric data variables")


def test_report_figure_prints_hash_and_not_null(tmp_path, capsys):
    png = tmp_path / "fig.png"
    Image.new("RGB", (4, 4), color=(1, 2, 3)).save(png)
    digest = report_figure(png, {"a": make_gridded(n_time=1)})
    out = capsys.readouterr().out
    assert f"plot hash: {digest}" in out
    assert "data: not null (precip 12/12 finite)" in out
    assert "all NaN" not in out


def test_report_figure_prints_null(tmp_path, capsys):
    png = tmp_path / "fig.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(png)
    report_figure(png, make_gridded(n_time=1, fill=np.nan))
    out = capsys.readouterr().out
    assert "data: NULL (precip 0/12 finite)" in out
    assert "inspect-zarr" in out


HEATMAP = {"data": [{"type": "heatmap", "uid": "a", "meta": {"source": {"input": "a"}}}]}


def test_export_prints_hash_and_not_null(tmp_path, capsys):
    from weather_skills_plotting import compile, export

    ds = make_gridded(n_time=1)
    out = tmp_path / "map.png"
    export(compile(HEATMAP, {"a": ds}), out, datasets={"a": ds})
    text = capsys.readouterr().out
    assert out.is_file()
    assert text.startswith("plot hash: ")
    assert "data: not null (precip 12/12 finite)" in text


def test_export_prints_null_when_field_is_all_nan(tmp_path, capsys):
    from weather_skills_plotting import compile, export

    ds = make_gridded(n_time=1, fill=np.nan)
    export(compile(HEATMAP, {"a": ds}), tmp_path / "empty.png", datasets={"a": ds})
    assert "data: NULL (precip 0/12 finite)" in capsys.readouterr().out


def test_export_html_has_no_hash_line(tmp_path, capsys):
    from weather_skills_plotting import compile, export

    ds = make_gridded(n_time=1)
    out = export(compile(HEATMAP, {"a": ds}), tmp_path / "map.html", datasets={"a": ds})
    assert "plotly" in out.read_text().lower()
    assert "plot hash" not in capsys.readouterr().out


def test_export_rejects_other_suffixes(tmp_path):
    from weather_skills_core.errors import UsageError

    from weather_skills_plotting import compile, export

    ds = make_gridded(n_time=1)
    with pytest.raises(UsageError, match=".png, .jpg or .html"):
        export(compile(HEATMAP, {"a": ds}), tmp_path / "map.svg")
