# Defaults, palettes and overrides

Everything not listed here is Vega-Lite's own default (axis ticks, fonts,
padding, legend placement, colours of nominal fields, ...). Change those with
the Vega-Lite keys for them: `axis`, `legend`, `scale`, `config`.

**A default only fills a key you left out. A key you wrote is never
changed**, even when it is `null`. Each default prints one line with its JSON path:

```text
default datasets.borders.bbox <- extent of the bound data [5.0, 33.5, -5.0, 42.0]
default spec.projection.fit <- extent of the bound data [5.0, 33.5, -5.0, 42.0]
default spec.layer[0].encoding.color.scale <- ppt_week (default for this variable; 13 classes)
default spec.layer[4].encoding.color.scale <- ppt_week (default for this variable; 13 classes)
default spec.layer[0].encoding.color.title <- 'Total precipitation [mm]'
```

`--dump-spec` writes the final spec with every default as an explicit value.
To change one default, copy that key from the dump into your spec and edit it.

## "Bound variable"

Title and colour defaults need the encoded field to be a **bound variable**:
a column whose `fields` source is a data variable of the input, and that no
transform in scope has created or overwritten (`calculate`/`as`,
`aggregate`, `window`, `joinaggregate`, `lookup`, `fold`, `quantile`,
`pivot`, `density`, `regression`, `loess`). That is the only case where
the skill knows the variable's `long_name`, `units` and `aggregation_period`.
An `aggregate` that keeps the column name, as in
`{"aggregate": [{"op": "mean", "field": "t2m", "as": "t2m"}]}`, counts as a new
column. Wind speed from u/v, a mean over members and an anomaly from a lookup
are all computed in the spec, so you set their `title` and `scale` yourself.

An encoding on a `layer` parent counts when every child layer that inherits it
binds that field to a variable with the same `long_name [units]`, for example
two precipitation products sharing a top-level `y` (recipe
`timeseries_two_products`).

## The defaults

### Colour scale

On `color`, `fill` or `stroke`, when all of these hold:

- the field is a bound variable and `"type": "quantitative"`;
- the variable is precipitation (by name, `standard_name` or units),
  SPI, or percent of normal;
- the scale sets none of `type`, `scheme`, `range`, `domain`, `domainMid`,
  `domainMin`, `domainMax`.

The scale becomes a Vega-Lite threshold scale for the variable's palette:
`{"type": "threshold", "domain": [class edges], "range": [under, classes..., over]}`.
Other scale keys you set (`clamp`, `reverse`, ...) are kept. Other variables
(temperature, wind, scores) keep Vega's continuous default; pick a scheme for them.

Which palette:

| Variable | Palette |
| --- | --- |
| SPI (`spi` in the name or `long_name`, or "standardized precipitation") | `spi` |
| Percent of normal (`poa`, "percent of", units `%`) | `ppt_poa` |
| Precip anomaly ("anomal" in name or `long_name`, or any negative value) | `ppt_anom_daily` / `_week` / `_month` / `_season` from `aggregation_period` |
| Precip total | `ppt_daily` / `_week` / `_month` / `_season` from `aggregation_period` |

Windows: under 2 days → daily (0–50 mm; anomalies ±50), under 10 days → week
(0–200; ±200), under 40 days → month (0–400; ±300), longer → season (0–1000;
±500). No `aggregation_period` counts as weekly. The same colour is always
the same millimetres across windows.

Two layers whose fields are the same kind of variable get identical scales, and
Vega-Lite merges identical scales into **one legend** (grid cells plus
station dots). Setting a scale on one layer only gives a second legend: set
the same scale on both.

### Palette name as `scale.scheme`

`"scale": {"scheme": "ppt_week"}` (any name in the table below) on a
quantitative colour field becomes that palette's threshold scale. This
applies on any field, computed or bound, and even with `usermeta.defaults: false`,
because it is an explicit choice. `default_precip` and `default_precip_anom` still pick their
window from the field's `aggregation_period` when the field is a bound
variable, and use the weekly window otherwise.

A scheme that is neither a weather palette nor a Vega scheme fails with both lists.

### Titles

On `x`, `y`, `color`, `fill`, `stroke`, `size`, `opacity`, `theta`, `radius`,
when the field is a bound variable and the encoding has no `title` key:
`long_name [units]` with short display units (`mm`, `mm/day`, `°C`, `m/s`).
Without `long_name`, the variable name is used.

Within one `layer` group, only the first layer that has a title for a channel
keeps it: Vega-Lite joins differing titles on a shared axis or legend with
commas ("Total precipitation [mm], precip"). `"title": null` removes a title
and counts as set.

### Map window: `projection.fit`

When a view has a `projection` that sets none of `fit`, `scale` or
`translate`, `fit` becomes the extent of the Zarr bindings drawn in that view,
written as a two-point `MultiPoint` feature. Each `hconcat` panel and each facet `spec`
fits its own data. Change the window by cropping the bindings with `bbox`;
use the same `bbox` on every panel's binding to give side-by-side panels the
same window. To set it by hand, write a `fit` (see `maps.md`) or a
`scale`/`center`.

The fit fills the view's `width` × `height`. When the box and the view have
different aspect ratios, the map is centred and the base map shows past the
data on two sides. Choose `height ≈ width × (lat span / lon span)` for
`equirectangular`.

### Base-map clip box

A `naturalearth` or `geojson` binding without `bbox` is clipped to the union
of all Zarr bindings' extents, plus a 1° pad. Set `bbox` when the base map
should cover more than the data (e.g. a station-only map with a wider frame).

### Classed legends

A threshold colour scale (from a default, a palette name, or written by you)
gets one equal-size square per class, labelled with its range (`5 – 10`,
`≥ 200`). Vega-Lite would draw a gradient where each class gets space in
proportion to its value range, so the 0–1 mm class is a sliver. The under entry (`< 0`) appears
only when a plotted value is below the first edge. Your `legend` keys
(`orient`, `direction`, `columns`, `title`, `labelFontSize`, ...) are kept.
Example: a horizontal legend under a facet,
`"legend": {"orient": "bottom", "direction": "horizontal", "columns": 8, "titleOrient": "left"}`.

### Cell seams

Antialiasing leaves hairline white gaps between abutting `rect` cells. Every
`rect` mark filled from a scale and with no `stroke` of its own gets
`stroke` = its fill with width 0.5. Bars, geoshapes, and marks with an
explicit stroke are left alone.

## Switching defaults off

```json
"usermeta": {"defaults": false}
```

| Key | Effect when `false` |
| --- | --- |
| `usermeta.defaults` | No colour scales, titles, `fit`, base-map clip or classed legends. Weather palette names in `scale.scheme` still resolve. Cell seams are still sealed. |
| `usermeta.classed_legend` | Threshold scales keep Vega-Lite's gradient legend. |
| `usermeta.seal_cells` | No seam stroke on `rect` cells. |

With `defaults: false` and no `fit`, a projection shows the whole world, and
base-map layers are not clipped, so a 10m layer embeds the whole planet.
Set `bbox` and `fit` yourself.

## Palettes

| Name | Classes |
| --- | --- |
| `default_precip` | Totals. Window from `aggregation_period` (see above). |
| `default_precip_anom` | Anomalies. Window from `aggregation_period`. |
| `ppt_daily` | 0–50 mm |
| `ppt_week` | 0–200 mm |
| `ppt_month` | 0–400 mm |
| `ppt_season` | 0–1000 mm |
| `ppt_anom_daily` | ±50 mm |
| `ppt_anom_week` | ±200 mm |
| `ppt_anom_month` | ±300 mm |
| `ppt_anom_season` | ±500 mm |
| `ppt_short`, `chirps_short` | CHC classic rainbow totals legend, short-period classes |
| `ppt_total`, `chirps_total` | CHC classic rainbow totals legend, long-period classes |
| `ppt_poa` | Percent of normal (30–300%) |
| `ppt_spp` | CHC seasonal rainfall performance probability classes |
| `spi` | Standardized Precipitation Index classes |

Names are case-insensitive. For continuous colour, use a
[Vega scheme](https://vega.github.io/vega/docs/schemes/) such as `viridis`,
`magma`, `blues`, `yellowgreen`, `yelloworangered`, or, for diverging data,
`redblue` and `brownbluegreen` with `"domainMid": 0`. Add `"reverse": true`
to flip a scheme. Fix the range with `"domain": [0, 12]` and add
`"clamp": true` so values outside it take the end colours.

A custom classed palette:

```json
"scale": {"type": "threshold",
          "domain": [0, 10, 25, 50],
          "range": ["#ffffff", "#c7e9c0", "#74c476", "#238b45", "#00441b"]}
```

`range` has one more colour than `domain` has edges: the first colour is
below the first edge, the last is at or above the last edge. It gets the
classed legend.
