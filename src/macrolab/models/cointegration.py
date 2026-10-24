"""Pinned statsmodels cointegration tests and rank-fixed VECM inference."""

from __future__ import annotations

from typing import Any

import numpy as np
from statsmodels.tsa.stattools import coint  # type: ignore[import-untyped]
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen  # type: ignore[import-untyped]

from macrolab.analysis.seasonality import require_regular_calendar
from macrolab.models.base import AnalysisData, BasePlugin, check
from macrolab.models.forecast_common import Cancelled, Progress, tick
from macrolab.models.linear import choice, integer, schema

# These are the three unrestricted deterministic cases exposed by coint_johansen.
CASES = {
    "none": (-1, "n", "No deterministic terms (case I)"),
    "constant": (0, "co", "Unrestricted constant, no linear trend (case III)"),
    "linear_trend": (1, "colo", "Unrestricted constant and linear trend (case V)"),
}
PARAMS = dict(
    lags=integer(2, 1, 12),
    deterministic=choice("constant", *CASES),
    eg_trend=choice("c", "n", "c", "ct", "ctt"),
    eg_lags=integer(4, 0, 24),
)
CAVEAT = (
    "Critical values are asymptotic; small samples can distort test size. "
    "Check that the inputs are I(1), not I(2), and inspect sensitivity "
    "to lags and deterministic terms."
)


def settings(
    data: AnalysisData, config: dict[str, Any]
) -> tuple[list[str], np.ndarray[Any, Any], int, str]:
    names = [s["concept_id"] for s in config["series"]]
    p = config["model"]["params"]
    return (
        names,
        data.frame[names].to_numpy(),
        int(p.get("lags", 2)),
        p.get("deterministic", "constant"),
    )


def test_cointegration(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    names, y, p, case = settings(data, config)
    det_order, deterministic, description = CASES[case]
    fitted = coint_johansen(y, det_order, p - 1)
    rank = 0
    while rank < len(names) and fitted.lr1[rank] > fitted.cvt[rank, 1]:
        rank += 1
    johansen = [
        dict(
            null_rank=r,
            trace=float(fitted.lr1[r]),
            maximum_eigenvalue=float(fitted.lr2[r]),
            trace_critical=dict(zip(["90", "95", "99"], map(float, fitted.cvt[r]), strict=True)),
            max_eigen_critical=dict(
                zip(["90", "95", "99"], map(float, fitted.cvm[r]), strict=True)
            ),
        )
        for r in range(len(names))
    ]
    eg = []
    if len(names) == 2:
        options = config["model"]["params"]
        trend = options.get("eg_trend", "c")
        for i, j in [(0, 1), (1, 0)]:
            statistic, probability, critical = coint(
                y[:, i],
                y[:, j],
                trend=trend,
                maxlag=int(options.get("eg_lags", 4)),
                autolag=None,
            )
            if not np.isfinite(statistic):
                raise ValueError("Engle–Granger is degenerate for perfectly collinear inputs.")
            eg.append(
                dict(
                    dependent=names[i],
                    regressor=names[j],
                    trend=trend,
                    trend_label={
                        "n": "No deterministic term",
                        "c": "Constant",
                        "ct": "Constant and linear trend",
                        "ctt": "Constant, linear and quadratic trend",
                    }[trend],
                    statistic=float(statistic),
                    p_value=float(probability),
                    critical_values=None
                    if not np.isfinite(critical).all()
                    else dict(zip(["99", "95", "90"], map(float, critical), strict=True)),
                )
            )
    return {
        "cointegration": dict(
            variables=names,
            deterministic_case=description,
            statsmodels_det_order=det_order,
            vecm_deterministic=deterministic,
            var_lags=p,
            lagged_differences=p - 1,
            suggested_rank=rank,
            rank_rule="Sequential trace test at 95%",
            johansen=johansen,
            engle_granger=eg,
            normalisation_note="Both Engle–Granger normalisations are shown; finite-sample "
            "conclusions can depend on the dependent variable.",
            caveat=CAVEAT,
        ),
        "diagnostics": {
            "estimated_indices": list(map(str, data.frame.index[p:])),
            "nobs": len(y) - p,
        },
        "sensitivity": {"status": "ok", "variants": []},
    }


def impulse_responses(
    coefficients: np.ndarray[Any, Any], covariance: np.ndarray[Any, Any], horizon: int
) -> np.ndarray[Any, Any]:
    p, k, _ = coefficients.shape
    responses = np.zeros((horizon + 1, k, k))
    responses[0] = np.linalg.cholesky(covariance)
    for h in range(1, horizon + 1):
        for lag in range(1, min(h, p) + 1):
            responses[h] += coefficients[lag - 1] @ responses[h - lag]
    return responses


def fit_vecm(
    data: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    result = test_cointegration(data, config)
    names, y, p, case = settings(data, config)
    options = config["model"]["params"]
    rank, horizon, draws = (
        int(options.get("rank", 1)),
        int(options.get("horizon", 20)),
        int(options.get("draws", 200)),
    )
    deterministic = CASES[case][1]
    fitted = VECM(y, k_ar_diff=p - 1, coint_rank=rank, deterministic=deterministic).fit()
    coefs, sigma = np.asarray(fitted.var_rep), np.asarray(fitted.sigma_u)
    point = impulse_responses(coefs, sigma, horizon)
    # Treat the first p observations and deterministic sequence as fixed. Center residuals.
    residuals = np.asarray(fitted.resid)
    residuals = residuals - residuals.mean(axis=0)
    lag_prediction = sum(y[p - lag : len(y) - lag] @ coefs[lag - 1].T for lag in range(1, p + 1))
    deterministic_path = np.asarray(fitted.fittedvalues) - lag_prediction
    samples = []
    rng = np.random.default_rng(config["seed"])
    for draw in range(draws):
        tick(progress, cancelled, "vecm_bootstrap", draw, draws)
        generated = y.copy()
        innovation = residuals[rng.integers(0, len(residuals), len(residuals))]
        for t in range(p, len(y)):
            generated[t] = deterministic_path[t - p] + innovation[t - p]
            for lag in range(1, p + 1):
                generated[t] += coefs[lag - 1] @ generated[t - lag]
        refit = VECM(generated, k_ar_diff=p - 1, coint_rank=rank, deterministic=deterministic).fit()
        response = impulse_responses(np.asarray(refit.var_rep), np.asarray(refit.sigma_u), horizon)
        if not np.isfinite(response).all():
            raise ValueError(f"VECM bootstrap draw {draw + 1} is non-finite; no draw was dropped.")
        samples.append(response)
    tick(progress, cancelled, "vecm_bootstrap", draws, draws)
    bands = (
        {
            str(level): dict(
                lower=np.quantile(samples, (1 - level) / 2, axis=0).tolist(),
                upper=np.quantile(samples, (1 + level) / 2, axis=0).tolist(),
            )
            for level in [0.68, 0.9]
        }
        if draws
        else {}
    )
    shock = options.get("shock") or names[0]
    if shock not in names:
        raise ValueError("The selected VECM impulse must be one of the ordered variables.")
    s = names.index(shock)
    result["vecm"] = dict(
        rank=rank,
        suggested_rank=result["cointegration"]["suggested_rank"],
        beta=fitted.beta.tolist(),
        beta_std_error=fitted.stderr_beta.tolist(),
        alpha=fitted.alpha.tolist(),
        alpha_std_error=fitted.stderr_alpha.tolist(),
        gamma=fitted.gamma.tolist(),
        gamma_std_error=fitted.stderr_gamma.tolist(),
        deterministic_coefficients=fitted.det_coef.tolist(),
        normalisation="The first rank rows of beta are an identity matrix "
        "(statsmodels normalisation).",
        var_coefficients=coefs.tolist(),
        residual_covariance=sigma.tolist(),
        order=names,
        draws=draws,
        seed=config["seed"],
        bands=bands,
        all_responses=point.tolist(),
        inference="Centered residual bootstrap; rank fixed and coefficients "
        "re-estimated; initial observations fixed; no draws excluded.",
        permanence_note="VECM responses can be permanent and need not return to zero.",
    )
    result["irf"] = dict(
        variables=names,
        shock=shock,
        shock_size=float(point[0, s, s]),
        periods=list(range(horizon + 1)),
        values=point[:, :, s].tolist(),
        lower=np.asarray(bands["0.68"]["lower"])[:, :, s].tolist()
        if draws
        else point[:, :, s].tolist(),
        upper=np.asarray(bands["0.68"]["upper"])[:, :, s].tolist()
        if draws
        else point[:, :, s].tolist(),
        confidence=0.68,
        band_level=0.68,
        band_method="rank-fixed residual bootstrap" if draws else "disabled",
        identification="Recursive ordering; one structural standard deviation",
    )
    result["diagnostics"].update(rank=rank, bootstrap_draws=draws)
    return result


class CointegrationPlugin(BasePlugin):
    id, family, title = "test.coint", "tests", "Cointegration tests"
    label = "Long-run association; not causation"
    summary = "Two Engle–Granger normalisations and Johansen rank tests on levels."
    inputs = {"min_series": 2, "max_series": 12, "frequencies": ["M", "Q", "A"]}
    params = schema(**PARAMS)
    assumptions = [CAVEAT]
    references = [
        {
            "title": "statsmodels coint / MacKinnon",
            "url": "https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.stattools.coint.html",
        },
        {
            "title": "statsmodels Johansen",
            "url": "https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.vector_ar.vecm.coint_johansen.html",
        },
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        errors = []
        try:
            require_regular_calendar(data)
        except ValueError as exc:
            errors.append(check("block", "cointegration_calendar", str(exc)))
        if any(s["transform"] not in {"level", "log"} for s in config["series"]):
            errors.append(
                check(
                    "block",
                    "cointegration_levels",
                    "Cointegration requires levels or log levels; differences and "
                    "growth rates remove the long-run relation being tested.",
                )
            )
        if any(s["role"] == "exogenous" for s in config["series"]) or (
            data.exog is not None and data.exog.shape[1]
        ):
            errors.append(
                check(
                    "block",
                    "cointegration_controls",
                    "The pinned Johansen test does not accept external or COVID dummy "
                    "regressors. Choose include for COVID and use only the stated "
                    "deterministic case.",
                )
            )
        n, k = data.frame.shape
        if not 2 <= k <= 12:
            errors.append(
                check(
                    "block",
                    "cointegration_dimension",
                    "The pinned Johansen critical values support 2–12 variables.",
                )
            )
        p = int(config["model"]["params"].get("lags", 2))
        if n - p <= k * p + 3 or n < 25:
            errors.append(
                check(
                    "block",
                    "cointegration_sample",
                    "Too few observations for the selected cointegration lag order and dimension.",
                )
            )
        if self.id == "vecm" and not 0 <= int(config["model"]["params"].get("rank", 1)) <= k:
            errors.append(
                check(
                    "block",
                    "cointegration_rank",
                    "Choose a rank from zero to the number of variables.",
                )
            )
        return errors

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return test_cointegration(data, config)


class VECMPlugin(CointegrationPlugin):
    id, title = "vecm", "Vector error-correction model"
    summary = "User-chosen rank, normalised long-run relations and rank-fixed bootstrap responses."
    params = schema(
        **PARAMS,
        rank=integer(1, 0, 12),
        horizon=integer(20, 1, 48),
        draws=integer(200, 0, 1000),
        shock={"type": "string", "default": ""},
    )

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return fit_vecm(data, config)
