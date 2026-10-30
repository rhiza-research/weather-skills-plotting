# Contributing

## Publish model

`main` is the consumer-facing branch. Anything merged to `main` is considered
published. Each `skills/<name>/SKILL.md` carries a `metadata.version` field (Agent Skills
spec). That is the published identity. Scripts carry a matching `_SKILL_VERSION`
constant; the version-bump workflow rewrites both in lockstep.

## PR workflow

1. Branch off `main`.
2. Open a PR back into `main`.
3. CI must pass (ruff, inline-deps, pytest, per-script `--help`).
4. Rebase onto `main` before merging — linear history is preferred.
5. Use the GitHub merge button.

Authors **must not** edit `metadata.version` or `_SKILL_VERSION` by hand.

## The `weather_skills_plotting` library

`skills/plot/scripts/weather_skills_plotting/` is the rendering engine (Jsonnet
evaluation, `@` reference resolution, Plotly validation, export, QA) with its
Jsonnet library in `lib/`.
It lives next to the one entry script, `skills/plot/scripts/plot.py`, so the
skill folder is self-contained: Python finds the package on the script's own
path, and the script's PEP 723 header lists the package's third-party
dependencies (keep it in step with `pyproject.toml`). Library modules carry no
`_SKILL_VERSION`; the version tools only look at top-level `scripts/*.py`. The
repo-root `pyproject.toml` installs the package for `uv run pytest`.

Every example figure is a runnable recipe in `skills/plot/recipes/`; the recipe
test renders each one. Add a recipe rather than a mode or a binding.

Design rule: [references select, they don't compute](docs/plotting.md#references-select-they-dont-compute).

## Skill correctness tests

Per-skill tests live in `skills/<name>/tests/`. Library-level tests (references
and their guardrails, the Jsonnet library) live in the top-level
`tests/`. Run everything with `uv sync --group dev && uv run pytest`. Tests
that write PNGs need Chrome for kaleido (`uv run plotly_get_chrome -y`).
Natural Earth (`NE`) layers are stubbed by the root `conftest.py`; mark a test
`@pytest.mark.overlays` to draw the real ones.

## Version bumps

On push to `main`, `.github/workflows/version-bump.yml` bumps changed skills and
publishes a lean plugin payload to `plugin-dist`. Bump kind comes from PR labels:

| Label            | Bump kind |
| ---------------- | --------- |
| `release: major` | major     |
| `release: minor` | minor     |
| (none)           | patch     |

## Local development against weather-skills-core

Skill scripts and `pyproject.toml` depend on `weather-skills-core` from PyPI
(for the `@weather_skill` CLI decorator and a handful of shared utilities the
plotting library itself uses). To iterate against a local checkout instead:

```bash
tools/run_with_local_core.sh skills/plot/scripts/plot.py --help
```
