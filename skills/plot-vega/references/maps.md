# Maps

A map is a Vega-Lite view with a `projection`, whose layers use the
`longitude`/`latitude` channels (cells, points, text) or the `geoshape` mark
(Natural Earth, GeoJSON, contours). Everything in
[Vega-Lite projections](https://vega.github.io/vega-lite/docs/projection.html) and
[geoshape](https://vega.github.io/vega-lite/docs/geoshape.html) applies.

## Layer order

Layers draw in order, bottom first:

1. data cells (`rect`) or contour bands (`geoshape`);
2. filled base-map polygons on top of the data: `lakes`, and `ocean` if you want land-only data;
3. line layers: `coastline`, `borders`, `admin1`, `rivers`, region outlines, isolines;
4. points (stations), arrows, then text labels.

Each mark sets `"clip": true`. Line layers set `"filled": false`.

```json
{"data": {"name": "lakes"},   "mark": {"type": "geoshape", "fill": "#cfe8f3", "stroke": "#4a7fa5", "strokeWidth": 0.5, "clip": true}},
{"data": {"name": "coast"},   "mark": {"type": "geoshape", "filled": false, "stroke": "#222", "strokeWidth": 0.8, "clip": true}},
{"data": {"name": "borders"}, "mark": {"type": "geoshape", "filled": false, "stroke": "#222", "strokeWidth": 1.2, "clip": true}}
```

Scale: `10m` for a country or smaller, `50m` for a region (East Africa, the
Sahel), `110m` for a continent.

## Projection and window

- `"projection": {"type": "equirectangular"}` is plate carrée, the usual
  choice for regional weather maps. `mercator`, `conicEqualArea`,
  `albers`, `azimuthalEqualArea`, `orthographic` and the other d3 projections
  all work.
- Leave out `fit`, `scale` and `translate`, and the window is the extent of
  the data in that view. **Change the window by cropping the data**:
  `"bbox": [N, W, S, E]` on the Zarr binding.
- A hand-written window uses a `MultiPoint` of two corners
  `[[W, S], [E, N]]`, which has no winding order to get wrong:

  ```json
  "projection": {"type": "equirectangular",
                 "fit": {"type": "Feature", "properties": {},
                         "geometry": {"type": "MultiPoint", "coordinates": [[33.5, -5], [42, 5]]}}}
  ```

  A `Polygon` box written counter-clockwise is read by d3 as "the whole
  globe except this box", and the map then shows the whole world.
- Set `width` and `height` to the data's aspect, or the base map shows past
  the data on two sides: for `equirectangular`, `height ≈ width × lat span / lon span`
  (Kenya, 8.5° × 10°: `"width": 400, "height": 470`).
- `projection` belongs to a single view or a `layer` view, not to an
  `hconcat`/`vconcat`/`concat` parent. In a `facet` or `repeat`, put it in `spec`.

## Gridded data as cells

```json
"datasets": {"obs": {"zarr": "obs", "fields": {"lon": "longitude.lo", "lon2": "longitude.hi",
                                               "lat": "latitude.lo",  "lat2": "latitude.hi",
                                               "precip": "precip"}}},
...
{"data": {"name": "obs"},
 "mark": {"type": "rect", "clip": true},
 "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
              "latitude":  {"field": "lat", "type": "quantitative"},
              "longitude2": {"field": "lon2"}, "latitude2": {"field": "lat2"},
              "color": {"field": "precip", "type": "quantitative"}}}
```

Each cell is drawn at its real size on any grid (0.05°, 0.25°, 1.5°, uneven),
so products at different resolutions can sit side by side without
regridding. `square` or `point` marks at cell centres do not tile; do not use them for grids.

NaN cells are dropped (`dropna`), so land-only products show the base map
through the ocean. To show only one region's cells, run `clip-region`
upstream: cells outside it become NaN and are dropped. Vega-Lite cannot mask
by a polygon itself.

## Stations and labels

```json
"stations": {"zarr": "stations", "fields": {"lon": "longitude", "lat": "latitude",
                                            "name": "station_name", "precip": "precip"}}
...
{"data": {"name": "stations"},
 "mark": {"type": "circle", "size": 140, "stroke": "black", "strokeWidth": 1.2, "opacity": 1, "clip": true},
 "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
              "latitude": {"field": "lat", "type": "quantitative"},
              "color": {"field": "precip", "type": "quantitative"}}},
{"data": {"name": "stations"},
 "mark": {"type": "text", "dy": -12, "fontSize": 10, "clip": true},
 "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
              "latitude": {"field": "lat", "type": "quantitative"},
              "text": {"field": "name"}}}
```

When the cells and the stations are the same kind of variable (both 7-day
precip totals), they get the same default scale and share one legend. Add
`"tooltip"` encodings for the HTML output. Cities or other fixed points can be
a plain row list in `datasets`.

## Outlining a country or region

- **A country**: the Natural Earth `countries` layer and a filter. Ask for the
  property you filter on:

  ```json
  "countries": {"naturalearth": "countries", "scale": "10m", "properties": ["ADM0_A3"]}
  ...
  {"data": {"name": "countries"},
   "transform": [{"filter": "datum.properties.ADM0_A3 == 'KEN'"}],
   "mark": {"type": "geoshape", "filled": false, "stroke": "black", "strokeWidth": 1.8, "clip": true}}
  ```

  Add `{"naturalearth": "admin1", "scale": "10m"}` for first-level divisions.
- **Any other polygon** (a county, a basin, a custom box): write it with
  `resolve-region --geojson` or by hand, pass `-i region=file.geojson`,
  bind `{"geojson": "region"}`, and draw it as a `geoshape` with `"filled": false`.
- Fill instead of outline: `{"type": "geoshape", "fill": "#000", "fillOpacity": 0.15}`.
- Colour or label countries by a property: bind with `"properties": ["NAME"]`, then
  `"color": {"field": "properties.NAME", "type": "nominal"}`.

## One map per lead (facet)

```json
"data": {"name": "fcst"},
"transform": [{"calculate": "'Week ' + (datum.lead_days / 7)", "as": "week"}],
"facet": {"field": "week", "type": "ordinal", "title": null},
"columns": 4,
"spec": {"width": 170, "height": 205, "projection": {"type": "equirectangular"},
         "layer": [ cells, {"data": {"name": "coast"}, ...}, {"data": {"name": "borders"}, ...} ]}
```

`fields` lists `"lead_days": "step"` so `step` becomes a column (days). The
base-map layers inside `spec` name their own `data`, so they repeat in every
panel. A horizontal legend under the grid:
`"legend": {"orient": "bottom", "direction": "horizontal", "columns": 8, "titleOrient": "left"}`.
Facet by `valid_time` or `time` with `"type": "temporal"` and a
`"header": {"format": "%d %b", "formatType": "time"}`, or by a `calculate`d label.

## Side by side, each product on its own grid

`hconcat` of two layer views, each with its own `projection` and its own
binding. Give both bindings the same `bbox` so the windows match, and
`"resolve": {"scale": {"color": "shared"}}` for one legend. See
`map_side_by_side_grids`. Use `"independent"` when the panels show different
quantities (a total and an anomaly).

## Anomalies

A precip anomaly (`anomal` in the name or `long_name`, or negative values) gets the
classed diverging palette by default. For a continuous diverging map, set
`"scale": {"scheme": "brownbluegreen", "domainMid": 0}` (or `redblue`,
`"reverse": true` to flip). For a temperature anomaly, pick the scheme and
title yourself: the default palette only covers precipitation.

## Contours

A `contours` binding produces bands (`"filled": true`, `properties.mid`) or
isolines (`properties.level`); draw both with `geoshape`:

```json
"bands": {"zarr": "fcst", "sel": {"step": "7D"},
          "contours": {"variable": "tp", "levels": [0, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200], "filled": true}},
"lines": {"zarr": "fcst", "sel": {"step": "7D"},
          "contours": {"variable": "tp", "levels": [10, 30, 50, 75]}}
...
{"data": {"name": "bands"}, "mark": {"type": "geoshape", "clip": true},
 "encoding": {"color": {"field": "properties.mid", "type": "quantitative"}}},
{"data": {"name": "lines"}, "mark": {"type": "geoshape", "filled": false, "stroke": "black", "strokeWidth": 0.6, "clip": true}}
```

Label isolines with a `text` layer on a rows dataset if you need numbers.

## Wind arrows (quiver)

Bind the grid twice: full resolution for speed cells, thinned with
`"isel": {"latitude": {"step": 3}, "longitude": {"step": 3}}` for arrows.
Arrows are `point` marks with an SVG-path `shape`, rotated by `angle` and
sized by speed:

```json
"transform": [{"calculate": "sqrt(datum.u * datum.u + datum.v * datum.v)", "as": "arrow_speed"},
              {"calculate": "atan2(datum.u, datum.v) * 180 / PI", "as": "toward"}],
"mark": {"type": "point", "shape": "M0,1 L0,-1 M-0.4,-0.45 L0,-1 L0.4,-0.45",
         "filled": false, "stroke": "black", "strokeWidth": 1.3, "opacity": 1, "clip": true},
"encoding": {"longitude": ..., "latitude": ...,
             "angle": {"field": "toward", "type": "quantitative", "scale": null},
             "size": {"field": "arrow_speed", "type": "quantitative",
                      "scale": {"type": "pow", "exponent": 2, "domain": [0, 12], "range": [0, 1296]}}}
```

`angle` is clockwise from north in degrees, so `atan2(u, v)` points along the
flow. `size` is an area, so a `pow` scale with exponent 2 makes arrow length
proportional to speed. Speed is computed in the spec, so set its colour
`scheme`, `domain` and `title` yourself, and add
`"resolve": {"legend": {"color": "independent", "size": "independent"}}` to
keep the arrow key separate from the colour legend. See `map_quiver_wind`.

## Map gotchas

| Symptom | Cause | Fix |
| --- | --- | --- |
| The whole world shows | A hand-written `fit` polygon is counter-clockwise, or `usermeta.defaults` is off with no `fit` | Use a two-corner `MultiPoint` fit, or leave `fit` to the default |
| Points, labels or lines outside the map | Marks are not clipped by default | `"clip": true` on every map mark |
| A line layer draws as filled black blobs | `geoshape` fills by default | `"filled": false` |
| White hairlines between cells | Antialiasing | Already sealed by default; do not set `stroke` on the `rect` mark, which turns sealing off for it |
| Stations get a second legend | Their colour scale differs from the cells' | Leave both to the default, or set the same scale on both |
| `projection` on `hconcat` is a schema error | Concat parents cannot own a projection | One `projection` per panel |
| Side-by-side panels show different windows | Each panel fits its own data | Same `bbox` on both bindings |
| Base map extends past the data | The view's aspect differs from the data's | Match `height`/`width` to the lat/lon span |
| Arrow and colour legends merge | Identical domains merge legends | `resolve.legend` `independent` |
| Slow render, huge file | Hundreds of thousands of cells | `bbox`, `isel` step, or coarsen upstream |
