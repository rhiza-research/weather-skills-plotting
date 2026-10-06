# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "weather-skills-plotting",
#   "weather-skills-core @ git+https://github.com/rhiza-research/weather-skills-core@dev",
#   "cf-xarray",
#   "cftime",
#   "numpy",
#   "xarray",
#   "zarr",
#   "pint-xarray>=0.6",
# ]
#
# [tool.uv.sources]
# weather-skills-plotting = { path = "../../..", editable = true }
# ///
"""Lead-week verification grid: observation, forecasts, and verify maps, as PNG or HTML.

Row 1 is the observation then the week-1 … week-N forecasts on one shared
color scale; row 2 holds each lead's verify map (hits, bias, or MAE) on a
second scale. The cell under the observation names the metric.
"""

import numpy as np
from weather_skills_core import Dataset, UsageError, weather_skill
from weather_skills_core.cf import auto_variable, cf_dim
from weather_skills_core.display_labels import combine_display_labels, dataset_display_label
from weather_skills_core.units import format_units_for_display, units_equal, variable_units

from weather_skills_plotting import parse_spec_arg
from weather_skills_plotting.cli import run, skeleton, warn
from weather_skills_plotting.labels import format_plot_date_range
from weather_skills_plotting.layout import axis_suffix
from weather_skills_plotting.palettes import aggregation_days, is_precip, widest_precip_window
from weather_skills_plotting.reference import install_spec_help
from weather_skills_plotting.spec import DUMP_SPEC_HELP, SPEC_ARGUMENT_HELP, merge_spec

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.3"

VERIFY_VARS = {"hits": "event_hit", "bias": "bias", "mae": "mae"}
METRIC_LABELS = {"hits": "Hits", "bias": "Bias", "mae": "MAE"}
HITS_PALETTE = {"colors": ["#d73027", "#f0f0f0", "#1a9850"], "bounds": [-1.5, -0.5, 0.5, 1.5]}
BIAS_COLORS = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#ffffff",
               "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"]  # fmt: skip
MAE_COLORS = ["#ffffff", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"]


def _as_list(value):
    return [] if value is None else (value if isinstance(value, list) else [value])


def _single_map(ds, variable, role):
    """The field must already be the verifying week: one time, no step."""
    da = ds[variable]
    if "step" in da.dims:
        raise UsageError(
            f"{role} still has a step axis; run step-to-time and select the verifying week first"
        )
    for dim in da.dims:
        if dim in (cf_dim(da, "latitude"), cf_dim(da, "longitude"), "number"):
            continue
        if da.sizes[dim] != 1:
            raise UsageError(
                f"{role} has {dim} size {da.sizes[dim]}; select the verifying week (one time) "
                "with the select skill before plot-verify"
            )
    return da


def _spacing(coord):
    vals = np.asarray(coord.values, dtype=float)
    return float(np.median(np.abs(np.diff(vals)))) if vals.size > 1 else None


def _require_same_grid(left, right, left_role, right_role):
    """Cells are compared side by side; coarsen obs onto the forecast, not the reverse."""
    bad = []
    for axis in ("latitude", "longitude"):
        a, b = cf_dim(left, axis), cf_dim(right, axis)
        if a in left.dims and b in right.dims:
            da, db = _spacing(left[a]), _spacing(right[b])
            if da and db and not np.isclose(da, db, rtol=0.01, atol=1e-6):
                bad.append(axis)
    if bad:
        raise UsageError(
            f"{right_role} grid spacing does not match {left_role} on {' and '.join(bad)}; "
            "coarsen --obs onto the forecast with --reference-grid <forecast.zarr>"
        )


def _week_title(da):
    if "time" not in da.coords:
        return None
    start = np.asarray(da["time"].values).reshape(-1)
    if not start.size or start.dtype.kind != "M":
        return None
    start = start[0].astype("datetime64[D]")
    days = aggregation_days(da)
    span = int(round(days)) if days and days >= 2 else 7
    return format_plot_date_range(start, start + np.timedelta64(span - 1, "D"))


def _user_variable(user, uid):
    trace = next((t for t in user.get("data") or [] if t.get("uid") == uid), {})
    return ((trace.get("meta") or {}).get("source") or {}).get("variable")


@weather_skill(name="plot-verify", version=_SKILL_VERSION)
@weather_skill.argument(
    "--obs",
    type=Dataset("spatial"),
    required=False,
    help="Observation Zarr for the verifying week (input id obs).",
)
@weather_skill.argument(
    "--forecast",
    type=Dataset("spatial"),
    action="append",
    required=False,
    help="Forecast Zarr for that week at one lead; repeat, week-1 first "
    "(input ids forecast1, forecast2, …).",
)
@weather_skill.argument(
    "--verify",
    type=Dataset("any"),
    action="append",
    required=False,
    help="Verify Zarr from the verify skill, once per --forecast, same order.",
)
@weather_skill.argument("--spec", default=None, type=parse_spec_arg, help=SPEC_ARGUMENT_HELP)
@weather_skill.argument(
    "--theme-file",
    default=None,
    help="Theme JSON/TOML: {template: <Plotly template>, palettes: {…}}.",
)
@weather_skill.argument(
    "--dump-spec", nargs="?", const="-", default=None, probe=True, help=DUMP_SPEC_HELP
)
def plot_verify(
    obs, forecast, verify, output, spec=None, theme_file=None, dump_spec=None, **kwargs
):
    """Lead-week verification grid from obs, forecast, and pre-computed verify Zarrs."""
    forecasts, verifies = _as_list(forecast), _as_list(verify)
    if obs is None and spec is not None:
        opened = spec.opened()
        obs = opened.get("obs")
        forecasts = forecasts or [opened[k] for k in sorted(opened) if k.startswith("forecast")]
        verifies = verifies or [opened[k] for k in sorted(opened) if k.startswith("verify")]
    if obs is None:
        raise UsageError("pass --obs, or a --spec whose layout.meta.inputs names obs")
    if not forecasts:
        raise UsageError("pass at least one --forecast")
    if len(verifies) != len(forecasts):
        raise UsageError(
            f"--verify was passed {len(verifies)} time(s) but --forecast {len(forecasts)} time(s); "
            "pass one --verify per --forecast"
        )
    metrics = set()
    for i, v in enumerate(verifies, start=1):
        metric = v.attrs.get("verify_metric")
        if metric not in VERIFY_VARS:
            raise UsageError(
                f"--verify {i} has no supported verify_metric attr; run the verify skill first"
            )
        if VERIFY_VARS[metric] not in v:
            raise UsageError(f"--verify {i} is missing its {VERIFY_VARS[metric]!r} variable")
        metrics.add(metric)
    if len(metrics) != 1:
        raise UsageError(f"all --verify inputs must share one verify_metric; got {sorted(metrics)}")
    metric = metrics.pop()
    user = spec.data if spec is not None else {}
    n = len(forecasts)
    cols = n + 1
    datasets = {
        "obs": obs,
        **{f"forecast{i}": f for i, f in enumerate(forecasts, 1)},
        **{f"verify{i}": v for i, v in enumerate(verifies, 1)},
    }

    obs_var = _user_variable(user, "obs") or auto_variable(obs)
    obs_da = _single_map(obs, obs_var, "--obs")
    fc_vars, fc_das = [], []
    for i, fc in enumerate(forecasts, 1):
        var = _user_variable(user, f"forecast{i}") or (
            obs_var if obs_var in fc else auto_variable(fc)
        )
        if var not in fc:
            raise UsageError(
                f"--forecast {i} has no variable {var!r}; available: {', '.join(fc.data_vars)}"
            )
        fc_vars.append(var)
        fc_das.append(_single_map(fc, var, f"--forecast {i}"))
        u_fc, u_obs = variable_units(fc[var]), variable_units(obs_da)
        if u_fc and u_obs and not units_equal(u_fc, u_obs):
            warn(
                f"--forecast {i} {var!r} units={u_fc!r} and --obs {obs_var!r} units={u_obs!r} differ"
            )
        _require_same_grid(forecasts[0], fc, "--forecast 1", f"--forecast {i}")
    _require_same_grid(forecasts[0], obs, "--forecast 1", "--obs")
    for i, v in enumerate(verifies, 1):
        summary = v.attrs.get("verify_score_summary")
        if isinstance(summary, str) and summary.strip():
            print(f"{i}-week lead  {summary.strip()}")

    field_meta = {}
    if is_precip(obs_da):
        window = widest_precip_window(
            aggregation_days(obs_da), *(aggregation_days(d) for d in fc_das)
        )
        field_meta = {"palette": window}
    data = [
        {
            "uid": "obs",
            "type": "heatmap",
            "coloraxis": "coloraxis",
            "meta": {"source": {"input": "obs", "variable": obs_var}, **field_meta},
        }
    ]
    for i, var in enumerate(fc_vars, 1):
        data.append(
            {
                "uid": f"forecast{i}",
                "type": "heatmap",
                "coloraxis": "coloraxis",
                "xaxis": f"x{i + 1}",
                "yaxis": f"y{i + 1}",
                "meta": {"source": {"input": f"forecast{i}", "variable": var}, **field_meta},
            }
        )
    for i in range(1, n + 1):
        p = cols + i + 1
        data.append(
            {
                "uid": f"verify{i}",
                "type": "heatmap",
                "coloraxis": "coloraxis2",
                "xaxis": f"x{p}",
                "yaxis": f"y{p}",
                "meta": {
                    "source": {"input": f"verify{i}", "variable": VERIFY_VARS[metric]},
                    **({"palette": HITS_PALETTE} if metric == "hits" else {}),
                },
            }
        )

    obs_label = dataset_display_label(obs, "Observation")
    fc_label = combine_display_labels([dataset_display_label(f, "Forecast") for f in forecasts])
    titles = [obs_label] + [f"{i}-week lead" for i in range(1, n + 1)]
    annotations = [
        {
            "name": f"panel-title-{p + 1}",
            "text": t,
            "xref": f"x{axis_suffix(p)} domain",
            "yref": f"y{axis_suffix(p)} domain",
            "x": 0.5,
            "y": 1,
            "yanchor": "bottom",
            "yshift": 3,
            "showarrow": False,
        }
        for p, t in enumerate(titles)
    ]
    # Verify cells sit under their forecast column title; no date of their own.
    annotations += [{"name": f"panel-title-{cols + i + 1}", "text": ""} for i in range(1, n + 1)]
    units = format_units_for_display(variable_units(obs_da))
    metric_label = METRIC_LABELS[metric]
    metric_title = f"{metric_label} [{units}]" if units and metric != "hits" else metric_label
    blank = axis_suffix(cols)
    annotations.append(
        {
            "name": "row-label-metric",
            "text": f"<b>{metric_label}</b><br>{fc_label}",
            "xref": f"x{blank} domain",
            "yref": f"y{blank} domain",
            "x": 0.5,
            "y": 0.5,
            "showarrow": False,
            "font": {"size": 18},
        }
    )
    if metric == "hits":
        axis2 = {
            "colorbar": {
                "title": {"text": "Event"},
                "tickvals": [0, 1, 2],
                "ticktext": ["disagree", "below", "hit"],
            }
        }
    elif metric == "bias":
        axis2 = {
            "colorscale": [[i / 10, c] for i, c in enumerate(BIAS_COLORS)],
            "colorbar": {"title": {"text": metric_title}},
        }
    else:
        axis2 = {
            "colorscale": [[i / 5, c] for i, c in enumerate(MAE_COLORS)],
            "cmin": 0,
            "colorbar": {"title": {"text": metric_title}},
        }
    week = _week_title(obs_da)
    user_title = (user.get("layout") or {}).get("title") or {}
    user_title = user_title.get("text") if isinstance(user_title, dict) else user_title
    title = (
        week
        if not user_title
        else (f"{user_title} · {week}" if week and week not in user_title else user_title)
    )
    layout = {"grid": {"rows": 2, "columns": cols}, "annotations": annotations, "coloraxis2": axis2}
    if title:
        layout["title"] = {"text": title}
    base = skeleton("plot-verify", datasets, data, layout)
    if user_title:
        user = {
            **user,
            "layout": {k: v for k, v in (user.get("layout") or {}).items() if k != "title"},
        }
    return run(merge_spec(base, user), None, datasets, output, dump_spec, theme_file=theme_file)


install_spec_help(plot_verify)

if __name__ == "__main__":
    plot_verify()
