# Plotting Skills

General-purpose weather and climate data plotting from weather-skills standard
dataset Zarrs, all from one `plot` skill: maps, panel grids, station maps, time
series, ensemble plumes, bars, xy scatter, cross-sections and animated maps. The
spec is Jsonnet that evaluates to a standard Plotly figure; strings starting with
`@` name the data (`'@OBS.precip.isel(time=0)'`). Output is PNG, JPG, PDF, SVG,
interactive HTML or animated GIF. Built on
[`weather-skills-core`](https://github.com/weather-skills/weather-skills-core)
for dataset loading, the CLI decorator, and provenance.

## Skill

| Skill | Role |
| --- | --- |
| [`plot`](skills/plot/) | Any Plotly figure from named inputs (`-i PATH=NAME`) and a Jsonnet spec; runnable recipes in [`skills/plot/recipes/`](skills/plot/recipes/) |

The design is in [`docs/plotting.md`](docs/plotting.md). PNG/JPG/PDF/SVG/GIF
export needs Chrome: kaleido uses an installed one, or run
`uv run plotly_get_chrome -y` once.

Prefer short titles and colorbar labels. A title names the subject in a few
words (`CHIRPS weekly totals`, `Week 1`), not the whole pipeline; put methods,
sources and caveats in the caption or report text. A colorbar label is the
quantity and its units (`Rain [mm]`), not a sentence.

## Quick start

```bash
uv sync --group dev
uv run pytest

# A map of the first time in a file, with the base map
uv run skills/plot/scripts/plot.py -i /tmp/rain.zarr=OBS -o /tmp/map.png --spec "
  local ws = import 'ws.libsonnet'; local b = std.extVar('inputs').OBS.bbox;
  {data: [{type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip.isel(time=0)'}] + ws.basemap(b),
   layout: ws.map(b) + {title: {text: 'Rainfall'}}}"

# A recipe
uv run skills/plot/scripts/plot.py -i /tmp/rain_daily.zarr=OBS \
  --spec skills/plot/recipes/animation.jsonnet -o /tmp/rain.html -o /tmp/rain.gif
```

## Install as a Claude plugin

```bash
./install_agent.sh
# or:
claude plugin marketplace add rhiza-research/weather-skills-plotting
claude plugin install rhiza-plotting@weather-skills-plotting
```

## Layout

Canonical skills under `skills/<name>/`, Claude plugin via `.claude-plugin/` +
`agents/`. The one skill carries its own rendering engine,
`skills/plot/scripts/weather_skills_plotting/`, next to its script: the skill
folder is self-contained (Python finds the package on the script's own path),
and a script and the code it calls always move together in one commit. The
repo-root `pyproject.toml` installs that package for tests and development.

See [CONTRIBUTING.md](CONTRIBUTING.md).
