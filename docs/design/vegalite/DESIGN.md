# Design: one Vega-Lite `plot` skill

Status: **implemented alongside the matplotlib skills** as
[`skills/plot-vega`](../../../skills/plot-vega/SKILL.md), with the library in
[`src/weather_skills_plotting/vega/`](../../../src/weather_skills_plotting/vega/).
The existing `plot`, `plot-timeseries`, `plot-verify` and `plot-mediogram`
are unchanged; replacing them (and naming the skill `plot`) is still the
proposal below. The skill's SKILL.md and `references/` are the user-facing
documentation and win where this document differs. Not yet built from this
design: the 110m offline fallback to core's `countries.geojson`, the
`<var>.flag` source, `usermeta.fit_aspect`, and passing compiler warnings
through to stderr.

The prototype under [`prototypes/`](prototypes/) renders every example in
this document from synthetic weather-skills Zarrs, so each claim below was
checked against real output. The pictures in this document are those renders.

## TL;DR

- One skill, `plot`, replaces `plot`, `plot-timeseries`, `plot-verify` and
  `plot-mediogram`. It depends on Altair and vl-convert. There is no
  matplotlib, seaborn, Cartopy or nc-time-axis.
- The agent writes a **plain Vega-Lite spec**. There is no placeholder
  syntax. The skill adds exactly three things on top of upstream Vega-Lite:
  1. **Data bindings.** An entry under the top-level `datasets` may be a
     binding object instead of rows. The binding names an input Zarr and
     maps columns to dims, coords or variables. The skill replaces the
     binding with rows. Layers point at the data with Vega-Lite's own
     `{"data": {"name": "obs"}}`.
  2. **Defaults for what the agent leaves unset.** These are derived from
     the bound data:
     - a colour scale (dev's precip, anomaly, SPI and percent-of-normal
       palettes, picked from the variable's attributes);
     - a classed legend with one equal-size entry per class;
     - axis and legend titles (`long_name [units]`);
     - the map window (`projection.fit`);
     - the clip box for base-map layers.

     Anything the agent writes wins. Every default the skill applies is
     printed, so the agent can see it and override it.
  3. **Our palette names as `scale.scheme` values,** such as
     `"scheme": "ppt_month"`, alongside Vega's built-in schemes.
- The CLI is
  `plot.py -i obs=chirps.zarr -i stations=st.zarr --spec spec.json -o out.png`.
  Inputs are named, so bindings can refer to them.
- The pipeline is:
  1. bind the data;
  2. fill the defaults;
  3. lint the fields;
  4. validate with Altair, which also picks `Chart`, `LayerChart`,
     `HConcatChart` and so on;
  5. compile to Vega;
  6. patch the cell seams and the classed legends;
  7. render the PNG with vl-convert;
  8. stamp provenance with the core `@weather_skill` decorator.

The figure below is the spec in
[`examples/map_heatmap_stations.json`](examples/map_heatmap_stations.json). It
sets no colour scale, legend, title, map window or base-map extent.

![Heatmap with base map and stations](img/map_heatmap_stations.png)

## Goals and non-goals

**Goals**

- The agent controls every element of the figure through one declarative
  document, the Vega-Lite spec. Our defaults only fill gaps, and the agent
  can see and override every one of them.
- There is a thin, explicit way to say which input, which slice and which
  dims or variables become which columns.
- A short spec gives a good weather figure. The dev branch's colorbar
  choices (the precip window from `aggregation_period`, the classed anomaly
  palette, units in labels) apply without the agent having to know them.
- The common weather figures are recipes, not features. These include a grid
  heatmap over a base map with station dots, faceted lead maps, classed and
  diverging anomalies, quiver, contours, time series, ensemble spaghetti with
  bands, multi-panel time series, grouped bars, box or mediogram plots and
  the wind rose.
- Errors are actionable. They name the JSON path, list the valid keys or
  columns, and never fall back silently.
- Provenance stamping and the QA lines work the same way as the current
  skills.

**Non-goals**

- No plotting vocabulary of our own. There is no `traces[]`, `subplots[]`,
  `layout.facet` or `$` placeholder. If Vega-Lite can express something, the
  agent writes it in Vega-Lite.
- No layout or styling defaults beyond the data-driven ones listed under
  [Defaults](#defaults). Fonts, sizes, spacing and so on are Vega-Lite's own
  defaults or `config`.
- No data reduction in the plot skill. Leftover dims are an error and are
  never averaged for the agent. Reductions belong to `aggregate-temporal`,
  `reduce`, `difference` and similar skills. Small chart-local summaries
  remain available through Vega-Lite transforms (`aggregate`, `quantile`,
  `window`, `pivot`).
- No interactive features. Rendering is static (PNG, plus optional HTML).
  Vega-Lite `params` still compile but are not supported.

## What carries over from dev, and what is dropped

| Area | Dev branch | New skill |
| --- | --- | --- |
| Spec language | Custom (`traces`, `inputs`, `subplots`, `layout`, `theme`, `geo`, `annotations`, `shapes`), compiled to matplotlib | Vega-Lite 6 (schema `v6.json`) plus data bindings |
| Renderer | matplotlib + Cartopy, constrained layout | vl-convert (Deno + resvg, no browser) |
| Automatic colour scale (`named_precip_scale`: precip total, anomaly, SPI, percent of normal, window from `aggregation_period`) | Used when `theme.colormap` is unset | **Kept**, as the default colour scale when the agent sets none |
| Palette tables (`ppt_*`, `ppt_anom_*`, CHC, SPI, `default_precip`, `default_precip_anom`) | `theme.colormap` names | **Kept**, as `scale.scheme` names |
| Classed colorbar (equal-width classes) | matplotlib `spacing="uniform"`, `extend="both"` | **Kept** in spirit, as a classed legend with one equal-size entry per class labelled with its range. The horizontal bar with end triangles is dropped. |
| Units in labels (`°C`, not `degC`) | core `format_units_for_display` | **Kept**, as the default title |
| Map overlays | Cartopy `NaturalEarthFeature` | Natural Earth GeoJSON bindings (`naturalearth: borders`, and so on) |
| Seaborn templates, `rocket`, `along` colour cycles, fontsize defaults, DPI, max columns, theme files, `WEATHER_SKILLS_PLOT_THEME` | `theme.py` | **Dropped.** Vega-Lite `config` covers these, and Vega schemes cover continuous colour maps (`viridis`, `magma`, `blues`, `redblue`, `brownbluegreen`, ...). |
| Kind-specific CLIs (`--obs`/`--forecast`/`--verify`, `--layer KIND:PATH`, `--x`/`--y`) | 4 skills | **Dropped.** There is one `-i NAME=PATH` that can repeat. |
| QA stdout (pixel hash, data status) | `qa.py` | **Kept** unchanged. It only needs PIL and numpy. |
| Provenance stamp and circular mark | core decorator | **Kept** unchanged. No core change is needed. |

## Architecture

```text
 -i obs=chirps.zarr ─┐                     ┌──────────── spec.json (plain Vega-Lite + data bindings) ────────────┐
 -i st=stations.zarr ┼─► @weather_skill ───┤                                                                     │
 -i rgn=ken.geojson ─┘   opens + hashes    ▼                                                                     │
                         inputs        1. bind      datasets.<name>: binding → rows; base maps clipped to data   │
                                       2. defaults  fill unset colour scale / title / projection.fit; log each   │
                                       3. lint      every encoding field exists in its dataset                   │
                                       4. validate  Altair: dispatch on top-level key, schema check              │
                                       5. compile   vl_convert.vegalite_to_vega (VL 6.4)                          │
                                       6. patch     seal_cells (rect seams), classed_legends (threshold legends)  │
                                       7. render    vl_convert.vega_to_png(scale=2)  /  HTML                      │
                                       8. return Path ─► decorator stamps provenance (+ mark), QA lines           │
```

Each step is a pure function, and the library exposes them separately
(`bind`, `apply_defaults`, `lint`, `validate`, `compile`, `render`). This lets
tests and the `--describe` and `--dump-spec` modes stop at any stage.

### Why bindings live inside `datasets`

Vega-Lite allows named datasets only at the top level (`datasets`). Any unit,
layer, facet or concat can then refer to one by `{"data": {"name": ...}}`.
Putting the binding in that slot gives us these properties:

- The rest of the spec is untouched, valid Vega-Lite. Upstream docs, Vega
  Editor examples and Altair's `to_dict()` output all apply directly.
- One binding can feed any number of layers and panels. For example, the
  station rows feed both the dots and the labels.
- The spec is self-describing. Everything that defines the figure lives in
  one JSON object, which is what provenance records.

Alternatives considered:

- **A separate `--bind name=zarr:...` flag.** This splits one figure across
  two documents, and per-column options do not fit on a CLI.
- **Inline `"data": "$fcst"` strings.** These break Vega-Lite schema
  validation of the template, and the same data has to be re-declared in
  every layer.
- **Agents writing Altair Python.** That means code execution rather than
  a declarative spec, and there would be nothing to validate or record.

### Dispatch

Altair needs to know the top-level class before it can validate or convert.
The skill picks it from the keys:

| Top-level key | Altair class | Typical use |
| --- | --- | --- |
| `mark` | `Chart` | Single bar chart, single line |
| `layer` | `LayerChart` | Map with base layers and stations, spaghetti with mean and band |
| `hconcat` / `vconcat` / `concat` | `HConcatChart` / `VConcatChart` / `ConcatChart` | Side-by-side grids, multi-panel time series |
| `facet` + `spec` | `FacetChart` | Lead-week maps, one panel per station |
| `repeat` + `spec` | `RepeatChart` | Same chart for several variables |

If none or more than one of these keys is present, the skill fails with a
message that lists the choices. Nested composition, such as a facet inside a
vconcat, is plain Vega-Lite and needs no dispatch.

## Command line

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot.py \
    -i obs=/tmp/chirps_week.zarr -i stations=/tmp/stations_week.zarr \
    -i region=/tmp/kenya.geojson \
    --spec /tmp/map.json -o /tmp/map.png
```

| Flag | Meaning |
| --- | --- |
| `-i`, `--input NAME=PATH` | An input, which can repeat. A path ending in `.geojson` or `.json` is a GeoJSON file, such as a region polygon from `resolve-region`; anything else is a Zarr. `NAME` is what a binding's `"zarr"` or `"geojson"` refers to, and binding a name with the wrong kind is an error. A single bare `PATH` is named `data`. Zarrs go through the core decorator, so they are opened, contract-checked and hashed into provenance. GeoJSON files are recorded by sha256 in the provenance parameters. |
| `--spec JSON\|PATH\|-` | The Vega-Lite spec with bindings. It can be inline JSON, a file, or stdin. |
| `-o`, `--output PATH` | A `.png` file (the default), `.jpg`, or `.html` (self-contained, with the data inlined). These are the formats core's `stamp_figure` accepts. |
| `--scale N` | The pixel ratio, default `2`. A 640-wide spec gives a 1280-pixel PNG. |
| `--describe` | Opens the inputs and prints, for each one, its dims, sizes, coords, variables (with `long_name`, `units` and `aggregation_period`) and the derived sources that are available. For each binding in `--spec`, if one is given, it also prints the columns and row count it would produce **and the defaults that would apply**. Nothing is rendered. This is the step an agent runs before writing a spec. |
| `--dump-spec PATH\|-` | Writes the final Vega-Lite after binding and defaults, and skips rendering. Every default is written out as an explicit value, so this is also how an agent copies a default and edits it. The output pastes into the [Vega Editor](https://vega.github.io/editor/) as-is. Add `--dump-spec-rows N` to truncate each dataset for reading. |
| `--max-rows N` | Raises the row guard (see [Limits](#performance-and-limits)). |

The `zarr_paths()` hook in the decorator means named inputs need no core
change. The skill wraps the `-i` list in a small holder whose `zarr_paths()`
returns the Zarr inputs only. The decorator opens and validates those, hashes
them and attaches `.datasets`, and the skill maps the names back. The skill
reads the GeoJSON inputs itself.

## Data bindings

A binding is an object under `datasets.<name>` that has exactly one of the
keys `zarr`, `geojson` or `naturalearth`. A plain list of rows passes through
unchanged.

### `zarr`: tidy rows from an input

```json
"datasets": {
  "obs": {
    "zarr": "obs",
    "bbox": [5, 33.5, -5, 42],
    "sel": {"time": "2026-10-01"},
    "fields": {"lon": "longitude.lo", "lon2": "longitude.hi",
               "lat": "latitude.lo",  "lat2": "latitude.hi",
               "precip": "precip"}
  }
}
```

| Key | Meaning |
| --- | --- |
| `zarr` | The input name from `-i NAME=PATH`. |
| `fields` | **Required.** A map from column name to source. A source is a data variable, a dim, a non-dim coord (such as `station_name`), or a derived source (see the next table). There must be at least one variable. Each listed dim becomes a column, and rows are the cartesian product over those dims (`to_dataframe`). |
| `sel` | Label selection on dims. Scalars use `method="nearest"` for numeric and time dims. Lists select several values. `{"start","stop","step"}` is a slice. Timedelta dims accept `"7D"` and datetime dims accept ISO strings. |
| `isel` | Positional selection with the same forms. `{"latitude": {"step": 3}}` thins quiver arrows. |
| `bbox` | `[N, W, S, E]` crop. It works on gridded data in either latitude order, and masks point data (stations). Because the default map window is the extent of the bound data, **this is how to set the map window.** |
| `dropna` | The default `true` drops rows where every variable is NaN, such as ocean cells in land-only products. |
| `cell_overlap` | An opt-in fraction (for example `0.25`) that widens `.lo`/`.hi` edges. Normally `seal_cells` makes this unnecessary. |

Derived sources:

| Source | Value |
| --- | --- |
| `<dim>.lo`, `<dim>.hi` | Cell edges from 1-D centres: midpoints, with the end cells mirrored. Used with `rect` and `longitude`/`longitude2`/`latitude`/`latitude2` to draw grid cells at their true size on any grid spacing. |
| `valid_time` | `time + step` for forecasts (init plus lead). |
| *(planned)* `<var>.flag` | The CF `flag_meanings` label for an integer flag variable, for example hit, miss or false alarm in a verify Zarr. |

Rules:

- **Leftover dims are an error.** A dim that has more than one value, is not
  a column, and was not reduced by `sel`/`isel` is an error. The message
  names it and suggests `sel`, adding it to `fields`, or an upstream
  reduction. Size-1 dims are squeezed.
- **Datetimes become UTC epoch milliseconds,** not ISO strings. Vega-Lite
  only parses ISO strings for datasets that feed a temporal encoding. A
  `lookup` join between a parsed and an unparsed dataset then silently
  matches nothing. Epoch milliseconds are unambiguous. The skill sets
  `TZ=UTC` as well, because the renderer's JS runtime otherwise parses
  dates in local time.
- **Timedeltas become float days.** This gives `lead_days / 7` arithmetic
  for "Week N" facet labels.
- Unknown sources fail with the input's dims, coords and variables listed.
- Each binding also records its **extent**, which the map defaults use.
  The extent is cell edges when the binding asks for `.lo`/`.hi` columns,
  because that data is drawn as cells. Otherwise it is point coordinates,
  as for stations and thinned arrows.

### `contours`: filled bands or isolines

Vega-Lite has no contour mark. A `zarr` binding with a `contours` block
traces a 2-D field with [contourpy](https://contourpy.readthedocs.io/) and
emits GeoJSON features, which a `geoshape` mark then draws:

```json
"bands": {"zarr": "fcst", "sel": {"step": "7D"},
          "contours": {"variable": "tp", "levels": [0, 5, 10, 20, 30, 40, 50, 75, 100, 150, 200], "filled": true}},
"lines": {"zarr": "fcst", "sel": {"step": "7D"},
          "contours": {"variable": "tp", "levels": [10, 30, 50, 75]}}
```

Bands carry `properties.lo`, `properties.hi` and `properties.mid`, and lines
carry `properties.level`. These values are in the variable's units, so they
get the same defaults as the variable. `"color": {"field":
"properties.mid", "type": "quantitative"}` picks up the precip palette. The
extent of a contour binding is the outermost cell centres, which is where
contourpy stops.

### `naturalearth`: base-map layers

```json
"borders": {"naturalearth": "borders", "scale": "10m"}
```

- The layers are `countries`, `borders` (land boundary lines), `coastline`,
  `lakes`, `rivers`, `admin1`, `ocean` and `land`. Scales are `10m`, `50m`
  and `110m`.
- Sources are the [natural-earth-vector](https://github.com/nvkelso/natural-earth-vector)
  GeoJSON files, **pinned to `v5.1.2`**. Each file is downloaded once into a
  cache (`WS_NE_CACHE`, defaulting to `~/.cache/weather-skills/naturalearth`).
  Its sha256 goes into the provenance parameters.
- Offline fallback: `countries` and `borders` at 110m fall back to the
  `countries.geojson` that core already ships. Other layers fail with a clear
  "no network and no cache" error.
- Features are clipped with shapely to `bbox` plus a 1° pad. **Without a
  `bbox`, the clip box defaults to the combined extent of all Zarr
  bindings.** This keeps the 10m files to kilobytes: the Kenya example binds
  15 lake features, 7 coastline features and 15 border features. Rings are
  re-oriented to clockwise for d3 (see
  [Gotchas](#gotchas-found-while-prototyping)). `properties` are reduced to
  `name` unless `"properties": [...]` asks for more.

### `geojson`: agent-supplied vectors

`{"geojson": "region"}` loads the input `-i region=/tmp/kenya.geojson`. It
accepts `bbox`, which has the same default, and applies the same clipping and
orientation as `naturalearth`.

## Defaults

The skill fills in a small set of things when the agent leaves them out.
Everything else is Vega-Lite's own default. A default only applies where
nothing is set. If the agent writes the key, the agent's value is used
unchanged.

| What | When the skill fills it | What it fills in |
| --- | --- | --- |
| **Colour scale** on `color`, `fill` or `stroke` | The field is a bound variable and is `quantitative`. The scale sets none of `type`, `scheme`, `range`, `domain`, `domainMid`, `domainMin` or `domainMax`. | Dev's automatic choice, `named_precip_scale`. Precip totals get the `ppt_daily`/`week`/`month`/`season` window from `aggregation_period`. Precip anomalies get the matching `ppt_anom_*` window. SPI and percent of normal get their palettes. It is emitted as a Vega-Lite `threshold` scale (domain = class edges, range = under + classes + over). Other variables keep Vega's default. Keys like `clamp` or `reverse` merge onto the default. |
| **Palette name as scheme** | `scale.scheme` is one of our names, on any quantitative colour field | The same threshold scale for that palette. `default_precip` and `default_precip_anom` still pick the window from the field's `aggregation_period`. |
| **Classed legend** | Any legend for a `threshold` colour scale, whether from defaults or written by the agent | One equal-size square per class, labelled with its range (`5 – 10`, `≥ 200`). Vega-Lite would draw a gradient sized by value, where the 0–1 and 1–2 mm classes are slivers, and it ignores `legend.type` for threshold scales. The patch works on the compiled Vega legend. The under entry (`< 0`) is shown only if some plotted value falls below the first edge. Legend placement keys the agent sets (`orient`, `direction`, `columns`, ...) are kept. |
| **Title** on `x`, `y`, `color`, `fill`, `stroke`, `size`, `opacity`, `theta` or `radius` | The field is a bound variable and `title` is not set. `"title": null` counts as set. | `long_name [units]`, with core's display units (`2 metre temperature [°C]`). Within one `layer` group, only the first layer that has a title for a channel keeps it, because Vega-Lite joins differing layer titles with commas. |
| **Map window** (`projection.fit`) | A `projection` sets none of `fit`, `scale` or `translate` | The combined extent of the Zarr bindings drawn under that projection, as a two-corner `MultiPoint` (see [Gotchas](#gotchas-found-while-prototyping)). |
| **Base-map clip box** | A `naturalearth` or `geojson` binding has no `bbox` | The combined extent of all Zarr bindings. |
| **Cell seams** | Always, unless `usermeta.seal_cells: false` | Scale-filled `rect` marks with no stroke get `stroke = fill` with width 0.5. |

"Bound variable" means the encoding's field is a column whose source is a
data variable of the input, and no transform in scope has created or
overwritten that column. A value computed in the spec has no units or
attributes to go on. Examples are wind speed from `u` and `v`, an
`aggregate` output, or a `quantile` output. Those fields keep Vega-Lite's
defaults, and the agent sets the scale or title.

**Seeing and overriding defaults.** Each default is printed with its JSON
path:

```text
default datasets.borders.bbox <- extent of the bound data [5.0, 33.5, -5.0, 42.0]
default spec.projection.fit <- extent of the bound data [5.0, 33.5, -5.0, 42.0]
default spec.layer[0].encoding.color.title <- 'Total precipitation [mm]'
default spec.layer[0].encoding.color.scale <- ppt_week (default for this variable; 13 classes)
default spec.layer[4].encoding.color.scale <- ppt_week (default for this variable; 13 classes)
```

`--dump-spec` writes these out as explicit values. To change one, set that
key in the spec. To switch them off:

- `usermeta.defaults: false` turns off all of them except `seal_cells`;
- `usermeta.classed_legend: false` turns off only the legend patch;
- `usermeta.seal_cells: false` turns off the seam patch.

Vega-Lite ignores `usermeta` by definition.

**Shared legends come for free.** In the heatmap example, the CHIRPS cells
and the station dots are both 7-day precip totals, so both get the same
`ppt_week` scale. Vega-Lite merges identical scales into one legend. If the
agent sets a scale on one layer only, the layers no longer match and a
second legend appears. The fix is to set the same scale on both.

For comparison, the same spec with `usermeta.defaults: false` (and a
hand-written `fit`) renders with Vega's continuous `yellowgreenblue` ramp, no
units in the legend title, and unclipped world-wide base layers:

![The heatmap spec with defaults switched off](img/defaults_off.png)

## Palettes

Every dev palette with class edges is a valid `scale.scheme` name:

- `default_precip` and `default_precip_anom`;
- the totals windows `ppt_daily`, `ppt_week`, `ppt_month` and `ppt_season`;
- the anomaly windows `ppt_anom_daily`, `ppt_anom_week`, `ppt_anom_month`
  and `ppt_anom_season`;
- `ppt_short`, `ppt_total`, `chirps_short` and `chirps_total`;
- `ppt_poa`, `ppt_spp` and `spi`.

The skill swaps the name for a threshold scale before validation, because
Vega-Lite's schema rejects scheme names it does not know. An unknown scheme
name gets its own error, which lists our names and points to Vega's schemes.

Continuous colour maps are Vega schemes (`"scheme": "viridis"`, `"magma"`,
`"blues"`, `"redblue"`, `"brownbluegreen"`, ...). For a diverging map
centred on zero, Vega-Lite's own `"domainMid": 0` does the job. The old
`viridis` and `rocket` theme entries are therefore not palettes any more.

A fully custom class palette is plain Vega-Lite:
`{"type": "threshold", "domain": [edges], "range": [under, ...classes, over]}`.
It still gets the classed legend.

## Output, provenance and QA

- The skill function returns the output `Path`. `@weather_skill` stamps it
  through core's `stamp_figure`, which works the same as today. PNG and JPEG
  get embedded history plus the circular mark when the provenance chain is
  intact. HTML gets a `<meta name="weather_skills_history">` tag and no mark.
- Provenance parameters record the **agent's spec before binding**, the
  input names and paths, and the hashes of any GeoJSON inputs and Natural
  Earth files. Defaults are deterministic given the spec and the inputs, so they
  are not recorded separately. The bound rows are not recorded either: they
  are just the inputs again, and they would make the record megabytes long.
- The stdout QA lines from `qa.py` are kept. `plot hash` is the sha256 of
  the RGB pixels. `data status` reports finite and NaN counts for each
  plotted variable, computed from the bound DataArrays rather than whole
  inputs, so a `sel` that picks an all-NaN slice is flagged.
- Each binding's row count also goes to stdout, for example
  `bound obs: 34000 rows (lon, lon2, lat, lat2, precip)`, followed by the
  `default ...` lines. The agent can then catch an empty `sel` or an
  unexpected palette before looking at the image.

## Validation and error messages

Several checks run in order, and the first failure stops the render:

1. **Binding errors** (`SpecError`) name the dataset and key, for example
   `datasets.obs: dims {'number': 11} are not columns in fields and have
   more than one value. Add each one to fields, pick one value with
   sel/isel, or reduce it upstream (reduce, aggregate-temporal). Nothing is
   averaged for you.`
2. **Scheme names.** A `scale.scheme` that is neither one of our palettes
   nor a Vega scheme fails, and the message lists both sets.
3. **Field lint.** Every `encoding.*.field` must be a column of the dataset
   the unit draws from, or a name produced by a transform (`as`, aggregate,
   window, joinaggregate, lookup, fold, quantile). Pivots switch the check
   off for that subtree. Vega-Lite itself draws nothing for an unknown field
   and raises no error. This check catches the most common silent failure.
4. **Schema validation** runs through Altair on a copy that keeps only 3
   rows per dataset, because full-data validation is slow. Altair's
   messages for unknown keys are excellent:

   ```text
   `HConcatChart` has no parameter named 'projection'

   Existing parameter names are:
   hconcat      center     description   params    title
   autosize     config     name          resolve   transform
   ...
   ```

   For bad values, `from_dict(validate=False)` misdispatches. For example,
   `"mark": "lines"` surfaces as `'RepeatChart' requires a spec`. The skill
   therefore also runs `jsonschema.best_match` against the Vega-Lite schema
   and prints the path:
   `spec.encoding.color.scale.type: 'thresh' is not one of ['linear', 'log', ..., 'threshold', ...]`.
5. **Compiler warnings** from vl-convert are passed through to stderr. An
   example is a dropped encoding with an incompatible type.

## Gotchas found while prototyping

These go into the SKILL.md "maps" reference, because an agent will hit each
one when writing those keys itself.

| Symptom | Cause | What the skill does or recommends |
| --- | --- | --- |
| A hand-written `projection.fit` shows the whole world | d3-geo treats a counter-clockwise polygon as "everything except this box" | The default fit is a `MultiPoint` of two corners, which has no winding. A hand-written fit should be one too (see [Recipes](#recipes)). Bound polygons are re-oriented to clockwise. |
| Stations, labels or outlines spill past the map edge | Marks are not clipped to the view by default | Every map layer sets `"clip": true`, in all recipes. |
| Hairline white seams between grid cells | Antialiasing on abutting rects | `seal_cells`, a post-compile Vega patch: scale-filled `rect` marks that have no stroke get `stroke = fill` with width 0.5. It works regardless of scale names and leaves legends alone. |
| Stations get a second legend | The two layers' colour scales differ | Defaults give matching variables identical scales, which Vega-Lite merges. If one layer sets a scale, set the same one on the other. `resolve: shared` alone did not merge differing scales. |
| `projection` on `hconcat` fails validation | A concat parent cannot own a projection | Put a `projection` on each panel. The default fit is computed per panel. |
| Side-by-side panels show different windows | Each panel fits its own data, and the forecast grid is larger than the observation grid | Crop with the same `bbox` on both bindings, as in the side-by-side recipe. |
| Quiver colour and arrow legends merge into one | Vega-Lite merges legends when scale domains are identical (speed 0–12 on both) | Add `"resolve": {"legend": {"color": "independent", "size": "independent"}}`. |
| Base layers extend past the data edge | The view's aspect differs from the data's, so the fitted view is wider than the data | Size the view to the data's aspect ratio. Planned: `usermeta.fit_aspect` derives `height` from `width`. |
| `lookup` between two time series matches nothing | ISO strings are parsed only on temporal-encoded datasets | Bind datetimes as epoch milliseconds. |
| Spaghetti legend symbols are faded | The legend takes `opacity` from the first layer (members at 0.35) | `config.legend.symbolOpacity: 1`, and `symbolType: "stroke"` for line legends. |
| A layered axis title reads "A, B" | Vega-Lite joins differing titles from layers that share an axis | Default titles go only on the first layer. A hand-written title on one layer and none on the others is fine. |

## Recipes

Each recipe is an [`examples/*.json`](examples/) spec that was rendered by the
prototype. The run commands are in
[`prototypes/run_examples.py`](prototypes/run_examples.py). In the skill they
ship as `skills/plot/recipes/*.json`, and `references/recipes.md` shows each
one with its `-i` names and picture. Every recipe leans on the defaults:
none of them sets a precip colour scale, a variable title or a map window.

### Heatmap over base map with station dots

[`examples/map_heatmap_stations.json`](examples/map_heatmap_stations.json),
with `-i obs=chirps_week.zarr -i stations=stations_week.zarr`. The picture is
at the top of this document. The layers are a CHIRPS 0.05° `rect` grid, 10m
lakes, coastline and borders, station circles, and text labels. The station
layer is just:

```json
{"data": {"name": "stations"},
 "mark": {"type": "circle", "size": 140, "stroke": "black", "strokeWidth": 1.2, "opacity": 1, "clip": true},
 "encoding": {"longitude": {"field": "lon", "type": "quantitative"},
              "latitude":  {"field": "lat", "type": "quantitative"},
              "color": {"field": "precip", "type": "quantitative"}}}
```

To pin the map window instead of fitting it to the data, crop the bindings
with `bbox`, or write the fit:

```json
"projection": {"type": "equirectangular",
               "fit": {"type": "Feature", "properties": {},
                       "geometry": {"type": "MultiPoint", "coordinates": [[33.5, -5], [42, 5]]}}}
```

### Lead-week facet

[`examples/map_forecast_leads_facet.json`](examples/map_forecast_leads_facet.json).
This is a `facet` over the `step` column (`"Week " + lead_days / 7`) with
`columns: 4`. The base layers bring their own data and repeat in every panel.
The classed legend sits underneath through ordinary legend keys:
`{"orient": "bottom", "direction": "horizontal", "columns": 8}`.

![Facet](img/map_forecast_leads_facet.png)

### Side-by-side grids at native resolution

[`examples/map_side_by_side_grids.json`](examples/map_side_by_side_grids.json).
CHIRPS at 0.05° is next to ECMWF at 0.25°, with one binding per input and a
`projection` on each panel. Neither is regridded. The forecast binding has
the same `bbox` as the observation grid, so both panels get the same window.
Both are 7-day totals, so both get `ppt_week`, and
`"resolve": {"scale": {"color": "shared"}}` draws one legend. This replaces
dev's `subplots[]`.

![Side by side](img/map_side_by_side_grids.png)

### Anomaly maps: classed and continuous diverging

[`examples/map_anomaly_diverging.json`](examples/map_anomaly_diverging.json).
The left panel uses the default: the variable is a precip anomaly, so it gets
`ppt_anom_week` and a classed legend in four columns. The right panel sets
`"scale": {"scheme": "brownbluegreen", "domainMid": 0}`, which centres white
at zero. `resolve.scale.color: independent` keeps the two panels apart.

![Anomaly](img/map_anomaly_diverging.png)

### Quiver (wind arrows over speed)

[`examples/map_quiver_wind.json`](examples/map_quiver_wind.json). Speed is
drawn as `rect` cells, and the arrows come from a second binding of the same
input, thinned with `isel` step 3. Speed is computed in the spec, so it has
no attributes, and the recipe sets its scale and title itself. An arrow is a
`point` mark with an SVG path `shape` that points up. It is turned by
`angle = atan2(u, v) * 180 / PI` with `"scale": null`, and its length is
linear in speed through a `pow` size scale with exponent 2, because `size`
is an area. The legend reuses the arrow path as its `symbolType`.

```json
"transform": [{"calculate": "sqrt(datum.u*datum.u + datum.v*datum.v)", "as": "arrow_speed"},
              {"calculate": "atan2(datum.u, datum.v) * 180 / PI", "as": "toward"}],
"mark": {"type": "point", "shape": "M0,1 L0,-1 M-0.4,-0.45 L0,-1 L0.4,-0.45",
         "filled": false, "stroke": "black", "strokeWidth": 1.3, "opacity": 1, "clip": true},
"encoding": {"angle": {"field": "toward", "type": "quantitative", "scale": null},
             "size": {"field": "arrow_speed", "type": "quantitative",
                      "scale": {"type": "pow", "exponent": 2, "domain": [0, 12], "range": [0, 1296]}}}
```

![Quiver](img/map_quiver_wind.png)

### Filled contours with isolines

[`examples/map_contours.json`](examples/map_contours.json). This recipe uses
the `contours` binding. The bands are coloured by `properties.mid`, which
gets the precip default like the variable itself.

![Contours](img/map_contours.png)

### Ensemble spaghetti with band, mean and climatology

[`examples/timeseries_ensemble_spaghetti.json`](examples/timeseries_ensemble_spaghetti.json).
There are four layers on one `ens` binding (`valid_time`, `number`, `t2m`),
plus a `clim` binding:

- members are thin lines, with `detail` set to member;
- the 10–90% band is `quantile`, then `calculate`, then `pivot`, drawn with
  `area` + `y2`;
- the mean is an `aggregate` line;
- climatology is dashed.

A `{"datum": "..."}` colour on each layer builds one legend, and
`config.range.category` fixes the colours. The y title is the default from
the members layer.

![Spaghetti](img/timeseries_ensemble_spaghetti.png)

### Multi-panel time series

[`examples/timeseries_multi_panel.json`](examples/timeseries_multi_panel.json).
This is a `vconcat` of members and mean above ensemble-mean anomaly bars. The
anomaly is a `lookup` join against the climatology binding, which only works
with epoch-millisecond times. The bars are coloured with a sign condition.

![Multi-panel](img/timeseries_multi_panel.png)

### Grouped bars for comparison

[`examples/bar_model_comparison.json`](examples/bar_model_comparison.json).
Grouping uses `xOffset` by model, with value labels as a text layer on the
same encoding. The input is a score Zarr with `model × lead` dims.

![Bars](img/bar_model_comparison.png)

### Box or mediogram by lead week

[`examples/box_mediogram.json`](examples/box_mediogram.json). Weekly means
come from `aggregate`, percentiles from `quantile` and `pivot`, and the
figure is drawn with `bar` (25–75%), `rule` (10–90%), `tick` (median) and a
climatology dot. The plotted values are computed in the spec, so the recipe
writes its own y title. This replaces `plot-mediogram`.

![Box](img/box_mediogram.png)

### Wind rose

[`examples/windrose.json`](examples/windrose.json). An `arc` mark uses
`theta`/`theta2` in radians with `scale: null`. The stacked radius comes from
a `window` sum by direction sector, and speed classes come from `calculate`.
Known gap: Vega-Lite has no polar axis, so the radial rings (percent of
time) are missing. The planned fix is a recipe layer of `arc` rings with
`text` labels.

![Wind rose](img/windrose.png)

### Recipes still to write before the old skills go

- **Verification grid**, replacing `plot-verify`. Observations sit in the
  first column and forecasts for weeks 1 to 4 to their right (an `hconcat`
  of per-panel projections, or a `facet` when the grids match). The metric
  row is categorical hits, misses and false alarms. That row needs the
  planned `<var>.flag` derived source, which would also give a categorical
  colour default from `flag_values` and `flag_meanings`.
- **Station time series facet**: `facet` by `station_name` on a
  `station_id × time` Zarr.
- **Scatter with 1:1 line**, forecast against observation.
- **Region outline**: an `-i region=....geojson` input from `resolve-region`,
  bound with `{"geojson": "region"}`.

## Performance and limits

All rows are serialised into the spec as JSON, so the cost scales with the
number of rows. The prototype measured a rect heatmap with base layers
([`prototypes/proto_perf.py`](prototypes/proto_perf.py)):

| Cells | Render | Peak RSS | Spec JSON |
| --- | --- | --- | --- |
| 40k | 2.0 s | 0.49 GB | 4.5 MB |
| 102k | 4.1 s | 0.89 GB | 11.4 MB |
| 202k | 8.2 s | 1.57 GB | 22.6 MB |
| 397k | 15.2 s | 2.77 GB | 44 MB |

That is roughly 25k cells per second and 7 KB of RAM per cell. All eleven
recipes render in about 17 s in total, including interpreter start-up. The
largest, with 34k CHIRPS cells, takes 2 s. The defaults step is negligible:
it reads attributes and one `min()` per coloured variable.

Proposed guard: total bound rows above **150k print a warning**, with
suggestions to `bbox`, `coarsen` upstream or `isel` step. Above **500k the
render fails** unless `--max-rows` is raised. A future fallback for big grids
would be a `raster` binding that renders the field to an image and places it
with an `image` mark. That only works for unprojected or equirectangular
views, so it stays out of scope until someone needs it.

## Package layout and dependencies

```text
src/weather_skills_plotting/
  __init__.py       render(spec, inputs, output, *, scale=2) and the stage functions
  bind.py           zarr / contours / geojson / naturalearth bindings, cell edges, time encoding, extents
  naturalearth.py   pinned download + cache, clip, d3 orientation, offline fallback
  defaults.py       colour scale, palette schemes, titles, projection fit, base-map clip; the defaults log
  palettes.py       dev theme.py colour tables + named_precip_scale detection (no seaborn, no matplotlib)
  validate.py       dispatch, stub-row Altair validation, jsonschema best_match, field lint
  vega.py           vegalite_to_vega, seal_cells, classed_legends, vega_to_png / HTML
  qa.py             unchanged
skills/plot/
  SKILL.md
  scripts/plot.py   CLI, @weather_skill, named-input holder, --describe / --dump-spec
  recipes/*.json    the examples above
  references/       bindings.md, defaults.md, recipes.md (with images), maps.md (gotchas)
```

Dependencies:

- **Removed**: `matplotlib`, `seaborn`, `cartopy` and `nc-time-axis`.
- **Added**:
  - `altair>=6.3` (Vega-Lite 6.4 schema);
  - `vl-convert-python>=1.9`, pinned exactly, because a renderer bump can
    move pixels;
  - `contourpy>=1.3`;
  - `pandas`.
- **Kept**: `shapely`, `xarray`, `zarr`, `numpy`, `cf-xarray`, `pint-xarray`,
  `cftime` and core. `pillow` stays for `qa.py`.

vl-convert ships wheels with an embedded Deno runtime for Linux, macOS and
Windows, so no browser or Node is needed. It bundles Vega-Lite 5.21, 6.1 and
6.4, and the skill pins `vl_version="6.4"`.

**Fonts.** vl-convert renders text with the system fonts it finds, which
makes text pixels differ between machines. The skill should bundle one
open font, such as Liberation Sans or Inter, and call
`vl_convert.register_font_directory` on it. `config.font` would then be set
only when the spec leaves it unset, which makes it one more fill-the-gap
default. It is what makes `plot hash` reproducible across CI and laptops.

## Testing plan

- **Unit tests**:
  - cell edges on ascending and descending, uneven and length-1 coords;
  - `sel`/`isel` forms;
  - the leftover-dim error;
  - `valid_time`, epoch milliseconds and timedelta days;
  - extents (edges compared with points);
  - Natural Earth clipping and orientation (the winding test that caught the
    world-fit bug);
  - dispatch for every top-level key;
  - the field lint cases (transforms, inline data, pivot);
  - `seal_cells` touching only scale-filled rects.
- **Defaults tests**, each a small spec checked against its `--dump-spec`
  output and log:
  - each palette detection case (total by window, anomaly, SPI, percent of
    normal, a non-precip variable left alone);
  - every key in `SCALE_CHOICE_KEYS` suppressing the default;
  - merge keys such as `clamp`;
  - every palette name as `scheme`;
  - an unknown scheme name;
  - titles: the single-owner rule in layers, `null` respected, computed
    fields skipped;
  - the fit default per panel, in facets, and suppressed by `fit`/`scale`;
  - the base-map `bbox` default;
  - the `classed_legends` under-entry rule;
  - the `usermeta` switches.
- **Recipe tests**: render every `recipes/*.json` against small synthetic
  Zarrs (the prototype's `make_data.py` moves to `tests/`). Each test checks
  that the PNG exists, has the expected size and is not blank, and that the
  stdout row counts and the default lines match. Pixel-hash golden files are
  only used with the bundled font and a pinned vl-convert.
- **Error tests**: each documented error message, so the wording an agent
  relies on does not drift.
- **CI**: the existing ruff, inline-deps, pytest and `--help` jobs. Natural
  Earth tests use a checked-in clipped fixture, so CI needs no network.

## Implementation phases

1. **Library.** Move the bindings, defaults, palettes, validation and Vega
   stages from `prototypes/vlbind.py` into the package layout above, and add
   unit and defaults tests. Drop matplotlib-backed modules from
   `weather_skills_plotting`.
2. **Skill CLI.** Add `plot.py` with `-i NAME=PATH` (Zarr or GeoJSON), `--spec`,
   `--describe`, `--dump-spec`, `-o png/jpg/html`, the `@weather_skill`
   integration, the row guard, the defaults log and the QA lines.
3. **Recipes and docs.** Add the recipes, `SKILL.md`, the `references/*.md`
   files with images, recipe tests in CI and a bundled font.
4. **Migration.**
   - Delete `plot-timeseries`, `plot-verify` and `plot-mediogram`.
   - Rewrite `agents/plotting.md` around one skill and the recipes.
   - Update the `.claude-plugin` descriptions and keywords (matplotlib and
     cartopy become vega-lite and altair).
   - Replace `docs/plotting.md` with the references.
   - Remove dev's spec tests.
5. **Gaps.**
   - The `<var>.flag` source, its categorical colour default, and the
     verification-grid recipe.
   - Wind rose rings.
   - `usermeta.fit_aspect`.
   - Optional `units` conversion in bindings (for example K to °C through
     pint), which today is an upstream transform.

## Proposed SKILL.md structure

```text
---
name: plot
description: Render any figure from weather-skills Zarrs with a plain Vega-Lite spec: maps (grid heatmaps, contours,
  quiver, station dots over Natural Earth borders), time series (ensemble spaghetti, bands, anomalies), bars, boxes,
  wind roses, facets and side-by-side panels. Name inputs with -i NAME=PATH and bind them under the spec's top-level
  "datasets"; precip palettes, units in titles and the map window are filled in when left out. Start from a recipe. ...
---
# plot
1. The contract in 10 lines (inputs → datasets bindings → {"data": {"name"}} → PNG)
2. Workflow: --describe → copy a recipe → edit → render → read the default lines → look at the PNG
   → --dump-spec to see every default as an explicit value
3. Bindings (short table; full reference in references/bindings.md)
4. Defaults: what is filled in, when, and how to override or switch it off (references/defaults.md)
5. Palettes: our scheme names; Vega schemes and domainMid for continuous scales
6. Recipe index: one line + thumbnail per recipe, linking recipes/*.json and references/recipes.md
7. Maps: the rules (clip: true on every layer, one projection per panel, set the window with a binding bbox,
   resolve legends for quiver) → references/maps.md
8. Errors you will see and what they mean
9. Output, provenance, QA lines, limits
```

The `SKILL.md` stays short and front-loads the contract and the recipe
index, following the Agent Skills progressive-disclosure pattern. The long
references load only when needed.

## Open decisions for review

1. **Where bindings live.** The proposal is inside `datasets` (one
   document). The alternative is a separate `--bind` JSON with a pure
   Vega-Lite `--spec`.
2. **Skill name.** Should the new skill reuse `plot`, so the agents and
   plugin keep their names, or use a new name such as `plot-vega` with the
   old skills deleted in the same PR?
3. **Which defaults.** The proposal is the seven in the defaults table, all
   on by default, with `usermeta.defaults: false` to turn them off. Things
   to decide:
   - Should the base-map clip and the map window default be kept? They are
     the least "colour-bar-like" of the seven.
   - Should anything else join the list, such as a default `config.font`?
4. **Under-entry rule in classed legends.** The proposal shows `< first
   edge` only when the data goes below it. The alternatives are to always
   show it, or never.
5. **Palette names as `scheme`.** This is non-standard Vega-Lite, which
   only knows its own scheme names, so the skill rewrites them. The
   alternative is a separate key, such as `usermeta.palette` per encoding.
   That would keep the spec strictly valid, but it is less discoverable.
6. **Datetime encoding.** The proposal is epoch milliseconds, which is
   robust for joins. ISO strings are easier to read in `--dump-spec`. A
   middle ground is epoch milliseconds in the render and ISO strings in
   `--dump-spec-rows` output.
7. **Row limits.** The proposal is a warning at 150k and an error at 500k.
8. **Contours in the skill.** The proposal includes contourpy, which is
   small and numpy-only. The alternative is a separate `contour` transform
   skill that writes GeoJSON.
9. **Natural Earth delivery.** The proposal is a pinned download with a
   cache and a 110m offline fallback. The alternative is to vendor the 10m
   and 50m files, which is too big for the plugin: the 10m coastline alone
   is 10 MB and 10m lakes is 5 MB.
10. **A bundled font**, for reproducible hashes.

## Running the prototype

```bash
cd docs/design/vegalite/prototypes
uv run make_data.py        # synthetic Zarrs → data/ (git-ignored)
uv run run_examples.py     # every ../examples/*.json → out/ (git-ignored), with the default lines
uv run run_examples.py map_quiver_wind   # just one
```

The other `proto_*.py` scripts are the A/B experiments behind the gotchas
table:

- seams (`proto_ab.py`, `proto_seams.py`);
- projection fit and winding (`proto_debug.py`);
- legend merging (`proto_legend_merge.py`);
- error messages (`proto_errors.py`);
- scaling (`proto_perf.py`).

## References

- Vega-Lite: [projection and fit](https://vega.github.io/vega-lite/docs/projection.html),
  [geoshape](https://vega.github.io/vega-lite/docs/geoshape.html),
  [named datasets](https://vega.github.io/vega-lite/docs/data.html#datasets),
  [threshold scales and `domainMid`](https://vega.github.io/vega-lite/docs/scale.html),
  [legends](https://vega.github.io/vega-lite/docs/legend.html),
  [resolve](https://vega.github.io/vega-lite/docs/resolve.html),
  [top-level spec and `usermeta`](https://vega.github.io/vega-lite/docs/spec.html)
- [Vega legends](https://vega.github.io/vega/docs/legends/) (`type: symbol` on the compiled legend)
- [Altair](https://altair-viz.github.io/) (6.x, Vega-Lite 6 schema)
- [vl-convert](https://github.com/vega/vl-convert) (Deno + resvg renderer, font registration)
- [d3-geo](https://github.com/d3/d3-geo) (spherical polygon winding: clockwise exterior rings)
- [natural-earth-vector](https://github.com/nvkelso/natural-earth-vector) (`v5.1.2` GeoJSON)
- [contourpy](https://contourpy.readthedocs.io/)
