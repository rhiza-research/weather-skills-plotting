# Plotting Skills

General-purpose weather and climate data plotting: heatmaps, filled-contour
maps, station maps, time series, xy scatter, wind roses, quiver, ECMWF-style
mediograms, lead-week event-verification grids, and animated maps, from weather-skills
standard dataset Zarrs, all from one `plot` skill. Figures are Plotly: its `--spec` is
a standard Plotly figure JSON, and output is PNG, JPG, interactive HTML, or animated GIF. Built on [`weather-skills-core`](https://github.com/weather-skills/weather-skills-core)
for dataset loading, the CLI decorator, and a handful of shared utilities.

## Skill

| Skill | Role |
| --- | --- |
| [`plot`](skills/plot/) | Heatmap, contour, timeseries, xy scatter, wind-rose, quiver, or layered map, one dataset or several side by side; several 1-D series share one time axis. `--obs`/`--forecast`/`--verify` draw a lead-week verification grid, `--mediogram` an ECMWF-style mediogram, and `--animate` plays any map (all its layers) through time as animated HTML or GIF |

The spec design (Plotly figure plus `meta` bindings) is documented in
[`docs/plotting.md`](docs/plotting.md). PNG/JPG export needs Chrome: kaleido
uses an installed one, or run `uv run plotly_get_chrome -y` once.

Prefer short titles and colorbar labels. A title names the subject in a few
words (`CHIRPS weekly totals`, `Week 1`), not the whole pipeline; put
methods, sources and caveats in the caption or report text. A colorbar label
is the quantity and its units (`Rain [mm]`), not a sentence. Long text wraps
badly, crowds multi-panel grids, and squeezes the side-by-side colorbars
along the bottom.

## Quick start

```bash
uv sync --group dev
uv run pytest

# A heatmap, one panel per step
uv run skills/plot/scripts/plot.py -i /tmp/forecast.zarr -o /tmp/out.png \
  --spec '{"layout": {"title": {"text": "S2S precip"}}}'

# The same figure, interactive. Also writes out.plotly.json beside it, for
# the chat's shared-library viewer.
uv run skills/plot/scripts/plot.py -i /tmp/forecast.zarr -o /tmp/out.html

# A timeseries overlay of two area means (each from summarize-dim --lat-weighted)
uv run skills/plot/scripts/plot.py -i /tmp/a_area.zarr -i /tmp/b_area.zarr \
  -o /tmp/timeseries.png

# A lead-week verification grid
uv run skills/plot/scripts/plot.py --obs /tmp/obs.zarr \
  --forecast /tmp/wk1.zarr --verify /tmp/v1.zarr --forecast /tmp/wk2.zarr --verify /tmp/v2.zarr \
  -o /tmp/verify.png

# A mediogram
uv run skills/plot/scripts/plot.py --mediogram \
  -i /tmp/forecast.zarr -i /tmp/mclimate.zarr -o /tmp/medio.png \
  --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}' 

# An animated map (HTML or GIF)
uv run skills/plot/scripts/plot.py --animate \
  -i /tmp/forecast.zarr -o /tmp/forecast.html -o /tmp/forecast.gif
```

## Install as a Claude plugin

```bash
./install_agent.sh
# or:
claude plugin marketplace add rhiza-research/weather-skills-plotting
claude plugin install rhiza-plotting@weather-skills-plotting
```

## Layout

Same packaging model as [`chc-skills`](https://github.com/rhiza-research/chc-skills):
canonical skills under `skills/<name>/`, Claude plugin via `.claude-plugin/` +
`agents/`. The one skill carries its own rendering engine,
`skills/plot/scripts/weather_skills_plotting/`, next to its script: the skill
folder is self-contained (Python finds the package on the script's own path),
and a script and the code it calls always move together in one commit. The
repo-root `pyproject.toml` installs that package for tests and development.

See [CONTRIBUTING.md](CONTRIBUTING.md).
