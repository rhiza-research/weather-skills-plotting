---
name: plot-video
description: "Animate a gridded weather-skills Zarr through its times or forecast steps as a self-contained interactive HTML map, with play and pause buttons and a frame slider. Use to show how a field such as rainfall, temperature, or air quality changes over time, one map per frame on one color scale."
license: MIT
compatibility: Requires Python 3.12 and uv. The HTML embeds plotly.js and works offline; no Chrome needed.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py *)
metadata:
  version: "0.0.1"
  catalog-group: figure
---

# plot-video

Turns one gridded Zarr into an animated map, one frame per time or step.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i chirps_daily.zarr -o chirps.html
```

The page opens paused on the first frame; **▶ Play** runs the frames, **❚❚ Pause** stops, and the slider jumps to any frame. The title names the current frame. Each frame is the map `plot` draws for that time, with the same palettes and base map, and every frame shares one color scale.

### Arguments
- `--input`, `-i` — one Zarr with a latitude/longitude grid and a time or step dim.
- `--spec` — Plotly figure JSON, inline or a file path.
- `--theme-file` — house style: a Plotly `template` (fonts, background, colors) and named `palettes`.
- `--dump-spec` — print (`-`) or save (a path) the spec, without drawing.
- `--output`, `-o` — must end in `.html`.

### Customizing with `--spec`
`--spec` takes [Plotly figure](https://plotly.com/python/reference/) JSON, `{"data": [...], "layout": {...}}`; write only the parts you want to change. The map is the entry in `data` with `"uid": "0"`.

| To | `--spec` |
| --- | --- |
| Set the title | `{"layout": {"title": {"text": "Daily rainfall"}}}` |
| Pick frames by position | `{"data": [{"uid": "0", "meta": {"source": {"isel": {"step": [0, 2, 4, 6, 8]}}}}]}` |
| Pick frames by date | `{"data": [{"uid": "0", "meta": {"source": {"sel": {"time": ["2026-10-01", "2026-10-02"]}}}}]}` |
| Pick the variable | `{"data": [{"uid": "0", "meta": {"source": {"variable": "t2m"}}}]}` |
| Pick one member | `{"data": [{"uid": "0", "meta": {"source": {"isel": {"number": 0}}}}]}` |
| Animate another dim | `{"data": [{"uid": "0", "meta": {"facet": "number"}}]}` |
| Set the map window | `{"layout": {"meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}}}}` |
| Set the speed | `{"layout": {"meta": {"animation": {"duration": 300}}}}` |
| Set the color range | `{"data": [{"uid": "0", "zmin": 0, "zmax": 30}]}` |

`isel` counts from 0 (`-1` is the last); `sel` picks by label. `bbox` is `[N, W, S, E]`. `duration` is milliseconds per frame (default 500); `transition` is milliseconds between frames (default 0). `--help` lists every option with recipes, shared with `plot`; `--dump-spec -` shows the spec for your file.

### Output
A self-contained HTML file at `-o`; it embeds plotly.js (about 4.5 MB) and opens offline. Stderr gives the frame count and the size of the figure data, and warns above 50 MB.

### Notes
- Every dim other than latitude, longitude, and the animated one must go: pick one value with `isel` / `sel`, or average it first with summarize-dim. The animated dim needs at least two values.
- Size grows with frames × grid cells: 10 days of a 0.25° Kenya grid is 0.2 MB of data, but a year of days on a 0.05° grid is hundreds of MB. Pick fewer frames or a smaller `bbox` for big inputs.
- Station data and 1-D series are refused.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/plot_video.py -i gefs_3h.zarr -o gefs_rain.html --spec '{
  "data": [{"uid": "0", "meta": {"source": {"variable": "tp", "isel": {"number": 0}}}}],
  "layout": {"title": {"text": "GEFS rainfall"}, "meta": {"geo": {"bbox": [5.5, 33.5, -5, 42.5]}, "animation": {"duration": 300}}}}'
```
Member 0 of a 3-hourly GEFS rainfall forecast over Kenya, nine frames from the 6 Oct 2026 init, playing at 0.3 s per frame.

## Details

### Frame titles
Frame titles follow the data: `6 Oct '26 03:00 (+3h)` for a 3-hourly forecast, `1 Oct '26` for daily data.

### More options
- Contours instead of cells: `{"data": [{"uid": "0", "type": "contour"}]}`.
- Colorbar label: `{"layout": {"coloraxis": {"colorbar": {"title": {"text": "Rain [mm/day]"}}}}}`.
- Base-map layers: `{"layout": {"meta": {"overlays": {"rivers": false, "admin1": true}}}}`.
- A boundary outline or city markers (see `plot --help` recipes) is a new entry in `data` with its own `uid`; it shows on every frame.
- Width: `{"layout": {"width": 900}}`; the height follows the map's shape.
- Your own `layout.updatemenus` or `layout.sliders` replace the default buttons and slider.

### Provenance
The file's history (`weather_skills_history`) is embedded in an HTML `<meta>` tag; read it with the `provenance` skill.
