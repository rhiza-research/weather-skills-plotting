# Plotting skills

How the figure stack works. The agent how-to is the skill's
[`SKILL.md`](../skills/plot/SKILL.md); runnable examples are in
[`skills/plot/recipes/`](../skills/plot/recipes/). This page is the design.

## The spec is Jsonnet that evaluates to a Plotly figure

The agent writes Jsonnet whose value is a standard Plotly figure,
`{"data": [...], "layout": {...}, "frames": [...]}`
(<https://plotly.com/python/reference/>). Jsonnet adds variables, functions,
loops and imports to JSON, so a 50-member plume or a 4 × 5 grid of maps is a
few lines, and long strings (selections, color tables) are written once.

Where Plotly expects data, the spec holds a **reference**: a string that starts
with `@` and names an input, `'@OBS.precip.isel(time=0)'`. Inputs are named on
the command line, `-i rain.zarr=OBS`. There is no other binding: no `meta`
keys, no inferred plot types, no layers or modes. What the spec says is what
Plotly draws.

```mermaid
flowchart LR
  Inputs["-i PATH=NAME"] --> Meta["metadata → std.extVar('inputs')"]
  Spec["--spec (Jsonnet)"] --> Eval[gojsonnet]
  Meta --> Eval
  Lib["lib/ws.libsonnet"] --> Eval
  Eval --> Dump["--dump-spec"]
  Eval --> Check["check references and literal arrays"]
  Check --> Resolve["resolve @ strings from the Zarrs"]
  Resolve --> Validate["go.Figure: Plotly's own validation"]
  Validate --> Out["PNG / JPG / PDF / SVG / GIF (kaleido) or HTML"]
```

## Metadata in Jsonnet, values in references

`std.extVar('inputs')` gives each input's dims, variables (dims, units,
long_name), small 1-D coordinates, attributes and bbox, all read from Zarr
metadata without loading data. The spec uses it for loop bounds, titles and
map windows. Anything that needs data values (arrays, a maximum for `zmax`)
is a reference, resolved after evaluation. Jsonnet never sees values.

## References select, they don't compute

`refs.py` parses each reference with `ast.parse(mode="eval")` and walks it
against a fixed table; nothing is `eval`'d. Each method has one job:

| Job | Methods |
| --- | --- |
| Select | `isel`, `sel` (with `method="nearest"`), `slice()`, `NE…clip(n, w, s, e)` |
| Reshape | `squeeze`, `transpose`, `flat` (a grid as one value per cell) |
| Label | `.dt.<part>`, `.dt.strftime`, `.attrs.<name>` |
| Display limit | `min`, `max`, `quantile`: whole array only, and only in `zmin`, `zmax`, `zmid`, `cmin`, `cmax`, `cmid`, an axis `range` or `tickvals` |

So every value drawn is a value stored in an input. Arithmetic, averages,
smoothing, regridding and masking are refused with the data skill that does
the job (`summarize-dim`, `aggregate-temporal`, `unit-convert`, `difference`,
`coarsen` / `downscale`, `clip-region`). A trace may hold up to 10 typed-in
numbers; longer literal arrays must come from an input. The recipe tests
check the invariant: each recipe's resolved arrays hold only values stored in
its inputs.

Shape rules are the only other logic: `z` must be 2-D (a lat/lon grid is
written with rows as latitudes), `customdata` 1-D or 2-D, everything else one
value or 1-D. A leftover dim is an error naming it.

## `ws.libsonnet`: conveniences in Jsonnet, not Python

Defaults that used to be Python (map axes, panel grids, base map, palettes,
animation controls) are Jsonnet functions that return plain Plotly JSON. The
agent can read them and override any part with `+`.

- **Map axes.** Equal-degree lon/lat axes (`scaleanchor`), not Plotly geo
  subplots, which cannot hold a heatmap. `ws.map` sizes the canvas from the
  bbox aspect; `ws.grid` lays out panels row by row with tick labels on the
  outer edge.
- **Base map.** `ws.basemap` returns line traces whose `x` / `y` reference the
  built-in `NE` input (Natural Earth via cartopy, clipped to the bbox, scale
  from the map span). If borders or coastline can't be fetched, the country
  outlines bundled with core stand in.
- **Palettes.** `ws.palettes` holds the CHC class palettes and the verify
  palettes as `{colors, bounds}` (and `labels` where classes have names).
  `ws.stepped` turns one into a coloraxis whose colors step at the bounds, so
  the map colors are exact without changing the data. Plotly's colorbar is
  linear in value, which would make the 0–1–2 mm classes slivers, so
  `ws.classBar` hides it and draws its own from layout shapes and annotations:
  one equal-height band per class, labelled at the bounds, with under / over
  triangles.
- **Animation.** Standard Plotly `frames`; `ws.player` adds play / pause and a
  slider. A `.gif` output draws each frame with kaleido and joins them on one
  shared palette, at the play button's frame duration.

## Output

The `-o` suffix picks the format. Images print a `plot hash` and a
`data: not null | NULL` line over the plotted traces (base-map lines and other
`hoverinfo: "skip"` traces are left out). Provenance is embedded in the file,
with the evaluated spec as the `spec` argument: it replays with `--spec` and
the same `-i` inputs.
