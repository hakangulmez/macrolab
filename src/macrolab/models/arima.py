"""SARIMAX likelihood, explicit order search and joint predictive covariance."""

from __future__ import annotations

import warnings
from itertools import product
from typing import Any

import numpy as np
from statsmodels.stats.diagnostic import acorr_ljungbox  # type: ignore[import-untyped]
from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore[import-untyped]
from statsmodels.tsa.stattools import adfuller, kpss  # type: ignore[import-untyped]

from macrolab.models.base import AnalysisData, BasePlugin, check
from macrolab.models.forecast_common import (
    Cancelled,
    Progress,
    forecast_checks,
    forecast_payload,
    future_controls,
    names,
    original_distribution,
    tick,
    training,
)
from macrolab.models.forecast_optimizer import portable_bfgs
from macrolab.models.linear import choice, integer, schema


class ForecastSARIMAX(SARIMAX):  # type: ignore[misc]
    """Same stationary initialization, evaluated without a Schur derivative.

    Small companion matrices use the direct Lyapunov equation. Larger seasonal
    systems use convergent doubling. Complex steps use transpose, not adjoint,
    as the analytic continuation of the real covariance equation requires.
    """

    def update(self, params: Any, *args: Any, **kwargs: Any) -> Any:
        result = super().update(params, *args, **kwargs)
        transition = self.ssm["transition"]
        selection = self.ssm["selection"]
        covariance = selection @ self.ssm["state_cov"] @ selection.T
        n = len(transition)
        intercept = self.ssm["state_intercept"]
        if intercept.ndim == 2:
            intercept = intercept[:, 0]
        mean = np.linalg.solve(np.eye(n) - transition, intercept)
        if n <= 8:
            covariance = np.linalg.solve(
                np.eye(n * n) - np.kron(transition, transition), covariance.ravel()
            ).reshape(n, n)
        else:
            power = transition.copy()
            for _ in range(32):
                covariance = covariance + power @ covariance @ power.T
                power = power @ power
        self.ssm.initialize_known(mean, covariance)
        return result


def difference_decision(y: np.ndarray) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adf = adfuller(y, regression="c", autolag="AIC")
        kp = kpss(y, regression="c", nlags="auto")
    stationary_adf, stationary_kpss = bool(adf[1] < 0.05), bool(kp[1] >= 0.05)
    disagree = stationary_adf != stationary_kpss
    return {
        "d": 0 if stationary_adf and stationary_kpss else 1,
        "disagree": disagree,
        "adf_p_value": float(adf[1]),
        "kpss_p_value": float(kp[1]),
        "adf_lags": int(adf[2]),
        "kpss_lags": int(kp[2]),
        "rule": (
            "5% tests with constant: ADF rejection and KPSS non-rejection "
            "imply d=0; both nonstationary imply d=1; disagreement uses d=1 "
            "and d=0 sensitivity. KPSS p-values are table-bounded."
        ),
    }


def seasonal_allowed(data: AnalysisData, config: dict[str, Any]) -> bool:
    card = data.metadata.get(names(config)[0], {})
    flags = [
        card.get("sa_flag", ""),
        *[s.get("sa_flag", "") for s in card.get("source_segments", [])],
    ]
    return data.frequency == "M" and "NSA" in flags


def fit_order(
    y: np.ndarray,
    exog: np.ndarray,
    order: tuple[int, int, int],
    seasonal: tuple[int, int, int, int],
) -> Any:
    model = ForecastSARIMAX(
        y,
        exog=exog if exog.shape[1] else None,
        order=order,
        seasonal_order=seasonal,
        trend="c",
        simple_differencing=True,
        enforce_stationarity=True,
        enforce_invertibility=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Explicit chain rule avoids the transposed score mapping in the pinned
        # MLEModel.score(transformed=False) for coupled AR/MA transforms.
        # Fixed feasible start avoids platform-dependent least-squares starts
        # along nearly unidentified AR/MA cancellation directions.
        start = np.zeros(model.k_params)
        start[model.param_names.index("sigma2")] = 1.0

        def objective(theta: np.ndarray) -> float:
            return float(-model.loglike(theta, transformed=False) / len(y))

        def gradient(theta: np.ndarray) -> np.ndarray:
            return np.array(
                [
                    -np.imag(
                        model.loglike(
                            theta.astype(complex) + 1j * 1e-20 * np.eye(len(theta))[j],
                            transformed=False,
                            complex_step=True,
                        )
                    )
                    / 1e-20
                    / len(y)
                    for j in range(len(theta))
                ]
            )

        optimum = portable_bfgs(objective, gradient, start)
        result = model.filter(model.transform_params(optimum["x"]), cov_type="none")
        result.mle_retvals = {
            "converged": optimum["converged"],
            "iterations": optimum["iterations"],
        }
    return result


def choose_order(
    data: AnalysisData,
    config: dict[str, Any],
    *,
    d_override: int | None = None,
    fixed: dict[str, Any] | None = None,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    p = config["model"]["params"]
    target = names(config)[0]
    values = data.frame[target].to_numpy()
    location, scale = float(values.mean()), float(values.std())
    if scale <= np.finfo(float).eps:
        raise ValueError("ARIMA requires nonconstant training observations")
    y = np.round((values - location) / scale, 12)
    past, _, controls, _ = future_controls(data, config, 1)
    tests = difference_decision(y)
    d = tests["d"] if d_override is None else d_override
    allowed = seasonal_allowed(data, config)
    if fixed is not None:
        orders = [(tuple(fixed["order"]), tuple(fixed["seasonal_order"]))]
    elif p.get("order_selection", "aicc") == "fixed":
        seasonal = (int(p.get("seasonal_p", 0)), 0, int(p.get("seasonal_q", 0)), 12)
        if (seasonal[0] or seasonal[2]) and not allowed:
            raise ValueError("Seasonal AR/MA terms are available only for monthly NSA series")
        orders = [
            (
                (int(p.get("p", 1)), int(p.get("d", 1)), int(p.get("q", 0))),
                seasonal if seasonal[0] or seasonal[2] else (0, 0, 0, 0),
            )
        ]
    else:
        seasonals = (
            [(a, 0, b, 12) if a or b else (0, 0, 0, 0) for a, b in product(range(2), repeat=2)]
            if allowed
            else [(0, 0, 0, 0)]
        )
        orders = [
            ((ar, d, ma), seasonal)
            for ar, ma in product(range(5), repeat=2)
            for seasonal in seasonals
        ]
    rows, fits, failures = [], [], []
    for i, (order, seasonal) in enumerate(orders):
        tick(progress, cancelled, "forecast_order_search", i, len(orders))
        try:
            fit = fit_order(y, past, order, seasonal)
            k, effective = len(fit.params), fit.nobs_effective
            if effective <= k + 1 or not np.isfinite(fit.llf) or not np.isfinite(fit.params).all():
                raise ValueError("Insufficient effective observations or nonfinite likelihood")
            if not fit.mle_retvals.get("converged", False):
                raise ValueError("Maximum-likelihood optimizer did not converge")
            aicc = float(
                -2 * fit.llf
                + 2 * k
                + 2 * k * (k + 1) / (effective - k - 1)
                + 2 * effective * np.log(scale)
            )
            rows.append(
                {
                    "order": list(order),
                    "seasonal_order": list(seasonal),
                    "aicc": aicc,
                    "log_likelihood": float(fit.llf - effective * np.log(scale)),
                    "parameters": k,
                    "effective_nobs": int(effective),
                }
            )
            fits.append(fit)
        except (ValueError, np.linalg.LinAlgError) as exc:
            failures.append(
                {"order": list(order), "seasonal_order": list(seasonal), "reason": str(exc)}
            )
    tick(progress, cancelled, "forecast_order_search", len(orders), len(orders))
    if not rows:
        raise ValueError("No admissible converged SARIMAX candidate: " + str(failures[:2]))
    best = sorted(
        range(len(rows)),
        key=lambda j: (rows[j]["aicc"], rows[j]["order"], rows[j]["seasonal_order"]),
    )
    return {
        "fit": fits[best[0]],
        "chosen": rows[best[0]],
        "runner_up": rows[best[1]] if len(best) > 1 else None,
        "candidates": sorted(rows, key=lambda r: r["aicc"]),
        "failed_candidates": failures,
        "tests": tests,
        "location": location,
        "scale": scale,
        "controls": controls,
        "selection": "fixed" if len(orders) == 1 else "AICc exhaustive grid",
        "seasonal_allowed": allowed,
    }


def joint_prediction(fit: Any, future: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    prediction = fit.get_forecast(horizon, exog=future if future.shape[1] else None)
    # alpha[T+1] | Y[1:T]. Cross-horizon covariance is essential for inverse differences.
    ssm = fit.model.ssm
    transition = np.asarray(ssm["transition"])
    design = np.asarray(ssm["design"])
    selection = np.asarray(ssm["selection"])
    q = np.asarray(ssm["state_cov"])
    measurement = float(ssm["obs_cov"][0, 0])
    covariance = np.zeros((horizon, horizon))
    state = fit.predicted_state_cov[:, :, -1].copy()
    for i in range(horizon):
        covariance[i, i] = float((design @ state @ design.T)[0, 0]) + measurement
        cross = state.copy()
        for j in range(i + 1, horizon):
            cross = cross @ transition.T
            covariance[i, j] = covariance[j, i] = float((design @ cross @ design.T)[0, 0])
        state = transition @ state @ transition.T + selection @ q @ selection.T
    mean = np.asarray(prediction.predicted_mean)
    if fit.model.simple_differencing and fit.model.k_diff:
        # SARIMAX predicts differences when simple_differencing=True.
        # Restore the requested transformed level with its joint covariance.
        accumulation = np.tril(np.ones((horizon, horizon)))
        mean = float(np.asarray(fit.model.orig_endog)[-1]) + accumulation @ mean
        covariance = accumulation @ covariance @ accumulation.T
    return mean, covariance


def predict_arima(
    data: AnalysisData, config: dict[str, Any], horizon: int, **kwargs: Any
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    fitted = choose_order(data, config, **kwargs)
    _, future, _, _ = future_controls(data, config, horizon)
    mean, cov = joint_prediction(fitted["fit"], future, horizon)
    return fitted["location"] + fitted["scale"] * mean, cov * fitted["scale"] ** 2, fitted


def run_arima(
    raw: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    data = training(raw, config)
    horizon = config["model"]["params"].get("horizon", 8)
    mean, covariance, fitted = predict_arima(
        data, config, horizon, progress=progress, cancelled=cancelled
    )
    target = names(config)[0]
    spec = next(s for s in config["series"] if s["concept_id"] == target)
    distribution = original_distribution(
        mean,
        covariance,
        None,
        spec,
        raw.frame[target].to_numpy(),
        data.frequency,
        data.sample["transforms"][target],
        config["seed"],
    )
    _, _, _, notes = future_controls(data, config, horizon)
    model = fitted.pop("fit")
    order = fitted["chosen"]["order"]
    seasonal = fitted["chosen"]["seasonal_order"]
    df = order[0] + order[2] + seasonal[0] + seasonal[2]
    lag = min(max(10, df + 3), len(data.frame) // 3)
    lb = acorr_ljungbox(
        model.resid[model.loglikelihood_burn :], lags=[lag], model_df=df, return_df=True
    )
    ljung = {
        "lag": lag,
        "model_df": df,
        "statistic": float(lb.lb_stat.iloc[0]),
        "p_value": None if not np.isfinite(lb.lb_pvalue.iloc[0]) else float(lb.lb_pvalue.iloc[0]),
    }
    result = forecast_payload(
        raw,
        data,
        config,
        {target: distribution},
        "SARIMAX",
        notes,
        arima={
            **fitted,
            "parameters_standardised": dict(
                zip(model.param_names, map(float, model.params), strict=True)
            ),
            "ljung_box": ljung,
        },
        model_space={target: {"mean": mean.tolist(), "covariance": covariance.tolist()}},
        interval_scope=(
            "Conditional on fitted SARIMAX parameters; innovation and state "
            "uncertainty included, parameter uncertainty not included."
        ),
    )
    if fitted["failed_candidates"]:
        result["checks"].append(
            check(
                "warn",
                "arima_failed_candidates",
                f"{len(fitted['failed_candidates'])} ARIMA candidates failed or did not converge; "
                "inspect the search details. No failed candidate was eligible for selection.",
                phase="post_estimation",
            )
        )
    if (
        fitted["tests"]["disagree"]
        and config["model"]["params"].get("order_selection", "aicc") != "fixed"
    ):
        result["checks"].append(
            check(
                "warn",
                "arima_d_disagreement",
                (
                    "ADF and KPSS disagree. Automatic differencing uses d = 1; the d "
                    "= 0 row shows specification sensitivity."
                ),
                phase="post_estimation",
            )
        )
        try:
            alt_mean, alt_cov, alt = predict_arima(
                data, config, horizon, d_override=0, progress=progress, cancelled=cancelled
            )
            dist = original_distribution(
                alt_mean,
                alt_cov,
                None,
                spec,
                raw.frame[target].to_numpy(),
                data.frequency,
                data.sample["transforms"][target],
                config["seed"],
            )
            result["sensitivity"]["variants"].append(
                {
                    "id": "d0",
                    "label": "d = 0",
                    "status": "ok",
                    "chosen": alt["chosen"],
                    "distribution": dist,
                }
            )
        except (ValueError, np.linalg.LinAlgError) as exc:
            result["sensitivity"]["variants"].append(
                {"id": "d0", "label": "d = 0", "status": "blocked", "reason": str(exc)}
            )
    return result


ARIMA_PARAMS = dict(
    order_selection=choice("aicc", "aicc", "fixed"),
    p=integer(1, 0, 4),
    d=integer(1, 0, 1),
    q=integer(0, 0, 4),
    seasonal_p=integer(0, 0, 1),
    seasonal_q=integer(0, 0, 1),
)
COMMON_PARAMS = dict(
    horizon=integer(8, 1, 24), future_exog=choice("unspecified", "unspecified", "hold_last", "zero")
)


class ARIMAPlugin(BasePlugin):
    id = "uni.arima"
    family = "Forecasting"
    title = "ARIMA / SARIMA"
    summary = "SARIMAX forecasts, explicit ADF/KPSS differencing and AICc order search."
    label = "Forecast"
    inputs = {"min_series": 1, "max_series": 8, "frequencies": ["M", "Q"]}
    params = schema(**COMMON_PARAMS, **ARIMA_PARAMS)
    assumptions = [
        "Final-vintage observations, stable parameters and explicit future controls.",
        (
            "68/90% predictive intervals in original units; SARIMAX intervals "
            "condition on fitted parameters."
        ),
    ]
    references = [
        {
            "title": "statsmodels SARIMAX",
            "url": (
                "https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html"
            ),
        }
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        return forecast_checks(data, config)

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return run_arima(data, config)
