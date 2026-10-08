---
name: plot-video
description: Animate a gridded weather-skills Zarr through time (or forecast step) as a self-contained interactive HTML map with play / pause buttons and a frame slider. One frame per value of the time or step dim, on one shared color scale. The --spec is a standard Plotly figure JSON, the same as plot's; meta.facet picks the dim to animate, meta.source.isel / sel pick which frames, layout.meta.geo.bbox crops the map, layout.meta.animation sets the frame speed. Output must be .html. For a still map or a grid of panels use plot. For precipitation, run aggregate-temporal then convert-to-totals first.
license: MIT
compatibility: Requires Python 3.12 and uv. The HTML embeds plotly.js and works offline; no Chrome needed.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py *)
metadata:
  version: "0.0.1"
  catalog-group: figure
---

# plot-video

Turns one gridded Zarr into an animated map: each value of its `time` or `step` dim becomes a frame. The file opens paused on the first frame. **▶ Play** steps through the frames, **❚❚ Pause** stops, and the slider jumps to any frame. The title above the map names the current frame (`6 Oct '26 03:00 (+3h)` for a 3-hourly forecast, `31 Oct '25 15:00` for 3-hourly analyses, `14 Sept '26` for daily data). Hovering shows the value under the cursor.

It draws the same map `plot` draws for that file: the same palettes (precipitation classes, diverging anomalies), coastline, borders, lakes and rivers, and the same `--spec`. Every frame shares one color scale, so colors mean the same value throughout the animation.

## How a spec is built

The command builds one trace, uid `a`, a `heatmap` bound to the `-i` file, then merges `--spec` onto it. `--spec` is a **standard Plotly figure** (`{"data": [...], "layout": {...}}`); every key outside `meta` is Plotly's own ([reference](https://plotly.com/python/reference/)). `--help` lists the `meta` keys and recipes, which are shared with `plot`.

Run with `--dump-spec -` in place of `-o` to print the figure it would draw, edit it, and pass it back with `--spec`.

## Choosing the frames

| Goal | `--spec` |
| --- | --- |
| Animate a dim other than time / step (e.g. `number`, `level`) | `{"data": [{"uid": "a", "meta": {"facet": "number"}}]}` |
| A subset of frames, by position | `{"data": [{"uid": "a", "meta": {"source": {"isel": {"step": [0, 8, 16, 24]}}}}]}` |
| A subset of frames, by label | `{"data": [{"uid": "a", "meta": {"source": {"sel": {"time": ["2025-10-31", "2025-11-01"]}}}}]}` |
| Pick the variable | `{"data": [{"uid": "a", "meta": {"source": {"variable": "pm25"}}}]}` |
| Fix one value of another dim | `{"data": [{"uid": "a", "meta": {"source": {"isel": {"level": 0}}}}]}` |

Ensemble `number` is averaged unless it is the animated dim. Any other leftover dim is an error naming the fix; nothing else is averaged silently. The animated dim needs at least two values.

## Look and speed

| Goal | `--spec` |
| --- | --- |
| Title | `{"layout": {"title": {"text": "NO2 forecast"}}}` |
| Map window | `{"layout": {"meta": {"geo": {"bbox": [33, 72, 23, 85]}}}}` (`[N, W, S, E]`; named places: run `resolve-region`) |
| Frame speed | `{"layout": {"meta": {"animation": {"duration": 300, "transition": 0}}}}` (milliseconds per frame, default 500, and between frames, default 0) |
| Color limits / scale | `{"data": [{"uid": "a", "zmin": 0, "zmax": 30, "colorscale": "YlOrRd"}]}` |
| Colorbar label | `{"layout": {"coloraxis": {"colorbar": {"title": {"text": "NO2 [ppb]"}}}}}` |
| Contours instead of cells | `{"data": [{"uid": "a", "type": "contour"}]}` |
| Base-map layers | `{"layout": {"meta": {"overlays": {"rivers": false, "admin1": true}}}}` |
| Boundary outline or city markers | Add a trace with a new uid (see `plot`'s recipes); it shows on every frame |
| Size | `{"layout": {"width": 900}}` (height follows the map's shape) |

Your own `layout.updatemenus` or `layout.sliders` replace the default play buttons and slider.

## Command line

```
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i <grid.zarr> -o <out.html> [--spec JSON]
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i <grid.zarr> --dump-spec -
```

- `-i` — one gridded Zarr (latitude/longitude plus the dim to animate). Station data and 1-D series are refused; use `plot` or `plot-timeseries`.
- `-o` — must end in `.html` (a PNG cannot play).
- `--spec` — inline JSON or a file path.
- `--dump-spec [PATH]` — print or write the merged spec and skip drawing.
- `--theme-file` — `{"template": <Plotly template>, "palettes": {…}}`, as for `plot`.

## Output

A self-contained HTML file at `--output` (plotly.js is embedded, about 4.5 MB, so it opens offline). Stderr reports the frame count and the size of the figure data, and warns above 50 MB. File size grows with frames × grid cells: a 0.4° India grid with 9 frames is about 2.4 MB of data, but a 0.05° grid over a year of days is hundreds of MB. Select fewer frames or a smaller bbox before rendering a large one.

Provenance (`weather_skills_history`) is embedded in an HTML `<meta>` tag. Read it with the `provenance` skill.

## Examples

```bash
# CAMS NO2 forecast over India, every 3 h for a day
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i /tmp/cams_india_no2.zarr -o /tmp/no2.html \
    --spec '{"layout": {"title": {"text": "NO2 forecast"}}}'

# EAC4 PM2.5 over north India, faster playback
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i /tmp/eac4_india.zarr -o /tmp/pm25.html \
    --spec '{"data": [{"uid": "a", "meta": {"source": {"variable": "pm25"}}}],
             "layout": {"title": {"text": "PM2.5"}, "meta": {"geo": {"bbox": [33, 72, 23, 85]},
                        "animation": {"duration": 300}}}}'

# Daily CHIRPS totals for a month with the precipitation class palette
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i /tmp/chirps_daily_mm.zarr -o /tmp/chirps.html \
    --spec '{"data": [{"uid": "a", "meta": {"palette": "ppt_daily"}}]}'
```
