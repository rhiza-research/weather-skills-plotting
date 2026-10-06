# Plotting Skills

General-purpose weather and climate data plotting: heatmaps, filled-contour
maps, station maps, time series, xy scatter, wind roses, quiver, ECMWF-style
mediograms, and lead-week event-verification grids, from weather-skills
standard dataset Zarrs. Figures are Plotly: the `--spec` every skill takes is
a standard Plotly figure JSON, and output is PNG, JPG, or interactive HTML. Built on [`weather-skills-core`](https://github.com/rhiza-research/weather-skills-core)
for dataset loading, the CLI decorator, and a handful of shared utilities.

## Skills

| Skill | Role |
| --- | --- |
| [`plot`](skills/plot/) | Heatmap, contour, timeseries, xy scatter, wind-rose, quiver, or layered map, one dataset or several side by side |
| [`plot-timeseries`](skills/plot-timeseries/) | One 1D trace per input Zarr overlaid on a shared time axis |
| [`plot-verify`](skills/plot-verify/) | Lead-week event-verification grid of maps for one observation week |
| [`plot-mediogram`](skills/plot-mediogram/) | ECMWF-style mediogram comparing a forecast ensemble against an m-climate ensemble |

The spec design (Plotly figure plus `meta` bindings) is documented in
[`docs/plotting.md`](docs/plotting.md). PNG/JPG export needs Chrome: kaleido
uses an installed one, or run `uv run plotly_get_chrome -y` once.

## Quick start

```bash
uv sync --group dev
uv run pytest

# A heatmap, one panel per step
uv run skills/plot/scripts/plot.py -i /tmp/forecast.zarr -o /tmp/out.png \
  --spec '{"layout": {"title": {"text": "S2S precip"}}}'

# The same figure, interactive
uv run skills/plot/scripts/plot.py -i /tmp/forecast.zarr -o /tmp/out.html

# A timeseries overlay of two area means
uv run skills/plot-timeseries/scripts/plot_timeseries.py -i /tmp/a.zarr -i /tmp/b.zarr \
  -o /tmp/timeseries.png \
  --spec '{"data": [{"uid": "a", "meta": {"source": {"reduce": ["latitude", "longitude"]}}}]}' 

# A lead-week verification grid
uv run skills/plot-verify/scripts/plot_verify.py \
  --obs /tmp/obs.zarr --forecast /tmp/wk1.zarr /tmp/wk2.zarr /tmp/wk3.zarr /tmp/wk4.zarr \
  -o /tmp/verify.png

# A mediogram
uv run skills/plot-mediogram/scripts/plot_mediogram.py \
  -i /tmp/forecast.zarr -i /tmp/mclimate.zarr -o /tmp/medio.png \
  --spec '{"layout": {"meta": {"geo": {"point": {"lat": -1.3, "lon": 36.8}}}}}' 
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
`agents/`. Unlike `chc-skills`, this repo also carries its own rendering
engine at `src/weather_skills_plotting/` — every skill script depends on it
as local library code (not a separately published package), since a script
and the code it calls should always move together in one commit.

See [CONTRIBUTING.md](CONTRIBUTING.md).
