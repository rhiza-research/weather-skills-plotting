"""Figure text: panel titles, dataset and variable labels, unit spellings."""

import json

import numpy as np
import xarray as xr

from conftest import make_forecast, make_gridded
from weather_skills_plotting import labels
from weather_skills_plotting.labels import format_calendar_panel, panel_title


def _forecast(step_hours, **attrs):
    da = xr.DataArray(
        np.zeros(len(step_hours)),
        dims=["step"],
        coords={
            "step": np.array(step_hours, dtype="timedelta64[h]").astype("timedelta64[ns]"),
            "time": np.datetime64("2026-10-16T00", "ns"),
        },
        attrs=attrs,
    )
    return da


def test_selected_six_hour_mean_names_its_window_and_lead():
    da = _forecast([18], aggregation_period="6 hour", data_interval="6 hour")
    step = da.step.values[0]
    assert panel_title(da, "step", step, [step]) == "16 Oct '26 18:00–00:00 (+18–24h)"


def test_selected_hourly_instant_names_its_valid_time_and_lead():
    da = _forecast([24], data_interval="1 hour")
    step = da.step.values[0]
    assert panel_title(da, "step", step, [step]) == "17 Oct '26 00:00 (+24h)"


def test_one_map_at_noon_keeps_its_hour():
    t = np.datetime64("2026-10-08T12", "ns")
    da = xr.DataArray([0.0], dims=["time"], coords={"time": [t]})
    assert panel_title(da, "time", t, [t]) == "8 Oct '26 12:00"


def test_month_bins_read_as_months():
    assert format_calendar_panel(np.datetime64("2090-01-16"), 31.0) == "Jan 2090"
    assert format_calendar_panel(np.datetime64("2026-10-01"), 30.4375) == "Oct 2026"
    # An exact 30-day window is a window, not a month.
    assert format_calendar_panel(np.datetime64("2026-10-14"), 30.0) == "14 Oct–12 Nov '26"


def test_period_axis_titles():
    from weather_skills_plotting.labels import period_axis_title

    da = xr.DataArray([1.0], attrs={"aggregation_period": "7 day"})
    assert period_axis_title(da, "time") == "Week starting"
    da.attrs["aggregation_period"] = "1 dekad"
    assert period_axis_title(da, "time") == "Dekad starting"
    da.attrs["aggregation_period"] = "1 day"
    assert period_axis_title(da, "time") == "time"


def test_dataset_display_label_from_history():
    ds = make_gridded()
    ds.attrs["weather_skills_history"] = json.dumps([{"skill": "chirps-fetch"}])
    assert labels.dataset_display_label(ds, "fallback") == "CHIRPS"


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
    assert labels.dataset_display_label(ds, "fallback") == "CHIRPS"


def test_dataset_display_label_from_source_token():
    ds = make_gridded()
    ds.attrs["weather_skills_source"] = "ecmwf-s2s"
    assert labels.dataset_display_label(ds, "fallback") == "ECMWF S2S"


def test_dataset_display_label_source_wins_over_history():
    ds = make_gridded()
    ds.attrs["weather_skills_source"] = "dynamical:nasa-imerg-analysis-late"
    ds.attrs["weather_skills_history"] = json.dumps([{"skill": "dynamical-fetch"}])
    assert labels.dataset_display_label(ds, "fallback") == "NASA IMERG LATE"


def test_label_from_source_token_colon_catalog():
    assert labels.label_from_source_token("dynamical:nasa-imerg-analysis-late") == "NASA IMERG LATE"


def test_label_from_source_token_colon_path():
    assert labels.label_from_source_token("kenya-forecasting-data:gefs/gefs_kenya.zarr") == "GEFS"
    assert (
        labels.label_from_source_token("cmip6:ACCESS-CM2/ssp585/r1i1p1f1/Amon/pr/gn")
        == "ACCESS CM2"
    )


def test_label_from_source_token_path_stem():
    assert labels.label_from_source_token("/tmp/chirps_2024-01-01.zarr") == "CHIRPS"


def test_dataset_display_label_fallback():
    assert labels.dataset_display_label(make_gridded(), "input 1") == "input 1"


def test_combine_display_labels():
    assert labels.combine_display_labels(["ECMWF S2S", "ECMWF S2S"]) == "ECMWF S2S"
    assert labels.combine_display_labels(["GEFS", "ECMWF S2S"]) == "GEFS / ECMWF S2S"


def test_format_units_for_display():
    """Figure labels use mm/day and °C, not CF or pint pretty-print."""
    assert labels.format_units_for_display("mm day-1") == "mm/day"
    assert labels.format_units_for_display("millimeter / day") == "mm/day"
    assert labels.format_units_for_display("mm") == "mm"
    assert labels.format_units_for_display("degree_Celsius") == "°C"
    assert labels.format_units_for_display("delta_degC") == "°C"
    assert labels.format_units_for_display("delta_degree_Celsius") == "°C"
    assert labels.format_units_for_display("") == ""
    assert labels.format_units_for_display(None) == ""


def test_variable_label_for_display_prefers_long_name():
    """Colorbars use long_name even when a leftover GRIB rate name is present."""
    da = make_forecast()["tp"]
    da.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        long_name="Total precipitation",
        GRIB_name="Precipitation rate",
    )
    assert labels.variable_label_for_display(da) == "Precipitation [mm]"
    assert labels.variable_label_for_display(da, include_units=False) == "Precipitation"

    product = make_gridded()["precip"]
    product.attrs["long_name"] = "IMERG daily precipitation"
    assert labels.variable_label_for_display(product) == "IMERG daily precipitation [mm/day]"

    amount = make_forecast()["tp"]
    amount.attrs.update(
        units="mm",
        standard_name="lwe_thickness_of_precipitation_amount",
        long_name="precipitation rate",
        GRIB_name="Precipitation rate",
    )
    assert labels.variable_label_for_display(amount) == "Precipitation [mm]"

    bare = make_gridded()["precip"]
    assert labels.variable_label_for_display(bare) == "precip [mm/day]"
    assert labels.variable_label_for_display(bare, fallback="rainfall") == "rainfall [mm/day]"


def test_dimensionless_units():
    assert labels.format_units_for_display("dimensionless") == ""
    assert labels.format_units_for_display("m3 m-3") == "m3 m-3"
    assert labels.format_units_for_display("mm h-1") == "mm/h"
