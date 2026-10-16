# Plot themes

[`default.json`](default.json) is the standard weather-skills plot look. A
theme file (`--theme-file`, JSON or TOML) has the same four sections, and
anything it sets is layered on top of `default.json`. So a theme lists only
what it changes. To start a house style, copy `default.json`, delete the
parts you keep as they are, and edit the rest.

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

`default.json` adds none. These are built in (in `palettes.py`, from CHC IDL
tables):

| Names | Use |
|---|---|
| `ppt_daily`, `ppt_week`, `ppt_month`, `ppt_season` | Precipitation totals |
| `ppt_anom_daily`, `ppt_anom_week`, `ppt_anom_month`, `ppt_anom_season` | Precipitation anomalies |
| `ppt_total`, `ppt_short`, `chirps_total`, `chirps_short` | Historical CHC rainbow scales |
| `ppt_poa` | Precipitation as percent of normal |
| `ppt_spp` | Seasonal rainfall performance probability classes |
| `spi` | Standardized Precipitation Index |
| `rocket` | Default sequential scale |

`default_precip` and `default_precip_anom` are not palettes of their own:
they pick `ppt_daily` … `ppt_season` (or `ppt_anom_*`) from the field's
`aggregation_period`. A theme palette adds a name, or replaces a built-in one
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
| `temperature` | Temperatures that do not straddle zero |
| `sequential` | Everything else |

The kinds are checked top to bottom. A spread or variance is never a precip
amount, and CF flag fields (e.g. verify hits) always get one color per flag.

## `overlays`

Plotly scatter line styles for the base-map layers: `admin1`, `rivers`,
`lakes`, `borders`, `coastline`, drawn in that order (later on top). A theme's
style merges into the standard one, so `{"borders": {"line": {"color":
"#333333"}}}` keeps the standard width. A spec's `layout.meta.overlays` turns
layers on or off.

Water is slate (`#708090`), so lakes and rivers never read as rainfall blues.
Lakes are a shoreline only: a filled lake hid the data under it, and Lake
Victoria is among the wettest cells.
