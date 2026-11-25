# Plotting Skills

General-purpose weather and climate data plotting from weather-skills standard
dataset Zarrs, all from one `plot` skill: maps, panel grids, station maps, time
series, ensemble plumes, bars, xy scatter, cross-sections and animated maps. The
spec is Jsonnet that evaluates to a standard Plotly figure; strings starting with
`@` name the data (`'@OBS.precip.isel(time=0)'`). Output is PNG, JPG, PDF, SVG,
interactive HTML or animated GIF. Built on
[`weather-skills-core`](https://github.com/weather-skills/weather-skills-core)
for dataset loading, the CLI decorator, and provenance.

## Skills

| Skill | Role |
| --- | --- |
| [`plot`](skills/plot/) | Any Plotly figure from named inputs (`-i PATH=NAME`) and a Jsonnet spec; runnable recipes in [`skills/plot/recipes/`](skills/plot/recipes/) |
| [`report-dashboard`](skills/report-dashboard/) | A report or dashboard from HTML text (`--html`): cleaned to an allowlist, images embedded, written as a self-contained page carrying the history of the figures it shows. Reports can also be `.pdf` (needs the Pango system library); dashboards switch between pre-made figures with dropdowns, tabs and collapsible sections, and can hold the `plot` skill's interactive HTML in sandboxed frames. |

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

## Install as an agent skill

```bash
npx skillkit install weather-skills/weather-skills-plotting --skill=plot
```

## Layout

Canonical skills under `skills/<name>/`. The `plot` skill carries its own rendering engine,
`skills/plot/scripts/weather_skills_plotting/`, next to its script: the skill
folder is self-contained (Python finds the package on the script's own path),
and a script and the code it calls always move together in one commit. The
repo-root `pyproject.toml` installs that package for tests and development.

See [CONTRIBUTING.md](CONTRIBUTING.md).
