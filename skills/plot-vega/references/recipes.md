# Recipes

Each recipe is a complete Vega-Lite spec in `${CLAUDE_SKILL_DIR}/recipes/`.
Its top-level `description` (a standard Vega-Lite key, ignored when drawing)
says which inputs it expects. Every recipe is rendered by the skill's tests
against synthetic inputs of that shape, so each one works as-is.

To adapt one:

1. Copy it, e.g. `cp ${CLAUDE_SKILL_DIR}/recipes/map_heatmap_stations.json /tmp/spec.json`.
2. Run `--describe -i NAME=PATH` on your inputs and change each binding's
   `fields` sources (right-hand side) to your variable and dim names. Keep the
   column names (left-hand side) and the encodings will still match.
3. Add `sel`/`isel` for any extra dim the `--describe` output shows (a
   `time` with several values, `number`, `step`), or keep it as a column.
4. Change the titles, `width`/`height` and, for maps, the `bbox`.
5. Render, read the `bound` and `default` lines, and look at the image.

The `-i` names below are the ones the recipes bind. Rename both sides if you prefer others.

## Maps

### `map_heatmap_stations`

A precipitation grid as true-size cells, Natural Earth lakes, coastline and
borders at 10m, station dots on the same colour scale (one shared legend),
station-name labels.

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_vega.py -o /tmp/map.png \
    -i obs=/tmp/chirps_week_total.zarr -i stations=/tmp/tahmo_week_total.zarr \
    --spec ${CLAUDE_SKILL_DIR}/recipes/map_heatmap_stations.json
```

- `obs`: `latitude` × `longitude`, optionally size-1 `time`, variable `precip` (a total).
- `stations`: `station_id` with `latitude`, `longitude`, `station_name` coords, variable `precip`.
- For gauges with no name coord, drop the `name` field and the text layer.

### `map_country_admin1`

A grid with admin-1 lines, dashed national borders and one country outlined
by filtering the Natural Earth `countries` layer on `ADM0_A3`. Needs no GeoJSON.

```bash
... -i obs=/tmp/kenya_week_total.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/map_country_admin1.json
```

Change `'KEN'` to another Natural Earth `ADM0_A3` code (`'GHA'`, `'ETH'`;
usually the ISO alpha-3 code, though not always: South Sudan is `'SDS'`). Bind
`"properties": ["ADM0_A3", "NAME"]` and filter on `NAME` if unsure. Crop the
grid to that country with `bbox` on the `obs` binding, or run `clip-region` upstream
to blank cells outside it.

### `map_region_outline`

A grid with a custom polygon on top, from `resolve-region --geojson` or any GeoJSON file.

```bash
... -i obs=/tmp/week_total.zarr -i region=/tmp/region.geojson \
    --spec ${CLAUDE_SKILL_DIR}/recipes/map_region_outline.json
```

### `map_forecast_leads_facet`

One map per lead week in a 4-column facet with a horizontal classed legend underneath.

```bash
... -i fcst=/tmp/ecmwf_weekly_totals_mean.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/map_forecast_leads_facet.json
```

- `fcst`: `step` × `latitude` × `longitude`, variable `tp`, ensemble already reduced
  (`summarize-dim --dim number`), steps at 7-day multiples.
- The panel label is `'Week ' + lead_days / 7`. For other leads, change the `calculate`.

### `map_side_by_side_grids`

Two products side by side, each at its own resolution (no regridding), both
cropped to the same `bbox`, sharing one legend.

```bash
... -i obs=/tmp/chirps_week.zarr -i fcst=/tmp/ecmwf_weekly_totals_mean.zarr \
    --spec ${CLAUDE_SKILL_DIR}/recipes/map_side_by_side_grids.json
```

Set the same `bbox` on both bindings (the recipe crops `fcst` to the obs
box), and pick the forecast lead with `sel.step`. For a different quantity in each
panel, set `"resolve": {"scale": {"color": "independent"}}`.

### `map_anomaly_diverging`

The same anomaly twice: the default classed anomaly palette, and a
continuous `brownbluegreen` scheme centred with `domainMid: 0`.

```bash
... -i anom=/tmp/tp_anomaly.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/map_anomaly_diverging.json
```

Keep one of the two panels. The default palette needs "anomal" in the
variable name or `long_name`, or negative values; otherwise set
`"scale": {"scheme": "default_precip_anom"}`.

### `map_contours`

Filled contour bands and isolines from `contours` bindings, with country borders.

```bash
... -i fcst=/tmp/ecmwf_weekly_totals_mean.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/map_contours.json
```

Choose `levels` on the palette's class edges (the totals palette's edges
are 0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, ...).

### `map_quiver_wind`

Wind speed as cells, direction arrows from a second binding thinned with
`isel` step 3. Speed is computed in the spec, so the recipe sets the colour scale and titles.

```bash
... -i wind=/tmp/era5_wind10m.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/map_quiver_wind.json
```

- `wind`: `latitude` × `longitude`, variables `u10`, `v10` in m/s. Select one `time` with `sel` if there are several.
- The base-map bindings carry an explicit `bbox`; change it with the data.
- Thinner or denser arrows: change the `isel` steps. Arrow length: the `size` scale `range`.

## Time series

### `timeseries_weekly_line`

One weekly series, line with a point per week, dashed mean line with a label in the right margin.

```bash
... -i weekly=/tmp/ghana_weekly_total.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/timeseries_weekly_line.json
```

`weekly`: `time` only (an area mean: `clip-region` → `summarize-dim` →
`aggregate-temporal` → `convert-to-totals`), variable `precipitation_surface`
(IMERG). For CHIRPS, change the source to `precip`.

### `timeseries_two_products`

Two products of the same quantity on one time axis, with a legend from each layer's colour `datum`.

```bash
... -i imerg=/tmp/imerg_weekly_total.zarr -i chirps=/tmp/chirps_weekly_total.zarr \
    --spec ${CLAUDE_SKILL_DIR}/recipes/timeseries_two_products.json
```

For a third product, add a binding mapping its variable to `week`/`precip`, a
layer with its own `datum`, and a third colour in `range`.

### `timeseries_ensemble_spaghetti`

Ensemble members as thin lines, a 10–90% quantile band, the ensemble mean,
and a dashed climatology, against valid time.

```bash
... -i ens=/tmp/point_t2m_ensemble.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/timeseries_ensemble_spaghetti.json
```

`ens`: `number` × `step` with a scalar init `time` (a point: select or average
lat/lon upstream), variables `t2m` and `t2m_clim`. Without a climatology,
delete the `clim` binding and its layer, and its colour from `config.range.category`.

### `timeseries_multi_panel`

Two stacked panels: members and mean above ensemble-mean anomaly bars
coloured by sign. The anomaly is a `lookup` join against the climatology binding.

```bash
... -i ens=/tmp/point_t2m_ensemble.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/timeseries_multi_panel.json
```

## Bars and distributions

### `bar_weekly_totals`

Weekly totals as bars spanning their own 7-day bin (`x` = bin start,
`x2` = start + 7 days, `y2` = 0), with tooltips for the HTML output.

```bash
... -i weekly=/tmp/ghana_weekly_total.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/bar_weekly_totals.json
```

### `bar_model_comparison`

Grouped bars: one group per lead, one bar per model (`xOffset`), value labels on top.

```bash
... -i scores=/tmp/rmse_by_model_lead.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/bar_model_comparison.json
```

`scores`: `model` × `lead` (string coords), variable `rmse`. Change the
`sort` lists (on `xOffset` and `color`) and the colour `range` to your models.
Merge per-model score Zarrs upstream so that `model` is a dim.

### `box_mediogram`

Weekly-mean distribution per lead week: box 25–75%, whiskers 10–90%,
median tick, climatology dot. Percentiles are computed in the spec with
`quantile` + `pivot`.

```bash
... -i ens=/tmp/point_t2m_ensemble.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/box_mediogram.json
```

### `windrose`

16 direction sectors stacked by speed class from u/v; every grid cell (and
time, and member) is a sample.

```bash
... -i wind=/tmp/era5_wind10m.zarr --spec ${CLAUDE_SKILL_DIR}/recipes/windrose.json
```

Change the speed classes in the two `calculate` steps that set
`speed_class` and `speed_label`. With a `time` dim, add `"t": "time"` to
`fields` so every time step counts as a sample.
