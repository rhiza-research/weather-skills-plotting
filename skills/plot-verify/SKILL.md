---
name: plot-verify
description: Plot a lead-week verification grid from pre-computed verify Zarrs, as PNG or interactive HTML. Row 1 is the observation then the week-1 … week-N forecasts on one color scale; row 2 holds each lead's verify map (hits, bias, or MAE). Every --obs and --forecast must already be a single time — run select on the verifying week first. Run verify on each forecast/obs pair before this skill. For precipitation, aggregate-temporal then convert-to-totals before verify. Pass --forecast week-1 first. The --spec is a standard Plotly figure (traces obs, forecast1…, verify1…).
license: MIT
compatibility: Requires Python 3.12 and uv. PNG/JPG export needs Chrome (installed, or `plotly_get_chrome -y`).
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py *)
metadata:
  version: "0.0.3"
  catalog-group: figure
---

# plot-verify

A 2-row grid for one verifying week:

| | column 1 | column 2 | column 3 | … |
| --- | --- | --- | --- | --- |
| row 1 | observation | 1-week lead | 2-week lead | … |
| row 2 | metric name | verify 1 | verify 2 | … |

Columns follow the `--forecast` order, so **pass week-1 first**. Observation and forecasts share one color scale (precipitation gets the nested-mm class palette for the widest aggregation window). The verify row has its own scale: hits as disagree / below / hit, bias diverging around zero, and MAE from white through warm colors. The figure title gets the verifying week's dates (`6–12 Oct '26`), and each lead's `verify_score_summary` is printed to stdout.

**`--obs` and each `--forecast` must have a single time.** If you see `has time size N; select the verifying week`, run `select` first. A leftover `step` axis needs `step-to-time` first. Obs and forecasts must share a grid: coarsen obs onto the forecast with `--reference-grid`, not the reverse.

## Pipeline

1. Prepare obs and each lead's forecast: aggregate, `step-to-time` if needed, **`select` the verifying week**, and coarsen obs onto the forecast grid.
2. Run `verify` on each lead.
3. Run this skill with single-time obs, forecasts week-1 … week-N, and the matching `--verify` Zarrs.

## The spec

`--spec` is a **standard Plotly figure** merged onto the grid this command builds:

- Traces are `obs`, `forecast1` … `forecastN` (axes `x`, `x2`, …) and `verify1` … `verifyN`, which sit in row 2.
- Panel titles are annotations named `panel-title-N`. The metric label is `row-label-metric`.
- Obs and forecasts share `coloraxis`; the verify maps use `coloraxis2`.

| Goal | `--spec` |
| --- | --- |
| Title (week dates are appended) | `{"layout": {"title": {"text": "Kenya weekly precip verification"}}}` |
| Rename a column | `{"layout": {"annotations": [{"name": "panel-title-2", "text": "Week 1 (init 29 Sept)"}]}}` |
| Different variable names | `{"data": [{"uid": "forecast1", "meta": {"source": {"variable": "precipitation_surface"}}}]}` (forecasts default to the obs variable) |
| Map window or mask | `{"layout": {"meta": {"geo": {"bbox": [5, 34, -5, 42]}}}}` |
| Field color limits | `{"layout": {"coloraxis": {"cmin": 0, "cmax": 100}}}` |
| Bigger text | `{"layout": {"font": {"size": 20}}}` |

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py --obs <obs.zarr> \
    --forecast <week1.zarr> --verify <verify_w1.zarr> \
    --forecast <week2.zarr> --verify <verify_w2.zarr> \
    -o <out.png|.html> [--spec JSON]
```

All `--verify` inputs must share one `verify_metric` (`hits`, `bias`, or `mae`). `--dump-spec [PATH]` prints or writes the merged spec and skips drawing.

## Example

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_verify.py \
    --obs /tmp/chirps_week.zarr \
    --forecast /tmp/s2s_week1.zarr --verify /tmp/verify_w1.zarr \
    --forecast /tmp/s2s_week2.zarr --verify /tmp/verify_w2.zarr \
    --forecast /tmp/s2s_week3.zarr --verify /tmp/verify_w3.zarr \
    --forecast /tmp/s2s_week4.zarr --verify /tmp/verify_w4.zarr \
    -o /tmp/verify_week.png \
    --spec '{"layout": {"title": {"text": "Kenya weekly precip verification"}, "meta": {"geo": {"bbox": [5, 34, -5, 42]}}}}'
```

## Output

PNG/JPG print a pixel `plot hash` and `data: not null` / `NULL`, then each lead's score summary. Look at the image; a hash only shows that pixels changed. Provenance is embedded in the PNG metadata or the HTML `<meta>` tag.
