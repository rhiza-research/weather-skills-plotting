---
name: plot
description: "Draw weather-skills Zarrs as any Plotly figure: maps (heatmap, contour, stations, wind arrows), panel grids, time series, ensemble plumes and bands, day-of-year season overlays, bars, xy scatter, cross-sections, and animated maps, saved as PNG, JPG, PDF, SVG, interactive HTML, or GIF. The spec is Jsonnet that evaluates to a standard Plotly figure; strings starting with @ name the data."
license: MIT
compatibility: Requires Python 3.12 and uv. PNG, JPG, PDF, SVG and GIF export needs Chrome (installed, or `plotly_get_chrome -y`). Self-contained; the plotting library ships in scripts/.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py *)
metadata:
  version: "1.0.10"
  catalog-group: figure
---

# plot

Draws a figure from a Jsonnet spec. The spec evaluates to a standard [Plotly figure](https://plotly.com/python/reference/) (`data`, `layout`, `frames`). Wherever Plotly expects data, write a string that starts with `@` and names it: `'@OBS.precip.isel(time=0)'`. Name every input on the command line.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py -i rain_week.zarr=OBS -i kenya.geojson=KENYA \
  --spec map.jsonnet -o map.png
```

Start from a recipe in `${CLAUDE_SKILL_DIR}/recipes/`. Each one runs as is: its second line is the command.

| Recipe | Draws |
| --- | --- |
| `map.jsonnet` | One map: a grid on a stepped palette, a GeoJSON outline, the base map |
| `stations.jsonnet` | Station dots over a grid on one colorbar, labelled with their ids |
| `panels.jsonnet` | One map per forecast step in a grid, one colorbar, panel titles |
| `members.jsonnet` | Ensemble members in grey and the mean in bold, at the cell nearest a point |
| `band.jsonnet` | A shaded 10–90% band between two quantile lines, with observations |
| `seasons.jsonnet` | Past years and a forecast plume on one day-of-year axis |
| `wind.jsonnet` | Wind speed shading with arrows on every 2nd cell |
| `animation.jsonnet` | A map played through time: HTML with play / slider, or a looping GIF |
| `cross_section.jsonnet` | A field over longitude and pressure, 1000 hPa at the bottom |
| `bars.jsonnet` | Horizontal bars per county from a name coordinate |
| `scatter_xy.jsonnet` | One variable against another, with year labels and a threshold line |
| `verify_grid.jsonnet` | Observation and each lead's forecast on one colorbar, verify hits maps underneath |
| `mediogram.jsonnet` | Forecast members vs model climate as boxes per lead at a point, with the forecast mean |
| `windrose.jsonnet` | Wind observations on polar axes by the direction they blow from, colored by speed |
| `mslp.jsonnet` | Labelled isobars every 4 hPa with H / L and central pressure from local-extrema |

### Arguments
- `-i`, `--input` — `PATH=NAME`, repeat. A Zarr, or a GeoJSON (`.geojson` / `.json`) of outlines. `NAME` is a letter or `_`, then letters, digits and `_` (`OBS`, `fc_week1`); it is how the spec refers to the file. Readable legend text goes in a trace's `"name"`, not here.
- `--spec` — a `.jsonnet` / `.json` file, or the Jsonnet text itself.
- `-o`, `--output` — `.png`, `.jpg`, `.pdf`, `.svg`, `.html`, or `.gif` (plays the spec's `frames`). Repeat to write several.
- `--dump-spec` — print (`-`) or save (a path) the evaluated spec, `@` strings unresolved, and draw nothing.
- `--ext-str KEY=VALUE` — read in the spec as `std.extVar('KEY')`; repeat.
- `-J DIR` — another folder for Jsonnet imports. The skill's `lib/` is always searched.

## The spec

It is ordinary Jsonnet. Use `local` variables for anything repeated, so long strings (selections, colors) are written once:

```jsonnet
local ws = import 'ws.libsonnet';               // helpers, below
local inputs = std.extVar('inputs');           // what each input holds
local day = '.isel(time=0)';
{
  data: [
    { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip' + day, coloraxis: 'coloraxis' },
  ],
  layout: ws.map(inputs.OBS.bbox) + {
    title: { text: 'Rainfall %s' % inputs.OBS.coords.time[0] },
    coloraxis: ws.stepped(ws.palettes.ppt_daily),
  },
}
```

**`std.extVar('inputs')`** describes each input, read from its metadata without loading data: `dims` (sizes), `vars` (each one's `dims`, `units`, `long_name`), `coords` (values of 1-D coordinates up to 400 long: dates as `2026-10-01`, leads in days, members, station ids), `attrs`, and `bbox` (`{n, w, s, e}`). Use it for loop bounds, titles and map windows. A GeoJSON input has `bbox`.

### `@` references
A string that starts with `@` is replaced by the data it names; the whole string is the reference. `@@` writes a literal `@`.

| Form | Gives |
| --- | --- |
| `@OBS.precip`, `@OBS.time`, `@OBS.county` | A variable or coordinate |
| `@OBS.lat`, `@OBS.lon` | The latitude / longitude coordinate, whatever the file calls it |
| `.isel(time=0)`, `.isel(time=-1)`, `.isel(time=slice(0, 7))` | Pick by position (`slice(None, None, 3)`: every 3rd) |
| `.sel(time='2026-10-01')`, `.sel(lat=-1.3, lon=36.8, method='nearest')`, `.sel(station_id=['A', 'B'])` | Pick by value |
| `.squeeze()`, `.transpose('vertical', 'lon')` | Drop size-1 dims, set dim order |
| `.flat()`, `.flat('lon')`, `.flat('lat')` | A lat/lon grid as one value per cell, and each cell's lon / lat: grid cells as scatter points |
| `.dt.dayofyear`, `.dt.year`, `.dt.month`, `.dt.day`, `.dt.hour`, `.dt.days`, `.dt.strftime('%d %b')` | Time labels (`.dt.days` of a lead time) |
| `.attrs.units` | A text attribute |
| `.min()`, `.max()`, `.quantile(0.98)` | One number for a scale only: `zmin`, `zmax`, `zmid`, `cmin`, `cmax`, `cmid`, an axis `range`, `tickvals` |
| `@KENYA.x`, `@KENYA.y` | A GeoJSON input's lines and rings, gaps between parts |
| `@NE.coastline_50m.clip(n, w, s, e).x` | Built-in Natural Earth lines: `coastline`, `borders`, `disputed`, `lakes`, `rivers` at `10m` / `50m` / `110m`, `admin1` at `10m` |

Shapes: `z` is 2-D (a lat/lon grid is drawn with rows as latitudes); `customdata` 1-D or 2-D; everything else one value or 1-D. A leftover dim is an error naming it: pick a value with `isel` / `sel`, or draw one trace per value with a Jsonnet loop (`for m in std.range(0, inputs.ENS.dims.number - 1)`).

References select and label stored values; they never compute. Arithmetic, averages and smoothing come from data skills first, and the error says which: `summarize-dim` (mean, quantiles over members), `aggregate-temporal` (rolling, resampling), `unit-convert`, `difference`, `coarsen` / `downscale`, `clip-region` (masks), `step-to-time` (valid dates), `wind-speed-direction` (speed and direction from u / v). A trace may hold up to 10 typed-in numbers (a marker, a threshold line); more must come from an input.

### `ws.libsonnet`
`local ws = import 'ws.libsonnet';` gives plain Plotly JSON; change any part with `+`.

- `ws.map(bbox, width=760)` — one map's axes (equal degrees, range from `bbox`) and a canvas sized to it.
- `ws.grid(bbox, rows, cols, panel=340)` — axes for maps in a grid, filled row by row; tick labels on the outer edge only. `ws.axes(i)` gives panel `i`'s `xaxis` / `yaxis` (`x`, `x2`, …) to add to a trace; `ws.panelTitle(i, text)` an annotation above it (add titles with `annotations+:` after `ws.classBar`).
- `ws.basemap(bbox, i=0, layers=null, style={})` — coastline, borders (disputed dashed), lakes, rivers and, on maps up to 20° across, admin-1 lines, on panel `i`. `layers: ['borders', 'coastline']` picks some; `style: {borders: {line: {color: 'red'}}}` restyles. A GeoJSON input draws boundaries of your own.
- `ws.classBar(palette, title='', axis='coloraxis')` — for a class palette: the `coloraxis` with color steps at the class bounds, and a colorbar with one equal-height band per class, labelled at the bounds (or by the palette's `labels`), under / over as triangles. It is drawn as layout shapes and annotations, so write your own as `annotations+: [...]` after it. `y` / `len` place it (paper fractions) when a figure has two.
- `ws.stepped(palette)` — the coloraxis alone, with Plotly's own colorbar (a continuous palette, or class bands sized by their value range).
- `ws.palettes.NAME` — `{colors, bounds}`: rainfall totals `ppt_daily` (0–50 mm), `ppt_week` (0–200, also a dekad), `ppt_month` (0–400), `ppt_season` (0–1000), `ppt_total` (0–2500); anomalies `ppt_anom_daily` … `ppt_anom_season` (±50 / ±200 / ±300 / ±500); `ppt_poa` (% of normal), `spi`, verify maps `hits`, `bias`, `precip_bias`, `mae`; `colorblind`, `rocket`. Your own: `{colors: [...], bounds: [...]}`, one color per class, or under + classes + over; `labels: [...]` names the classes.
- `ws.player(names, duration=500)` — play / pause buttons and a slider for frames named `names`; a `.gif` plays at the same `duration` (ms).
- `ws.template` — the house colorway, as `layout.template`.
- `import 'themes/tropical_tidbits.libsonnet'` — Tropical Tidbits palettes: `tt_precip_rate` (mm/h), `tt_precip_total`, `tt_pwat` (mm), `tt_wind` (m/s), `tt_z500` (dam).

## Notes
- Values are drawn in the file's own units (K stays K, Pa stays Pa): run unit-convert for °C or hPa, and set palette bounds and contour levels in those units.
- A forecast's `step` is a lead time. Run step-to-time to draw it by valid date beside observations, or use `.dt.days` for lead days.
- Animations: `frames[k].data` replaces the traces listed in `frames[k].traces` (by position in `data`). Keep the base map out of the frames: it stays on every frame.
- A still image takes at most 100 panels; play more as frames.
- Errors come from Jsonnet (syntax, unknown field), from the reference checks (which data, which dim, which skill), or from Plotly itself, naming the trace (`data[3] (scatter)`).

## Output
The figure at each `-o`. PNG, JPG, PDF, SVG and GIF print `plot hash:` and `data: not null | NULL` for the plotted traces. The provenance (`weather_skills_history`, with the evaluated spec) is embedded in the file; read it with the provenance skill.
