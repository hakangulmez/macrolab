"""Independent reference, inversion, bootstrap and explicit no-look-ahead checks."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm, t
from statsmodels.tsa.api import VAR
from statsmodels.tsa.statespace.sarimax import SARIMAX

from macrolab.analysis.config import validated_config
from macrolab.ident.bootstrap import CancelledError
from macrolab.models.arima import (
    ForecastSARIMAX,
    choose_order,
    difference_decision,
    joint_prediction,
    run_arima,
)
from macrolab.models.base import AnalysisData
from macrolab.models.forecast_common import forecast_checks, original_distribution, training
from macrolab.models.forecast_eval import dm_hln, origin_forecast, run_evaluation
from macrolab.models.forecast_var import predict_var, run_var_forecast


def fixture(model="uni.arima", count=105, transform="level", frequency="Q", **params):
    rng = np.random.default_rng(73)
    y = np.zeros((count, 2))
    for i in range(1, count):
        y[i] = 0.55 * y[i - 1] + rng.normal(size=2) * 0.3
    y += [5, 3]
    columns = ["x"] if model == "uni.arima" else ["x", "z"]
    index = [
        str(p).replace("Q", "-Q") for p in pd.period_range("1999", periods=count, freq=frequency)
    ]
    data = AnalysisData(
        pd.DataFrame(y[:, : len(columns)], index=index, columns=columns), frequency=frequency
    )
    config = validated_config(
        dict(
            schema_version=1,
            snapshot_id="fixture",
            countries=["SYN"],
            frequency=frequency,
            series=[
                dict(
                    concept_id=c,
                    role="dependent" if c == "x" else "endogenous",
                    transform=transform,
                    transform_params={"base_period": index[0]}
                    if transform == "index_to_base"
                    else {},
                )
                for c in columns
            ],
            model=dict(id=model, params=params),
            seed=47,
        )
    )
    return data, config


def test_ar1_closed_form_joint_covariance_and_intervals():
    y = np.random.default_rng(10).normal(size=150)
    phi, intercept, sigma = 0.7, 0.1, 0.4
    fitted = SARIMAX(y, order=(1, 0, 0), trend="c").filter([intercept, phi, sigma**2])
    mean, cov = joint_prediction(fitted, np.zeros((12, 0)), 12)
    h = np.arange(1, 13)
    expected = phi**h * y[-1] + intercept * (1 - phi**h) / (1 - phi)
    np.testing.assert_allclose(mean, expected, atol=1e-14)
    ref = sigma**2 * (1 - phi ** (2 * h)) / (1 - phi**2)
    np.testing.assert_allclose(np.diag(cov), ref, atol=1e-14)
    for i in range(12):
        for j in range(i, 12):
            assert cov[i, j] == pytest.approx(phi ** (j - i) * ref[i], abs=1e-14)
    r = original_distribution(mean, cov, None, {"transform": "level"}, y, "Q", {}, 8)
    np.testing.assert_allclose(
        r["bands"]["0.9"]["upper"], expected + norm.ppf(0.95) * np.sqrt(ref), atol=1e-14
    )
    np.testing.assert_allclose(
        fitted.get_forecast(12).conf_int(alpha=0.1),
        np.column_stack([r["bands"]["0.9"]["lower"], r["bands"]["0.9"]["upper"]]),
        atol=1e-14,
    )


def test_fixed_sarimax_native_reference_and_seed():
    data, c = fixture(order_selection="fixed", p=1, d=0, q=0)
    trained = training(data, c)
    selected = choose_order(trained, c)
    y = data.frame.x.to_numpy()
    location = y.mean()
    scale = y.std()
    ref = SARIMAX((y - location) / scale, order=(1, 0, 0), trend="c").fit(
        disp=False,
        method="lbfgs",
        maxiter=150,
        optim_score="approx",
        optim_complex_step=True,
        pgtol=1e-8,
        factr=100,
    )
    np.testing.assert_allclose(ref.params, selected["fit"].params, atol=1e-6, rtol=0)
    r = run_arima(data, c)
    s = run_arima(data, c)
    assert r == s
    np.testing.assert_allclose(
        r["forecast"]["distributions"]["x"]["mean"],
        ref.get_forecast(8).predicted_mean * scale + location,
        atol=1e-14,
    )
    assert r["forecast"]["arima"]["ljung_box"]["p_value"] is not None


def test_difference_decision_agreement_and_disagreement(monkeypatch):
    import macrolab.models.arima as module

    for a, k, d, disagree in [
        (0.01, 0.1, 0, False),
        (0.2, 0.01, 1, False),
        (0.01, 0.01, 1, True),
        (0.2, 0.1, 1, True),
    ]:
        monkeypatch.setattr(module, "adfuller", lambda *args, a=a, **kwargs: (0, a, 1))
        monkeypatch.setattr(module, "kpss", lambda *args, k=k, **kwargs: (0, k, 1))
        result = difference_decision(np.arange(80))
        assert result["d"] == d and result["disagree"] == disagree


@pytest.mark.parametrize(
    "order,seasonal",
    [
        ((2, 0, 2), (0, 0, 0, 0)),
        ((2, 1, 1), (0, 0, 0, 0)),
        ((1, 0, 1), (1, 0, 1, 12)),
    ],
)
def test_stationary_initialization_matches_sarimax_and_score(order, seasonal):
    y = np.random.default_rng(914).normal(size=160)
    options = dict(order=order, seasonal_order=seasonal, trend="c", simple_differencing=True)
    model, reference = ForecastSARIMAX(y, **options), SARIMAX(y, **options)
    theta = np.repeat(0.15, model.k_params)
    theta[-1] = 1.0
    params = reference.transform_params(theta)
    actual, expected = model.filter(params), reference.filter(params)
    assert actual.llf == pytest.approx(expected.llf, abs=1e-10)
    np.testing.assert_allclose(
        actual.get_forecast(12).predicted_mean,
        expected.get_forecast(12).predicted_mean,
        atol=1e-11,
        rtol=0,
    )
    np.testing.assert_allclose(
        actual.get_forecast(12).var_pred_mean,
        expected.get_forecast(12).var_pred_mean,
        atol=1e-11,
        rtol=0,
    )
    for axis in np.eye(len(theta)):
        score = (
            np.imag(
                model.loglike(
                    theta.astype(complex) + axis * 1j * 1e-20, transformed=False, complex_step=True
                )
            )
            / 1e-20
        )
        step = 1e-5
        finite = (
            model.loglike(theta + axis * step, transformed=False)
            - model.loglike(theta - axis * step, transformed=False)
        ) / (2 * step)
        assert score == pytest.approx(finite, abs=1e-6)


@pytest.mark.parametrize("transform", ["level", "diff", "yoy_diff", "index_to_base"])
def test_linear_inverse_joint_covariance(transform):
    mean = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    cov = 0.04 * np.fromfunction(lambda i, j: 0.5 ** abs(i - j), (6, 6))
    raw = np.arange(1, 13, dtype=float)
    spec = {"transform": transform}
    detail = {"base_value": 12}
    r = original_distribution(mean, cov, None, spec, raw, "Q", detail, 33)
    from macrolab.analysis.transforms import invert_transform

    expected = invert_transform(mean.tolist(), transform, raw.tolist(), "Q", 12)
    np.testing.assert_allclose(r["mean"], expected, atol=1e-14)
    paths = np.random.default_rng(33).multivariate_normal(mean, cov, 150000)
    inverse = np.array(
        [invert_transform(v.tolist(), transform, raw.tolist(), "Q", 12) for v in paths]
    )
    np.testing.assert_allclose(
        r["bands"]["0.9"]["upper"], np.quantile(inverse, 0.95, axis=0), atol=0.015
    )


@pytest.mark.parametrize("transform", ["log", "log_diff", "yoy_pct", "qoq_saar"])
def test_nonlinear_inverse_seeded_intervals(transform):
    mean = np.full(8, 0.01)
    cov = np.eye(8) * 0.001
    r = original_distribution(
        mean, cov, None, {"transform": transform}, np.full(12, 10.0), "Q", {}, 73, 100000
    )
    assert r == original_distribution(
        mean, cov, None, {"transform": transform}, np.full(12, 10.0), "Q", {}, 73, 100000
    )
    if transform == "log":
        np.testing.assert_allclose(r["mean"], np.exp(mean + np.diag(cov) / 2), atol=0.0003)
        np.testing.assert_allclose(
            r["bands"]["0.9"]["upper"],
            np.exp(mean + norm.ppf(0.95) * np.sqrt(np.diag(cov))),
            atol=0.001,
        )
    assert all(
        a < b for a, b in zip(r["bands"]["0.9"]["lower"], r["bands"]["0.9"]["upper"], strict=True)
    )
    assert r != original_distribution(
        mean, cov, None, {"transform": transform}, np.full(12, 10.0), "Q", {}, 74, 100000
    )


def test_invalid_inverse_draws_never_silently_dropped():
    with pytest.raises(ValueError, match="no draws were dropped"):
        original_distribution(
            np.zeros(2),
            None,
            np.array([[0.0, -101.0]]),
            {"transform": "yoy_pct"},
            np.ones(4),
            "Q",
            {},
            0,
        )


def test_ols_var_reference_reestimation_seed_and_bvar():
    data, c = fixture("fc.var", draws=100)
    mean, paths, detail = predict_var(training(data, c), c, 8)
    ref = VAR(data.frame).fit(2)
    np.testing.assert_allclose(mean, ref.forecast(data.frame.to_numpy()[-2:], 8), atol=1e-14)
    assert detail["draws"] == 100
    np.testing.assert_array_equal(paths, predict_var(training(data, c), c, 8)[1])
    c["seed"] += 1
    assert not np.array_equal(paths, predict_var(training(data, c), c, 8)[1])
    c["model"]["params"]["estimator"] = "bvar"
    result = run_var_forecast(data, c)
    assert result["forecast"]["var"]["ar_residual_scales"]
    assert "coefficient and covariance" in result["forecast"]["interval_scope"]


def test_dm_hln_independent_fixture_and_negative_fallback():
    rng = np.random.default_rng(200)
    for h in [1, 4, 8]:
        a = rng.normal(size=90)
        b = rng.normal(size=90) * 1.2
        d = a * a - b * b
        z = d - d.mean()
        n = len(z)
        gamma = np.correlate(z, z, "full")[n - 1 : n - 1 + h] / n
        v = gamma[0] + 2 * sum(gamma[1:])
        fallback = v < 0
        if fallback:
            v = gamma[0] + 2 * sum(gamma[j] * (h - j) / h for j in range(1, h))
        statistic = d.mean() / np.sqrt(v / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
        result = dm_hln(a, b, h)
        assert result["statistic"] == pytest.approx(statistic, abs=1e-14)
        assert result["p_value"] == pytest.approx(2 * t.sf(abs(statistic), n - 1), abs=1e-14)
    a = np.sqrt(np.tile([3.0, 1.0], 40))
    b = np.sqrt(np.repeat(2.0, 80))
    assert dm_hln(a, b, 2)["bartlett_fallback"]
    assert dm_hln(np.ones(20), np.ones(20), 4)["status"] == "unavailable"


@pytest.mark.parametrize(
    "transform",
    ["level", "log", "diff", "log_diff", "yoy_pct", "yoy_diff", "qoq_saar", "index_to_base"],
)
def test_every_origin_is_invariant_to_post_origin_values(transform):
    data, c = fixture(
        "fc.eval", count=48, transform=transform, order_selection="fixed", p=1, d=0, q=0, draws=100
    )
    if transform == "index_to_base":
        for s in c["series"]:
            s["transform_params"] = {"base_period": str(data.frame.index[0])}
    if transform == "qoq_saar":
        data.frame = 5 + (data.frame - data.frame.mean()) * 0.01
    fixed = None
    for stop in range(40, 48):
        altered = deepcopy(data)
        altered.frame.iloc[stop:] *= 1000
        a, info = origin_forecast(data, c, stop, 8, fixed)
        b, other = origin_forecast(altered, c, stop, 8, fixed)
        assert info == other
        for model in a:
            np.testing.assert_array_equal(a[model], b[model])
        fixed = {"ar_order": info["ar_order"], "arima": info["arima"]}


def test_filters_blocked_and_future_exogenous_explicit():
    data, c = fixture("fc.var")
    c["series"][1]["role"] = "exogenous"
    assert any(x["code"] == "forecast_exog_path" for x in forecast_checks(data, c))
    c["model"]["params"]["future_exog"] = "hold_last"
    result = run_var_forecast(data, c)
    assert any("held at last" in n for n in result["forecast"]["assumptions"])
    c["series"][0]["transform"] = "hp_cycle"
    assert any(x["code"] == "forecast_lossy_filter" for x in forecast_checks(data, c))


def test_evaluation_counts_sensitivity_progress_cancel():
    data, c = fixture("fc.eval", count=49, order_selection="fixed", p=1, d=0, q=0, draws=100)
    events = []
    r = run_evaluation(data, c, progress=events.append)
    counts = {x["horizon"]: x["n_forecasts"] for x in r["evaluation"]["metrics"]}
    assert counts == {1: 9, 4: 6, 8: 2}
    assert r["evaluation"]["models"] == ["Random walk", "AR (BIC)", "ARIMA", "BVAR"]
    assert events[-1]["completed"] == 9
    with pytest.raises(CancelledError):
        run_evaluation(data, c, cancelled=lambda: True)
    with pytest.raises(CancelledError):
        run_arima(*fixture(), cancelled=lambda: True)


def test_monthly_seasonality_guard_and_fixed_order():
    data, c = fixture(
        frequency="M", count=150, order_selection="fixed", p=1, d=0, q=0, seasonal_p=1
    )
    with pytest.raises(ValueError, match="monthly NSA"):
        choose_order(training(data, c), c)
    data.metadata["x"] = {"sa_flag": "NSA"}
    result = choose_order(training(data, c), c)
    assert result["chosen"]["seasonal_order"] == [1, 0, 0, 12]


def test_differenced_sarimax_random_walk_drift_original_units():
    y = np.cumsum(np.random.default_rng(53).normal(size=80))
    fit = SARIMAX(y, order=(0, 1, 0), trend="c", simple_differencing=True).filter([0.15, 0.25])
    mean, cov = joint_prediction(fit, np.zeros((12, 0)), 12)
    np.testing.assert_allclose(mean, y[-1] + 0.15 * np.arange(1, 13), atol=1e-14, rtol=0)
    expected = np.minimum.outer(np.arange(1, 13), np.arange(1, 13)) * 0.25
    np.testing.assert_allclose(cov, expected, atol=1e-14, rtol=0)


def test_future_controls_never_enter_an_origin_and_covid_is_zero():
    from macrolab.models.forecast_common import future_controls

    data, c = fixture(
        "fc.eval",
        count=48,
        order_selection="fixed",
        p=1,
        d=0,
        q=0,
        draws=100,
        future_exog="hold_last",
    )
    c["series"][1]["role"] = "exogenous"
    data.exog = pd.DataFrame(
        {"covid_2009-Q3": [float(i == 42) for i in range(48)]}, index=data.frame.index
    )
    changed = deepcopy(data)
    changed.frame.iloc[40:, 1] *= 100000
    a, detail = origin_forecast(data, c, 40, 8)
    b, other = origin_forecast(changed, c, 40, 8)
    for name in a:
        np.testing.assert_array_equal(a[name], b[name])
    assert detail == other
    trained = training(data, c)
    past, future, names, notes = future_controls(trained, c, 8)
    assert np.all(future[:, names.index("covid_2009-Q3")] == 0)
    assert np.all(future[:, names.index("z")] == trained.frame.z.iloc[-1])


def test_automatic_order_selection_is_prefix_only():
    data, c = fixture("fc.eval", count=45, draws=100)
    altered = deepcopy(data)
    altered.frame.iloc[40:] *= 1234
    a, detail = origin_forecast(data, c, 40, 8)
    b, other = origin_forecast(altered, c, 40, 8)
    assert detail == other
    for name in a:
        np.testing.assert_array_equal(a[name], b[name])


def test_evaluation_target_and_origin_exclusions_are_distinct(monkeypatch):
    import macrolab.models.forecast_eval as module

    data, config = fixture("fc.eval", count=100)

    def fake_origin(raw, config, stop, horizon, fixed, **kwargs):
        value = raw.frame["x"].iloc[stop - 1]
        predictions = {m: np.repeat(value + j * 0.01, horizon) for j, m in enumerate(module.MODELS)}
        return predictions, {"ar_order": 2, "arima": {}, "arima_tests": {"disagree": False}}

    monkeypatch.setattr(module, "origin_forecast", fake_origin)
    result = run_evaluation(data, config)
    predictions = result["evaluation"]["predictions"]
    target_rows = [r for r in predictions if not "2020" <= r["target"][:4] <= "2021"]
    origin_rows = [r for r in predictions if not "2020" <= r["origin"][:4] <= "2021"]
    assert target_rows != origin_rows
    for variant, selected in zip(
        result["sensitivity"]["variants"], [target_rows, origin_rows], strict=True
    ):
        metrics, tests = module.score_predictions(selected, "Q")
        assert variant["metrics"] == metrics
        assert variant["dm_tests"] == tests
        assert variant["removed_predictions"] == len(predictions) - len(selected)
    assert any(r["origin"] == "2020-Q2" and r["target"] == "2022-Q2" for r in target_rows)
    assert not any(r["origin"] == "2020-Q2" for r in origin_rows)
