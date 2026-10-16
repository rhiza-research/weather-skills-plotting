# Plot themes

[`default.json`](default.json) is the standard weather-skills plot look. A
theme file (`--theme-file`, JSON or TOML) has the same four sections, and
anything it sets is layered on top of `default.json`. So a theme lists only
what it changes. To start a house style, copy `default.json`, delete the
parts you keep as they are, and edit the rest.

`--theme-file` also takes the name of a theme shipped here:

| Name | Look |
|---|---|
| [`tropical_tidbits`](tropical_tidbits.json) | Tropical Tidbits model-chart colors, sampled from its colorbars: `tt_precip_rate` (mm/h), `tt_precip_total` (mm, the precip default), `tt_pwat` (mm), `tt_wind` (m/s, the wind-speed default; TT's knot classes converted), `tt_z500` (dam). Black coastlines and borders. A precip *rate* still gets the totals default: unit-convert it to mm/h and set `meta.palette` `tt_precip_rate` (rate data usually arrives in mm/day, which mm/h classes would color 24x too dry). |

Without `--theme-file`, `$WEATHER_SKILLS_PLOT_THEME` or
`~/.config/weather-skills/plot.json|toml` is used if present.

## `template`

A [Plotly template](https://plotly.com/python/templates/): fonts, colorway,
backgrounds, axis and shape defaults. It is applied on top of Plotly's
`seaborn` template to make `weather_skills`, the template every figure uses
unless the spec sets `layout.template`. A theme's `template` merges into this
one key by key, and a list such as `colorway` is replaced whole.

- `layout.colorway`: line and marker colors in order, used for series,
  ensemble members and bands (seaborn "deep").
- `layout.shapedefaults`: seaborn's shapes have no line and a blue fill, so
  a box given only a line color would draw as a tinted patch. Here a shape is
  an outline unless it sets a fill.

The `colorblind` template gets the same settings but always keeps its own
colorblind-safe colorway, even when a theme sets one.

## `palettes`

Named palettes for a trace's `meta.palette` and for `defaults`:

- `{"colors": [...], "bounds": [...]}` draws one color per class between
  bounds (optional `under`, `over`, `labels`).
- `{"colors": [...]}`, or a plain list, draws a continuous scale.

The standard palettes come from two places. Fixed tables are listed in
`default.json`, so a copy of it shows them:

| Names | Use |
|---|---|
| `ppt_poa` | Precipitation as percent of normal (CHC `ppt_poa_cmap.pro`) |
| `ppt_spp` | Seasonal rainfall performance probability classes (CHC `ppt_spp_cmap.pro`) |
| `spi` | Standardized Precipitation Index (CHC `spi_cmap.pro`) |
| `rocket` | Default sequential scale (seaborn "rocket", light to dark) |

Palettes that are computed are built in `palettes.py`. A theme can still use
or replace them by name:

| Names | Use |
|---|---|
| `ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season` | Precipitation totals, each cropped from one master so a color means the same millimetres on every window |
| `ppt_anom_daily`, `ppt_anom_week`, `ppt_anom_month`, `ppt_anom_season` | Precipitation anomalies, cropped the same way |
| `ppt_total` | Historical CHC rainbow scale (0 … 2500 mm), the source of the totals master |

`default_precip` and `default_precip_anom` are not palettes of their own:
they pick `ppt_daily` … `ppt_season` (or `ppt_anom_*`) from the field's
`aggregation_period`. A theme palette adds a name, or replaces a standard one
of the same name, `default_precip` included.

## `defaults`

The color a field gets when the spec names no palette or colorscale, by kind
of field. A value is a palette name, a color list, a `{colors, bounds}`
object, or a Plotly colorscale name (`Viridis`, `RdBu_r`, …).

| Kind | Which fields |
|---|---|
| `precip` | Precipitation amounts and rates |
| `precip_anomaly` | Precipitation anomalies |
| `precip_poa` | Precipitation as percent of normal |
| `spi` | Standardized Precipitation Index |
| `wind_speed` | CF `standard_name: wind_speed`, including speed drawn from u/v |
| `diverging` | Any other field whose color range straddles zero |
| `sea_level_pressure` | Mean sea-level pressure (not surface pressure); the range is centred on 1013.25 hPa |
| `temperature` | Temperatures that do not straddle zero |
| `sequential` | Everything else |

The kinds are checked top to bottom. A spread or variance is never a precip
amount, and CF flag fields (e.g. verify hits) always get one color per flag.

## `overlays`

Plotly scatter line styles for the base-map layers: `admin1`, `rivers`,
`lakes`, `borders`, `coastline`, drawn in that order (later on top). A theme's
style merges into the standard one, so `{"borders": {"line": {"color":
"#333333"}}}` keeps the standard width. A spec's `layout.meta.overlays` turns
layers on or off. `admin1` also styles an outline layer with many polygons (county
boundaries from a GeoJSON), so a theme's county-line color applies to official
boundary files too.

Water is slate (`#708090`), so lakes and rivers never read as rainfall blues.
Lakes are filled opaque over the data, so a lake never reads as a rainfall
cell; the fill also hides river centerlines through it. To see the data under
a lake, set `{"lakes": {"fill": "none"}}`.
