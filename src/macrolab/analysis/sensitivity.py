"""Bounded, explicit v0 sensitivity comparisons using the same model plugins."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import numpy as np

from macrolab.analysis.config import config_hash
from macrolab.analysis.data import input_fingerprint, prepare_country
from macrolab.analysis.g21 import run_configured_plugin
from macrolab.analysis.g31 import lag_criteria_evidence
from macrolab.models.base import AnalysisData, ModelPlugin, check
from macrolab.models.registry import get_plugin

LINEAR = {"sing.ols", "sing.ardl", "sing.rolling"}
VAR = {"var.ols", "ident.recursive"}
SIGN_TOLERANCE = 1e-10


def _sample(data: AnalysisData, result: dict[str, Any] | None = None) -> dict[str, Any]:
    diagnostics = (result or {}).get("diagnostics", {})
    common = list(map(str, data.frame.index))
    periods = list(diagnostics.get("estimated_indices", common))
    sample = deepcopy(data.sample)
    sample.setdefault("dropped_periods", [])
    sample["dropped_periods"].extend(
        {"period": period, "reasons": ["model_initialisation"]}
        for period in common
        if period not in set(periods)
    )
    sample.update(
        {
            "start": periods[0] if periods else None,
            "end": periods[-1] if periods else None,
            "nobs": int(diagnostics.get("nobs", len(periods))),
            "common_nobs": len(common),
            "periods": periods,
            "frequency": data.frequency,
        }
    )
    sample.setdefault("frequency_conversion", {})
    sample.setdefault("transforms", {})
    if "coefficient_sample" in diagnostics:
        sample["coefficient_sample"] = diagnostics["coefficient_sample"]
    return sample


def _inputs_hash(data: AnalysisData) -> tuple[str, str]:
    """Identify source inputs and preparation choices, not fitted/filter floats.

    Retained transformed subsets keep their original preparation configuration;
    their selected periods differ. This does not claim a checksum of computed
    values. Direct synthetic AnalysisData has no source provenance, so its
    fallback is explicitly runtime-specific and is not used for browser parity.
    """
    source_hash = data.sample.get("source_data_sha256")
    if source_hash:
        transforms = {
            concept: {
                key: value
                for key, value in metadata.items()
                if key
                in {
                    "transform",
                    "formula",
                    "params",
                    "input_start",
                    "input_end",
                    "retrospective_filter",
                }
            }
            for concept, metadata in data.sample.get("transforms", {}).items()
        }
        payload = {
            "source_data_sha256": source_hash,
            "country": data.country,
            "frequency": data.frequency,
            "columns": list(data.frame.columns),
            "selected_periods": list(map(str, data.frame.index)),
            "preparation_config": data.sample.get("preparation_config", {}),
            "frequency_conversion": data.sample.get("frequency_conversion", {}),
            "transforms": transforms,
            "fixed_regressors": [] if data.exog is None else list(data.exog.columns),
        }
        return input_fingerprint(payload), "portable_source_inputs_rules_and_selected_periods"
    return config_hash(
        {
            "columns": list(data.frame.columns),
            "periods": list(map(str, data.frame.index)),
            "values": data.frame.to_numpy(dtype=float).tolist(),
            "exog": None
            if data.exog is None
            else {
                "columns": list(data.exog.columns),
                "values": data.exog.to_numpy(dtype=float).tolist(),
            },
        }
    ), "runtime_specific_direct_analysis_data_values"


def _recent(data: AnalysisData) -> AnalysisData:
    start = len(data.frame) // 2
    frame = data.frame.iloc[start:].copy()
    # Dummy columns outside the retained sample must not create rank deficiency.
    exog = None if data.exog is None else data.exog.iloc[start:].copy()
    if exog is not None:
        exog = exog.loc[:, (exog != 0).any(axis=0)]
    sample = {
        **deepcopy(data.sample),
        "sensitivity_subset": "recent half",
        "start": str(frame.index[0]) if len(frame) else None,
        "end": str(frame.index[-1]) if len(frame) else None,
        "nobs": len(frame),
        "periods": list(map(str, frame.index)),
    }
    sample.setdefault("dropped_periods", [])
    sample["dropped_periods"].extend(
        {"period": str(period), "reasons": ["sensitivity_recent_half"]}
        for period in data.frame.index[:start]
    )
    if data.exog is not None:
        sample["omitted_zero_fixed_regressors"] = sorted(
            set(data.exog.columns) - set(exog.columns if exog is not None else [])
        )
    return replace(data, frame=frame, exog=exog, sample=sample, panels={})


def _input_checks(
    plugin: ModelPlugin, data: AnalysisData, config: dict[str, Any]
) -> list[dict[str, Any]]:
    inputs = plugin.inputs
    count = (
        sum(s["role"] in {"shock", "response", "endogenous"} for s in config["series"])
        if config["model"]["id"] in VAR
        else len(config["series"])
    )
    checks = []
    if not int(inputs.get("min_series", 1)) <= count <= int(inputs.get("max_series", 20)):
        checks.append(
            check(
                "block", "series_count", "The requested method needs a different number of series."
            )
        )
    for role, required in inputs.get("required_roles", {}).items():
        if sum(series["role"] == role for series in config["series"]) != required:
            checks.append(
                check(
                    "block",
                    "required_role",
                    f"The requested method requires {required} {role} series.",
                )
            )
    if sum(s["role"] == "regressor" for s in config["series"]) < inputs.get("min_regressors", 0):
        checks.append(
            check("block", "required_role", "The requested method needs more regressors.")
        )
    return checks + plugin.check(data, config)


def _sign(value: float) -> int:
    return 0 if abs(value) <= SIGN_TOLERANCE else 1 if value > 0 else -1


def _metrics(result: dict[str, Any]) -> dict[str, Any]:
    if "irf" in result:
        irf = result["irf"]
        values, lower, upper = (
            np.asarray(irf[key], dtype=float) for key in ("values", "lower", "upper")
        )
        if not (values.shape == lower.shape == upper.shape) or not all(
            np.isfinite(a).all() for a in (values, lower, upper)
        ):
            raise ValueError("Sensitivity requires finite aligned IRF values and intervals")
        responses = []
        for column, name in enumerate(irf["variables"]):
            peak = int(np.argmax(np.abs(values[:, column])))
            excludes = (lower[:, column] > 0) | (upper[:, column] < 0)
            responses.append(
                {
                    "variable": name,
                    "peak_horizon": irf["periods"][peak],
                    "peak_response": float(values[peak, column]),
                    "peak_absolute_response": float(abs(values[peak, column])),
                    "lower_at_peak": float(lower[peak, column]),
                    "upper_at_peak": float(upper[peak, column]),
                    "band_excludes_zero_at_peak": bool(excludes[peak]),
                    "band_excludes_zero_horizons": [
                        int(irf["periods"][i]) for i in np.flatnonzero(excludes)
                    ],
                    "periods": list(irf["periods"]),
                    "values": values[:, column].tolist(),
                }
            )
        return {
            "responses": responses,
            "shock": irf["shock"],
            "shock_size": irf["shock_size"],
            "band_level": irf["band_level"],
            "band_method": irf["band_method"],
            "shock_normalization": irf.get("shock_normalization", {}),
        }
    coefficient_rows = [
        {key: row[key] for key in ("term", "estimate", "lower", "upper") if key in row}
        for row in result.get("coefficients_table", [])
    ]
    if any(
        not np.isfinite([row.get(key, np.nan) for key in ("estimate", "lower", "upper")]).all()
        for row in coefficient_rows
    ):
        raise ValueError("Sensitivity requires finite coefficient estimates and intervals")
    return {"coefficients": coefficient_rows}


def _variant(
    identifier: str,
    data: AnalysisData,
    config: dict[str, Any],
    changes: list[str],
    *,
    result: dict[str, Any] | None = None,
    extra_checks: list[dict[str, Any]] | None = None,
    informative_point_comparison: bool = True,
    fixed_shock_size: float | None = None,
) -> dict[str, Any]:
    prepared_hash, hash_basis = _inputs_hash(data)
    entry: dict[str, Any] = {
        "variant_id": identifier,
        "model_id": config["model"]["id"],
        "changes": changes,
        "config": config,
        "config_hash": config_hash(config),
        "prepared_inputs_sha256": prepared_hash,
        "prepared_inputs_hash_basis": hash_basis,
        "sample": _sample(data),
        "informative_point_comparison": informative_point_comparison,
    }
    try:
        plugin = get_plugin(config["model"]["id"])
        checks = _input_checks(plugin, data, config) + (extra_checks or [])
        entry["checks"] = checks
        if any(item["level"] == "block" for item in checks):
            return {
                **entry,
                "status": "blocked",
                "reason": "Alternative did not pass its input checks.",
            }
        fitted = (
            result
            if result is not None
            else run_configured_plugin(
                data, config, fixed_shock_size=fixed_shock_size, plugin=plugin
            )
        )
        from macrolab.checks.core import postfit_checks

        checks.extend(postfit_checks(data, config, fitted))
        if any(item["level"] == "block" for item in checks):
            return {
                **entry,
                "checks": checks,
                "status": "blocked",
                "reason": "Alternative failed fitted-model checks.",
            }
        return {
            **entry,
            "status": "available",
            "sample": _sample(data, fitted),
            "metrics": _metrics(fitted),
            "diagnostics": {
                key: value
                for key, value in fitted.get("diagnostics", {}).items()
                if key
                in {
                    "selected_lags",
                    "lag_selection",
                    "parameter_count_per_equation",
                    "nobs",
                    "residual_degrees_of_freedom",
                    "stable",
                    "companion_spectral_radius",
                    "information_criteria",
                }
            },
            "resolved_config": fitted.get("resolved_config", {}),
        }
    except (ValueError, KeyError, ArithmeticError, RuntimeError, np.linalg.LinAlgError) as exc:
        return {
            **entry,
            "status": "failed",
            "checks": entry.get("checks", []),
            "reason": str(exc),
            "error_type": type(exc).__name__,
        }


def _unsupported(identifier: str, model_id: str, reason: str) -> dict[str, Any]:
    return {
        "variant_id": identifier,
        "model_id": model_id,
        "status": "unsupported",
        "reason": reason,
        "checks": [],
    }


def _coefficient_summary(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = variants[0]
    baseline_model = baseline["model_id"]
    rows = []
    for coefficient in baseline.get("metrics", {}).get("coefficients", []):
        term = coefficient["term"]
        if term == "const" or term == "trend" or term.startswith("covid_"):
            continue
        comparisons = []
        for variant in variants[1:]:
            same_estimand = variant["model_id"] == baseline_model or {
                variant["model_id"],
                baseline_model,
            } <= {"sing.ols", "sing.rolling"}
            if (
                variant["status"] != "available"
                or not same_estimand
                or not variant.get("informative_point_comparison")
            ):
                continue
            matching = next(
                (row for row in variant["metrics"].get("coefficients", []) if row["term"] == term),
                None,
            )
            if matching is not None:
                comparisons.append((variant, matching))
        baseline_sign = _sign(coefficient["estimate"])
        share = (
            sum(_sign(row["estimate"]) == baseline_sign for _, row in comparisons)
            / len(comparisons)
            if comparisons and baseline_sign
            else None
        )
        estimates = [coefficient["estimate"]] + [row["estimate"] for _, row in comparisons]
        rows.append(
            {
                "term": term,
                "baseline_estimate": coefficient["estimate"],
                "estimate_range": [min(estimates), max(estimates)],
                "sign_agreement_share": share,
                "comparable_alternatives": len(comparisons),
                "variant_ids": [variant["variant_id"] for variant, _ in comparisons],
                "baseline_interval_excludes_zero": coefficient["lower"] > 0
                or coefficient["upper"] < 0,
                "interval_exclusion_share": sum(
                    row["lower"] > 0 or row["upper"] < 0 for _, row in comparisons
                )
                / len(comparisons)
                if comparisons
                else None,
            }
        )
    return rows


def _response_summary(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for baseline in variants[0].get("metrics", {}).get("responses", []):
        comparisons = []
        for variant in variants[1:]:
            if variant["status"] != "available" or not variant.get("informative_point_comparison"):
                continue
            response = next(
                (
                    row
                    for row in variant["metrics"].get("responses", [])
                    if row["variable"] == baseline["variable"]
                ),
                None,
            )
            if response is not None:
                comparisons.append((variant, response))
        horizon = baseline["peak_horizon"]
        baseline_sign = _sign(baseline["peak_response"])
        at_common_horizon = [row["values"][row["periods"].index(horizon)] for _, row in comparisons]
        peak_sizes = [baseline["peak_absolute_response"]] + [
            row["peak_absolute_response"] for _, row in comparisons
        ]
        peak_times = [horizon] + [row["peak_horizon"] for _, row in comparisons]
        signed_peaks = [baseline["peak_response"]] + [
            row["peak_response"] for _, row in comparisons
        ]
        rows.append(
            {
                "variable": baseline["variable"],
                "baseline_peak_horizon": horizon,
                "baseline_peak_response": baseline["peak_response"],
                "peak_absolute_response_range": [min(peak_sizes), max(peak_sizes)],
                "peak_response_range": [min(signed_peaks), max(signed_peaks)],
                "peak_horizon_range": [min(peak_times), max(peak_times)],
                "sign_comparison_horizon": horizon,
                "sign_agreement_share": sum(
                    _sign(value) == baseline_sign for value in at_common_horizon
                )
                / len(comparisons)
                if comparisons and baseline_sign
                else None,
                "comparable_alternatives": len(comparisons),
                "variant_ids": [variant["variant_id"] for variant, _ in comparisons],
                "baseline_band_excludes_zero_at_peak": baseline["band_excludes_zero_at_peak"],
                "alternative_own_peak_band_exclusion_share": sum(
                    row["band_excludes_zero_at_peak"] for _, row in comparisons
                )
                / len(comparisons)
                if comparisons
                else None,
            }
        )
    return rows


def build_sensitivity(
    data: AnalysisData,
    config: dict[str, Any],
    baseline: dict[str, Any],
    *,
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a small predefined set; failed/blocked alternatives remain visible."""
    comparison = config.get("comparison", {})
    if comparison.get("enabled", True) is False:
        return {
            "status": "disabled",
            "enabled": False,
            "reason": "Sensitivity was explicitly disabled in the analysis configuration.",
            "variants": [],
        }
    model_id = config["model"]["id"]
    requested = list(dict.fromkeys(comparison.get("methods", [])))
    if model_id not in LINEAR | VAR:
        return {
            "status": "not_applicable",
            "enabled": True,
            "reason": "This descriptive, test or filter result has no supported coefficient "
            "or identified-shock sensitivity comparison in v0.",
            "variants": [
                _unsupported(
                    f"requested_{method}",
                    method,
                    "Cross-method estimand comparison is unavailable for this result type.",
                )
                for method in requested
            ],
        }
    if model_id in VAR and "irf" not in baseline:
        return {
            "status": "not_applicable",
            "enabled": True,
            "reason": "Shock sensitivity requires explicit recursive identification; "
            "a reduced-form VAR does not define an identified shock.",
            "variants": [
                _unsupported(
                    f"requested_{method}",
                    method,
                    "Specify recursive identification before comparing shock responses.",
                )
                for method in requested
            ],
        }
    variants = [_variant("baseline", data, deepcopy(config), [], result=baseline)]
    seen = {(config_hash(config), tuple(map(str, data.frame.index)))}

    def add(
        identifier: str,
        candidate_data: AnalysisData,
        candidate: dict[str, Any],
        changes: list[str],
        **options: Any,
    ) -> None:
        identity = (config_hash(candidate), tuple(map(str, candidate_data.frame.index)))
        if identity in seen:
            variants.append(
                {
                    "variant_id": identifier,
                    "model_id": candidate["model"]["id"],
                    "status": "duplicate",
                    "reason": "Configuration and sample match an already reported variant.",
                    "checks": [],
                }
            )
            return
        seen.add(identity)
        variants.append(_variant(identifier, candidate_data, candidate, changes, **options))

    if model_id in LINEAR:
        opposite = (
            "HC1" if config["model"].get("params", {}).get("covariance", "HAC") == "HAC" else "HAC"
        )
        candidate = deepcopy(config)
        candidate["model"].setdefault("params", {})["covariance"] = opposite
        add(
            f"covariance_{opposite}",
            data,
            candidate,
            ["covariance only; point estimates are mechanically unchanged"],
            informative_point_comparison=False,
        )
        recent = _recent(data)
        sample_checks = (
            []
            if len(recent.frame) >= 40
            else [
                check(
                    "block",
                    "small_sample",
                    "The recent-half sensitivity sample requires at least 40 observations.",
                )
            ]
        )
        candidate = deepcopy(config)
        candidate.setdefault("sample", {}).update(
            {
                "start": str(recent.frame.index[0]) if len(recent.frame) else None,
                "end": str(recent.frame.index[-1]) if len(recent.frame) else None,
            }
        )
        fixed_terminal_window = (
            model_id == "sing.rolling"
            and config["model"].get("params", {}).get("mode", "rolling") == "rolling"
        )
        changes = ["recent half of the prepared sample"]
        if fixed_terminal_window:
            changes.append("terminal rolling-window coefficient sample is unchanged")
        if "recent_half_full_sample" not in comparison.get("scenarios", []):
            add(
                "recent_half",
                recent,
                candidate,
                changes,
                extra_checks=sample_checks,
                informative_point_comparison=not fixed_terminal_window,
            )
    else:
        order = list(baseline["irf"]["variables"])
        for identifier, ordering in (
            ("reverse_order", list(reversed(order))),
            ("rotate_order", order[1:] + order[:1]),
        ):
            candidate = deepcopy(config)
            candidate["identification"] = {"id": "recursive", "params": {"order": ordering}}
            add(
                identifier,
                data,
                candidate,
                ["recursive contemporaneous ordering; baseline physical shock size held fixed"],
                fixed_shock_size=baseline["irf"]["shock_size"],
            )
        for lag in (2, 4):
            baseline_lag = baseline.get("diagnostics", {}).get("selected_lags")
            original_params = config["model"].get("params", {})
            if baseline_lag == lag and original_params.get(
                "lag_selection", original_params.get("ic", "fixed")
            ) in (None, "fixed"):
                variants.append(
                    {
                        "variant_id": f"lags_{lag}",
                        "model_id": model_id,
                        "status": "duplicate",
                        "reason": "The baseline already uses this fixed lag order.",
                        "checks": [],
                    }
                )
                continue
            candidate = deepcopy(config)
            candidate["model"].setdefault("params", {}).update(
                {"lags": lag, "lag_selection": "fixed"}
            )
            candidate["model"]["params"].pop("ic", None)
            add(
                f"lags_{lag}",
                data,
                candidate,
                [f"fixed lag order {lag}; baseline physical shock size held fixed"],
                fixed_shock_size=baseline["irf"]["shock_size"],
            )
    for method in requested:
        try:
            plugin = get_plugin(method)
        except ValueError as exc:
            variants.append(_unsupported(f"requested_{method}", method, str(exc)))
            continue
        same_family = (method in LINEAR and model_id in LINEAR) or (
            method in VAR and model_id in VAR
        )
        if not same_family:
            variants.append(
                _unsupported(
                    f"requested_{method}",
                    method,
                    "This method does not share the current roles and estimand; "
                    "no automatic reinterpretation is made.",
                )
            )
            continue
        if method in VAR:
            variants.append(
                {
                    "variant_id": f"requested_{method}",
                    "model_id": method,
                    "status": "duplicate",
                    "reason": "With the same recursive identification "
                    "these v0 IDs invoke the same VAR estimator.",
                    "checks": [],
                }
            )
            continue
        candidate = deepcopy(config)
        allowed = plugin.params.get("properties", {})
        candidate["model"] = {
            "id": method,
            "params": {
                key: value
                for key, value in config["model"].get("params", {}).items()
                if key in allowed
            },
        }
        if method == "sing.rolling":
            candidate["model"]["params"].setdefault("window", 40)
        for key, rule in allowed.items():
            if "default" in rule:
                candidate["model"]["params"].setdefault(key, deepcopy(rule["default"]))
        add(f"requested_{method}", data, candidate, ["explicitly requested v0 method"])
    criteria_evidence: dict[str, Any] | None = None
    for scenario in comparison.get("scenarios", []):
        if scenario == "lag_criteria":
            if model_id not in VAR or "irf" not in baseline:
                variants.append(
                    _unsupported(scenario, model_id, "Lag criteria require an identified VAR.")
                )
                continue
            try:
                criteria_evidence = lag_criteria_evidence(data, config)
                for criterion, lag in criteria_evidence["selected_lags"].items():
                    candidate = deepcopy(config)
                    candidate["model"]["params"].update(
                        {
                            "lag_selection": "hq" if criterion == "hqic" else criterion,
                            "maxlags": criteria_evidence["candidate_lags"][-1],
                        }
                    )
                    equivalent = next(
                        (
                            v
                            for v in variants
                            if v["status"] == "available"
                            and v.get("diagnostics", {}).get("selected_lags") == lag
                            and v.get("prepared_inputs_sha256")
                            == variants[0]["prepared_inputs_sha256"]
                            and v["config"].get("identification") == candidate.get("identification")
                        ),
                        None,
                    )
                    if equivalent is not None:
                        variants.append(
                            {
                                "variant_id": f"lag_{criterion}",
                                "model_id": model_id,
                                "status": "duplicate",
                                "selected_lags": lag,
                                "reason": f"{criterion.upper()} selects lag {lag}; "
                                "already fitted as "
                                f"{equivalent['variant_id']}; default unchanged.",
                                "equivalent_variant": equivalent["variant_id"],
                                "sample": deepcopy(equivalent["sample"]),
                                "checks": deepcopy(equivalent["checks"]),
                                "diagnostics": deepcopy(equivalent.get("diagnostics", {})),
                                "config": candidate,
                                "config_hash": config_hash(candidate),
                            }
                        )
                    else:
                        add(
                            f"lag_{criterion}",
                            data,
                            candidate,
                            [
                                f"{criterion.upper()} chooses lag {lag} from bounded "
                                "common-sample candidates; default unchanged",
                                "baseline physical shock size held fixed",
                            ],
                            fixed_shock_size=baseline["irf"]["shock_size"],
                        )
            except (ValueError, KeyError, ArithmeticError, RuntimeError) as exc:
                criteria_evidence = {"status": "failed", "reason": str(exc)}
                variants.append(
                    {
                        "variant_id": scenario,
                        "model_id": model_id,
                        "status": "failed",
                        "reason": str(exc),
                        "checks": [],
                    }
                )
            continue
        if bundle is None:
            variants.append(
                _unsupported(
                    scenario,
                    model_id,
                    "The original source bundle is required to reprepare this scenario.",
                )
            )
            continue
        candidate = deepcopy(config)
        changes = []
        frequency = config["frequency"]
        if scenario == "extended_var":
            endogenous = {
                s["concept_id"]
                for s in candidate["series"]
                if s["role"] in {"shock", "response", "endogenous"}
            }
            if model_id not in VAR or endogenous != {"gdp_real", "cpi", "unemp", "policy_rate"}:
                variants.append(
                    _unsupported(
                        scenario,
                        model_id,
                        "Extended VAR requires the four-variable GDP, CPI, unemployment "
                        "and policy-rate system.",
                    )
                )
                continue
            if any(s["concept_id"] in {"reer", "credit_pnfs"} for s in candidate["series"]):
                variants.append(
                    _unsupported(
                        scenario,
                        model_id,
                        "REER or credit is already assigned another role; "
                        "no automatic reassignment.",
                    )
                )
                continue
            candidate["series"].extend(
                [
                    {
                        "concept_id": "reer",
                        "role": "endogenous",
                        "transform": "log",
                        "transform_params": {},
                    },
                    {
                        "concept_id": "credit_pnfs",
                        "role": "endogenous",
                        "transform": "level",
                        "transform_params": {},
                    },
                ]
            )
            candidate["aggregation"].update({"reer": "mean", "credit_pnfs": "mean"})
            ordering = candidate["identification"]["params"]["order"]
            position = ordering.index("policy_rate")
            ordering[position:position] = ["reer", "credit_pnfs"]
            changes = [
                "add log REER and credit in levels before policy in the recursive ordering",
                "retain baseline lags and physical shock size; reprepare actual common sample",
            ]
        elif scenario == "covid_include":
            candidate["special_periods"]["covid"] = "include"
            changes = ["include COVID periods without intervention dummies"]
        elif scenario == "end_2019":
            candidate["sample"]["end"] = {"M": "2019-12", "Q": "2019-Q4", "A": "2019"}[frequency]
            changes = ["end the estimation sample in 2019"]
        elif scenario in {"full_sample", "recent_half_full_sample"}:
            candidate["sample"] = {
                "start": {"M": "1999-01", "Q": "1999-Q1", "A": "1999"}[frequency],
                "end": "latest",
            }
            changes = [
                "prepare the full available sample from 1999; recompute filters through its own end"
            ]
        elif scenario == "quarterly_okun":
            specs = {s["concept_id"]: s for s in candidate["series"]}
            if (
                frequency != "Q"
                or specs.get("unemp", {}).get("role") != "dependent"
                or specs.get("gdp_real", {}).get("role") != "regressor"
            ):
                variants.append(
                    _unsupported(
                        scenario,
                        model_id,
                        "Quarterly Okun comparison requires quarterly unemployment "
                        "as dependent and GDP as regressor.",
                    )
                )
                continue
            specs["unemp"]["transform"] = "diff"
            specs["gdp_real"]["transform"] = "log_diff"
            changes = [
                "quarterly unemployment-rate change on 100 times quarterly GDP log change "
                "(not annualised); different horizon estimand"
            ]
        else:
            variants.append(_unsupported(scenario, model_id, "Unsupported scenario."))
            continue
        try:
            candidate_data, scenario_checks = prepare_country(candidate, bundle, data.country)
            if scenario == "recent_half_full_sample":
                candidate_data = _recent(candidate_data)
                candidate["sample"] = {
                    "start": candidate_data.sample["start"],
                    "end": candidate_data.sample["end"],
                }
                changes.append(
                    "estimate on the recent half of the full prepared sample; "
                    "retain full-sample filter values"
                )
                if len(candidate_data.frame) < 40:
                    scenario_checks.append(
                        check(
                            "block",
                            "small_sample",
                            "Recent-half sensitivity requires at least 40 observations.",
                        )
                    )
            from macrolab.checks.core import evaluate_checks

            scenario_checks.extend(evaluate_checks(candidate_data, candidate, bundle))
            add(
                scenario,
                candidate_data,
                candidate,
                changes,
                extra_checks=scenario_checks,
                informative_point_comparison=scenario != "quarterly_okun",
                fixed_shock_size=baseline["irf"]["shock_size"]
                if scenario == "extended_var"
                else None,
            )
        except (ValueError, KeyError, ArithmeticError, RuntimeError) as exc:
            variants.append(
                {
                    "variant_id": scenario,
                    "model_id": model_id,
                    "status": "failed",
                    "reason": str(exc),
                    "checks": [],
                    "config": candidate,
                }
            )
    identified = "irf" in baseline
    return {
        "status": "available",
        "enabled": True,
        "variants": variants,
        "summary": _response_summary(variants) if identified else _coefficient_summary(variants),
        "lag_criteria": criteria_evidence,
        "comparison_rule": (
            "For each response, compare signs at the baseline absolute-peak horizon, "
            "including impact. "
            "Signed peak_response_range uses each variant's signed response at its own "
            "absolute peak; peak_absolute_response_range uses magnitudes. Bands are pointwise; "
            "exclusion at a selected peak is descriptive."
            if identified
            else "Compare matching non-intercept coefficient terms within the same estimand. "
            "Covariance-only changes and identical terminal rolling samples "
            "are excluded from point-estimate agreement."
        ),
        "sign_zero_tolerance": SIGN_TOLERANCE,
        "limitations": [
            "Agreement across this bounded set is descriptive sensitivity evidence, "
            "not proof of causal identification or specification validity.",
            "Blocked, failed, duplicate and unsupported alternatives are visible "
            "and excluded from agreement denominators.",
            "Recent-half comparisons retain prior transformations; "
            "they test estimation-sample sensitivity, "
            "not re-estimation of retrospective filters.",
        ],
    }
