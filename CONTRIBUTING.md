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

`src/weather_skills_plotting/` is the actual rendering engine (Plotly spec
merge and validation, dataset binding, figure assembly, palettes, QA) that
every skill in `skills/` depends on. It's local library code, not a separately
published package: each skill script depends on it via `[tool.uv.sources]`
with a relative `path`, not a git URL, so a script and the library it calls
always move together in one commit. See any `skills/*/scripts/*.py` header
for the exact form.

## Skill correctness tests

Per-skill tests live in `skills/<name>/tests/`. Library-level tests (spec
merge and validation, palettes, figure assembly, QA) live in the top-level
`tests/`. Run everything with `uv sync --group dev && uv run pytest`. Tests
that write PNGs need Chrome for kaleido (`uv run plotly_get_chrome -y`).
Natural Earth overlays are stubbed by the root `conftest.py`; mark a test
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

Skill scripts still pin `weather-skills-core` (for the `@weather_skill` CLI
decorator and a handful of shared utilities the plotting library itself
uses) over git. To iterate against a local checkout instead:

```bash
tools/run_with_local_core.sh skills/plot/scripts/plot.py --help
```

Core is currently pinned to `plotting-refactor` in every skill script's PEP
723 header (and in `pyproject.toml`) until that branch merges to `main`.
