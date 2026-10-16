"""Panel titles for forecast leads, single times and calendar bins."""

import numpy as np
import xarray as xr

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
    assert panel_title(da, "step", step, [step]) == "16 Oct '26 18:00–00:00 (+18h)"


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
