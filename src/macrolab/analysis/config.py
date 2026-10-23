"""Canonical, bounded analysis configuration; no executable code in configuration."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any

MODEL_IDS = (
    "desc.plot",
    "desc.corr",
    "desc.compare",
    "test.adf_kpss_pp",
    "sing.ols",
    "sing.ardl",
    "sing.rolling",
    "test.granger",
    "filter.hp",
    "filter.hamilton",
    "var.ols",
    "ident.recursive",
    "lp.ols",
    "out.hd",
    "ident.external_series",
    "cmp.common_shock",
)
TRANSFORMS = (
    "level",
    "log",
    "diff",
    "log_diff",
    "yoy_pct",
    "yoy_diff",
    "qoq_saar",
    "index_to_base",
    "hp_cycle",
    "hamilton_cycle",
)
ROLES = ("shock", "response", "endogenous", "exogenous", "dependent", "regressor")


class ConfigError(ValueError):
    """A configuration is invalid or requests an unreleased capability."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode()).hexdigest()


def required_concepts(config: dict[str, Any]) -> list[str]:
    """Include source-only series needed by explicitly enabled comparisons."""
    concepts = [str(item["concept_id"]) for item in config["series"]]
    first = config.get("model", {}).get("params", {}).get("first_stage")
    if isinstance(first, dict):
        concepts.extend(required_concepts(first))
    comparison = config.get("comparison", {})
    if comparison.get("enabled", True) and "extended_var" in comparison.get("scenarios", []):
        concepts.extend(["reer", "credit_pnfs"])
    return list(dict.fromkeys(concepts))


def required_countries(config: dict[str, Any]) -> list[str]:
    first = config.get("model", {}).get("params", {}).get("first_stage", {})
    return list(dict.fromkeys([*config["countries"], *first.get("countries", [])]))


def _fields(value: Any, allowed: set[str], required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ConfigError(f"{name}: missing required or unrecognised fields")
    return value


def _period(value: Any, frequency: str) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(
            {"M": r"\d{4}-(0[1-9]|1[0-2])", "Q": r"\d{4}-Q[1-4]", "A": r"\d{4}"}[frequency], value
        )
    )


def normalise_config(value: dict[str, Any]) -> dict[str, Any]:
    """Store every consequential default before hashing; reject unknown capability IDs."""
    c = copy.deepcopy(
        _fields(
            value,
            {
                "schema_version",
                "snapshot_id",
                "countries",
                "series",
                "frequency",
                "aggregation",
                "sample",
                "special_periods",
                "model",
                "identification",
                "outputs",
                "comparison",
                "seed",
            },
            {"schema_version", "snapshot_id", "countries", "series", "frequency", "model"},
            "config",
        )
    )
    if c["schema_version"] != 1 or isinstance(c["schema_version"], bool):
        raise ConfigError("Unsupported schema version")
    if not isinstance(c["snapshot_id"], str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", c["snapshot_id"]
    ):
        raise ConfigError("Invalid snapshot ID")
    countries = c["countries"]
    if (
        not isinstance(countries, list)
        or not 1 <= len(countries) <= 50
        or any(
            not isinstance(s, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,11}", s)
            for s in countries
        )
        or len(set(countries)) != len(countries)
    ):
        raise ConfigError("Select unique country codes")
    if c["frequency"] not in ("M", "Q", "A"):
        raise ConfigError("Frequency must be M, Q or A")
    if not isinstance(c["series"], list) or not 1 <= len(c["series"]) <= 20:
        raise ConfigError("Select one to twenty series")
    concepts = []
    for series in c["series"]:
        _fields(
            series,
            {"concept_id", "role", "transform", "transform_params"},
            {"concept_id", "role", "transform"},
            "series",
        )
        if not isinstance(series["concept_id"], str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,60}", series["concept_id"]
        ):
            raise ConfigError("Invalid concept ID")
        if series["role"] not in ROLES or series["transform"] not in TRANSFORMS:
            raise ConfigError("Unknown role or transformation")
        if series["transform"] == "qoq_saar" and c["frequency"] != "Q":
            raise ConfigError("Annualised quarter-on-quarter growth requires quarterly data")
        transform_params = series.setdefault("transform_params", {})
        _fields(
            transform_params, {"base_period", "lamb", "log", "h", "p"}, set(), "transform_params"
        )
        if "log" in transform_params and not isinstance(transform_params["log"], bool):
            raise ConfigError("Filter log option must be boolean")
        for key in ("h", "p"):
            if key in transform_params and (
                type(transform_params[key]) is not int or not 1 <= transform_params[key] <= 120
            ):
                raise ConfigError(f"Filter {key} must be an integer between 1 and 120")
        if "lamb" in transform_params and (
            type(transform_params["lamb"]) not in (int, float)
            or not 0 < transform_params["lamb"] <= 1e8
        ):
            raise ConfigError("HP smoothing parameter must be positive and at most 1e8")
        if series["transform"] == "index_to_base" and not _period(
            transform_params.get("base_period"), c["frequency"]
        ):
            raise ConfigError("Choose an explicit base period for the index")
        concepts.append(series["concept_id"])
    if len(set(concepts)) != len(concepts):
        raise ConfigError("Each concept may appear only once")
    model = _fields(c["model"], {"id", "params"}, {"id"}, "model")
    if model["id"] not in MODEL_IDS:
        raise ConfigError("This model is not in the validated v0 library")
    if not isinstance(model.setdefault("params", {}), dict):
        raise ConfigError("Model parameters must be an object")
    aggregation = c.setdefault("aggregation", {})
    if (
        not isinstance(aggregation, dict)
        or set(aggregation) - set(concepts)
        or any(v not in ("mean", "last", "sum") for v in aggregation.values())
    ):
        raise ConfigError("Aggregation requires selected concepts and mean/last/sum methods")
    frequency = c["frequency"]
    sample = c.setdefault(
        "sample",
        {"start": {"M": "1999-01", "Q": "1999-Q1", "A": "1999"}[frequency], "end": "latest"},
    )
    _fields(sample, {"start", "end"}, {"start", "end"}, "sample")
    if not _period(sample["start"], frequency) or (
        sample["end"] != "latest" and not _period(sample["end"], frequency)
    ):
        raise ConfigError("Sample periods must use the chosen frequency")
    if sample["end"] != "latest" and sample["end"] < sample["start"]:
        raise ConfigError("Sample end precedes sample start")
    special = c.setdefault("special_periods", {"covid": "include"})
    _fields(special, {"covid", "covid_window", "elb_threshold"}, {"covid"}, "special_periods")
    covid_window = special.setdefault(
        "covid_window",
        {
            "start": {"M": "2020-01", "Q": "2020-Q1", "A": "2020"}[frequency],
            "end": {"M": "2021-06", "Q": "2021-Q2", "A": "2021"}[frequency],
        },
    )
    _fields(covid_window, {"start", "end"}, {"start", "end"}, "covid_window")
    if (
        not all(_period(covid_window[key], frequency) for key in ("start", "end"))
        or covid_window["end"] < covid_window["start"]
    ):
        raise ConfigError("COVID window must use ordered periods at the analysis frequency")
    threshold = special.setdefault("elb_threshold", 0.25)
    if type(threshold) not in (int, float) or not math.isfinite(threshold):
        raise ConfigError("ELB threshold must be finite percentage points")
    if special["covid"] not in ("include", "dummy", "exclude"):
        raise ConfigError("Choose include, dummy or exclude for COVID periods")
    seed = c.setdefault("seed", 20261021)
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ConfigError("Seed must be an unsigned 32-bit integer")
    identification = c.setdefault("identification", None)
    if identification is not None:
        _fields(identification, {"id", "params"}, {"id", "params"}, "identification")
        if identification["id"] not in ("recursive", "ident.recursive"):
            raise ConfigError("Only recursive identification is released in v0")
        if model["id"] not in ("var.ols", "ident.recursive", "out.hd", "ident.external_series"):
            raise ConfigError("Identification requires a VAR model")
        _fields(identification["params"], {"order"}, {"order"}, "identification.params")
        endogenous = [
            s["concept_id"] for s in c["series"] if s["role"] in ("shock", "endogenous", "response")
        ]
        order = identification["params"]["order"]
        if (
            not isinstance(order, list)
            or any(not isinstance(x, str) for x in order)
            or len(order) != len(endogenous)
            or set(order) != set(endogenous)
        ):
            raise ConfigError(
                "Recursive order must contain each selected endogenous variable exactly once"
            )
    if (
        model["id"] in {"ident.recursive", "out.hd", "ident.external_series"}
        and identification is None
    ):
        raise ConfigError("Specify an explicit recursive ordering")
    outputs = c.setdefault("outputs", {})
    _fields(outputs, {"irf", "confidence"}, set(), "outputs")
    confidence = outputs.setdefault("confidence", model["params"].get("confidence", 0.95))
    if type(confidence) not in (int, float) or not 0.5 <= confidence < 1:
        raise ConfigError("Confidence level must be between 0.5 and 1")
    if identification is not None or "irf" in outputs:
        irf = outputs.setdefault("irf", {})
        _fields(
            irf,
            {"horizon", "bands", "shock_size", "shock_mode", "method", "draws"},
            set(),
            "outputs.irf",
        )
        for key, default in {
            "horizon": 12,
            "bands": 0.68,
            "shock_size": 1.0,
            "shock_mode": "fixed",
            "method": "bootstrap",
            "draws": 500,
        }.items():
            irf.setdefault(key, default)
        if type(irf["horizon"]) is not int or not 1 <= irf["horizon"] <= 80:
            raise ConfigError("IRF horizon must be between 1 and 80")
        if type(irf["draws"]) is not int or not 20 <= irf["draws"] <= 10000:
            raise ConfigError("Bootstrap draws must be between 20 and 10000")
        if type(irf["bands"]) not in (int, float) or not 0.5 <= irf["bands"] < 1:
            raise ConfigError("IRF band level must be between 0.5 and 1")
        if (
            type(irf["shock_size"]) not in (int, float)
            or not math.isfinite(irf["shock_size"])
            or irf["shock_size"] == 0
        ):
            raise ConfigError("Shock size must be finite and nonzero")
        if irf["shock_mode"] not in {"fixed", "one_sd"}:
            raise ConfigError("Shock mode must be fixed or one_sd")
        if irf["shock_mode"] == "one_sd" and irf["shock_size"] != 1.0:
            raise ConfigError("one_sd requests exactly +1 standard deviation; set shock_size to 1")
        if irf["method"] not in ("bootstrap", "asymptotic"):
            raise ConfigError("Choose bootstrap or asymptotic IRF bands")
    comparison = c.setdefault("comparison", {"identifications": [], "methods": []})
    _fields(comparison, {"identifications", "methods", "enabled", "scenarios"}, set(), "comparison")
    comparison.setdefault("enabled", True)
    comparison.setdefault("identifications", [])
    comparison.setdefault("methods", [])
    comparison.setdefault("scenarios", [])
    scenarios = comparison["scenarios"]
    supported_scenarios = {
        "covid_include",
        "end_2019",
        "full_sample",
        "recent_half_full_sample",
        "quarterly_okun",
        "extended_var",
        "lag_criteria",
    }
    if (
        not isinstance(scenarios, list)
        or any(not isinstance(s, str) or s not in supported_scenarios for s in scenarios)
        or len(set(scenarios)) != len(scenarios)
    ):
        raise ConfigError("Choose unique supported sensitivity scenarios")
    if not isinstance(comparison["enabled"], bool):
        raise ConfigError("Comparison enabled must be boolean")
    if not isinstance(comparison["methods"], list) or any(
        m not in MODEL_IDS for m in comparison["methods"]
    ):
        raise ConfigError("Comparison requests an unreleased model")
    if not isinstance(comparison["identifications"], list) or any(
        i not in ("recursive", "ident.recursive") for i in comparison["identifications"]
    ):
        raise ConfigError("Only recursive identification is available in v0 comparisons")
    try:
        canonical_json(c)
    except (ValueError, TypeError) as exc:
        raise ConfigError("Configuration must contain finite JSON values") from exc
    return c


def validated_config(value: dict[str, Any]) -> dict[str, Any]:
    """Validate plugin parameters without a heavyweight runtime schema dependency."""
    from macrolab.models.registry import get_plugin

    config = normalise_config(value)
    plugin = get_plugin(config["model"]["id"])
    properties = plugin.params.get("properties", {})
    params = config["model"]["params"]
    frequency = config["frequency"]
    if plugin.id == "filter.hp":
        params.setdefault("lambda", {"M": 129600, "Q": 1600, "A": 6.25}[frequency])
    if plugin.id == "filter.hamilton":
        params.setdefault("horizon", {"M": 24, "Q": 8, "A": 2}[frequency])
        params.setdefault("lags", {"M": 12, "Q": 4, "A": 1}[frequency])
    for series in config["series"]:
        options = series["transform_params"]
        if series["transform"] == "hp_cycle":
            options.setdefault("lamb", {"M": 129600, "Q": 1600, "A": 6.25}[frequency])
            options.setdefault("log", False)
        elif series["transform"] == "hamilton_cycle":
            options.setdefault("h", {"M": 24, "Q": 8, "A": 2}[frequency])
            options.setdefault("p", {"M": 12, "Q": 4, "A": 1}[frequency])
            options.setdefault("log", False)
    if set(params) - set(properties):
        raise ConfigError(
            "Unknown model parameters: " + ", ".join(sorted(set(params) - set(properties)))
        )
    if "confidence" in properties:
        if "confidence" in params and params["confidence"] != config["outputs"]["confidence"]:
            raise ConfigError("Model and output confidence levels must agree")
        params["confidence"] = config["outputs"]["confidence"]
    for key, rule in properties.items():
        if key not in params:
            if "default" in rule:
                params[key] = copy.deepcopy(rule["default"])
            continue
        v = params[key]
        kind = rule.get("type")
        if (
            (kind == "integer" and type(v) is not int)
            or (kind == "number" and type(v) not in (int, float))
            or (kind == "string" and not isinstance(v, str))
            or (kind == "boolean" and not isinstance(v, bool))
            or (kind == "object" and not isinstance(v, dict))
        ):
            raise ConfigError(f"Model parameter {key} has an invalid type")
        if "enum" in rule and v not in rule["enum"]:
            raise ConfigError(f"Invalid choice for {key}")
        if "minimum" in rule and v < rule["minimum"]:
            raise ConfigError(f"{key} is below the minimum")
        if "maximum" in rule and v > rule["maximum"]:
            raise ConfigError(f"{key} exceeds the maximum")
    if plugin.id == "cmp.common_shock":
        first = params.get("first_stage")
        if not isinstance(first, dict) or first.get("model", {}).get("id") not in {
            "var.ols",
            "ident.recursive",
            "ident.external_series",
        }:
            raise ConfigError("Common-shock comparison requires a first-stage recursive VAR config")
        first = validated_config(first)
        if not first.get("identification") or len(first["countries"]) != 1:
            raise ConfigError("First stage needs one country and explicit recursive identification")
        if (
            first["snapshot_id"] != config["snapshot_id"]
            or first["frequency"] != config["frequency"]
        ):
            raise ConfigError("Both stages must use the same snapshot and frequency")
        if roles := [s["concept_id"] for s in config["series"] if s["role"] == "shock"]:
            if roles != ["identified_impulse"]:
                raise ConfigError(
                    "The common impulse must use the generated identified_impulse field"
                )
        params["first_stage"] = first
    if plugin.id in {"lp.ols", "out.hd", "ident.external_series", "cmp.common_shock"}:
        # JavaScript JSON has one numeric type. Normalize integral floats only
        # for the new model contracts; accepted v0 config hashes stay intact.
        def portable_numbers(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: portable_numbers(item) for key, item in value.items()}
            if isinstance(value, list):
                return [portable_numbers(item) for item in value]
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value

        config = portable_numbers(config)
    canonical_json(config)
    return config


def encode_config(config: dict[str, Any]) -> str:
    """Versioned, compressed configuration only; no observations or executable code."""
    import base64
    import zlib

    raw = canonical_json(validated_config(config)).encode()
    if len(raw) > 65536:
        raise ConfigError("Configuration exceeds 64 KiB")
    return "v1." + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def decode_config(token: str) -> dict[str, Any]:
    import base64
    import zlib

    if not isinstance(token, str) or not token.startswith("v1.") or len(token) > 100000:
        raise ConfigError("Invalid or oversized configuration token")
    try:
        encoded = token[3:]
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        decoder = zlib.decompressobj()
        text = decoder.decompress(raw, 65537)
        if len(text) > 65536 or not decoder.eof or decoder.unused_data:
            raise ValueError("Invalid compressed configuration")
        return validated_config(json.loads(text))
    except (ValueError, TypeError, zlib.error) as exc:
        raise ConfigError("Invalid compressed configuration") from exc
