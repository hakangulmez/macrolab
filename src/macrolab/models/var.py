"""Reduced-form VAR and recursive shocks with explicit physical-unit normalization."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.stats import norm  # type: ignore[import-untyped]
from statsmodels.tsa.api import VAR  # type: ignore[import-untyped]

from macrolab.models.base import (
    AnalysisConfig,
    AnalysisData,
    BasePlugin,
    check,
    parameters,
    sample_size_check,
)

FloatArray = NDArray[np.float64]
IDENTIFIERS = {"recursive", "ident.recursive"}


def _integer(value: Any, name: str, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer between {lower} and {upper}.")
    return int(value)


def _settings(config: AnalysisConfig, *, recursive: bool = False) -> dict[str, Any]:
    params = parameters(config)
    identification = config.get("identification") or {}
    identifier = identification.get("id")
    if identifier and identifier not in IDENTIFIERS:
        raise ValueError("This VAR supports recursive identification only in v0.")
    identified = recursive or identifier in IDENTIFIERS
    names = [
        item["concept_id"]
        for item in config.get("series", [])
        if item["role"] in {"shock", "endogenous", "response"}
    ]
    if len(names) < 2 or len(names) != len(set(names)):
        raise ValueError("Select at least two distinct endogenous series for a VAR.")
    shocks = [item["concept_id"] for item in config["series"] if item["role"] == "shock"]
    order = identification.get("params", {}).get("order")
    if identified:
        if len(shocks) != 1:
            raise ValueError("Recursive identification requires exactly one shock series.")
        if not isinstance(order, list) or len(order) != len(names) or set(order) != set(names):
            raise ValueError(
                "Recursive ordering must contain every selected endogenous series once."
            )
        names = list(order)
    trend = params.get("trend", "c")
    if trend not in {"c", "ct", "n"}:
        raise ValueError("Choose no deterministic term, a constant, or a constant and trend.")
    criterion = params.get("lag_selection", params.get("ic"))
    criterion = str(criterion).lower() if criterion is not None else None
    if criterion == "fixed":
        criterion = None
    if criterion == "hq":
        criterion = "hqic"
    if criterion not in {None, "aic", "bic", "hqic"}:
        raise ValueError("Lag selection must be fixed, AIC, BIC or HQ.")
    options = config.get("outputs", {}).get("irf", {})
    level = float(options.get("bands", 0.68))
    coefficient_level = float(config.get("outputs", {}).get("confidence", 0.95))
    shock_size = float(options.get("shock_size", 1.0))
    if not 0 < level < 1 or not math.isfinite(shock_size):
        raise ValueError("Band level must lie between zero and one; shock size must be finite.")
    if not 0 < coefficient_level < 1:
        raise ValueError("Coefficient confidence must lie between zero and one.")
    method = options.get("method", "bootstrap")
    if method == "residual_bootstrap":
        method = "bootstrap"
    if identified and method not in {"bootstrap", "asymptotic"}:
        raise ValueError("IRF uncertainty must use residual bootstrap or asymptotic bands.")
    seed = config.get("seed", options.get("seed"))
    if identified and method == "bootstrap":
        seed = _integer(seed, "Bootstrap seed", 0, 2**32 - 1)
    return {
        "names": names,
        "identified": identified,
        "shock": shocks[0] if identified else None,
        "lags": _integer(params.get("lags", 2), "Lags", 0, 24),
        "maxlags": _integer(params.get("maxlags", 8), "Maximum lags", 1, 24),
        "criterion": criterion,
        "trend": trend,
        "horizon": _integer(options.get("horizon", 12), "IRF horizon", 1, 60),
        "level": level,
        "coefficient_level": coefficient_level,
        "shock_size": shock_size,
        "method": method,
        "draws": _integer(options.get("draws", 500), "Bootstrap draws", 20, 5000),
        "seed": seed,
    }


def _inputs(
    data: AnalysisData, config: AnalysisConfig, settings: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    names = settings["names"]
    if not set(names) <= set(data.frame.columns):
        raise ValueError("One or more selected endogenous series are missing from the sample.")
    frame = data.frame[names].astype(float)
    exogenous = [item["concept_id"] for item in config["series"] if item["role"] == "exogenous"]
    if len(exogenous) != len(set(exogenous)) or set(exogenous) & set(names):
        raise ValueError("An exogenous series must be distinct from the endogenous series.")
    if not set(exogenous) <= set(data.frame.columns):
        raise ValueError("One or more selected exogenous series are missing from the sample.")
    parts = [data.frame[exogenous]] if exogenous else []
    if data.exog is not None and len(data.exog.columns):
        if not data.exog.index.equals(frame.index):
            raise ValueError("Deterministic and COVID regressors must use the same sample dates.")
        parts.append(data.exog)
    exog = pd.concat(parts, axis=1).astype(float) if parts else None
    if exog is not None and not exog.columns.is_unique:
        raise ValueError("Exogenous and deterministic regressor names must be distinct.")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("VAR observations must have unique, increasing sample dates.")
    if not np.isfinite(frame.to_numpy()).all() or (
        exog is not None and not np.isfinite(exog.to_numpy()).all()
    ):
        raise ValueError("VAR inputs require a common finite sample; no values are interpolated.")
    return frame, exog


def moving_average(coefficients: FloatArray, horizon: int) -> FloatArray:
    """MA matrices Phi[h], including the identity at horizon zero and VAR(0)."""
    lags, variables, _ = coefficients.shape
    result = np.zeros((horizon + 1, variables, variables))
    result[0] = np.eye(variables)
    for period in range(1, horizon + 1):
        for lag in range(1, min(lags, period) + 1):
            result[period] += result[period - lag] @ coefficients[lag - 1]
    return result


def _stable(coefficients: FloatArray) -> tuple[bool, float]:
    lags, variables, _ = coefficients.shape
    if not lags:
        return True, 0.0
    companion = np.zeros((lags * variables, lags * variables))
    companion[:variables] = np.concatenate(coefficients, axis=1)
    companion[variables:, :-variables] = np.eye((lags - 1) * variables)
    radius = float(np.max(np.abs(np.linalg.eigvals(companion))))
    return radius < 1.0, radius


def _normalized_response(
    coefficients: FloatArray, covariance: FloatArray, horizon: int, shock: int, size: float
) -> FloatArray:
    impact = np.linalg.cholesky(covariance)
    return np.asarray(
        moving_average(coefficients, horizon) @ (impact[:, shock] * (size / impact[shock, shock])),
        dtype=float,
    )


def normalized_asymptotic_se(fitted: Any, horizon: int, shock: int, size: float) -> FloatArray:
    """Delta method for a fixed own-impact shock, including its random denominator."""
    covariance = np.asarray(fitted.sigma_u, dtype=float)
    impact = np.linalg.cholesky(covariance)
    variables = len(impact)
    denominator = impact[shock, shock]
    ma = moving_average(np.asarray(fitted.coefs, dtype=float), horizon)
    # Derivatives of the lower Cholesky factor w.r.t. column-major vech(Sigma).
    pairs = [(row, col) for col in range(variables) for row in range(col, variables)]
    inverse = np.linalg.inv(impact)
    derivatives = []
    for row, col in pairs:
        perturbation = np.zeros_like(covariance)
        perturbation[row, col] = perturbation[col, row] = 1.0
        normalized = inverse @ perturbation @ inverse.T
        lower = np.tril(normalized)
        lower[np.diag_indices(variables)] *= 0.5
        derivatives.append(impact @ lower)
    derivative_array = np.asarray(derivatives)
    covariance_sigma = (
        np.array(
            [
                [
                    covariance[i, k] * covariance[j, ell] + covariance[i, ell] * covariance[j, k]
                    for k, ell in pairs
                ]
                for i, j in pairs
            ]
        )
        / fitted.nobs
    )
    normalized_impact_derivative = size * (
        derivative_array[:, :, shock].T / denominator
        - impact[:, shock, None] * derivative_array[:, shock, shock][None, :] / denominator**2
    )
    analysis = fitted.irf(horizon) if fitted.k_ar else None
    result = np.empty((horizon + 1, variables))
    selector = np.kron((impact[:, shock] * size / denominator)[None, :], np.eye(variables))
    for period in range(horizon + 1):
        derivative_sigma = ma[period] @ normalized_impact_derivative
        variance = derivative_sigma @ covariance_sigma @ derivative_sigma.T
        if period and analysis is not None:
            derivative_alpha = selector @ analysis.G[period - 1]
            variance += derivative_alpha @ analysis.cov_a @ derivative_alpha.T
        result[period] = np.sqrt(np.maximum(np.diag(variance), 0.0))
    # This coordinate is fixed by the requested normalization, not estimated.
    result[0, shock] = 0.0
    return result


def residual_bootstrap(
    fitted: Any, *, horizon: int, shock: int, size: float, draws: int, seed: int
) -> tuple[FloatArray, dict[str, Any]]:
    """Conditional residual bootstrap, refitted at fixed selected lag and trend."""
    generator = np.random.default_rng(seed)
    original = np.asarray(fitted.endog, dtype=float)
    lags, variables = fitted.k_ar, fitted.neqs
    deterministic = np.asarray(fitted.endog_lagged[:, : fitted.k_exog], dtype=float)
    deterministic_mean = deterministic @ np.asarray(fitted.params)[: fitted.k_exog]
    residuals = np.asarray(fitted.resid, dtype=float)
    residuals = (residuals - residuals.mean(axis=0)) * np.sqrt(fitted.nobs / fitted.df_resid)
    coefficients = np.asarray(fitted.coefs, dtype=float)
    collected = []
    failures = unstable = 0
    maximum_attempts = draws + max(10, draws // 10)
    for _attempt in range(maximum_attempts):
        innovations = residuals[generator.integers(0, len(residuals), size=fitted.nobs)]
        simulated = np.empty_like(original)
        simulated[:lags] = original[:lags]
        for t in range(lags, len(simulated)):
            value = deterministic_mean[t - lags] + innovations[t - lags]
            for lag in range(1, lags + 1):
                value = value + coefficients[lag - 1] @ simulated[t - lag]
            simulated[t] = value
        design = np.column_stack(
            [deterministic]
            + [simulated[lags - lag : len(simulated) - lag] for lag in range(1, lags + 1)]
        )
        try:
            parameters_draw = np.linalg.lstsq(design, simulated[lags:], rcond=1e-15)[0]
            residuals_draw = simulated[lags:] - design @ parameters_draw
            sigma = residuals_draw.T @ residuals_draw / fitted.df_resid
            ar = (
                parameters_draw[fitted.k_exog :]
                .reshape(lags, variables, variables)
                .transpose(0, 2, 1)
            )
            response = _normalized_response(ar, sigma, horizon, shock, size)
            if not np.isfinite(response).all():
                raise np.linalg.LinAlgError("Non-finite bootstrap response")
            collected.append(response)
            unstable += int(not _stable(ar)[0])
        except np.linalg.LinAlgError:
            failures += 1
        if len(collected) == draws:
            break
    if len(collected) != draws:
        raise ValueError(
            "Bootstrap failed to obtain the requested finite draws; no bands reported."
        )
    return np.asarray(collected), {
        "draws": draws,
        "seed": seed,
        "numerical_retries": failures,
        "unstable_draws_retained": unstable,
        "residual_scale": "centered, multiplied by sqrt(nobs / residual degrees of freedom)",
        "initial_conditions": "observed initial lags; deterministic and exogenous paths fixed",
        "lag_selection": "selected lag held fixed; lag-selection uncertainty is not included",
        "normalization": "each draw uses its own Cholesky own-impact coefficient",
    }


def _omit_inactive_covid(
    data: AnalysisData, exog: pd.DataFrame | None, lags: int
) -> tuple[pd.DataFrame | None, list[str]]:
    """Omit only generated COVID impulses outside the actual estimation window."""
    if exog is None or data.exog is None:
        return exog, []
    omitted = [
        str(name)
        for name in data.exog.columns
        if re.fullmatch(r"covid_\d{4}(?:-(?:Q[1-4]|0[1-9]|1[0-2]))?", str(name))
        and name in exog
        and not np.count_nonzero(exog[name].iloc[lags:].to_numpy())
    ]
    active = exog.drop(columns=omitted)
    return (active if len(active.columns) else None), omitted


def _estimate(data: AnalysisData, config: AnalysisConfig, settings: dict[str, Any]) -> Any:
    frame, exog = _inputs(data, config, settings)
    lags = settings["lags"]
    selection_omitted: list[str] = []
    if settings["criterion"]:
        # IC candidates all use the maxlag holdback. Inactive impulses have no
        # effect on that comparison; restore any active after the selected lag.
        selection_exog, selection_omitted = _omit_inactive_covid(data, exog, settings["maxlags"])
        selected = VAR(frame, exog=selection_exog).select_order(
            settings["maxlags"], trend=settings["trend"]
        )
        lags = int(selected.selected_orders[settings["criterion"]])
    active_exog, omitted = _omit_inactive_covid(data, exog, lags)
    fitted = VAR(frame, exog=active_exog).fit(lags, trend=settings["trend"])
    fitted._macrolab_omitted_covid = omitted
    fitted._macrolab_selection_omitted_covid = selection_omitted
    design = np.asarray(fitted.endog_lagged, dtype=float)
    parameter_count = design.shape[1]
    if fitted.nobs < 8:
        raise ValueError("At least eight effective observations are required.")
    if fitted.df_resid <= 0:
        raise ValueError("Positive residual degrees of freedom are required.")
    if parameter_count and np.linalg.matrix_rank(design) < parameter_count:
        raise ValueError(
            "Regressors are collinear; remove a duplicate series or deterministic term."
        )
    np.linalg.cholesky(np.asarray(fitted.sigma_u, dtype=float))
    return fitted


def _diagnostics(fitted: Any, data: AnalysisData, settings: dict[str, Any]) -> dict[str, Any]:
    coefficients = np.asarray(fitted.coefs, dtype=float)
    stable, radius = _stable(coefficients)
    condition = float(np.linalg.cond(fitted.endog_lagged)) if fitted.endog_lagged.shape[1] else 1.0
    result: dict[str, Any] = {
        "nobs": int(fitted.nobs),
        "estimated_indices": list(map(str, data.frame.index[fitted.k_ar :])),
        "selected_lags": int(fitted.k_ar),
        "lag_selection": settings["criterion"] or "fixed",
        "trend": settings["trend"],
        "variables": settings["names"],
        "parameter_count_per_equation": int(fitted.endog_lagged.shape[1]),
        "residual_degrees_of_freedom": int(fitted.df_resid),
        "stable": stable,
        "companion_spectral_radius": radius,
        "condition_number": condition,
        "information_criteria": {
            key: float(getattr(fitted, key)) for key in ("aic", "bic", "hqic")
        },
        "residual_covariance": np.asarray(fitted.sigma_u).tolist(),
        "coefficients": coefficients.tolist(),
        "omitted_zero_covid_regressors": list(fitted._macrolab_omitted_covid),
        "lag_selection_omitted_zero_covid_regressors": list(
            fitted._macrolab_selection_omitted_covid
        ),
    }
    methods: list[tuple[str, Callable[[], Any]]] = [
        ("normality", lambda: fitted.test_normality()),
        (
            "residual_whiteness",
            lambda: fitted.test_whiteness(nlags=min(fitted.k_ar + 10, int(fitted.nobs // 3))),
        ),
    ]
    for name, method in methods:
        try:
            test = method()
            result[name] = {"statistic": float(test.test_statistic), "pvalue": float(test.pvalue)}
        except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as error:
            result[name] = {"unavailable": str(error)}
    if settings["identified"]:
        shock = settings["names"].index(settings["shock"])
        impact = np.linalg.cholesky(np.asarray(fitted.sigma_u))
        structural = np.linalg.solve(impact, np.asarray(fitted.resid).T).T
        physical = structural[:, shock] * impact[shock, shock]
        result["residual_shock_quantiles"] = {
            "q05": float(np.quantile(physical, 0.05)),
            "q95": float(np.quantile(physical, 0.95)),
            "shock": settings["shock"],
            "units": "original transformed shock-series units",
        }
        result["identified_shocks"] = physical.tolist()
        result["identification_order"] = settings["names"]
    return result


def _run(data: AnalysisData, config: AnalysisConfig, *, recursive: bool = False) -> dict[str, Any]:
    settings = _settings(config, recursive=recursive)
    fitted = _estimate(data, config, settings)
    quantile = float(norm.ppf((1 + settings["level"]) / 2))
    coefficient_quantile = float(norm.ppf((1 + settings["coefficient_level"]) / 2))
    coefficient_rows = []
    for term in fitted.params.index:
        for equation in settings["names"]:
            estimate, error = (
                float(fitted.params.loc[term, equation]),
                float(fitted.stderr.loc[term, equation]),
            )
            coefficient_rows.append(
                {
                    "term": str(term),
                    "equation": equation,
                    "estimate": estimate,
                    "std_error": error,
                    "lower": estimate - coefficient_quantile * error,
                    "upper": estimate + coefficient_quantile * error,
                    "band_level": settings["coefficient_level"],
                }
            )
    diagnostics = _diagnostics(fitted, data, settings)
    notes = [
        "VAR coefficient intervals use the model's multivariate OLS covariance.",
        "Exogenous inputs and deterministic/COVID terms are conditioned on, not shocked.",
    ]
    if not diagnostics["stable"]:
        notes.append(
            "The estimated VAR is unstable; long-horizon responses may grow without bound."
        )
    result: dict[str, Any] = {
        "coefficients_table": coefficient_rows,
        "diagnostics": diagnostics,
        "notes": notes,
        "label": "Association, not causation",
    }
    if not settings["identified"]:
        return result
    horizon, names = settings["horizon"], settings["names"]
    shock = names.index(settings["shock"])
    covariance, coefficients = np.asarray(fitted.sigma_u), np.asarray(fitted.coefs)
    response = _normalized_response(
        coefficients, covariance, horizon, shock, settings["shock_size"]
    )
    bootstrap_metadata: dict[str, Any] = {}
    if settings["method"] == "bootstrap":
        draws, bootstrap_metadata = residual_bootstrap(
            fitted,
            horizon=horizon,
            shock=shock,
            size=settings["shock_size"],
            draws=settings["draws"],
            seed=settings["seed"],
        )
        tail = (1 - settings["level"]) / 2
        lower, upper = np.quantile(draws, [tail, 1 - tail], axis=0)
    else:
        errors = normalized_asymptotic_se(fitted, horizon, shock, settings["shock_size"])
        lower, upper = response - quantile * errors, response + quantile * errors
    orthogonal = moving_average(coefficients, horizon - 1) @ np.linalg.cholesky(covariance)
    cumulative = np.cumsum(orthogonal**2, axis=0)
    shares = cumulative / cumulative.sum(axis=2, keepdims=True)
    result.update(
        {
            "label": "Model-based scenario, not a forecast",
            "irf": {
                "periods": list(range(horizon + 1)),
                "variables": names,
                "values": response.tolist(),
                "lower": lower.tolist(),
                "upper": upper.tolist(),
                "shock": settings["shock"],
                "shock_size": settings["shock_size"],
                "band_level": settings["level"],
                "band_method": settings["method"],
                "band_interpretation": "pointwise confidence intervals, not simultaneous bands",
                "normalization": "fixed own-impact response in original transformed variable units",
                "bootstrap": bootstrap_metadata,
            },
            "fevd": {
                "periods": list(range(1, horizon + 1)),
                "variables": names,
                "shocks": names,
                "values": shares.tolist(),
                "units": "share of forecast-error variance; sum across shocks equals one",
                "uncertainty": "point estimates only; no FEVD interval is reported",
            },
        }
    )
    notes.append(
        "Recursive shocks depend on the stated ordering and contemporaneous zero restrictions; "
        "the response is a conditional model scenario, not an unconditional causal claim."
    )
    return result


class VAROLSPlugin(BasePlugin):
    id = "var.ols"
    family = "multivariate"
    title = "Vector autoregression"
    summary = (
        "Estimate joint dynamics and, with recursive assumptions, responses to a chosen shock."
    )
    label = "Association, not causation"
    runtime = "browser"
    assumptions = [
        "The chosen lag structure and deterministic terms describe the joint dynamics.",
        "Innovations are serially uncorrelated; the bootstrap assumes exchangeable innovations.",
        "Exogenous regressors are treated as fixed and contemporaneously exogenous.",
    ]
    inputs = {
        "min_series": 2,
        "max_series": 6,
        "required_roles": {},
        "min_regressors": 0,
        "frequencies": ["M", "Q", "A"],
        "cross_country": False,
    }
    params = {
        "type": "object",
        "properties": {
            "lags": {"type": "integer", "minimum": 0, "maximum": 24, "default": 2},
            "lag_selection": {"enum": ["fixed", "aic", "bic", "hq"], "default": "fixed"},
            "maxlags": {"type": "integer", "minimum": 1, "maximum": 24, "default": 8},
            "trend": {"enum": ["c", "ct", "n"], "default": "c"},
        },
    }
    references = [
        {
            "title": "Lütkepohl (2005), New Introduction to Multiple Time Series Analysis",
            "url": "https://doi.org/10.1007/978-3-540-27752-1",
        },
        {
            "title": "statsmodels VAR reference",
            "url": "https://www.statsmodels.org/stable/vector_ar.html",
        },
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        try:
            settings = _settings(config, recursive=self.id == "ident.recursive")
            frame, exog = _inputs(data, config, settings)
            lags = settings["lags"] if settings["criterion"] is None else 0
            exog, _omitted = _omit_inactive_covid(data, exog, lags)
            parameter_count = (
                len(settings["names"]) * lags
                + {"n": 0, "c": 1, "ct": 2}[settings["trend"]]
                + (len(exog.columns) if exog is not None else 0)
            )
            nobs = len(frame) - lags
            sample = sample_size_check(nobs, parameter_count, minimum_observations=8)
            if sample is not None and (sample["level"] == "block" or settings["criterion"] is None):
                return [sample]
            return []
        except (ValueError, TypeError, KeyError) as error:
            return [check("block", "invalid_var_configuration", str(error))]

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        return _run(data, config, recursive=self.id == "ident.recursive")


class RecursiveIdentificationPlugin(VAROLSPlugin):
    id = "ident.recursive"
    family = "identification"
    title = "Recursive identification"
    summary = "Identify ordered shocks with Cholesky restrictions and explicit shock units."
    label = "Model-based scenario, not a forecast"
    assumptions = VAROLSPlugin.assumptions + [
        "Earlier variables do not respond contemporaneously to later shocks in the stated ordering."
    ]
    inputs = {**VAROLSPlugin.inputs, "required_roles": {"shock": 1}}


PLUGINS = [VAROLSPlugin(), RecursiveIdentificationPlugin()]


def _synthetic_sample(seed: int, observations: int) -> tuple[AnalysisData, FloatArray, FloatArray]:
    generator = np.random.default_rng(seed)
    autoregression = np.array([[0.55, 0.12], [-0.08, 0.35]])
    impact = np.array([[0.6, 0.0], [0.15, 0.3]])
    values = np.zeros((observations + 200, 2))
    for t in range(1, len(values)):
        values[t] = autoregression @ values[t - 1] + impact @ generator.normal(size=2)
    frame = pd.DataFrame(
        values[200:],
        columns=["activity", "rate"],
        index=pd.period_range("1950Q1", periods=observations, freq="Q"),
    )
    return AnalysisData(frame=frame), autoregression, impact


def _validation_config(*, method: str = "bootstrap", draws: int = 199) -> AnalysisConfig:
    return {
        "seed": 74000,
        "series": [
            {"concept_id": "activity", "role": "endogenous"},
            {"concept_id": "rate", "role": "shock"},
        ],
        "model": {"id": "var.ols", "params": {"lags": 1, "trend": "c"}},
        "identification": {"id": "recursive", "params": {"order": ["activity", "rate"]}},
        "outputs": {
            "irf": {
                "horizon": 4,
                "bands": 0.68,
                "shock_size": 1.0,
                "method": method,
                "draws": draws,
            }
        },
    }


def synthetic_recovery(*, replications: int = 40, draws: int = 199) -> dict[str, Any]:
    """Fixed, untuned Monte Carlo; report the observed pointwise coverage."""
    if replications < 10:
        raise ValueError("Coverage reporting requires at least ten Monte Carlo replications.")
    irf_hits, coefficient_hits = [], []
    config = _validation_config(draws=draws)
    # Both Monte Carlo coverage targets were predeclared at 68 percent.
    config["outputs"]["confidence"] = 0.68
    for replication in range(replications):
        data, autoregression, impact = _synthetic_sample(43000 + replication, 180)
        config["seed"] = 74000 + replication
        output = VAROLSPlugin().run(data, config)
        # Independent DGP truth uses matrix powers, not the implementation's MA recursion.
        truth = np.array(
            [
                np.linalg.matrix_power(autoregression, h) @ impact[:, 1] / impact[1, 1]
                for h in range(5)
            ]
        )
        lower, upper = np.asarray(output["irf"]["lower"]), np.asarray(output["irf"]["upper"])
        irf_hits.append(((truth >= lower) & (truth <= upper))[1:])
        lookup = {(row["term"], row["equation"]): row for row in output["coefficients_table"]}
        names = ["activity", "rate"]
        coefficient_hits.append(
            [
                lookup[f"L1.{regressor}", equation]["lower"]
                <= autoregression[i, j]
                <= lookup[f"L1.{regressor}", equation]["upper"]
                for i, equation in enumerate(names)
                for j, regressor in enumerate(names)
            ]
        )
    irf_coverage = float(np.mean(irf_hits))
    coefficient_coverage = float(np.mean(coefficient_hits))
    nominal = 0.68
    # Conservative diagnostic envelope uses the number of independent datasets,
    # not the larger count of correlated horizon/variable cells.
    margin = 3 * np.sqrt(nominal * (1 - nominal) / replications)
    envelope = [float(max(0, nominal - margin)), float(min(1, nominal + margin))]
    large_data, truth_coefficients, _impact = _synthetic_sample(51021, 4000)
    large = VAROLSPlugin().run(large_data, _validation_config(method="asymptotic"))
    recovery_error = float(
        np.max(np.abs(np.asarray(large["diagnostics"]["coefficients"])[0] - truth_coefficients))
    )
    return {
        "passed": bool(
            envelope[0] <= irf_coverage <= envelope[1]
            and envelope[0] <= coefficient_coverage <= envelope[1]
            and recovery_error < 0.06
        ),
        "nominal_coverage": nominal,
        "coverage": irf_coverage,
        "coefficient_coverage": coefficient_coverage,
        "coverage_by_horizon_variable": np.mean(irf_hits, axis=0).tolist(),
        "replications": replications,
        "observations_per_replication": 180,
        "bootstrap_draws": draws,
        "dgp_seed_start": 43000,
        "bootstrap_seed_start": 74000,
        "coverage_diagnostic_envelope": envelope,
        "large_sample_coefficient_max_abs_error": recovery_error,
        "large_sample_observations": 4000,
        "interpretation": (
            "Pointwise coverage at horizons 1–4; fixed impact restrictions excluded. "
            "The envelope is a finite-Monte-Carlo diagnostic, not a proof of calibrated "
            "coverage for arbitrary empirical data. Seeds, DGP and thresholds were not tuned."
        ),
    }


def validation_evidence() -> list[dict[str, Any]]:
    """Native callable for the gate's deterministic and simulation validation cards."""
    data, _autoregression, _impact = _synthetic_sample(23019, 240)
    config = _validation_config(method="asymptotic")
    output = VAROLSPlugin().run(data, config)
    reference = VAR(data.frame).fit(1, trend="c")
    lookup = {(row["term"], row["equation"]): row for row in output["coefficients_table"]}
    differences = {
        "coefficients": max(
            abs(lookup[term, equation]["estimate"] - reference.params.loc[term, equation])
            for term in reference.params.index
            for equation in data.frame.columns
        ),
        "standard_errors": max(
            abs(lookup[term, equation]["std_error"] - reference.stderr.loc[term, equation])
            for term in reference.params.index
            for equation in data.frame.columns
        ),
        "coefficient_intervals": max(
            abs(
                lookup[term, equation][bound]
                - (
                    reference.params.loc[term, equation]
                    + sign * float(norm.ppf(0.975)) * reference.stderr.loc[term, equation]
                )
            )
            for term in reference.params.index
            for equation in data.frame.columns
            for bound, sign in (("lower", -1), ("upper", 1))
        ),
        "normalized_irf": float(
            np.max(
                np.abs(
                    np.asarray(output["irf"]["values"])
                    - reference.irf(4).orth_irfs[:, :, 1]
                    / np.linalg.cholesky(reference.sigma_u)[1, 1]
                )
            )
        ),
        "fevd": float(
            np.max(
                np.abs(
                    np.asarray(output["fevd"]["values"])
                    - reference.fevd(4).decomp.transpose(1, 0, 2)
                )
            )
        ),
    }
    recovery = synthetic_recovery()
    generator = np.random.default_rng(31920)
    benchmark_names = [f"variable_{index}" for index in range(6)]
    transition = np.eye(6) * 0.35 + np.ones((6, 6)) * 0.025
    impact = np.eye(6) * 0.4 + np.tril(np.ones((6, 6)), -1) * 0.04
    observations = np.zeros((320, 6))
    for t in range(1, len(observations)):
        observations[t] = transition @ observations[t - 1] + impact @ generator.normal(size=6)
    benchmark_data = AnalysisData(
        frame=pd.DataFrame(
            observations[200:],
            columns=benchmark_names,
            index=pd.period_range("1990Q1", periods=120, freq="Q"),
        )
    )
    benchmark = _validation_config(draws=500)
    benchmark["series"] = [
        {"concept_id": name, "role": "shock" if index == 5 else "endogenous"}
        for index, name in enumerate(benchmark_names)
    ]
    benchmark["identification"]["params"]["order"] = benchmark_names
    benchmark["model"]["params"]["lags"] = 2
    benchmark["outputs"]["irf"]["horizon"] = 12
    started = time.perf_counter()
    VAROLSPlugin().run(benchmark_data, benchmark)
    elapsed = 1000 * (time.perf_counter() - started)
    return [
        {
            "model_id": identifier,
            "reference_max_abs_difference": float(max(differences.values())),
            "reference_tolerance": 1e-8,
            "reference_outputs": differences,
            "reference": "statsmodels 0.14 VAR coefficients/SEs and normal intervals, "
            "orthogonalized IRF, FEVD",
            "recovery": deepcopy(recovery),
            "runtime_ms": elapsed,
            "runtime_configuration": {
                "variables": 6,
                "observations": 120,
                "lags": 2,
                "draws": 500,
                "horizon": 12,
            },
            "limitations": [
                "Residual bootstrap conditions on the selected lag and initial observations.",
                "Pointwise bands are not simultaneous; exogenous paths are held fixed.",
                "Recursive ordering is an identifying assumption, not an established causal fact.",
            ],
        }
        for identifier in ("var.ols", "ident.recursive")
    ]
