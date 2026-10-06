# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["numpy", "pandas", "xarray", "zarr>=3"]
# ///
"""Synthetic weather-skills-shaped Zarrs for the Vega-Lite prototypes.

Shapes mirror the standard dataset contract: CF names, ``aggregation_period``
on precip totals, forecast ``time`` (init) + ``step`` (lead), ensemble
``number``, station data on ``station_id`` with lat/lon coords.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(42)
INIT = np.datetime64("2026-10-01")


def field(lat, lon, phase=0.0):
    lon2, lat2 = np.meshgrid(lon, lat)
    return 45 + 40 * np.sin(lon2 / 1.6 + phase) * np.cos(lat2 / 2.1 - phase)


def write(ds, name):
    ds.to_zarr(OUT / f"{name}.zarr", mode="w", consolidated=True)
    print(name, dict(ds.sizes), list(ds.data_vars))


# Weekly ensemble precip forecast, 0.25°, East Africa, 4 lead weeks, 11 members.
lat = np.arange(-5.375, 6.0, 0.25)[::-1]  # descending, like ECMWF
lon = np.arange(33.125, 42.5, 0.25)
steps = pd.to_timedelta([7, 14, 21, 28], unit="D")
tp = np.stack(
    [
        np.stack(
            [
                np.clip(field(lat, lon, 0.4 * s) + rng.normal(0, 12, (lat.size, lon.size)), 0, None)
                for s in range(4)
            ]
        )
        for _ in range(11)
    ]
)
fcst = xr.Dataset(
    {
        "tp": (
            ("number", "step", "latitude", "longitude"),
            tp,
            {"long_name": "Total precipitation", "units": "mm", "aggregation_period": "7D"},
        )
    },
    coords={
        "number": np.arange(11),
        "step": steps,
        "latitude": lat,
        "longitude": lon,
        "time": INIT,
    },
)
write(fcst, "fcst_weekly")
# What `reduce --dim number --method mean` would write upstream.
mean = fcst.mean("number", keep_attrs=True)
write(mean, "fcst_weekly_mean")
anom = mean - mean.mean(["latitude", "longitude"])
anom["tp"].attrs = {
    "long_name": "Total precipitation anomaly",
    "units": "mm",
    "aggregation_period": "7D",
}
write(anom, "fcst_weekly_anom")

# CHIRPS-like 0.05° obs week.
lat_o = np.arange(-4.975, 5.0, 0.05)
lon_o = np.arange(33.525, 42.0, 0.05)
obs = xr.Dataset(
    {
        "precip": (
            ("time", "latitude", "longitude"),
            np.clip(field(lat_o, lon_o, 0.2) + rng.normal(0, 6, (lat_o.size, lon_o.size)), 0, None)[
                None
            ],
            {"long_name": "Total precipitation", "units": "mm", "aggregation_period": "7D"},
        )
    },
    coords={"time": [INIT], "latitude": lat_o, "longitude": lon_o},
)
write(obs, "obs_chirps_week")

# Station totals (TAHMO-like).
stations = {
    "Nairobi": (-1.29, 36.82),
    "Mombasa": (-4.04, 39.67),
    "Kisumu": (-0.09, 34.77),
    "Nakuru": (-0.30, 36.07),
    "Eldoret": (0.51, 35.27),
    "Garissa": (-0.45, 39.65),
    "Lodwar": (3.12, 35.60),
    "Marsabit": (2.33, 37.99),
    "Wajir": (1.75, 40.06),
    "Malindi": (-3.22, 40.12),
    "Kitui": (-1.37, 38.01),
    "Nyeri": (-0.42, 36.95),
    "Meru": (0.05, 37.65),
    "Kakamega": (0.28, 34.75),
    "Voi": (-3.40, 38.56),
    "Mandera": (3.94, 41.86),
    "Isiolo": (0.35, 37.58),
    "Lamu": (-2.27, 40.90),
}
names = list(stations)
slat = np.array([stations[n][0] for n in names])
slon = np.array([stations[n][1] for n in names])
svals = np.clip(
    45 + 40 * np.sin(slon / 1.6 + 0.2) * np.cos(slat / 2.1 - 0.2) + rng.normal(0, 15, slat.size),
    0,
    None,
)
st = xr.Dataset(
    {
        "precip": (
            ("station_id",),
            svals,
            {"long_name": "Total precipitation", "units": "mm", "aggregation_period": "7D"},
        )
    },
    coords={
        "station_id": [f"TA{i:05d}" for i in range(len(names))],
        "station_name": ("station_id", names),
        "latitude": ("station_id", slat),
        "longitude": ("station_id", slon),
        "time": INIT,
    },
)
write(st, "stations_week")

# 10 m wind, 0.5°, one valid time.
lat_w = np.arange(-12.0, 12.01, 0.5)
lon_w = np.arange(28.0, 52.01, 0.5)
lw, aw = np.meshgrid(lon_w, lat_w)
u = 6 * np.cos(np.deg2rad(aw * 8)) + 3 * np.sin(lw / 3) + rng.normal(0, 0.6, lw.shape)
v = 4 * np.sin(np.deg2rad(lw * 6)) - 2 * np.cos(aw / 4) + rng.normal(0, 0.6, lw.shape)
wind = xr.Dataset(
    {
        "u10": (
            ("latitude", "longitude"),
            u,
            {
                "long_name": "10 metre U wind component",
                "units": "m s-1",
                "standard_name": "eastward_wind",
            },
        ),
        "v10": (
            ("latitude", "longitude"),
            v,
            {
                "long_name": "10 metre V wind component",
                "units": "m s-1",
                "standard_name": "northward_wind",
            },
        ),
    },
    coords={"latitude": lat_w, "longitude": lon_w, "time": INIT},
)
write(wind, "wind_10m")

# 46-day daily 2 m temperature ensemble at one point (area mean already taken).
days = pd.to_timedelta(np.arange(1, 47), unit="D")
base = 24 + 2.5 * np.sin(np.arange(46) / 7)
spread = np.linspace(0.3, 2.5, 46)
t2m = base[None, :] + np.cumsum(rng.normal(0, 1, (51, 46)), axis=1) * spread[None, :] / 4
ens = xr.Dataset(
    {
        "t2m": (("number", "step"), t2m, {"long_name": "2 metre temperature", "units": "degC"}),
        "t2m_clim": (
            ("step",),
            24 + 2.0 * np.sin(np.arange(46) / 7 + 0.3),
            {"long_name": "2 metre temperature climatology", "units": "degC"},
        ),
    },
    coords={"number": np.arange(51), "step": days, "time": INIT},
)
write(ens, "ens_point_t2m")

# Lead-week verification scores per model.
models = ["ECMWF", "UKMO", "NCEP", "Climatology"]
leads = ["week 1", "week 2", "week 3", "week 4"]
rmse = np.array([[9, 14, 18, 20], [10, 15, 19, 21], [11, 16, 20, 21], [21, 21, 21, 21]], float)
rmse += rng.normal(0, 0.4, rmse.shape)
scores = xr.Dataset(
    {"rmse": (("model", "lead"), rmse, {"long_name": "Weekly precipitation RMSE", "units": "mm"})},
    coords={"model": models, "lead": leads},
)
write(scores, "scores")
