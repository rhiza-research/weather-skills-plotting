---
name: plot-mediogram
description: Render an ECMWF-style mediogram comparing a forecast ensemble against an m-climate ensemble at one point, as PNG or interactive HTML. Pass the forecast Zarr then the m-climate Zarr with -i. Set the point in --spec as layout.meta.geo.point {lat, lon}; the spec is a standard Plotly figure (traces forecast, mclimate, forecast-mean). Grouped box plots per step (forecast cyan, m-climate red) plus the forecast mean line. For precipitation, run convert-to-totals after aggregate-temporal before plotting.
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot-mediogram

Grouped box plots per forecast step: forecast members in cyan and m-climate members in red, plus a black forecast-mean line, at the grid cell nearest one point. The first 6 common steps are drawn, labelled by lead (`+7d`, `+10d`, …).

`--spec` is a **standard Plotly figure** merged onto the one the command builds. That figure has three traces:

| uid | Plotly type | What |
| --- | --- | --- |
| `forecast` | `box` | every forecast member per step |
| `mclimate` | `box` | every m-climate member per step |
| `forecast-mean` | `scatter` | forecast ensemble mean per step |

Restyle them with Plotly keys, e.g. `{"data": [{"uid": "mclimate", "fillcolor": "orange"}]}`. To choose steps, set `meta.source.isel` on all three, e.g. `{"step": [0, 2, 4, 6]}`. If the two archives name the field differently, set each trace's `meta.source.variable`.

## Input schema

Both inputs need `number` (members) and `step` (lead) dims, plus latitude/longitude. Selection is nearest-neighbour.

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py -i <forecast.zarr> -i <mclimate.zarr> -o <out.png|.html> \
    --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}'
```

- `-i` — exactly twice: forecast first (input id `forecast`), then m-climate (`mclimate`).
- `--spec` — must set `layout.meta.geo.point`. Titles, axes and size are plain Plotly `layout` keys.
- `--dump-spec [PATH]` — print or write the merged spec and skip drawing.

## Example

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_mediogram.py -i /tmp/ecmwf_forecast.zarr -i /tmp/ecmwf_mclimate.zarr \
    -o /tmp/mediogram_nairobi.png \
    --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}, "title": {"text": "Nairobi"}}}'
```

## Output

A 1000×520 px figure (2× pixels in PNG). The default title names the variable and the snapped grid point. The legend sits below the boxes. PNG/JPG print a pixel `plot hash` and `data: not null` / `NULL`. Look at the image; a hash only shows that pixels changed. Provenance is embedded in the PNG metadata or the HTML `<meta>` tag.
