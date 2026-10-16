"""Tests for weather_skills_plotting.display (labels, units, precip totals)."""

import json

import numpy as np
from weather_skills_core.units import PRECIP_AMOUNT_LONG_NAME, STANDARD

from conftest import make_forecast, make_gridded
from weather_skills_plotting import display as dl


def test_dataset_display_label_from_history():
    ds = make_gridded()
    ds.attrs["weather_skills_history"] = json.dumps([{"skill": "chirps-fetch"}])
    assert dl.dataset_display_label(ds, "fallback") == "CHIRPS"


def test_dataset_display_label_from_join_history():
    ds = make_gridded()
    ds.attrs["weather_skills_history"] = json.dumps(
        [
            {
                "skill": "concat",
                "version": "0.1.0",
                "args": {},
                "input": [
                    {
                        "basename": "a.zarr",
                        "hash": "aa",
                        "history": [{"skill": "chirps-fetch"}],
                    },
                    {
                        "basename": "b.zarr",
                        "hash": "bb",
                        "history": [{"skill": "dynamical-fetch"}],
                    },
                ],
            }
        ]
    )
    assert dl.dataset_display_label(ds, "fallback") == "CHIRPS"


def test_dataset_display_label_from_source_token():
    ds = make_gridded()
    ds.attrs["weather_skills_source"] = "ecmwf-s2s"
    assert dl.dataset_display_label(ds, "fallback") == "ECMWF S2S"


def test_dataset_display_label_source_wins_over_history():
    ds = make_gridded()
    ds.attrs["weather_skills_source"] = "dynamical:nasa-imerg-analysis-late"
    ds.attrs["weather_skills_history"] = json.dumps([{"skill": "dynamical-fetch"}])
    assert dl.dataset_display_label(ds, "fallback") == "NASA IMERG LATE"


def test_label_from_source_token_colon_catalog():
    assert dl.label_from_source_token("dynamical:nasa-imerg-analysis-late") == "NASA IMERG LATE"


def test_label_from_source_token_colon_path():
    assert dl.label_from_source_token("kenya-forecasting-data:gefs/gefs_kenya.zarr") == "GEFS"
    assert dl.label_from_source_token("cmip6:ACCESS-CM2/ssp585/r1i1p1f1/Amon/pr/gn") == "ACCESS CM2"


def test_label_from_source_token_path_stem():
    assert dl.label_from_source_token("/tmp/chirps_2024-01-01.zarr") == "CHIRPS"


def test_dataset_display_label_fallback():
    assert dl.dataset_display_label(make_gridded(), "input 1") == "input 1"


def test_combine_display_labels():
    assert dl.combine_display_labels(["ECMWF S2S", "ECMWF S2S"]) == "ECMWF S2S"
    assert dl.combine_display_labels(["GEFS", "ECMWF S2S"]) == "GEFS / ECMWF S2S"


def test_format_units_for_display():
    """Figure labels use mm/day and °C, not CF or pint pretty-print."""
    assert dl.format_units_for_display("mm day-1") == "mm/day"
    assert dl.format_units_for_display("millimeter / day") == "mm/day"
    assert dl.format_units_for_display("mm") == "mm"
    assert dl.format_units_for_display("degree_Celsius") == "°C"
    assert dl.format_units_for_display("delta_degC") == "°C"
    assert dl.format_units_for_display("delta_degree_Celsius") == "°C"
    assert dl.format_units_for_display("") == ""
    assert dl.format_units_for_display(None) == ""


def test_variable_label_for_display_prefers_long_name():
    """Colorbars use long_name even when a leftover GRIB rate name is present."""
    da = make_forecast()["tp"]
    da.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        long_name="Total precipitation",
        GRIB_name="Precipitation rate",
    )
    assert dl.variable_label_for_display(da) == "Precipitation [mm]"
    assert dl.variable_label_for_display(da, include_units=False) == "Precipitation"

    product = make_gridded()["precip"]
    product.attrs["long_name"] = "IMERG daily precipitation"
    assert dl.variable_label_for_display(product) == "IMERG daily precipitation [mm/day]"

    amount = make_forecast()["tp"]
    amount.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        long_name="precipitation rate",
        GRIB_name="Precipitation rate",
    )
    assert dl.variable_label_for_display(amount) == "Precipitation [mm]"

    bare = make_gridded()["precip"]
    assert dl.variable_label_for_display(bare) == "precip [mm/day]"
    assert dl.variable_label_for_display(bare, fallback="rainfall") == "rainfall [mm/day]"


def test_precip_for_display_converts_aggregated_rate():
    """A rate with aggregation_period becomes an amount for display."""
    ds = make_gridded(name="precip", fill=2.0, units="mm day-1")
    ds["precip"].attrs["aggregation_period"] = "1 day"
    ds["precip"].attrs["standard_name"] = "lwe_precipitation_rate"
    out = dl.precip_for_display(ds, "precip")
    assert out["precip"].attrs["units"] == STANDARD["precip_amount"]["units"]
    assert out["precip"].attrs["long_name"] == PRECIP_AMOUNT_LONG_NAME
    assert out["precip"].attrs["aggregation_period"] == "1 day"
    np.testing.assert_allclose(out["precip"].values, 2.0)


def test_precip_for_display_noop_without_period():
    """Without aggregation_period the rate is left as a rate."""
    ds = make_gridded(name="precip", units="mm day-1")
    out = dl.precip_for_display(ds, "precip")
    assert out["precip"].attrs["units"] == "mm day-1"


def test_sub_daily_rate_stays_a_rate():
    from weather_skills_plotting.display import precip_for_display

    ds = make_gridded(name="precip", fill=2.0, units="mm h-1")
    ds["precip"].attrs.update(standard_name="lwe_precipitation_rate", aggregation_period="6 hour")
    assert precip_for_display(ds, "precip") is ds
    ds["precip"].attrs["aggregation_period"] = "1 day"
    assert precip_for_display(ds, "precip")["precip"].attrs["units"] == "mm"


def test_dimensionless_units():
    assert dl.format_units_for_display("dimensionless") == ""
    assert dl.format_units_for_display("m3 m-3") == "m3 m-3"
    assert dl.format_units_for_display("mm h-1") == "mm/h"
