---
name: plot-timeseries
description: Overlay one series per input Zarr on a shared time axis, as lines or bars, to PNG or interactive HTML. Name files with repeatable -i. The --spec is a standard Plotly figure JSON; each input is a trace with uid a, b, … whose meta.source.reduce averages leftover dims and meta.along fans one out (number for ensemble spaghetti, with meta.band for a percentile band). Settings on the first trace apply to the rest. Nothing is averaged silently. --dump-spec prints the merged spec. For precipitation, run aggregate-temporal then convert-to-totals first.
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py *)
metadata:
  version: "0.0.2"
  catalog-group: figure
---

# plot-timeseries

Each `-i` becomes one trace on a shared time axis: uid `a`, `b`, … in order, named after the file (or the station id). `--spec` is a **standard Plotly figure** merged onto that, with traces matched by `uid`. Everything except `meta` is plain Plotly: `type: "bar"`, `line`, `marker`, `layout.barmode`, `layout.yaxis2`, `layout.grid`. The `-o` suffix picks `.png`, `.jpg`, or `.html`.

**Settings on `data[0]` apply to every series that leaves them unset:** `meta.source.variable`, `meta.source.reduce`, `meta.along`, `meta.along_color`, `meta.band`, `meta.align`. Set them once on trace `a`.

## Dimensions

A series keeps one time axis, either `time` or a forecast `step`. A forecast is plotted against valid time (`init + step`). Every other dim must be:

- **averaged:** `meta.source.reduce: ["latitude", "longitude"]`
- **selected:** `meta.source.isel: {"number": 0}`, or `meta.source.sel: {"latitude": -1.3}` (nearest)
- **fanned out:** `meta.along: "number"`, one line per member. `along_color: "same"` gives one color and one legend entry; `"cycle"` gives each value its own color. `band: [10, 90]` shades the 10–90% range around the mean.

A leftover dim is an error that names the fix; nothing is averaged silently. For 101 ensemble members use `along` on one input, not 101 `-i` files (at most 26 inputs).

## Layout

| Goal | `--spec` |
| --- | --- |
| Bars for one series | `{"data": [{"uid": "a", "type": "bar"}]}` |
| Stacked or overlaid bars | `{"layout": {"barmode": "stack"}}` (`group` is the default, `overlay`) |
| Highlight a series | `{"data": [{"uid": "b", "line": {"color": "black", "width": 3, "dash": "dash"}}]}` |
| One panel per series (independent y) | `{"layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}` |
| Second y-axis | `{"data": [{"uid": "b", "yaxis": "y2"}], "layout": {"yaxis2": {"overlaying": "y", "side": "right"}}}` |
| Seasonal overlay of years | `{"data": [{"uid": "a", "meta": {"align": "dayofyear"}}]}` |
| Title, labels, size | `{"layout": {"title": {"text": "…"}, "yaxis": {"title": {"text": "mm"}}, "width": 1200, "font": {"size": 18}}}` |

`align: "dayofyear"` puts every year on one calendar (labelled `1 Oct`, `15 Nov`, …), so dates line up across leap and non-leap years; 29 Feb folds onto 28 Feb. A season that crosses New Year (e.g. DJF) splits at 1 Jan.

Series on one y-axis in different units print a warning and still render; give them separate panels or a second axis.

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i <a.zarr> [-i <b.zarr> …] -o <out.png|.html> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i <a.zarr> --dump-spec -
```

`--help` lists every `meta` key with recipes. `--theme-file` takes `{"template": <Plotly template>, "palettes": {…}}`.

## Examples

```bash
# CHIRPS and IMERG area means, one panel each
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i /tmp/chirps.zarr -i /tmp/imerg.zarr -o /tmp/precip.png \
    --spec '{"data": [{"uid": "a", "name": "CHIRPS", "meta": {"source": {"reduce": ["latitude", "longitude"]}}},
                      {"uid": "b", "name": "IMERG"}],
             "layout": {"grid": {"rows": 2, "columns": 1, "pattern": "coupled"}}}'

# Every ensemble member, interactive
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i /tmp/ens_diff.zarr -o /tmp/members.html \
    --spec '{"data": [{"uid": "a", "meta": {"along": "number", "source": {"reduce": ["latitude", "longitude"]}}}],
             "layout": {"title": {"text": "Ensemble difference traces"}}}'

# Observed bars with a dashed climatology line
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_timeseries.py -i /tmp/obs.zarr -i /tmp/clim.zarr -o /tmp/obs_vs_clim.png \
    --spec '{"data": [{"uid": "a", "type": "bar", "meta": {"source": {"reduce": ["latitude", "longitude"]}}},
                      {"uid": "b", "mode": "lines", "line": {"dash": "dash", "width": 2.5}}],
             "layout": {"title": {"text": "30-day precip vs climatology"}}}'
```

## Output

The figure at `--output`, 1000×600 px by default (2× pixels in PNG), legend below. The y-axis label is the variable's `long_name` plus short units. PNG/JPG print a pixel `plot hash` and `data: not null` / `NULL` (`NULL` means all-NaN input; run `inspect-zarr`). Look at the image rather than comparing hashes. Provenance is embedded in the PNG metadata or the HTML `<meta>` tag.
