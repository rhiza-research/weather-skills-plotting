# Charts: time series, bars, distributions, wind roses

Charts are plain Vega-Lite views over bound rows. The
[Vega-Lite docs](https://vega.github.io/vega-lite/docs/) and
[examples](https://vega.github.io/vega-lite/examples/) apply unchanged; this
page covers what is specific to weather-skills data.

## Time

- Bound datetimes are **epoch milliseconds, UTC**. Encode with
  `"type": "temporal"`. Dates render in UTC, so a 00:00 week start shows as that day.
- Axis format: `"axis": {"format": "%b %Y"}` (months), `"%d %b"` (days),
  `"tickCount": "month"` for one tick per month. Put the time range in the
  title or subtitle; `"title": null` on a date axis is usually cleaner.
- Forecasts: `"valid": "valid_time"` in `fields` gives init + lead as a
  datetime. For lead as a number, bind `"lead_days": "step"` (float days).
- **Aggregated bins are labelled at their start** (`aggregate-temporal`
  writes the first day of each 7-day bin). Say so in the subtitle, or compute the end:
  `{"calculate": "timeOffset('day', datum.week, 7)", "as": "week_end"}`.
  The value is exclusive (the next bin's start); for an inclusive label use
  `timeOffset('day', datum.week, 6)`.
- Expressions on time: `year(datum.t)`, `month(datum.t)` (0-based),
  `timeFormat(datum.t, '%d %b')`, `timeOffset('month', datum.t, 1)`, `datetime(2026, 0, 1)`.
- Vega-Lite `timeUnit` groups by calendar units in the spec, as an encoding
  key (`"timeUnit": "yearmonth"` next to `field`) or a transform
  (`{"timeUnit": "yearmonth", "field": "t", "as": "month"}` then an `aggregate`).

## One series

```json
"datasets": {"weekly": {"zarr": "weekly", "fields": {"week": "time", "precip": "precipitation_surface"}}},
"data": {"name": "weekly"},
"mark": {"type": "line", "point": {"size": 25}},
"encoding": {"x": {"field": "week", "type": "temporal", "title": null, "axis": {"format": "%b %Y"}},
             "y": {"field": "precip", "type": "quantitative"}}
```

The y title is the default (`long_name [units]`). Add `"interpolate": "monotone"`
for smooth lines, `"step-after"` for a staircase over bins.

A horizontal reference line with a label at the right edge (recipe `timeseries_weekly_line`):

```json
{"data": {"name": "weekly"},
 "transform": [{"aggregate": [{"op": "mean", "field": "precip", "as": "mean"}]},
               {"calculate": "['mean', format(datum.mean, '.1f') + ' mm']", "as": "label"}],
 "layer": [
   {"mark": {"type": "rule", "color": "#555", "strokeDash": [4, 3]},
    "encoding": {"y": {"field": "mean", "type": "quantitative"}}},
   {"mark": {"type": "text", "align": "left", "dx": 4, "color": "#555"},
    "encoding": {"x": {"value": "width"}, "y": {"field": "mean", "type": "quantitative"},
                 "text": {"field": "label"}}}]}
```

`"x": {"value": "width"}` puts the label at the right edge of the plot, in the
margin, so it never covers data. A text value that is an array draws one line per element.

## Several products on one axis

Bind each product separately, mapping its own variable name to the **same
column names**. Put the shared `x`/`y` at the top level, and give each layer
only its data and a constant colour `datum`, which becomes its legend entry:

```json
"datasets": {
  "imerg":  {"zarr": "imerg",  "fields": {"week": "time", "precip": "precipitation_surface"}},
  "chirps": {"zarr": "chirps", "fields": {"week": "time", "precip": "precip"}}
},
"encoding": {
  "x": {"field": "week", "type": "temporal", "title": null},
  "y": {"field": "precip", "type": "quantitative"},
  "color": {"scale": {"range": ["#2c7fb8", "#d95f02"]},
            "legend": {"orient": "top-left", "title": null, "symbolType": "stroke"}}
},
"layer": [
  {"data": {"name": "imerg"},  "mark": "line", "encoding": {"color": {"datum": "IMERG Late"}}},
  {"data": {"name": "chirps"}, "mark": "line", "encoding": {"color": {"datum": "CHIRPS"}}}
]
```

The y title is the default when both variables have the same `long_name` and units.
The colours in `range` are taken in layer order; add
`"domain": ["IMERG Late", "CHIRPS"]` to the scale to pin the pairing
explicitly. Products with different time ranges are fine: each
line covers its own range.

Alternatively, put several variables of **one** Zarr in long form with a
`fold` transform: `{"fold": ["tp_a", "tp_b"], "as": ["product", "precip"]}`
then `"color": {"field": "product", "type": "nominal"}`. Folded values are
computed columns, so set the y title yourself.

## Ensembles

Keep `number` as a column and summarise in the spec (recipe
`timeseries_ensemble_spaghetti`):

- members: `"detail": {"field": "member"}` on a thin, faded line;
- mean: `{"aggregate": [{"op": "mean", "field": "t2m", "as": "mean"}], "groupby": ["valid"]}`;
- a 10–90% band: `{"quantile": "t2m", "groupby": ["valid"], "probs": [0.1, 0.9]}`,
  `{"calculate": "datum.prob < 0.5 ? 'lo' : 'hi'", "as": "edge"}`,
  `{"pivot": "edge", "value": "value", "groupby": ["valid"]}`, then an `area`
  with `y: lo` and `y2: hi`;
- climatology: a second binding of the same input with only `valid` and the climatology variable;
- legend: `"color": {"datum": "Members"}` (and so on) on each layer, colours in
  `config.range.category`, and `config.legend.symbolOpacity: 1` so the faded
  members' swatch is not faded too.

Use `"scale": {"zero": false}` on temperature y axes.

## Stacked panels

`vconcat` of views with their own `height` and `title`; each panel has its
own data and transforms. Join two bindings with `lookup` on a shared time
column (exact match on epoch ms):

```json
{"lookup": "valid", "from": {"data": {"name": "clim"}, "key": "valid", "fields": ["clim"]}},
{"calculate": "datum.mean - datum.clim", "as": "anomaly"}
```

Colour bars by sign: `"color": {"condition": {"test": "datum.anomaly >= 0", "value": "#d6604d"}, "value": "#4393c3"}`.
Share the x axis across panels with `"resolve": {"scale": {"x": "shared"}}`.
Panels side by side are `hconcat`; small multiples of one chart are `facet`
or `repeat`.

## Bars

- **A bar spanning a time interval**: `x` = start, `x2` = end, and
  `"y2": {"datum": 0}`. Without `y2`, a bar with `x2` is drawn as a thin
  floating dash at the value. Recipe `bar_weekly_totals`.
- Bars on a temporal `x` without `x2` are drawn as narrow bars centred on each timestamp.
  For one bar per calendar month, group in the encoding:
  `"x": {"field": "week", "timeUnit": "yearmonth", "type": "temporal"}` with
  `"y": {"field": "precip", "aggregate": "sum", "type": "quantitative"}`;
  each bar spans its month. Weekly bins into months is only exact for daily
  data; aggregate upstream for exact monthly totals.
- **Grouped bars**: `x` the group (`lead`), `xOffset` the member of the group
  (`model`), `color` the same field. Fix the order with `"sort": [...]` on
  both `xOffset` and `color`. Recipe `bar_model_comparison`.
- Value labels: a `text` layer with the same `x`/`xOffset`/`y`, `"dy": -6`,
  `"text": {"field": "rmse", "format": ".1f"}`.
- Stacked bars are the default when `color` is a field on a bar; set
  `"stack": null` on `y` to overlap instead.
- Negative and positive anomalies: `y` from the value and `"y2": {"datum": 0}`,
  coloured by a `condition` on the sign.

## Distributions

- Vega-Lite's composite `"mark": "boxplot"` (`"extent": "min-max"` or a
  multiple of the IQR) is fine for a quick look.
- For fixed percentiles (10/25/50/75/90), compute them with `quantile` and
  `pivot`, and draw `rule` (whiskers), `bar` with `y`/`y2` (box) and `tick`
  (median). Recipe `box_mediogram`.
- Histograms: `"x": {"field": "precip", "bin": {"maxbins": 30}, "type": "quantitative"}`,
  `"y": {"aggregate": "count"}`. Density: the `density` transform.
- Scatter of two variables: `point` marks on `x`/`y`; a fit line from the
  `regression` or `loess` transform.

## Wind rose

Compute direction sectors and speed classes in the spec from `u`/`v` columns
and draw stacked `arc` marks with `theta`/`theta2` (radians, `"scale": null`)
and `radius`/`radius2` (cumulative percent, via a `window` sum). The direction
the wind blows **from** is `(atan2(-u, -v) * 180 / PI + 360) % 360`. Every row
(cell × time × member) is a sample. Recipe `windrose`; add the N/E/S/W
labels as a `text` layer on inline `values`. Use `"config": {"view": {"stroke": null}}`
to drop the frame.

## Chart gotchas

| Symptom | Cause | Fix |
| --- | --- | --- |
| Hundreds of tick labels, or a categorical legend for a number | The encoding has no `type`, so Vega-Lite treats it as nominal | Set `"type"` on every field encoding |
| Bars float as dashes | `x`/`x2` without `y2` | `"y2": {"datum": 0}` |
| Axis title reads "A, B" | Layers with different titles share the axis | Set the title on one layer, or on the top-level encoding |
| Legend swatches faded | The legend copies the first layer's opacity | `config.legend.symbolOpacity: 1` |
| Line legend shows circles | Default legend symbol | `"symbolType": "stroke"` |
| `lookup` matches nothing | Keys differ (one side was computed or rounded) | Join on a bound time column on both sides |
| The y axis starts at 0 for temperatures | Quantitative scales include zero by default | `"scale": {"zero": false}` |
| Bars too narrow on a time axis | No `x2` | Give an interval end, or group with `timeUnit` |
| A fold, aggregate or calculate output has no title or units | Computed columns carry no attributes | Set `title` (and a colour `scale`) on that encoding |
