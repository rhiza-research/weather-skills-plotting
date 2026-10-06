# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["altair>=6.3", "vl-convert-python>=1.9"]
# ///
"""What validation errors look like to an agent: raw jsonschema vs Altair's formatted errors."""

import altair as alt

cases = {
    "projection on hconcat": {"hconcat": [{"mark": "point"}], "projection": {"type": "mercator"}},
    "typo in encoding": {"data": {"values": []}, "mark": "line", "encodng": {"x": {"field": "a"}}},
    "bad channel": {"data": {"values": []}, "mark": "line", "encoding": {"colour": {"field": "a"}}},
    "bad mark type": {"data": {"values": []}, "mark": "lines"},
    "bad scale type": {
        "data": {"values": []},
        "mark": "rect",
        "encoding": {"color": {"field": "a", "type": "quantitative", "scale": {"type": "thresh"}}},
    },
}
import jsonschema  # noqa: E402

full_schema = alt.vegalite.v6.schema.core.load_schema()
validator = jsonschema.validators.validator_for(full_schema)(full_schema)
for name in ("bad mark type", "bad scale type"):
    best = jsonschema.exceptions.best_match(validator.iter_errors(cases[name]))
    path = "spec" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in best.absolute_path)
    print(f"== jsonschema best_match, {name}: {path}: {best.message[:300]}\n")

for name, spec in cases.items():
    cls = alt.HConcatChart if "hconcat" in spec else alt.Chart
    try:
        cls.from_dict(spec, validate=False).to_dict(validate=True)
        print(f"== {name}: no error")
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        print(f"== {name}: {type(exc).__name__} ({len(text)} chars)\n{text[:700]}\n")
