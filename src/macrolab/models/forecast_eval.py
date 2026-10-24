"""Expanding-window evaluation. Every estimator only receives its origin prefix."""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t  # type: ignore[import-untyped]

from macrolab.models.arima import ARIMA_PARAMS, COMMON_PARAMS, predict_arima
from macrolab.models.base import AnalysisData, BasePlugin, check
from macrolab.models.forecast_common import (
    EVALUATION_LABEL,
    Cancelled,
    Progress,
    forecast_checks,
    names,
    original_distribution,
    original_unit,
    tick,
    training,
)
from macrolab.models.forecast_var import predict_var
from macrolab.models.linear import integer, schema

MODELS = ["Random walk", "AR (BIC)", "ARIMA", "BVAR"]


def dm_hln(
    a: np.ndarray, b: np.ndarray, horizon: int, periods: np.ndarray | None = None
) -> dict[str, Any]:
    """Squared-error differential, h−1 autocovariances / N and HLN t(N−1)."""
    d = np.asarray(a) ** 2 - np.asarray(b) ** 2
    n = len(d)
    result: dict[str, Any] = {
        "n": n,
        "horizon": horizon,
        "loss": "squared error",
        "lags": horizon - 1,
        "bartlett_fallback": False,
    }
    if n <= horizon:
        return {
            **result,
            "status": "unavailable",
            "reason": "Too few paired forecasts for HLN correction",
        }
    centered = d - d.mean()
    calendar = np.arange(n) if periods is None else periods
    lookup = {int(p): i for i, p in enumerate(calendar)}
    gamma = [float(centered @ centered / n)]
    for lag in range(1, horizon):
        gamma.append(
            sum(
                centered[i] * centered[lookup[int(p) - lag]]
                for i, p in enumerate(calendar)
                if int(p) - lag in lookup
            )
            / n
        )
    variance = gamma[0] + 2 * sum(gamma[1:])
    original = variance
    if variance < 0:
        variance = gamma[0] + 2 * sum((1 - k / horizon) * gamma[k] for k in range(1, horizon))
        result["bartlett_fallback"] = True
    result.update(long_run_variance=float(variance), unweighted_long_run_variance=float(original))
    if variance <= 0 or not np.isfinite(variance):
        return {
            **result,
            "status": "unavailable",
            "reason": "Zero or invalid loss-differential variance",
        }
    correction = np.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    statistic = float(d.mean() / np.sqrt(variance / n) * correction)
    return {
        **result,
        "status": "ok",
        "statistic": statistic,
        "p_value": float(2 * t.sf(abs(statistic), n - 1)),
        "hln_factor": float(correction),
    }


def ar_benchmark(
    y: np.ndarray, horizon: int, fixed_order: int | None = None
) -> tuple[np.ndarray, int]:
    maximum = min(12, (len(y) - 5) // 3)
    candidates = range(1, maximum + 1) if fixed_order is None else [fixed_order]
    fits = []
    # Common BIC estimation sample across candidate orders; refit selected on all its rows.
    hold = maximum if fixed_order is None else fixed_order
    for p in candidates:
        x = np.column_stack(
            [np.ones(len(y) - hold), *[y[hold - i : len(y) - i] for i in range(1, p + 1)]]
        )
        b = np.linalg.lstsq(x, y[hold:], rcond=None)[0]
        errors = y[hold:] - x @ b
        variance = errors @ errors / len(errors)
        if variance <= 0:
            raise ValueError("Degenerate AR benchmark")
        fits.append((len(errors) * np.log(variance) + (p + 1) * np.log(len(errors)), p))
    p = min(fits)[1]
    x = np.column_stack([np.ones(len(y) - p), *[y[p - i : len(y) - i] for i in range(1, p + 1)]])
    beta = np.linalg.lstsq(x, y[p:], rcond=None)[0]
    values = list(y)
    for _ in range(horizon):
        values.append(float(beta[0] + np.dot(beta[1:], values[-p:][::-1])))
    return np.asarray(values[-horizon:]), p


def origin_forecast(
    raw: AnalysisData,
    config: dict[str, Any],
    stop: int,
    horizon: int,
    fixed: dict[str, Any] | None = None,
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    # Physically truncate raw inputs before any model or transform sees them.
    prefix = deepcopy(raw)
    prefix.frame = raw.frame.iloc[:stop].copy()
    prefix.exog = None if raw.exog is None else raw.exog.iloc[:stop].copy()
    data = training(prefix, config)
    target = names(config)[0]
    original = prefix.frame[target].to_numpy()
    transformed_scale = config["model"]["params"].get("evaluation_scale") == "transformed"
    if transformed_scale:
        original = data.frame[target].to_numpy()
    spec = next(s for s in config["series"] if s["concept_id"] == target)
    details = data.sample["transforms"][target]
    ar, order = ar_benchmark(original, horizon, None if fixed is None else fixed["ar_order"])
    arima_config = deepcopy(config)
    arima_config["series"] = [
        s for s in config["series"] if s["concept_id"] == target or s["role"] == "exogenous"
    ]
    mean, cov, fitted = predict_arima(
        data,
        arima_config,
        horizon,
        fixed=None if fixed is None else fixed["arima"],
        progress=progress,
        cancelled=cancelled,
    )
    arima = (
        mean
        if transformed_scale
        else original_distribution(
            mean, cov, None, spec, original, data.frequency, details, config["seed"]
        )["mean"]
    )
    bconfig = deepcopy(config)
    bconfig["model"]["params"]["estimator"] = "bvar"
    mean_b, paths_b, info = predict_var(
        data, bconfig, horizon, progress=progress, cancelled=cancelled
    )
    assert paths_b is not None
    bvar = (
        paths_b[:, :, 0].mean(axis=0)
        if transformed_scale
        else original_distribution(
            mean_b[:, 0],
            None,
            paths_b[:, :, 0],
            spec,
            original,
            data.frequency,
            details,
            config["seed"],
        )["mean"]
    )
    return {
        "Random walk": np.repeat(original[-1], horizon),
        "AR (BIC)": ar,
        "ARIMA": np.array(arima),
        "BVAR": np.array(bvar),
    }, {
        "ar_order": order,
        "arima": fitted["chosen"],
        "arima_tests": fitted["tests"],
        "arima_failed_candidates": fitted["failed_candidates"],
        "bvar_scales": info["ar_residual_scales"],
        "transform_details": details,
        "training_start": str(data.frame.index[0]),
        "training_end": str(data.frame.index[-1]),
        "training_nobs": len(data.frame),
    }


def score_predictions(
    rows: list[dict[str, Any]], frequency: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metrics, tests = [], []
    for h in sorted({r["horizon"] for r in rows}):
        group = [r for r in rows if r["horizon"] == h]
        errors = {
            model: np.array([r["actual"] - r["predictions"][model] for r in group])
            for model in MODELS
        }
        rw_rmse = np.sqrt(np.mean(errors["Random walk"] ** 2))
        for model, error in errors.items():
            rmse = float(np.sqrt(np.mean(error**2)))
            metrics.append(
                {
                    "model": model,
                    "horizon": h,
                    "rmse": rmse,
                    "mae": float(np.mean(np.abs(error))),
                    "relative_rmse": rmse / rw_rmse if rw_rmse > 0 else None,
                    "n_forecasts": len(error),
                }
            )
        calendar = np.array([pd.Period(r["target"], freq=frequency).ordinal for r in group])
        for a, b in combinations(MODELS, 2):
            tests.append({"model_a": a, "model_b": b, **dm_hln(errors[a], errors[b], h, calendar)})
    return metrics, tests


def run_evaluation(
    raw: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    frequency = raw.frequency
    initial = 120 if frequency == "M" else 40
    horizons = [1, 6, 12] if frequency == "M" else [1, 4, 8]
    target = names(config)[0]
    transformed_scale = config["model"]["params"].get("evaluation_scale") == "transformed"
    first_stop = initial
    actuals = raw.frame[target]
    if transformed_scale:
        # Find the first prefix with 40/120 usable transformed observations.
        # No transform or estimated scaling may see observations after that origin.
        while (
            first_stop < len(raw.frame) and len(training(raw, config, first_stop).frame) < initial
        ):
            first_stop += 1
        # These are realised target observations, never supplied to estimators.
        actuals = training(raw, config).frame[target]
    rows: list[dict[str, Any]] = []
    origins: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    fixed = None
    n_origins = len(raw.frame) - first_stop
    for i, stop in enumerate(range(first_stop, len(raw.frame))):
        tick(progress, cancelled, "forecast_evaluation", i, n_origins)
        h = max(horizons)
        try:
            predictions, detail = origin_forecast(raw, config, stop, h, fixed, cancelled=cancelled)
            origins.append({"origin": str(raw.frame.index[stop - 1]), **detail})
            if fixed is None and not config["model"]["params"].get("reselect", False):
                fixed = {"ar_order": detail["ar_order"], "arima": detail["arima"]}
            for horizon in horizons:
                if stop + horizon <= len(raw.frame):
                    rows.append(
                        {
                            "origin": str(raw.frame.index[stop - 1]),
                            "target": str(raw.frame.index[stop + horizon - 1]),
                            "horizon": horizon,
                            "actual": float(actuals.loc[raw.frame.index[stop + horizon - 1]]),
                            "predictions": {
                                model: float(prediction[horizon - 1])
                                for model, prediction in predictions.items()
                            },
                        }
                    )
        except (ValueError, np.linalg.LinAlgError) as exc:
            # Never shift the first-order selection to a later origin unnoticed.
            if i == 0:
                raise ValueError("First evaluation origin failed: " + str(exc)) from exc
            failures.append({"origin": str(raw.frame.index[stop - 1]), "reason": str(exc)})
    tick(progress, cancelled, "forecast_evaluation", n_origins, n_origins)
    if not rows:
        raise ValueError("No common successful evaluation origins")
    metrics, tests = score_predictions(rows, frequency)
    retained = [r for r in rows if not "2020" <= r["target"][:4] <= "2021"]
    smetrics, stests = score_predictions(retained, frequency)
    origin_retained = [r for r in rows if not "2020" <= r["origin"][:4] <= "2021"]
    ometrics, otests = score_predictions(origin_retained, frequency)
    checks = []
    if failures:
        checks.append(
            check(
                "warn",
                "forecast_failed_origins",
                f"{len(failures)} origins failed. Metrics and paired tests use the common "
                "successful origins; inspect all failures in details.",
                phase="post_estimation",
            )
        )
    if any(t.get("bartlett_fallback") for t in tests + stests + otests):
        checks.append(
            check(
                "warn",
                "dm_bartlett_fallback",
                (
                    "A negative unweighted DM variance required Bartlett weights; "
                    "flagged tests retain h−1 calendar lags."
                ),
                phase="post_estimation",
            )
        )
    if any(o["arima_tests"]["disagree"] for o in origins):
        checks.append(
            check(
                "warn",
                "arima_d_disagreement",
                (
                    "ADF/KPSS disagreement occurred. The first-origin automatic rule "
                    "uses d = 1; fixed orders remain fixed thereafter. The ARIMA "
                    "output exposes d = 0 sensitivity."
                ),
                phase="post_estimation",
            )
        )
    return {
        "evaluation": {
            "label": EVALUATION_LABEL,
            "target": target,
            "unit": "percentage points of year-on-year HICP inflation"
            if transformed_scale
            else original_unit(raw, target),
            "models": MODELS,
            "initial_observations": initial,
            "horizons": horizons,
            "attempted_origins": n_origins,
            "successful_origins": len(origins),
            "failed_origins": failures,
            "order_policy": "Re-select at each origin"
            if config["model"]["params"].get("reselect")
            else (
                "Orders fixed at first origin; all coefficients and BVAR AR(p) "
                "scales re-estimated at every origin"
            ),
            "metrics": metrics,
            "dm_tests": tests,
            "predictions": rows,
            "origins": origins,
            "notes": [
                "Several pairwise DM tests are not a joint test.",
                (
                    "All metrics are in original units on paired common origins. "
                    "Benchmarks use the raw original-unit target."
                )
                if not transformed_scale
                else (
                    "All four models predict year-on-year HICP inflation itself, in percentage "
                    "points, on paired common origins. Pre-1999 observations only initialise "
                    "causal transforms; the first origin has 40 usable training quarters."
                ),
                "Future COVID dummies are zero; seasonal controls use the known calendar.",
                (
                    "No full-sample standardisation or estimated scale is used. Lossy "
                    "HP/Hamilton transforms are blocked."
                ),
                (
                    "BVAR points are seeded posterior predictive means; ARIMA "
                    "nonlinear inverse means use 10,000 seeded joint Gaussian paths."
                )
                if not transformed_scale
                else (
                    "BVAR points are seeded posterior predictive means; ARIMA means are on "
                    "the inflation scale. No inverse HICP-index transformation is applied."
                ),
            ],
        },
        "diagnostics": {
            "estimated_indices": list(map(str, raw.frame.index)),
            "n_origins": len(origins),
        },
        "checks": checks,
        "sensitivity": {
            "status": "ok",
            "variants": [
                {
                    "id": "exclude_2020_2021_targets",
                    "label": "Exclude 2020–2021 forecast targets",
                    "status": "ok" if retained else "unavailable",
                    "metrics": smetrics,
                    "dm_tests": stests,
                    "removed_predictions": len(rows) - len(retained),
                },
                {
                    "id": "exclude_2020_2021_origins",
                    "label": "Exclude forecasts made from 2020–2021 origins",
                    "status": "ok" if origin_retained else "unavailable",
                    "metrics": ometrics,
                    "dm_tests": otests,
                    "removed_predictions": len(rows) - len(origin_retained),
                },
            ],
        },
    }


class ForecastEvaluationPlugin(BasePlugin):
    id = "fc.eval"
    family = "Forecasting"
    title = "Expanding-window evaluation"
    summary = "RW, AR(BIC), ARIMA and BVAR, paired errors and DM/HLN comparisons."
    label = "Forecast evaluation"
    inputs = {"min_series": 1, "max_series": 8, "frequencies": ["M", "Q"]}
    params = schema(
        template_id={"type": "string", "enum": ["ea_inflation_horse_race"]},
        evaluation_scale={"type": "string", "enum": ["original", "transformed"]},
        **COMMON_PARAMS,
        **ARIMA_PARAMS,
        lags=integer(2, 1, 12),
        draws=integer(500, 100, 5000),
        reselect={"type": "boolean", "default": False},
        **{"lambda": {"type": "number", "default": 0.2, "minimum": 0.001, "maximum": 100}},
    )
    assumptions = [
        EVALUATION_LABEL,
        "Expanding training prefixes; no look-ahead. Pairwise DM tests are not a joint test.",
    ]
    references = [
        {
            "title": "Harvey, Leybourne and Newbold (1997)",
            "url": "https://doi.org/10.1016/S0169-2070(96)00719-4",
        }
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        return forecast_checks(data, config)

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return run_evaluation(data, config)
