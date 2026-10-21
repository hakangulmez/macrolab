"""Generate the documented JSON contracts from the bounded configuration vocabulary."""

import json
from pathlib import Path

from macrolab.analysis.config import MODEL_IDS, ROLES, TRANSFORMS

ROOT = Path(__file__).resolve().parents[1]


def obj(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def write_schemas():
    string = {"type": "string"}

    def array(items):
        return {"type": "array", "items": items}

    generic = {"type": "object"}
    period = obj({"start": string, "end": string}, ["start", "end"])
    series = obj(
        {
            "concept_id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,60}$"},
            "role": {"enum": list(ROLES)},
            "transform": {"enum": list(TRANSFORMS)},
            "transform_params": generic,
        },
        ["concept_id", "role", "transform"],
    )
    config = obj(
        {
            "schema_version": {"const": 1},
            "snapshot_id": string,
            "countries": {**array(string), "uniqueItems": True, "minItems": 1, "maxItems": 50},
            "series": {**array(series), "minItems": 1, "maxItems": 20},
            "frequency": {"enum": ["M", "Q", "A"]},
            "aggregation": {
                "type": "object",
                "additionalProperties": {"enum": ["mean", "last", "sum"]},
            },
            "sample": period,
            "special_periods": obj(
                {
                    "covid": {"enum": ["include", "dummy", "exclude"]},
                    "elb_threshold": {"type": "number"},
                    "covid_window": period,
                },
                ["covid"],
            ),
            "model": obj({"id": {"enum": list(MODEL_IDS)}, "params": generic}, ["id"]),
            "identification": {"type": ["object", "null"]},
            "outputs": obj(
                {
                    "confidence": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
                    "irf": obj(
                        {
                            "horizon": {"type": "integer", "minimum": 1, "maximum": 80},
                            "bands": {
                                "type": "number",
                                "exclusiveMinimum": 0,
                                "exclusiveMaximum": 1,
                            },
                            "shock_mode": {"enum": ["fixed", "one_sd"]},
                            "shock_size": {"type": "number"},
                            "method": {"enum": ["bootstrap", "asymptotic"]},
                            "draws": {"type": "integer", "minimum": 20, "maximum": 10000},
                        },
                        [],
                    ),
                },
                [],
            ),
            "comparison": obj(
                {
                    "enabled": {"type": "boolean"},
                    "methods": {**array(string), "uniqueItems": True},
                    "identifications": {**array(string), "uniqueItems": True},
                    "scenarios": {
                        **array(
                            {
                                "enum": [
                                    "covid_include",
                                    "end_2019",
                                    "full_sample",
                                    "recent_half_full_sample",
                                    "quarterly_okun",
                                    "extended_var",
                                    "lag_criteria",
                                ]
                            }
                        ),
                        "uniqueItems": True,
                    },
                },
                [],
            ),
            "seed": {"type": "integer", "minimum": 0, "maximum": 2**32 - 1},
        },
        ["schema_version", "snapshot_id", "countries", "series", "frequency", "model"],
    )
    check = {
        "type": "object",
        "required": ["level", "code", "message", "phase"],
        "properties": {
            "level": {"enum": ["ok", "info", "warn", "block"]},
            "code": string,
            "message": string,
            "phase": {"enum": ["preflight", "pre_estimation", "post_estimation"]},
        },
    }
    sample = {
        "type": "object",
        "required": [
            "start",
            "end",
            "nobs",
            "common_nobs",
            "periods",
            "dropped_periods",
            "frequency_conversion",
            "transforms",
        ],
        "properties": {
            "start": {"type": ["string", "null"]},
            "end": {"type": ["string", "null"]},
            "nobs": {"type": "integer", "minimum": 0},
            "common_nobs": {"type": "integer", "minimum": 0},
            "periods": array(string),
            "dropped_periods": array(generic),
            "frequency_conversion": generic,
            "transforms": generic,
        },
    }
    country = {
        "type": "object",
        "required": [
            "country",
            "model_id",
            "status",
            "label",
            "checks",
            "actual_sample",
            "sensitivity",
        ],
        "properties": {
            "country": string,
            "model_id": {"enum": list(MODEL_IDS)},
            "status": {"enum": ["ok", "blocked"]},
            "checks": array(check),
            "actual_sample": sample,
            "sensitivity": {"type": "object", "required": ["status", "variants"]},
        },
    }
    result = {
        "type": "object",
        "required": [
            "schema_version",
            "status",
            "config_hash",
            "snapshot_id",
            "code_version",
            "runtime_ms",
            "label",
            "config",
            "checks",
            "results",
            "actual_samples",
        ],
        "properties": {
            "schema_version": {"const": 1},
            "status": {"enum": ["ok", "partial", "blocked"]},
            "config_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "snapshot_id": string,
            "code_version": string,
            "runtime_ms": {"type": "number", "minimum": 0},
            "config": config,
            "checks": array(check),
            "results": array(country),
            "actual_samples": {"type": "object", "additionalProperties": sample},
        },
    }
    for name, schema in [("analysis_config", config), ("model_result", result)]:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://macrolab.local/schemas/{name}.schema.json",
            **schema,
        }
        (ROOT / "schemas" / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    write_schemas()
