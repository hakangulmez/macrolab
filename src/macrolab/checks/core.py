"""Shared pre-fit and post-fit checks without engine or filesystem dependencies.

Data checks own coverage/conversion; plugins own sample size, rank and Granger
language. These checks never transform data or change a configuration.
"""

from __future__ import annotations

import math
import warnings
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss  # type: ignore[import-untyped]

from macrolab.models.base import AnalysisConfig, AnalysisData, check, sample_size_check

# Test-enforced mirror of configs/checks.yaml; usable in the browser without I/O.
DEFAULTS: dict[str, Any] = {
    "stationarity_alpha": 0.05,
    "stationarity_min_observations": 20,
    "elb_threshold": 0.25,
    "covid_start": "2020-01-01",
    "covid_end": "2021-06-30",
    "shock_quantile_low": 0.05,
    "shock_quantile_high": 0.95,
}
REGRESSION_MODELS = {
    "sing.ols",
    "sing.ardl",
    "sing.rolling",
    "var.ols",
    "ident.recursive",
    "lp.ols",
    "out.hd",
    "ident.external_series",
    "cmp.common_shock",
    "panel.fe",
    "panel.lp",
    "bvar.minn",
}
DYNAMIC_MODELS = {
    "sing.ardl",
    "test.granger",
    "var.ols",
    "ident.recursive",
    "lp.ols",
    "out.hd",
    "ident.external_series",
    "cmp.common_shock",
    "panel.fe",
    "panel.lp",
    "bvar.minn",
}
VAR_MODELS = {"var.ols", "ident.recursive", "out.hd", "ident.external_series"}
ENDOGENOUS_ROLES = {"shock", "endogenous", "response"}


def _model_id(config: AnalysisConfig) -> str:
    return str(config.get("model", {}).get("id", ""))


def _periods(data: AnalysisData) -> pd.PeriodIndex:
    return pd.PeriodIndex(data.frame.index, freq="Y" if data.frequency == "A" else data.frequency)


def _label(period: pd.Period) -> str:
    return str(period).replace("Q", "-Q")


def _input_checks(data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
    from macrolab.models.registry import get_plugin

    try:
        inputs = get_plugin(_model_id(config)).inputs
    except ValueError as exc:
        return [check("block", "model_inputs", str(exc))]
    series = config.get("series", [])
    names = [str(item["concept_id"]) for item in series]
    roles = Counter(str(item.get("role", "")) for item in series)
    output: list[dict[str, Any]] = []
    count = (
        sum(roles[role] for role in ENDOGENOUS_ROLES)
        if _model_id(config) in VAR_MODELS
        else len(names)
    )
    low, high = inputs.get("min_series", 1), inputs.get("max_series", 20)
    if not low <= count <= high:
        output.append(
            check(
                "block",
                "model_inputs",
                f"Choose between {low} and {high} series.",
                selected=count,
                minimum=low,
                maximum=high,
            )
        )
    if len(set(names)) != len(names):
        output.append(check("block", "model_inputs", "Each selected concept must be unique."))
    required_roles = inputs.get("required_roles", {})
    for role, required in required_roles.items():
        if roles[role] != required:
            output.append(
                check(
                    "block",
                    "model_roles",
                    f"Assign exactly {required} series to {role}.",
                    role=role,
                    required=required,
                    selected=roles[role],
                )
            )
    if roles["regressor"] < inputs.get("min_regressors", 0):
        output.append(
            check(
                "block",
                "model_roles",
                "Choose at least one regressor.",
                role="regressor",
                selected=roles["regressor"],
            )
        )
    if _model_id(config) in VAR_MODELS:
        if sum(roles[role] for role in ENDOGENOUS_ROLES) < 2:
            output.append(
                check("block", "model_roles", "VAR requires at least two endogenous series.")
            )
        if any(role not in ENDOGENOUS_ROLES | {"exogenous"} for role in roles):
            output.append(
                check(
                    "block",
                    "model_roles",
                    "Use shock, response, endogenous or exogenous VAR roles.",
                )
            )
        if config.get("identification") and roles["shock"] != 1 and "shock" not in required_roles:
            output.append(
                check(
                    "block",
                    "model_roles",
                    "Recursive identification requires exactly one shock series.",
                )
            )
    elif inputs.get("min_regressors", 0):
        if any(role not in {"dependent", "regressor"} for role in roles):
            output.append(
                check("block", "model_roles", "Use dependent and regressor roles for this model.")
            )
    frequency = config.get("frequency", data.frequency)
    if frequency != data.frequency or frequency not in inputs.get("frequencies", ["M", "Q", "A"]):
        output.append(
            check(
                "block",
                "freq_mismatch",
                "The prepared frequency is incompatible with this model or configuration.",
            )
        )
    # Multiple selected countries mean separate fits, not a pooled panel.
    if len(data.panels) > 1 and not inputs.get("cross_country", False):
        output.append(
            check(
                "block",
                "model_inputs",
                "This model estimates each country separately; it cannot pool country panels.",
            )
        )
    return output


def _stationarity(data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
    if _model_id(config) not in REGRESSION_MODELS:
        return []
    output = []
    trend = config.get("model", {}).get("params", {}).get("trend", "c")
    # KPSS lacks a no-intercept test: diagnostics use a common constant in that case.
    test_trend = "ct" if trend == "ct" else "c"
    alpha = DEFAULTS["stationarity_alpha"]
    for spec in config.get("series", []):
        cid = spec["concept_id"]
        role = spec.get("role")
        if spec.get("transform") not in {"level", "log", "index_to_base"} or cid not in data.frame:
            continue
        values = data.frame[cid].to_numpy(dtype=float)
        if (
            len(values) < DEFAULTS["stationarity_min_observations"]
            or not np.isfinite(values).all()
            or np.ptp(values) == 0
        ):
            output.append(
                check(
                    "info",
                    "stationarity_unavailable",
                    "Stationarity diagnostics require at least 20 finite, varying observations.",
                    concept_id=cid,
                    role=role,
                )
            )
            continue
        try:
            with warnings.catch_warnings(record=True) as reported:
                warnings.simplefilter("always")
                adf = adfuller(values, regression=test_trend, autolag="AIC")
                stationary = kpss(values, regression=test_trend, nlags="auto")
            adf_p, kpss_p = float(adf[1]), float(stationary[1])
            if not math.isfinite(adf_p) or not math.isfinite(kpss_p):
                raise ValueError("Stationarity tests returned nonfinite p-values")
            detail = {
                "concept_id": cid,
                "role": role,
                "alpha": alpha,
                "deterministic_terms": test_trend,
                "adf_p_value": adf_p,
                "kpss_p_value": kpss_p,
                "adf_lags": int(adf[2]),
                "kpss_lags": int(stationary[2]),
                "diagnostic_warnings": list(dict.fromkeys(str(item.message) for item in reported)),
            }
        except (ValueError, np.linalg.LinAlgError, OverflowError, ZeroDivisionError) as exc:
            output.append(
                check("info", "stationarity_unavailable", str(exc), concept_id=cid, role=role)
            )
            continue
        unit_root, rejects_stationarity = adf_p >= alpha, kpss_p < alpha
        if unit_root and rejects_stationarity:
            output.append(
                check(
                    "info" if role == "exogenous" else "warn",
                    "nonstationary_level",
                    "This series looks non-stationary in levels; consider growth rates "
                    "or a cointegration model. These tests do not establish "
                    "cointegration.",
                    fix={"concept_id": cid, "transform": "diff"},
                    **detail,
                )
            )
        elif unit_root != rejects_stationarity:
            output.append(
                check(
                    "info",
                    "stationarity_inconclusive",
                    "ADF and KPSS give conflicting evidence; the series is not "
                    "certified stationary.",
                    **detail,
                )
            )
    return output


def _policy_checks(
    data: AnalysisData, config: AnalysisConfig, bundle: dict[str, Any] | None
) -> list[dict[str, Any]]:
    periods = _periods(data)
    if periods.empty:
        return []
    selected = {s["concept_id"]: s for s in config.get("series", [])}
    policy_ids = set(selected) & {"policy_rate", "us_policy_rate"}
    if not policy_ids:
        return []
    output = []
    country = (bundle or {}).get("countries", {}).get(data.country, {})
    metadata = country.get("metadata", {})
    adoption = metadata.get("euro_adoption")
    if "policy_rate" in selected and selected["policy_rate"].get("role") == "shock":
        starts, ends = periods.start_time.min(), periods.end_time.max()
        adoption_date = pd.Timestamp(adoption) if adoption else None
        if (
            data.country != "EA"
            and metadata.get("monetary_union") == "EA"
            and (adoption_date is None or ends >= adoption_date)
        ):
            output.append(
                check(
                    "warn",
                    "shared_rate",
                    "After euro adoption, this country's policy shock is applied to "
                    "the shared ECB rate, not an independent national rate.",
                    euro_adoption=adoption,
                    monetary_union="EA",
                )
            )
        if adoption_date is not None and starts < adoption_date <= ends:
            first_full = pd.Period(
                adoption_date, freq="Y" if data.frequency == "A" else data.frequency
            )
            if first_full.start_time < adoption_date:
                first_full += 1
            output.append(
                check(
                    "warn",
                    "pre_euro_break",
                    "The policy rate changes from national to ECB at euro adoption.",
                    euro_adoption=adoption,
                    fix={"sample": {"start": _label(first_full)}},
                )
            )
    threshold = float(
        config.get("special_periods", {}).get("elb_threshold", DEFAULTS["elb_threshold"])
    )
    if not math.isfinite(threshold):
        return output + [
            check("block", "invalid_elb_threshold", "The lower-bound threshold must be finite.")
        ]
    for cid in sorted(policy_ids):
        source = country.get("series", {}).get(cid, {})
        rows = source.get("observations", [])
        native_frequency = source.get("metadata", {}).get(
            "frequency", data.metadata.get(cid, {}).get("frequency", data.frequency)
        )
        near: list[str] = []
        evidence = "native_observations"
        if rows:
            target_set = set(periods)
            for row in rows:
                native = pd.Period(
                    row[0], freq="Y" if native_frequency == "A" else native_frequency
                )
                # Every source month contributing to an effective period, not its mean.
                if (
                    native.asfreq("Y" if data.frequency == "A" else data.frequency, how="end")
                    in target_set
                    and float(row[1]) <= threshold
                ):
                    near.append(str(row[0]))
        elif cid in data.frame and selected[cid].get("transform") == "level":
            near = [str(p) for p, value in data.frame[cid].items() if float(value) <= threshold]
            evidence = "prepared_levels_only"
        else:
            output.append(
                check(
                    "info",
                    "elb_unavailable",
                    "Original policy-rate levels are unavailable; the lower-bound "
                    "check cannot use transformed rates.",
                    concept_id=cid,
                )
            )
            continue
        if near:
            output.append(
                check(
                    "warn",
                    "elb_period",
                    "Rates were near or below zero; consider a shorter sample. Shadow "
                    "rates are not available in MacroLab.",
                    concept_id=cid,
                    threshold=threshold,
                    threshold_units="percentage points",
                    periods=near,
                    evidence=evidence,
                    native_frequency=native_frequency,
                )
            )
        if (
            evidence == "prepared_levels_only"
            and data.sample.get("frequency_conversion", {}).get(cid, {}).get("method", "none")
            != "none"
        ):
            output.append(
                check(
                    "info",
                    "elb_resolution_limited",
                    "Only aggregated policy-rate levels are available; averaging may "
                    "conceal lower-bound months.",
                    concept_id=cid,
                )
            )
    return output


def _covid_checks(data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
    periods = _periods(data)
    window = config.get("special_periods", {}).get("covid_window", {})
    start = (
        pd.Period(window["start"], freq=data.frequency).start_time
        if window
        else pd.Timestamp(DEFAULTS["covid_start"])
    )
    end = (
        pd.Period(window["end"], freq=data.frequency).end_time
        if window
        else pd.Timestamp(DEFAULTS["covid_end"])
    )
    mask = (periods.start_time <= end) & (periods.end_time >= start)
    affected = [_label(p) for p in periods[mask]]
    mode = config.get("special_periods", {}).get("covid", "include")
    excluded = [
        item["period"]
        for item in data.sample.get("dropped_periods", [])
        if "covid_excluded" in item.get("reasons", [])
    ]
    if mode not in {"include", "dummy", "exclude"}:
        return [
            check("block", "covid_treatment", "Choose include, dummy or exclude for COVID periods.")
        ]
    if mode == "exclude":
        if affected:
            return [
                check(
                    "block",
                    "covid_exclusion_failed",
                    "COVID periods remain despite the exclusion request.",
                    periods=affected,
                )
            ]
        if excluded:
            return [
                check(
                    "info",
                    "covid_period",
                    "COVID periods were excluded; calendar gaps are not treated as "
                    "consecutive observations.",
                    treatment=mode,
                    periods=excluded,
                )
            ]
        return []
    if not affected:
        return []
    if mode == "include":
        return [
            check(
                "warn",
                "covid_period",
                "COVID periods can dominate estimates; choose include, period dummies or exclude.",
                treatment=mode,
                periods=affected,
                fix={"special_periods": {"covid": "dummy"}},
            )
        ]
    if _model_id(config) not in REGRESSION_MODELS:
        return [
            check(
                "info",
                "covid_period",
                "COVID periods remain visible. This descriptive, test or filter model "
                "does not use the requested regression dummies.",
                treatment=mode,
                applied=False,
                periods=affected,
            )
        ]
    expected = [f"covid_{p}" for p in affected]
    correct = (
        data.exog is not None
        and data.exog.index.equals(data.frame.index)
        and all(name in data.exog for name in expected)
    )
    if correct:
        assert data.exog is not None
        for name, period in zip(expected, periods[mask], strict=True):
            correct = correct and bool(
                np.array_equal(
                    data.exog[name].to_numpy(dtype=float), (periods == period).astype(float)
                )
            )
    if not correct:
        return [
            check(
                "block",
                "covid_dummy_missing",
                "The requested COVID period dummies are missing or do not match the "
                "effective sample.",
                periods=affected,
            )
        ]
    return [
        check(
            "info",
            "covid_period",
            "A separate fixed dummy is included for each observed COVID period; this "
            "does not remove every pandemic-related structural change.",
            treatment=mode,
            applied=True,
            periods=affected,
            dummy_count=len(expected),
        )
    ]


def _nsa_checks(data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
    if _model_id(config) not in DYNAMIC_MODELS or data.frequency == "A":
        return []
    output = []
    periods = _periods(data)
    for spec in config.get("series", []):
        if spec.get("transform") in {"yoy_pct", "yoy_diff"}:
            continue
        cid = spec["concept_id"]
        card = data.metadata.get(cid, {})
        adjustments = {str(card.get("sa_flag", "")).upper()}
        for segment in card.get("source_segments", []):
            native = segment.get("freq", card.get("frequency", data.frequency))
            frequency = "Y" if native == "A" else native
            if segment.get("first_date") and segment.get("last_date"):
                start = pd.Period(segment["first_date"], freq=frequency).start_time
                end = pd.Period(segment["last_date"], freq=frequency).end_time
                if end < periods.start_time.min() or start > periods.end_time.max():
                    continue
            adjustments.add(str(segment.get("sa_flag", "")).upper())
        if "NSA" in adjustments:
            output.append(
                check(
                    "info"
                    if _model_id(config)
                    in {
                        "lp.ols",
                        "cmp.common_shock",
                        "out.hd",
                        "ident.external_series",
                        "panel.fe",
                        "panel.lp",
                    }
                    else "warn",
                    "nsa_series",
                    "Calendar seasonal dummies are included for this unadjusted input."
                    if _model_id(config)
                    in {
                        "lp.ols",
                        "cmp.common_shock",
                        "out.hd",
                        "ident.external_series",
                        "panel.fe",
                        "panel.lp",
                    }
                    else "Not seasonally adjusted; year-on-year changes or seasonal dummies "
                    "can address recurring seasonal patterns.",
                    concept_id=cid,
                    fix={"concept_id": cid, "transform": "yoy_diff"},
                )
            )
    return output


def evaluate_checks(
    data: AnalysisData, config: AnalysisConfig, bundle: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return shared compatibility and caveat checks; never mutate inputs."""
    output = _input_checks(data, config)
    if any(item["level"] == "block" for item in output) or data.frame.empty:
        return output
    output.extend(_stationarity(data, config))
    output.extend(_policy_checks(data, config, bundle))
    output.extend(_covid_checks(data, config))
    output.extend(_nsa_checks(data, config))
    return output


def postfit_checks(
    data: AnalysisData, config: AnalysisConfig, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Check fitted stability and physical shock size against identified innovations."""
    return [{**item, "phase": "post_estimation"} for item in _postfit_checks(data, config, payload)]


def _postfit_checks(
    data: AnalysisData, config: AnalysisConfig, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    diagnostics = payload.get("diagnostics", {})
    output = []
    if _model_id(config) in VAR_MODELS and "parameter_count_per_equation" in diagnostics:
        nobs = int(diagnostics["nobs"])
        count = int(diagnostics["parameter_count_per_equation"])
        automatic = diagnostics.get("lag_selection", "fixed") != "fixed"
        sample = sample_size_check(
            nobs,
            count,
            minimum_observations=8,
            selected_lags=diagnostics.get("selected_lags"),
        )
        if sample is not None and (sample["level"] == "block" or automatic):
            output.append(sample)
    stable, radius = diagnostics.get("stable"), diagnostics.get("companion_spectral_radius")
    if _model_id(config) != "ident.external_series" and (
        stable is False or (radius is not None and float(radius) >= 1)
    ):
        output.append(
            check(
                "warn",
                "unstable_dynamics",
                "Estimated dynamics are unstable; impulse responses need not decay and "
                "long-horizon interpretations are unreliable.",
                companion_spectral_radius=radius,
            )
        )
    if not (config.get("identification") or _model_id(config) == "ident.recursive"):
        return output
    quantiles = diagnostics.get("residual_shock_quantiles")
    if not quantiles:
        return output + [
            check(
                "info",
                "shock_range_unavailable",
                "Identified historical shock quantiles are unavailable; the "
                "extrapolation check could not be completed.",
            )
        ]
    selected = [s["concept_id"] for s in config.get("series", []) if s.get("role") == "shock"]
    lower, upper = float(quantiles["q05"]), float(quantiles["q95"])
    irf = payload.get("irf", {})
    size = float(
        irf.get("shock_size", config.get("outputs", {}).get("irf", {}).get("shock_size", 1.0))
    )
    if (
        selected != [quantiles.get("shock")]
        or not all(math.isfinite(x) for x in (lower, upper, size))
        or lower > upper
    ):
        return output + [
            check(
                "block",
                "shock_range_invalid",
                "Identified shock quantiles do not match the selected shock or are invalid.",
            )
        ]
    if size < lower or size > upper:
        output.append(
            check(
                "warn",
                "shock_out_of_range",
                "The scenario is outside the historical 5th–95th percentile range: "
                "linear extrapolation.",
                concept_id=selected[0],
                shock_size=size,
                q05=lower,
                q95=upper,
                units=quantiles.get("units", "original transformed shock-series units"),
            )
        )
    return output
