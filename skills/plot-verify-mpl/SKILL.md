---
name: plot-verify-mpl
description: Matplotlib version of plot-verify; use plot-verify (Plotly) unless matplotlib is asked for or Chrome is not available for PNG export. Plot a lead-week verification grid for ONE fixed valid (obs) week, with one forecast init per lead (week-1 = the latest init, week-4 = the init 3 weeks earlier) so every column verifies the same obs week. Not for the weeks 1-4 of a single init — those verify different obs weeks (a warning is printed when inits repeat or are out of order). Columns are observation, then week-1 through week-4 forecasts; the metric row (hits, bias, or MAE from pre-computed verify Zarrs) sits under the forecasts. Every --obs and --forecast must already be a single time — run select on the verifying week first. Run verify on each forecast/obs pair before this skill. For precipitation, aggregate-temporal then convert-to-totals before verify. Pass --forecast week-1 first.
license: MIT
compatibility: Requires Python 3.12 and uv.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify_mpl.py *)
metadata:
  version: "0.0.3"
  catalog-group: figure
---

# plot-verify-mpl

Lead-week **verification figure** for **one observation (valid) week**:
each column is a different forecast init whose lead lands on that same week
(week-1 = latest init, e.g. inits 14 Sep, 7 Sep, 31 Aug, 24 Aug for weeks
1–4 of 14–20 Sep). The weeks 1–4 of a *single* init verify four different obs
weeks and do not fit this grid; a stderr warning fires when the forecasts'
`weather_skills_forecast_init` repeat or are not newest-first. This skill
**plots only** — it does not compute verification and it does not pick a
time. Run `select` so every cube is one verifying week, run `verify` on
each forecast/obs pair, then pass those Zarrs here.

## Before guessing a flag or a key

Every drawing choice besides `--obs`/`--forecast`/`--verify`/`--output` is a
JSON key under `--spec` (see **Parameters** below); an unknown or misplaced
key is a hard error listing every valid key at that level, not a silent
no-op. If you don't already know the shape of `--spec`, run `--help`: after
the flags it prints the plot spec reference (every section and key, with
recipes), rather than guessing keys one at a time. To modify a figure you
already drew, `--dump-spec -` with the same files prints its current spec to
edit and pass back. The `plot hash`
printed after a render only tells you the pixels changed,
never what changed or how it looks.

**`--obs` and each `--forecast` must have a single time (size 1).** If you
see `has time size N; select the verifying week`, run `select` first
(`--dim time --value <week start>`). A leftover `step` axis needs
`step-to-time` first.

Columns are **observation, then week-1 through week-4** (week-1 next to
obs). Pass `--forecast` week-1 first. Column titles are `traces[0].leads`
(default `N-week lead`, plus `init <date>` when the inputs carry
`weather_skills_forecast_init`).
If those titles include week numbers (e.g. `Week 4 (init …)`), columns are
sorted week-1 → week-4 even when you pass week-4 first. Label size is
`theme.fontsize` (default 16).

| | Obs | 1-week lead | 2-week lead | 3-week lead | 4-week lead |
| --- | --- | --- | --- | --- |
| forecast row | obs map | week-1 | week-2 | week-3 | week-4 |
| metric row | (empty) | verify | verify | verify | verify |

The metric row comes from `--verify` Zarrs. All `--verify` inputs must
share the same `verify_metric` (`hits`, `bias`, or `mae`). Regional
scores are read from each verify Zarr's `verify_score_summary` attr.

## Pipeline (one obs week)

1. Prepare obs and each lead's forecast: aggregate, `step-to-time` if
   needed, **`select` the verifying week**, coarsen obs onto the forecast
   grid. This figure plots those already-aligned fields. It does not draw
   a native-resolution observation next to a coarser forecast. `plot-mpl --layer`
   draws each dataset on its own grid.
2. For each lead, run `verify`.
3. Pass single-time obs, then forecasts week-1 … week-4, with matching
   `--verify` Zarrs.

## Usage

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify_mpl.py \
    --obs <obs.zarr> \
    --forecast <week1.zarr> --verify <verify_w1.zarr> \
    --forecast <week2.zarr> --verify <verify_w2.zarr> \
    -o <out.png> \
    --spec '{"inputs":[{"id":"obs","variable":"precip"}],"title":"Kenya weekly precip verification","geo":{"bbox":[5,34,-5,42]}}'
```

### Arguments

- `--obs` — observation Zarr for the verifying week. Must already be one time. Optional when `--spec` lists an obs input.
- `--forecast` — forecast Zarr for that same week at one lead. Pass **week-1 first**. Repeat with a matching `--verify`. Must already be one time.
- `--verify` — verify Zarr for that lead, once per `--forecast`, same order.
- `--output`, `-o` — PNG path.
- `--spec` — JSON object or path, always deep-merged onto the spec built from the opened files. Your values win. A `patch` key inside the object is rejected.
- `--dump-spec` — write the merged spec as JSON and skip the PNG. Bare `--dump-spec` or `-` prints to stdout. Use it to get the current spec to modify; for what keys exist, use `--help`.

### Parameters (`--spec`)

- `inputs[]` — `variable` per input (`obs`, `forecast1`, `forecast2`, …); an input that omits it uses `inputs[0].variable` (the obs input) when it has that variable, else auto-detects its own. So obs `precip` next to a forecast's `precipitation_surface` needs only the obs `variable`. `label` on obs and each forecast.
- `title`, `theme.fontsize` (default 16), `theme.colormap`, `vmin`, `vmax`.
- `traces[0].leads` — column titles. Default `1-week lead` … `N-week lead`. Titles that name a week are sorted so week-1 sits next to the observation.
- Keep `title` and `traces[0].leads` short: the grid has many panels, and the week dates are already added to the title.
- `geo.bbox` as `[N, W, S, E]`, `geo.mask_geojson`. There is no `geo.region` / `geo.country` — for a named place, run `resolve-region` and pass its bbox or polygon.
- `layout.figsize` as `[W, H]`, `layout.facet.wspace` / `hspace`.

### Output

A PNG with observation in column 0 and N lead columns of forecast +
verify maps. Two colorbars sit **side by side at the bottom**: values
(obs/forecast) on the left, the verify metric (hits / bias / MAE) on
the right. Stdout also prints `plot hash` (sha256 of RGB pixels) and
`data: not null` or `data: NULL`, then each column's `verify_score_summary`.
A changed hash only proves the pixels differ, not what changed or whether
it looks right — never use hash comparisons to answer a layout or
appearance question. `NULL` means inspect-zarr the
inputs. Hits
use false alarm / miss / below / hit (verify's `disagree` split by whether
the obs had the event), and the colorbar names the threshold from the
verify Zarr (`event: ≥ 10 mm`); bias uses a diverging scale centered on
zero; MAE uses white at zero through warm colors. The verifying week
dates are added to the figure title when the obs time coordinate can
be read — `select --value` drops that coordinate, so put the week in
`title` yourself when the obs was selected down to one time.

## Example

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify_mpl.py \
    --obs /tmp/chirps_week.zarr \
    --forecast /tmp/s2s_week1.zarr --verify /tmp/verify_w1.zarr \
    --forecast /tmp/s2s_week2.zarr --verify /tmp/verify_w2.zarr \
    --forecast /tmp/s2s_week3.zarr --verify /tmp/verify_w3.zarr \
    --forecast /tmp/s2s_week4.zarr --verify /tmp/verify_w4.zarr \
    -o /tmp/verify_week.png \
    --spec '{"inputs":[{"id":"obs","variable":"precip"}],"title":"Kenya weekly precip verification","geo":{"bbox":[5,34,-5,42]}}'
```
