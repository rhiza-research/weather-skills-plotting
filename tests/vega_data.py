"""Synthetic weather-skills Zarrs and fixtures for the plot-vega tests and recipes.

Shapes follow the standard dataset contract: CF names, ``aggregation_period`` on
precip totals, forecast ``time`` (init) + ``step`` (lead), ensemble ``number``,
stations on ``station_id`` with lat/lon coords. Sizes are kept small so every
recipe renders in about a second.

``NE_FIXTURES`` holds Natural Earth files clipped to East Africa (27–53°E,
13°S–13°N) and simplified to 0.01°, so tests never download. Point
``WS_NE_CACHE`` at it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

NE_FIXTURES = Path(__file__).parent / "data" / "naturalearth"
INIT = np.datetime64("2026-10-01")
PRECIP_WEEK = {"long_name": "Total precipitation", "units": "mm", "aggregation_period": "7D"}


def _field(lat, lon, phase=0.0):
    lon2, lat2 = np.meshgrid(lon, lat)
    return 45 + 40 * np.sin(lon2 / 1.6 + phase) * np.cos(lat2 / 2.1 - phase)


def fcst_weekly_mean(rng):
    lat = np.arange(-5.25, 6.0, 0.5)[::-1]  # descending, like ECMWF
    lon = np.arange(33.25, 42.5, 0.5)
    tp = np.stack(
        [
            np.clip(_field(lat, lon, 0.4 * s) + rng.normal(0, 8, (lat.size, lon.size)), 0, None)
            for s in range(4)
        ]
    )
    return xr.Dataset(
        {"tp": (("step", "latitude", "longitude"), tp, dict(PRECIP_WEEK))},
        coords={
            "step": pd.to_timedelta([7, 14, 21, 28], unit="D"),
            "latitude": lat,
            "longitude": lon,
            "time": INIT,
        },
    )


def fcst_weekly_anom(rng):
    mean = fcst_weekly_mean(rng)
    anom = mean - mean.mean(["latitude", "longitude"])
    anom["tp"].attrs = {**PRECIP_WEEK, "long_name": "Total precipitation anomaly"}
    return anom


def obs_week(rng):
    lat = np.arange(-4.95, 5.0, 0.1)
    lon = np.arange(33.55, 42.0, 0.1)
    values = np.clip(_field(lat, lon, 0.2) + rng.normal(0, 6, (lat.size, lon.size)), 0, None)
    return xr.Dataset(
        {"precip": (("time", "latitude", "longitude"), values[None], dict(PRECIP_WEEK))},
        coords={"time": [INIT], "latitude": lat, "longitude": lon},
    )


STATIONS = {
    "Nairobi": (-1.29, 36.82),
    "Mombasa": (-4.04, 39.67),
    "Kisumu": (-0.09, 34.77),
    "Lodwar": (3.12, 35.60),
    "Marsabit": (2.33, 37.99),
    "Wajir": (1.75, 40.06),
    "Garissa": (-0.45, 39.65),
    "Voi": (-3.40, 38.56),
}


def stations_week(rng):
    names = list(STATIONS)
    lat = np.array([STATIONS[n][0] for n in names])
    lon = np.array([STATIONS[n][1] for n in names])
    vals = np.clip(_field(lat, lon, 0.2).diagonal() + rng.normal(0, 15, lat.size), 0, None)
    return xr.Dataset(
        {"precip": (("station_id",), vals, dict(PRECIP_WEEK))},
        coords={
            "station_id": [f"TA{i:05d}" for i in range(len(names))],
            "station_name": ("station_id", names),
            "latitude": ("station_id", lat),
            "longitude": ("station_id", lon),
            "time": INIT,
        },
    )


def wind_10m(rng):
    lat = np.arange(-12.0, 12.01, 0.5)
    lon = np.arange(28.0, 52.01, 0.5)
    lw, aw = np.meshgrid(lon, lat)
    u = 6 * np.cos(np.deg2rad(aw * 8)) + 3 * np.sin(lw / 3) + rng.normal(0, 0.6, lw.shape)
    v = 4 * np.sin(np.deg2rad(lw * 6)) - 2 * np.cos(aw / 4) + rng.normal(0, 0.6, lw.shape)
    attrs = {"units": "m s-1"}
    return xr.Dataset(
        {
            "u10": (("latitude", "longitude"), u, {**attrs, "long_name": "10 metre U wind"}),
            "v10": (("latitude", "longitude"), v, {**attrs, "long_name": "10 metre V wind"}),
        },
        coords={"latitude": lat, "longitude": lon, "time": INIT},
    )


def ens_point_t2m(rng):
    n_member, n_day = 21, 46
    base = 24 + 2.5 * np.sin(np.arange(n_day) / 7)
    spread = np.linspace(0.3, 2.5, n_day)
    t2m = base[None, :] + np.cumsum(rng.normal(0, 1, (n_member, n_day)), axis=1) * spread / 4
    return xr.Dataset(
        {
            "t2m": (("number", "step"), t2m, {"long_name": "2 metre temperature", "units": "degC"}),
            "t2m_clim": (
                ("step",),
                24 + 2.0 * np.sin(np.arange(n_day) / 7 + 0.3),
                {"long_name": "2 metre temperature climatology", "units": "degC"},
            ),
        },
        coords={
            "number": np.arange(n_member),
            "step": pd.to_timedelta(np.arange(1, n_day + 1), unit="D"),
            "time": INIT,
        },
    )


def scores(rng):
    models = ["ECMWF", "UKMO", "NCEP", "Climatology"]
    leads = ["week 1", "week 2", "week 3", "week 4"]
    rmse = np.array([[9, 14, 18, 20], [10, 15, 19, 21], [11, 16, 20, 21], [21, 21, 21, 21]], float)
    rmse += rng.normal(0, 0.4, rmse.shape)
    return xr.Dataset(
        {
            "rmse": (
                ("model", "lead"),
                rmse,
                {"long_name": "Weekly precipitation RMSE", "units": "mm"},
            )
        },
        coords={"model": models, "lead": leads},
    )


def weekly_series(rng, *, name="precip", n_weeks=52, wet=1.0):
    """Area-mean weekly totals, labelled at the start of each week (aggregate-temporal output)."""
    weeks = np.arange(n_weeks)
    season = 20 + 18 * np.sin(2 * np.pi * (weeks - 30) / 52) + 10 * np.sin(4 * np.pi * weeks / 52)
    vals = np.clip(wet * season + rng.normal(0, 6, n_weeks), 0.5, None)
    return xr.Dataset(
        {name: (("time",), vals, dict(PRECIP_WEEK))},
        coords={"time": pd.date_range("2025-10-07", periods=n_weeks, freq="7D")},
    )


def region_geojson() -> dict:
    """A small Kenya-shaped polygon, as ``resolve-region --geojson`` would write."""
    ring = [[34.0, 4.6], [41.9, 4.0], [41.0, -1.6], [39.3, -4.7], [37.6, -3.0], [33.9, -1.0]]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Kenya", "iso3": "KEN"},
                "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]},
            }
        ],
    }


BUILDERS = {
    "fcst_weekly_mean": fcst_weekly_mean,
    "fcst_weekly_anom": fcst_weekly_anom,
    "obs_week": obs_week,
    "stations_week": stations_week,
    "wind_10m": wind_10m,
    "ens_point_t2m": ens_point_t2m,
    "scores": scores,
    "imerg_weekly": lambda rng: weekly_series(rng, name="precipitation_surface"),
    "chirps_weekly": lambda rng: weekly_series(rng, wet=1.3),
}


def write_all(root: Path) -> dict[str, Path]:
    """Write every fixture under ``root``; returns name -> path."""
    rng = np.random.default_rng(42)
    root.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, build in BUILDERS.items():
        path = root / f"{name}.zarr"
        build(rng).to_zarr(path, mode="w", consolidated=True)
        paths[name] = path
    region = root / "region.geojson"
    region.write_text(json.dumps(region_geojson()))
    paths["region"] = region
    return paths


# The ``-i NAME=fixture`` pairs each recipe in skills/plot-vega/recipes/ is rendered with.
RECIPE_INPUTS = {
    "map_heatmap_stations": {"obs": "obs_week", "stations": "stations_week"},
    "map_country_admin1": {"obs": "obs_week"},
    "map_region_outline": {"obs": "obs_week", "region": "region"},
    "map_forecast_leads_facet": {"fcst": "fcst_weekly_mean"},
    "map_anomaly_diverging": {"anom": "fcst_weekly_anom"},
    "map_side_by_side_grids": {"obs": "obs_week", "fcst": "fcst_weekly_mean"},
    "map_quiver_wind": {"wind": "wind_10m"},
    "map_contours": {"fcst": "fcst_weekly_mean"},
    "timeseries_weekly_line": {"weekly": "imerg_weekly"},
    "timeseries_two_products": {"imerg": "imerg_weekly", "chirps": "chirps_weekly"},
    "bar_weekly_totals": {"weekly": "imerg_weekly"},
    "timeseries_ensemble_spaghetti": {"ens": "ens_point_t2m"},
    "timeseries_multi_panel": {"ens": "ens_point_t2m"},
    "bar_model_comparison": {"scores": "scores"},
    "box_mediogram": {"ens": "ens_point_t2m"},
    "windrose": {"wind": "wind_10m"},
}
