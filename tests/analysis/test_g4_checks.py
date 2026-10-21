"""G4 precision bands, role-aware diagnostics and check discovery provenance."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import ValidationError, validate
from statsmodels.api import OLS, add_constant
from statsmodels.tsa.api import VAR

from macrolab.analysis import engine, sensitivity
from macrolab.checks import core
from macrolab.models.base import AnalysisData, check
from macrolab.models.linear import OLSPlugin, fit_checks
from macrolab.models.var import VAROLSPlugin


def var_inputs(nobs=40, lags=1):
    rng = np.random.default_rng(944)
    frame = pd.DataFrame(
        rng.normal(size=(nobs + lags, 2)),
        columns=["x", "y"],
        index=pd.period_range("1980Q1", periods=nobs + lags, freq="Q"),
    )
    config = {
        "schema_version": 1,
        "snapshot_id": "synthetic",
        "countries": ["SYN"],
        "frequency": "Q",
        "series": [
            {"concept_id": "x", "role": "shock", "transform": "level"},
            {"concept_id": "y", "role": "endogenous", "transform": "level"},
        ],
        "model": {"id": "var.ols", "params": {"lags": lags, "trend": "c"}},
        "sample": {"start": "1980-Q1", "end": "latest"},
        "comparison": {"enabled": False},
    }
    return AnalysisData(frame), config


@pytest.mark.parametrize(
    "nobs,expected",
    [
        (10, "block"),
        (11, "warn"),
        (29, "warn"),
        (30, "warn"),
        (49, "warn"),
        (50, "info"),
        (99, "info"),
        (100, None),
        (101, None),
    ],
)
def test_linear_parameter_boundaries_keep_only_estimability_block(nobs, expected):
    result = fit_checks(nobs, 10)
    assert [row["level"] for row in result] == ([] if expected is None else [expected])
    if result:
        assert result[0]["observations_per_parameter"] == nobs / 10
        assert result[0]["phase"] == "pre_estimation"


@pytest.mark.parametrize(
    "nobs,expected", [(8, "warn"), (14, "warn"), (15, "info"), (29, "info"), (30, None)]
)
def test_fixed_var_precision_boundaries(nobs, expected):
    data, config = var_inputs(nobs)
    result = VAROLSPlugin().check(data, config)
    assert [row["level"] for row in result] == ([] if expected is None else [expected])
    if result:
        assert result[0]["parameters"] == 3
        assert result[0]["nobs"] == nobs
        assert result[0]["phase"] == "pre_estimation"


def test_var_below_three_observations_per_parameter_fits_reference_unchanged():
    data, config = var_inputs(8)
    plugin = VAROLSPlugin()
    assert plugin.check(data, config)[0]["level"] == "warn"
    output = plugin.run(data, config)
    reference = VAR(data.frame).fit(1)
    np.testing.assert_allclose(
        output["diagnostics"]["coefficients"], reference.coefs, rtol=0, atol=1e-12
    )
    np.testing.assert_allclose(
        output["diagnostics"]["residual_covariance"], reference.sigma_u, rtol=0, atol=1e-12
    )
    assert output["diagnostics"]["nobs"] / output["diagnostics"]["parameter_count_per_equation"] < 3


def test_ols_below_three_observations_per_parameter_fits_reference_unchanged():
    data, _ = var_inputs(4, lags=0)
    config = {
        "series": [
            {"concept_id": "x", "role": "dependent"},
            {"concept_id": "y", "role": "regressor"},
        ],
        "model": {"id": "sing.ols", "params": {"covariance": "HC1"}},
    }
    plugin = OLSPlugin()
    assert not any(item["level"] == "block" for item in plugin.check(data, config))
    output = plugin.run(data, config)
    reference = OLS(data.frame["x"], add_constant(data.frame[["y"]])).fit(
        cov_type="HC1", use_t=True
    )
    np.testing.assert_allclose(
        [row["estimate"] for row in output["coefficients_table"]],
        reference.params,
        rtol=0,
        atol=1e-12,
    )


@pytest.mark.parametrize("case", ["minimum_observations", "residual_df", "rank"])
def test_var_true_estimability_failures_remain_blocking(case):
    if case == "minimum_observations":
        data, config = var_inputs(7)
        message = "eight"
    elif case == "residual_df":
        data, config = var_inputs(9, lags=4)
        message = "degrees of freedom"
    else:
        data, config = var_inputs(40)
        data.frame["y"] = data.frame["x"]
        message = "collinear"
    if case != "rank":
        assert VAROLSPlugin().check(data, config)[0]["level"] == "block"
    with pytest.raises((ValueError, np.linalg.LinAlgError), match=message):
        VAROLSPlugin().run(data, config)


def test_exogenous_stationarity_keeps_evidence_but_is_information(monkeypatch):
    data, config = var_inputs()
    data.frame["oil"] = data.frame["x"].cumsum()
    config["series"].append({"concept_id": "oil", "role": "exogenous", "transform": "log"})
    original = deepcopy(config)
    monkeypatch.setattr(core, "adfuller", lambda *args, **kwargs: (-1, 0.4, 2))
    monkeypatch.setattr(core, "kpss", lambda *args, **kwargs: (1, 0.01, 3))
    findings = {
        row["concept_id"]: row
        for row in core.evaluate_checks(data, config)
        if row["code"] == "nonstationary_level"
    }
    assert findings["x"]["level"] == findings["y"]["level"] == "warn"
    assert findings["oil"]["level"] == "info"
    assert findings["oil"]["role"] == "exogenous"
    for row in findings.values():
        assert (row["adf_p_value"], row["kpss_p_value"], row["adf_lags"], row["kpss_lags"]) == (
            0.4,
            0.01,
            2,
            3,
        )
        assert row["phase"] == "pre_estimation"
    assert config == original


def test_all_postfit_branches_have_machine_readable_phase():
    data, config = var_inputs()
    config["identification"] = {"id": "recursive"}
    payload = {
        "diagnostics": {
            "stable": False,
            "companion_spectral_radius": 1.1,
            "nobs": 29,
            "parameter_count_per_equation": 10,
            "lag_selection": "aic",
        }
    }
    result = core.postfit_checks(data, config, payload)
    assert {row["code"] for row in result} == {
        "small_sample",
        "unstable_dynamics",
        "shock_range_unavailable",
    }
    assert all(row["phase"] == "post_estimation" for row in result)
    payload["diagnostics"]["residual_shock_quantiles"] = {"shock": "wrong", "q05": -1, "q95": 1}
    assert core.postfit_checks(data, config, payload)[-1]["phase"] == "post_estimation"
    payload["diagnostics"]["residual_shock_quantiles"]["shock"] = "x"
    config["outputs"] = {"irf": {"shock_size": 2}}
    result = core.postfit_checks(data, config, payload)
    assert result[-1]["code"] == "shock_out_of_range"
    assert result[-1]["phase"] == "post_estimation"


def test_estimation_failure_phase_survives_result_and_schema(monkeypatch):
    data, config = var_inputs()
    bundle = {
        "snapshot_id": "synthetic",
        "countries": {
            "SYN": {
                "metadata": {"iso3": "SYN"},
                "series": {
                    name: {
                        "metadata": {
                            "frequency": "Q",
                            "status": "available",
                            "flags": [],
                            "warnings": [],
                        },
                        "observations": [
                            [str(period).replace("Q", "-Q"), float(value)]
                            for period, value in data.frame[name].items()
                        ],
                    }
                    for name in data.frame
                },
            }
        },
    }

    def fail(*args, **kwargs):
        raise ValueError("Synthetic failed estimation")

    monkeypatch.setattr(engine, "run_configured_plugin", fail)
    result = engine.run_analysis(config, bundle)
    assert result["status"] == "blocked"
    failure = next(row for row in result["checks"] if row["code"] == "model_fit_failed")
    assert failure["phase"] == "post_estimation"
    assert result["results"][0]["checks"][-1] == failure
    schema = json.loads(Path("schemas/model_result.schema.json").read_text())
    validate(result, schema)
    missing_phase = dict(failure)
    missing_phase.pop("phase")
    with pytest.raises(ValidationError):
        validate(missing_phase, schema["properties"]["checks"]["items"])
    assert check("info", "coverage", "Quick coverage", phase="preflight")["phase"] == "preflight"


def test_baseline_and_equivalent_lags_retain_fitted_caveats_without_refitting(monkeypatch):
    data, config = var_inputs()
    config["identification"] = {"id": "recursive", "params": {"order": ["y", "x"]}}
    config["outputs"] = {"irf": {"method": "asymptotic", "shock_size": 20, "horizon": 4}}
    config["seed"] = 944
    config["comparison"] = {"enabled": True, "scenarios": ["lag_criteria"]}
    baseline = VAROLSPlugin().run(data, config)
    # Exercise instability metadata independently of the finite-sample DGP.
    baseline["diagnostics"].update(stable=False, companion_spectral_radius=1.1)
    before = deepcopy(baseline)
    expected = core.postfit_checks(data, config, baseline)
    assert {item["code"] for item in expected} == {"unstable_dynamics", "shock_out_of_range"}
    monkeypatch.setattr(
        sensitivity,
        "lag_criteria_evidence",
        lambda *args: {"candidate_lags": [0, 1], "selected_lags": {"aic": 1, "bic": 1, "hqic": 1}},
    )
    variants = {
        row["variant_id"]: row
        for row in sensitivity.build_sensitivity(data, config, baseline)["variants"]
    }
    for identifier in ("baseline", "lag_aic", "lag_bic", "lag_hqic"):
        assert variants[identifier]["checks"] == expected
        assert all(item["phase"] == "post_estimation" for item in variants[identifier]["checks"])
        if identifier != "baseline":
            assert variants[identifier]["status"] == "duplicate"
            assert variants[identifier]["equivalent_variant"] == "baseline"
    assert variants["baseline"]["metrics"] == sensitivity._metrics(baseline)
    assert baseline == before
