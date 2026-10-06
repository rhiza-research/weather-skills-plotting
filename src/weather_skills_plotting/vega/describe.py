"""``--describe``: what each input offers a binding, and what a spec's bindings produce."""

from __future__ import annotations

import numpy as np

from weather_skills_plotting.vega.bind import plain


def _span(values) -> str:
    v = np.asarray(values)
    if v.size == 0:
        return "(empty)"
    if v.dtype.kind == "M":
        a, b = (np.datetime_as_string(x, unit="auto") for x in (v.min(), v.max()))
        return f"{a} .. {b}"
    if v.dtype.kind == "m":
        days = v.astype("timedelta64[s]").astype(float) / 86400
        return f"{days.min():g} .. {days.max():g} days"
    if v.dtype.kind in "iuf":
        step = ""
        if v.ndim == 1 and v.size > 1:
            d = np.diff(v.astype(float))
            if np.allclose(d, d[0], rtol=1e-3):
                step = f", step {d[0]:.4g}"
        return f"{np.nanmin(v):.6g} .. {np.nanmax(v):.6g}{step}"
    first = ", ".join(str(x) for x in v.ravel()[:4])
    return first + (", ..." if v.size > 4 else "")


def describe_zarr(name: str, ds) -> list[str]:
    ds = plain(ds)
    lines = [f"input {name}: zarr  dims {dict(ds.sizes)}"]
    for c in ds.coords:
        coord = ds[c]
        dims = "" if coord.dims == (c,) else f" on {coord.dims}"
        lines.append(f"  coord {c}{dims} ({coord.dtype}): {_span(coord.values)}")
    for v, da in ds.data_vars.items():
        attrs = {
            k: da.attrs[k] for k in ("long_name", "units", "aggregation_period") if k in da.attrs
        }
        extra = "  " + "  ".join(f"{k}={val!r}" for k, val in attrs.items()) if attrs else ""
        lines.append(f"  variable {v} {da.dims}{extra}")
    sources = [f"{d}.lo, {d}.hi" for d in ds.dims if d in ds.coords and ds[d].dtype.kind in "iuf"]
    if "time" in ds.coords and "step" in ds.coords:
        sources.append("valid_time")
    if sources:
        lines.append("  derived fields sources: " + "; ".join(sources))
    return lines


def describe_geojson(name: str, data: dict) -> list[str]:
    if data.get("type") == "FeatureCollection":
        feats = data.get("features") or []
    elif data.get("type") == "Feature":
        feats = [data]
    else:
        feats = [{"geometry": data, "properties": {}}]
    kinds = sorted({(f.get("geometry") or {}).get("type", "None") for f in feats})
    props = sorted({k for f in feats[:50] for k in (f.get("properties") or {})})
    return [
        f"input {name}: geojson  {len(feats)} feature(s) {kinds}",
        f"  properties: {props}  (encode as properties.<key>)",
    ]


def describe_inputs(inputs: dict) -> list[str]:
    lines = []
    for name, obj in inputs.items():
        lines += describe_geojson(name, obj) if isinstance(obj, dict) else describe_zarr(name, obj)
    return lines


def describe_bindings(prep) -> list[str]:
    lines = []
    for name, m in prep.meta.items():
        cols = ", ".join(m.get("columns", []))
        lines.append(f"bound {name}: {m['rows']} rows ({cols})")
    lines += [f"default {n}" for n in prep.notes]
    return lines
