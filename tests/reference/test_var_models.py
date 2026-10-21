"""Deterministic reference contract, written before the VAR implementation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.api import VAR

from macrolab.models.base import AnalysisData
from macrolab.models.var import (
    RecursiveIdentificationPlugin,
    VAROLSPlugin,
    normalized_asymptotic_se,
    residual_bootstrap,
)


def fixture(*, exogenous: bool = False) -> tuple[AnalysisData, dict[str, Any]]:
    generator = np.random.default_rng(19021)
    coefficients = np.array([[0.45, 0.08, 0.0], [0.05, 0.35, -0.1], [0.0, 0.1, 0.3]])
    impact = np.array([[0.6, 0.0, 0.0], [0.12, 0.4, 0.0], [0.08, 0.07, 0.25]])
    values = np.zeros((380, 3))
    for t in range(1, len(values)):
        values[t] = coefficients @ values[t - 1] + impact @ generator.normal(size=3)
    frame = pd.DataFrame(values[100:], columns=["output", "prices", "rate"])
    frame.index = pd.period_range("1950Q1", periods=len(frame), freq="Q")
    exog = None
    if exogenous:
        exog = pd.DataFrame({"covid_dummy": np.zeros(len(frame))}, index=frame.index)
        exog.iloc[120:124] = 1
        frame.iloc[120:124] += np.array([1.0, 0.5, 0.2])
        frame["external"] = generator.normal(size=len(frame))
    config: dict[str, Any] = {
        "seed": 109,
        "series": [
            {"concept_id": "output", "role": "endogenous"},
            {"concept_id": "prices", "role": "response"},
            {"concept_id": "rate", "role": "shock"},
        ],
        "model": {"id": "var.ols", "params": {"lags": 2, "trend": "c"}},
        "identification": {
            "id": "recursive",
            "params": {"order": ["output", "prices", "rate"]},
        },
        "outputs": {
            "irf": {"horizon": 8, "bands": 0.68, "shock_size": 1.0, "method": "asymptotic"}
        },
    }
    if exogenous:
        config["series"].append({"concept_id": "external", "role": "exogenous"})
    return AnalysisData(frame=frame, exog=exog), config


@pytest.mark.parametrize("trend", ["c", "ct", "n"])
@pytest.mark.parametrize("exogenous", [False, True])
def test_coefficients_standard_errors_irfs_and_fevd_match_statsmodels(
    trend: str, exogenous: bool
) -> None:
    data, config = fixture(exogenous=exogenous)
    config["model"]["params"]["trend"] = trend
    names = ["output", "prices", "rate"]
    reference_exog = pd.concat([data.frame[["external"]], data.exog], axis=1) if exogenous else None
    reference = VAR(data.frame[names], exog=reference_exog).fit(2, trend=trend)

    result = VAROLSPlugin().run(data, config)

    lookup = {(row["term"], row["equation"]): row for row in result["coefficients_table"]}
    for term in reference.params.index:
        for equation in names:
            assert lookup[term, equation]["estimate"] == pytest.approx(
                reference.params.loc[term, equation], abs=1e-8
            )
            assert lookup[term, equation]["std_error"] == pytest.approx(
                reference.stderr.loc[term, equation], abs=1e-8
            )
    impact = np.linalg.cholesky(reference.sigma_u)
    expected = reference.irf(8).orth_irfs[:, :, 2] / impact[2, 2]
    np.testing.assert_allclose(result["irf"]["values"], expected, atol=1e-8, rtol=0)
    np.testing.assert_allclose(
        result["fevd"]["values"], reference.fevd(8).decomp.transpose(1, 0, 2), atol=1e-8, rtol=0
    )
    np.testing.assert_allclose(np.sum(result["fevd"]["values"], axis=2), 1.0, atol=1e-12)
    assert result["diagnostics"]["estimated_indices"] == list(map(str, data.frame.index[2:]))
    assert result["diagnostics"]["nobs"] == reference.nobs


@pytest.mark.parametrize("criterion", ["aic", "bic", "hq"])
def test_lag_selection_matches_statsmodels(criterion: str) -> None:
    data, config = fixture()
    config["model"]["params"].update(lag_selection=criterion, maxlags=5)
    expected = VAR(data.frame).fit(5, ic="hqic" if criterion == "hq" else criterion).k_ar
    result = VAROLSPlugin().run(data, config)
    assert result["diagnostics"]["selected_lags"] == expected


@pytest.mark.parametrize(
    "order", [["output", "prices"], ["output", "rate", "rate"], ["output", "prices", "alien"]]
)
def test_recursive_order_must_be_exact_selected_variable_permutation(order: list[str]) -> None:
    data, config = fixture()
    config["identification"]["params"]["order"] = order
    assert any(check["level"] == "block" for check in VAROLSPlugin().check(data, config))
    with pytest.raises(ValueError):
        VAROLSPlugin().run(data, config)


def test_recursive_plugin_and_alias_produce_same_result() -> None:
    data, config = fixture()
    first = VAROLSPlugin().run(data, config)
    alias = deepcopy(config)
    alias["identification"]["id"] = "ident.recursive"
    second = RecursiveIdentificationPlugin().run(data, alias)
    np.testing.assert_array_equal(first["irf"]["values"], second["irf"]["values"])


def test_fixed_shock_normalization_applies_to_asymptotic_impact_bands() -> None:
    data, config = fixture()
    config["outputs"]["irf"]["shock_size"] = -0.5
    result = VAROLSPlugin().run(data, config)
    assert result["irf"]["values"][0][2] == pytest.approx(-0.5)
    assert result["irf"]["lower"][0][2] == pytest.approx(-0.5, abs=1e-10)
    assert result["irf"]["upper"][0][2] == pytest.approx(-0.5, abs=1e-10)


def test_zero_lag_model_has_only_contemporaneous_responses_and_valid_fevd() -> None:
    data, config = fixture()
    config["model"]["params"]["lags"] = 0
    result = VAROLSPlugin().run(data, config)
    np.testing.assert_array_equal(np.asarray(result["irf"]["values"])[1:], 0.0)
    np.testing.assert_allclose(np.sum(result["fevd"]["values"], axis=2), 1.0, atol=1e-12)
    assert result["diagnostics"]["stable"] is True


def test_normalized_delta_standard_errors_match_independent_numerical_derivatives() -> None:
    from scipy.linalg import block_diag
    from statsmodels.tsa.vector_ar.var_model import ma_rep

    data, _config = fixture()
    fitted = VAR(data.frame).fit(2, trend="c")
    variables, lags, horizon, shock = 3, 2, 3, 1
    pairs = [(row, col) for col in range(variables) for row in range(col, variables)]
    sigma = np.asarray(fitted.sigma_u)
    alpha = np.asarray(fitted.params)[fitted.k_exog :].ravel()
    parameters = np.concatenate([alpha, np.array([sigma[row, col] for row, col in pairs])])

    def response(vector: np.ndarray) -> np.ndarray:
        coefficients = vector[: len(alpha)].reshape(lags, variables, variables).transpose(0, 2, 1)
        covariance = np.zeros((variables, variables))
        for value, (row, col) in zip(vector[len(alpha) :], pairs, strict=True):
            covariance[row, col] = covariance[col, row] = value
        impact = np.linalg.cholesky(covariance)
        return (ma_rep(coefficients, horizon) @ (impact[:, shock] / impact[shock, shock])).ravel()

    gradient = []
    step = 1e-6
    for position in range(len(parameters)):
        plus, minus = parameters.copy(), parameters.copy()
        plus[position] += step
        minus[position] -= step
        gradient.append((response(plus) - response(minus)) / (2 * step))
    jacobian = np.asarray(gradient).T
    covariance = block_diag(fitted._cov_alpha, fitted._cov_sigma / fitted.nobs)
    expected = np.sqrt(np.maximum(np.diag(jacobian @ covariance @ jacobian.T), 0)).reshape(
        horizon + 1, variables
    )
    actual = normalized_asymptotic_se(fitted, horizon, shock, 1.0)
    np.testing.assert_allclose(actual, expected, atol=1e-8, rtol=0)


def test_bootstrap_refit_with_trend_and_covid_dummies_matches_direct_statsmodels() -> None:
    data, _config = fixture(exogenous=True)
    names = ["output", "prices", "rate"]
    exog = pd.concat([data.frame[["external"]], data.exog], axis=1)
    fitted = VAR(data.frame[names], exog=exog).fit(2, trend="ct")
    actual, _metadata = residual_bootstrap(
        fitted, horizon=5, shock=2, size=0.5, draws=1, seed=61052
    )
    residuals = np.asarray(fitted.resid)
    residuals = (residuals - residuals.mean(axis=0)) * np.sqrt(fitted.nobs / fitted.df_resid)
    sampled = residuals[np.random.default_rng(61052).integers(0, fitted.nobs, fitted.nobs)]
    simulated = np.zeros_like(np.asarray(fitted.endog))
    simulated[:2] = fitted.endog[:2]
    coefficients = np.asarray(fitted.params)
    for t in range(2, len(simulated)):
        predictors = np.concatenate(
            [[1.0, t + 1], np.asarray(exog.iloc[t]), simulated[t - 1], simulated[t - 2]]
        )
        simulated[t] = predictors @ coefficients + sampled[t - 2]
    reference = VAR(pd.DataFrame(simulated, columns=names, index=data.frame.index), exog=exog).fit(
        2, trend="ct"
    )
    expected = reference.irf(5).orth_irfs[:, :, 2] * (
        0.5 / np.linalg.cholesky(reference.sigma_u)[2, 2]
    )
    np.testing.assert_allclose(actual[0], expected, atol=1e-8, rtol=0)


@pytest.mark.parametrize("confidence", [0.9, 0.95, 0.99])
def test_coefficient_intervals_use_requested_confidence_independent_of_irf(
    confidence: float,
) -> None:
    from scipy.stats import norm

    data, config = fixture()
    config["outputs"]["confidence"] = confidence
    config["outputs"]["irf"]["bands"] = 0.68
    result = VAROLSPlugin().run(data, config)
    reference = VAR(data.frame).fit(2, trend="c")
    quantile = norm.ppf((1 + confidence) / 2)
    for row in result["coefficients_table"]:
        estimate = reference.params.loc[row["term"], row["equation"]]
        error = reference.stderr.loc[row["term"], row["equation"]]
        assert row["band_level"] == confidence
        assert row["lower"] == pytest.approx(estimate - quantile * error, abs=1e-8)
        assert row["upper"] == pytest.approx(estimate + quantile * error, abs=1e-8)
    assert result["irf"]["band_level"] == 0.68


def test_reduced_form_default_coefficient_confidence_is_95_percent() -> None:
    data, config = fixture()
    config["identification"] = None
    config.pop("outputs")
    assert {
        row["band_level"] for row in VAROLSPlugin().run(data, config)["coefficients_table"]
    } == {0.95}


def test_fixed_lag_omits_only_inactive_generated_covid_dummy() -> None:
    generator = np.random.default_rng(555)
    frame = pd.DataFrame(
        generator.normal(size=(21, 2)),
        columns=["x", "y"],
        index=pd.period_range("2021Q2", periods=21, freq="Q"),
    )
    exog = pd.DataFrame({"covid_2021-Q2": [1.0] + [0.0] * 20}, index=frame.index)
    data = AnalysisData(frame=frame, exog=exog)
    config = {
        "series": [{"concept_id": name, "role": "endogenous"} for name in frame],
        "model": {"id": "var.ols", "params": {"lags": 1, "trend": "c"}},
    }
    output = VAROLSPlugin().run(data, config)
    reference = VAR(frame).fit(1, trend="c")
    diagnostics = output["diagnostics"]
    assert diagnostics["nobs"] == 20
    assert diagnostics["parameter_count_per_equation"] == 3
    assert diagnostics["omitted_zero_covid_regressors"] == ["covid_2021-Q2"]
    np.testing.assert_allclose(diagnostics["coefficients"], reference.coefs, atol=1e-8, rtol=0)
    assert list(data.exog.columns) == ["covid_2021-Q2"]


@pytest.mark.parametrize("kind", ["selected_exogenous", "other_fixed", "nonperiod_covid_prefix"])
def test_zero_user_regressors_are_not_silently_omitted(kind: str) -> None:
    data, config = fixture()
    config["identification"] = None
    if kind == "selected_exogenous":
        data.frame["external"] = 0.0
        config["series"].append({"concept_id": "external", "role": "exogenous"})
    else:
        name = "covid_dummy" if kind == "nonperiod_covid_prefix" else "fixed_user"
        data.exog = pd.DataFrame({name: np.zeros(len(data.frame))}, index=data.frame.index)
    with pytest.raises(ValueError, match="collinear"):
        VAROLSPlugin().run(data, config)


def test_automatic_lag_reintroduces_covid_dummy_active_after_selected_holdback() -> None:
    generator = np.random.default_rng(8)
    values = np.zeros((150, 3))
    for t in range(2, 150):
        values[t] = 0.2 * values[t - 1] + 0.6 * values[t - 2] + generator.normal(size=3)
    frame = pd.DataFrame(
        values[-50:], columns=["x", "y", "z"], index=pd.period_range("2020Q1", periods=50, freq="Q")
    )
    exog = pd.DataFrame(
        {"covid_2020-Q1": np.eye(50)[0], "covid_2020-Q4": np.eye(50)[3]}, index=frame.index
    )
    data = AnalysisData(frame=frame, exog=exog)
    config = {
        "series": [{"concept_id": name, "role": "endogenous"} for name in frame],
        "model": {"id": "var.ols", "params": {"trend": "c", "lag_selection": "aic", "maxlags": 4}},
    }
    result = VAROLSPlugin().run(data, config)
    diagnostics = result["diagnostics"]
    assert diagnostics["selected_lags"] == 2
    assert diagnostics["omitted_zero_covid_regressors"] == ["covid_2020-Q1"]
    assert diagnostics["lag_selection_omitted_zero_covid_regressors"] == [
        "covid_2020-Q1",
        "covid_2020-Q4",
    ]
    assert diagnostics["parameter_count_per_equation"] == 8
    reference = VAR(frame, exog=exog[["covid_2020-Q4"]]).fit(2, trend="c")
    np.testing.assert_allclose(diagnostics["coefficients"], reference.coefs, atol=1e-8, rtol=0)
