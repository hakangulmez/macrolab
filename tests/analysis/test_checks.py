"""Exact shared-check triggers on synthetic input, with no network or real data."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from macrolab.checks import core
from macrolab.models.base import AnalysisData


def example(
    model: str = "var.ols", start: str = "2010-Q1", n: int = 24, frequency: str = "Q"
) -> tuple[AnalysisData, dict[str, Any]]:
    periods = pd.period_range(start, periods=n, freq="Y" if frequency == "A" else frequency)
    frame = pd.DataFrame(
        np.random.default_rng(944).normal(size=(n, 2)),
        index=[str(p).replace("Q", "-Q") for p in periods],
        columns=["x", "y"],
    )
    single = model.startswith("sing.") or model == "test.granger"
    config: dict[str, Any] = {
        "model": {"id": model, "params": {"trend": "c"}},
        "frequency": frequency,
        "countries": ["SYN"],
        "special_periods": {"covid": "include"},
        "series": [
            {"concept_id": "x", "role": "dependent" if single else "shock", "transform": "diff"},
            {
                "concept_id": "y",
                "role": "regressor" if single else "endogenous",
                "transform": "diff",
            },
        ],
    }
    return AnalysisData(frame, frequency=frequency), config


def codes(result: list[dict[str, Any]]) -> set[str]:
    return {item["code"] for item in result}


def by_code(result: list[dict[str, Any]], code: str) -> dict[str, Any]:
    return next(item for item in result if item["code"] == code)


def policy(
    start: str = "2010-Q1", n: int = 8
) -> tuple[AnalysisData, dict[str, Any], dict[str, Any]]:
    data, config = example(start=start, n=n)
    data.country = "DEU"
    data.frame = data.frame.rename(columns={"x": "policy_rate"})
    data.frame["policy_rate"] = 2.0
    config["series"][0].update(concept_id="policy_rate", transform="level")
    source = {
        "countries": {
            "DEU": {
                "metadata": {
                    "monetary_union": "EA",
                    "euro_adoption": "1999-01-01",
                },
                "series": {},
            }
        }
    }
    return data, config, source


def test_yaml_defaults_match_browser_runtime_and_delegated_owners() -> None:
    specification = yaml.safe_load(Path("configs/checks.yaml").read_text())
    assert specification["defaults"] == core.DEFAULTS
    rules = {r["code"]: r for r in specification["rules"]}
    assert rules["weak_instrument"]["status"] == "future_only"
    assert rules["small_sample"]["owner"] == "model_plugin"
    assert rules["missing_coverage"]["owner"] == "data"


@pytest.mark.parametrize("model", ["var.ols", "sing.ols", "desc.plot"])
def test_valid_inputs_and_independent_multicountry_fits(model: str) -> None:
    data, config = example(model)
    config["countries"] = ["SYN", "OTHER"]
    assert core.evaluate_checks(data, config) == []


@pytest.mark.parametrize(
    "case,expected",
    [
        ("too_few", "model_inputs"),
        ("too_many", "model_inputs"),
        ("duplicate", "model_inputs"),
        ("bad_role", "model_roles"),
        ("only_one_endogenous", "model_roles"),
        ("no_shock", "model_roles"),
        ("two_shocks", "model_roles"),
        ("unknown_model", "model_inputs"),
        ("frequency", "freq_mismatch"),
        ("pooled", "model_inputs"),
    ],
)
def test_input_blocks(case: str, expected: str) -> None:
    data, config = example()
    if case == "too_few":
        config["series"] = config["series"][:1]
    elif case == "too_many":
        config["series"] = [{"concept_id": f"v{i}", "role": "endogenous"} for i in range(7)]
    elif case == "duplicate":
        config["series"][1]["concept_id"] = "x"
    elif case == "bad_role":
        config["series"][0]["role"] = "dependent"
    elif case == "only_one_endogenous":
        config["series"][1]["role"] = "exogenous"
    elif case in {"no_shock", "two_shocks"}:
        config["identification"] = {"id": "recursive"}
        config["series"][0 if case == "no_shock" else 1]["role"] = (
            "endogenous" if case == "no_shock" else "shock"
        )
    elif case == "unknown_model":
        config["model"]["id"] = "future.iv"
    elif case == "frequency":
        config["frequency"] = "M"
    else:
        data.panels = {"SYN": data.frame, "OTHER": data.frame}
    result = core.evaluate_checks(data, config)
    assert by_code(result, expected)["level"] == "block"
    assert not codes(result) & {"small_sample", "collinearity", "missing_coverage"}


@pytest.mark.parametrize("case", ["two_dependent", "no_regressor", "ignored_role"])
def test_single_equation_roles_block(case: str) -> None:
    data, config = example("sing.ols")
    config["series"][1]["role"] = {
        "two_dependent": "dependent",
        "no_regressor": "exogenous",
        "ignored_role": "shock",
    }[case]
    assert "model_roles" in codes(core.evaluate_checks(data, config))


def test_recursive_plugin_requires_shock_without_config_identification() -> None:
    data, config = example("ident.recursive")
    config["series"][0]["role"] = "endogenous"
    assert "model_roles" in codes(core.evaluate_checks(data, config))


@pytest.mark.parametrize(
    "adf_p,kpss_p,expected",
    [
        (0.4, 0.01, "nonstationary_level"),
        (0.05, 0.049, "nonstationary_level"),
        (0.01, 0.1, None),
        (0.4, 0.1, "stationarity_inconclusive"),
        (0.01, 0.01, "stationarity_inconclusive"),
        (0.05, 0.05, "stationarity_inconclusive"),
    ],
)
def test_stationarity_decision_uses_both_opposite_nulls(
    monkeypatch: pytest.MonkeyPatch,
    adf_p: float,
    kpss_p: float,
    expected: str | None,
) -> None:
    data, config = example("sing.ols")
    config["series"][0]["transform"] = "log"
    monkeypatch.setattr(core, "adfuller", lambda *a, **k: (-1, adf_p, 2))
    monkeypatch.setattr(core, "kpss", lambda *a, **k: (1, kpss_p, 3))
    result = core.evaluate_checks(data, config)
    if expected:
        item = by_code(result, expected)
        assert item["adf_p_value"] == adf_p and item["kpss_p_value"] == kpss_p
        assert item["adf_lags"] == 2 and item["kpss_lags"] == 3
    else:
        assert result == []


@pytest.mark.parametrize("trend,expected", [("c", "c"), ("ct", "ct"), ("n", "c")])
def test_stationarity_deterministic_terms(
    trend: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, config = example()
    config["series"][0]["transform"] = "level"
    config["model"]["params"]["trend"] = trend
    calls = []

    def fake(*args: Any, **kwargs: Any) -> tuple[float, float, int]:
        calls.append(kwargs)
        return 0, 0.06, 1

    monkeypatch.setattr(core, "adfuller", fake)
    monkeypatch.setattr(core, "kpss", fake)
    result = core.evaluate_checks(data, config)
    assert calls == [
        {"regression": expected, "autolag": "AIC"},
        {"regression": expected, "nlags": "auto"},
    ]
    assert by_code(result, "stationarity_inconclusive")["deterministic_terms"] == expected


@pytest.mark.parametrize("reason", ["constant", "short", "nonfinite", "test_error", "bad_p"])
def test_stationarity_unavailable(reason: str, monkeypatch: pytest.MonkeyPatch) -> None:
    data, config = example()
    config["series"][0]["transform"] = "level"
    if reason == "constant":
        data.frame["x"] = 0.0
    elif reason == "short":
        data.frame = data.frame.iloc[:10]
    elif reason == "nonfinite":
        data.frame.loc[data.frame.index[0], "x"] = np.nan
    elif reason == "bad_p":
        monkeypatch.setattr(core, "adfuller", lambda *a, **k: (0, np.nan, 1))
    else:

        def fail(*args: Any, **kwargs: Any) -> None:
            raise ValueError("synthetic failure")

        monkeypatch.setattr(core, "adfuller", fail)
    assert (
        by_code(core.evaluate_checks(data, config), "stationarity_unavailable")["level"] == "info"
    )


def test_stationarity_actual_diagnostic_matches_library_and_does_not_mutate() -> None:
    data, config = example(n=180)
    data.frame["x"] = np.random.default_rng(2704).normal(size=180).cumsum()
    config["series"][0]["transform"] = "level"
    before = data.frame.copy(deep=True), copy.deepcopy(config)
    result = by_code(core.evaluate_checks(data, config), "nonstationary_level")
    assert (
        result["adf_p_value"]
        == core.adfuller(data.frame.x.to_numpy(), regression="c", autolag="AIC")[1]
    )
    pd.testing.assert_frame_equal(data.frame, before[0])
    assert config == before[1]


@pytest.mark.parametrize(
    "start,n,shared,crosses",
    [
        ("1998-Q1", 8, True, True),
        ("1999-Q1", 4, True, False),
        ("1998-Q1", 4, False, False),
        ("2010-Q1", 4, True, False),
    ],
)
def test_euro_warnings_use_effective_sample(
    start: str, n: int, shared: bool, crosses: bool
) -> None:
    data, config, source = policy(start, n)
    config["sample"] = {"start": "1900-Q1", "end": "latest"}
    result = codes(core.evaluate_checks(data, config, source))
    assert ("shared_rate" in result) == shared
    assert ("pre_euro_break" in result) == crosses


@pytest.mark.parametrize("case", ["aggregate", "not_shock", "national"])
def test_no_false_shared_rate(case: str) -> None:
    data, config, source = policy()
    if case == "aggregate":
        source["countries"]["EA"] = source["countries"].pop("DEU")
        data.country = "EA"
    elif case == "not_shock":
        config["series"][0]["role"] = "endogenous"
    else:
        source["countries"]["DEU"]["metadata"]["monetary_union"] = None
    assert "shared_rate" not in codes(core.evaluate_checks(data, config, source))


def test_elb_uses_native_months_not_quarterly_mean_or_outside_sample() -> None:
    data, config, source = policy(n=1)
    source["countries"]["DEU"]["series"]["policy_rate"] = {
        "metadata": {"frequency": "M"},
        "observations": [
            ["2009-12", -0.5],
            ["2010-01", 0.25],
            ["2010-02", 2],
            ["2010-03", 3],
            ["2010-04", -0.5],
        ],
    }
    item = by_code(core.evaluate_checks(data, config, source), "elb_period")
    assert item["periods"] == ["2010-01"]
    assert item["threshold"] == 0.25 and item["evidence"] == "native_observations"
    config["special_periods"]["elb_threshold"] = 0.1
    assert "elb_period" not in codes(core.evaluate_checks(data, config, source))


def test_elb_prepared_fallback_and_transformed_unavailability() -> None:
    data, config, _ = policy(n=1)
    data.frame["policy_rate"] = -0.1
    data.sample["frequency_conversion"] = {"policy_rate": {"method": "mean"}}
    result = core.evaluate_checks(data, config)
    assert by_code(result, "elb_period")["evidence"] == "prepared_levels_only"
    assert "elb_resolution_limited" in codes(result)
    config["series"][0]["transform"] = "diff"
    result = core.evaluate_checks(data, config)
    assert "elb_unavailable" in codes(result) and "elb_period" not in codes(result)


def test_elb_invalid_threshold_is_blocked() -> None:
    data, config, _ = policy(n=1)
    config["special_periods"]["elb_threshold"] = np.nan
    assert by_code(core.evaluate_checks(data, config), "invalid_elb_threshold")["level"] == "block"


@pytest.mark.parametrize(
    "frequency,start,n,affected",
    [
        ("Q", "2019-Q4", 8, 6),
        ("M", "2019-12", 20, 18),
        ("A", "2019", 4, 2),
    ],
)
def test_covid_calendar_bounds(frequency: str, start: str, n: int, affected: int) -> None:
    data, config = example(start=start, n=n, frequency=frequency)
    item = by_code(core.evaluate_checks(data, config), "covid_period")
    assert item["level"] == "warn" and len(item["periods"]) == affected
    assert item["fix"]["special_periods"]["covid"] == "dummy"


@pytest.mark.parametrize("case", ["valid", "missing", "wrong_value", "wrong_index", "wrong_name"])
def test_covid_dummy_treatment_verified(case: str) -> None:
    data, config = example(start="2020-Q1", n=3)
    config["special_periods"]["covid"] = "dummy"
    data.exog = pd.DataFrame(
        np.eye(3), index=data.frame.index, columns=[f"covid_{p}" for p in data.frame.index]
    )
    if case == "missing":
        data.exog = None
    elif case == "wrong_value":
        data.exog.iloc[0, 0] = 0
    elif case == "wrong_index":
        data.exog.index = data.exog.index[::-1]
    elif case == "wrong_name":
        data.exog.columns = ["a", "b", "c"]
    result = core.evaluate_checks(data, config)
    if case == "valid":
        item = by_code(result, "covid_period")
        assert item["applied"] and item["dummy_count"] == 3 and item["level"] == "info"
    else:
        assert by_code(result, "covid_dummy_missing")["level"] == "block"


def test_covid_descriptive_does_not_claim_dummies_applied() -> None:
    data, config = example("desc.plot", "2020-Q1", 4)
    config["special_periods"]["covid"] = "dummy"
    item = by_code(core.evaluate_checks(data, config), "covid_period")
    assert item["applied"] is False


def test_covid_exclusion_success_and_failed_treatment() -> None:
    data, config = example(start="2020-Q1", n=4)
    config["special_periods"]["covid"] = "exclude"
    assert by_code(core.evaluate_checks(data, config), "covid_exclusion_failed")["level"] == "block"
    data, config = example(start="2022-Q1", n=4)
    config["special_periods"]["covid"] = "exclude"
    data.sample["dropped_periods"] = [{"period": "2020-Q1", "reasons": ["covid_excluded"]}]
    item = by_code(core.evaluate_checks(data, config), "covid_period")
    assert item["level"] == "info" and item["treatment"] == "exclude"
    config["special_periods"]["covid"] = "bad"
    assert "covid_treatment" in codes(core.evaluate_checks(data, config))


@pytest.mark.parametrize(
    "model,transform,frequency,expected",
    [
        ("var.ols", "diff", "Q", True),
        ("sing.ardl", "level", "M", True),
        ("test.granger", "log_diff", "Q", True),
        ("var.ols", "yoy_pct", "Q", False),
        ("var.ols", "yoy_diff", "M", False),
        ("var.ols", "diff", "A", False),
        ("sing.ols", "diff", "Q", False),
        ("desc.plot", "level", "Q", False),
    ],
)
def test_nsa_short_dynamics(model: str, transform: str, frequency: str, expected: bool) -> None:
    data, config = example(
        model, {"Q": "2010-Q1", "M": "2010-01", "A": "1980"}[frequency], frequency=frequency
    )
    config["series"][0]["transform"] = transform
    data.metadata["x"] = {"source_segments": [{"sa_flag": "NSA"}]}
    result = core.evaluate_checks(data, config)
    assert ("nsa_series" in codes(result)) == expected


def identified(size: float) -> tuple[AnalysisData, dict[str, Any], dict[str, Any]]:
    data, config = example()
    config["identification"] = {"id": "recursive"}
    config["outputs"] = {"irf": {"shock_size": size}}
    return (
        data,
        config,
        {
            "diagnostics": {
                "stable": True,
                "companion_spectral_radius": 0.5,
                "residual_shock_quantiles": {
                    "q05": -0.3,
                    "q95": 0.2,
                    "shock": "x",
                    "units": "percentage points",
                },
            }
        },
    )


@pytest.mark.parametrize(
    "size,warning", [(-0.31, True), (-0.3, False), (0, False), (0.2, False), (0.21, True)]
)
def test_shock_range_uses_signed_physical_size_and_inclusive_quantile_bounds(
    size: float, warning: bool
) -> None:
    data, config, payload = identified(size)
    result = core.postfit_checks(data, config, payload)
    assert ("shock_out_of_range" in codes(result)) == warning
    if warning:
        assert by_code(result, "shock_out_of_range")["units"] == "percentage points"


@pytest.mark.parametrize("case", ["mismatch", "reversed", "nan", "missing"])
def test_bad_shock_range_is_never_silently_accepted(case: str) -> None:
    data, config, payload = identified(1)
    quantiles = payload["diagnostics"]["residual_shock_quantiles"]
    if case == "mismatch":
        quantiles["shock"] = "y"
    elif case == "reversed":
        quantiles["q05"] = 2
    elif case == "nan":
        quantiles["q05"] = np.nan
    else:
        payload["diagnostics"].pop("residual_shock_quantiles")
    result = core.postfit_checks(data, config, payload)
    assert ("shock_range_unavailable" if case == "missing" else "shock_range_invalid") in codes(
        result
    )


@pytest.mark.parametrize(
    "stable,radius,warning",
    [(True, 0.9, False), (False, 0.9, True), (True, 1.0, True), (False, 1.1, True)],
)
def test_instability_without_identification(stable: bool, radius: float, warning: bool) -> None:
    data, config = example()
    payload = {"diagnostics": {"stable": stable, "companion_spectral_radius": radius}}
    result = core.postfit_checks(data, config, payload)
    assert ("unstable_dynamics" in codes(result)) == warning
    assert "shock_range_unavailable" not in codes(result)


def test_euro_fix_starts_first_fully_postadoption_period() -> None:
    data, config, source = policy("2000-Q1", 4)
    source["countries"]["DEU"]["metadata"]["euro_adoption"] = "2000-02-01"
    item = by_code(core.evaluate_checks(data, config, source), "pre_euro_break")
    assert item["fix"] == {"sample": {"start": "2000-Q2"}}


def test_nsa_segment_outside_actual_sample_does_not_trigger_warning() -> None:
    data, config = example()
    data.metadata["x"] = {
        "source_segments": [
            {"sa_flag": "NSA", "freq": "M", "first_date": "1990-01", "last_date": "1999-12"},
            {"sa_flag": "SA", "freq": "M", "first_date": "2000-01", "last_date": "2026-09"},
        ]
    }
    assert "nsa_series" not in codes(core.evaluate_checks(data, config))


@pytest.mark.parametrize(
    "nobs,count,criterion,expected",
    [
        (29, 10, "aic", "warn"),
        (30, 10, "aic", "warn"),
        (49, 10, "aic", "warn"),
        (50, 10, "bic", "info"),
        (99, 10, "bic", "info"),
        (100, 10, "hqic", None),
        (99, 10, "fixed", None),
        (29, 10, "fixed", None),
        (10, 10, "aic", "block"),
        (10, 10, "fixed", "block"),
        (7, 1, "fixed", "block"),
    ],
)
def test_var_selected_parameter_sample_thresholds(
    nobs: int, count: int, criterion: str, expected: str | None
) -> None:
    data, config = example()
    payload = {
        "diagnostics": {
            "nobs": nobs,
            "parameter_count_per_equation": count,
            "selected_lags": 3,
            "lag_selection": criterion,
        }
    }
    result = core.postfit_checks(data, config, payload)
    if expected is None:
        assert "small_sample" not in codes(result)
    else:
        item = by_code(result, "small_sample")
        assert item["level"] == expected and item["parameters"] == count and item["nobs"] == nobs


def test_actual_automatic_lag_fit_gets_small_sample_information() -> None:
    from macrolab.models.var import VAROLSPlugin

    generator = np.random.default_rng(8)
    values = np.zeros((150, 3))
    for t in range(2, 150):
        values[t] = 0.2 * values[t - 1] + 0.6 * values[t - 2] + generator.normal(size=3)
    data = AnalysisData(
        pd.DataFrame(
            values[-50:],
            columns=["x", "y", "z"],
            index=pd.period_range("1980Q1", periods=50, freq="Q"),
        )
    )
    config = {
        "series": [
            {"concept_id": n, "role": "endogenous", "transform": "diff"} for n in data.frame
        ],
        "model": {"id": "var.ols", "params": {"trend": "c", "lag_selection": "aic", "maxlags": 4}},
    }
    assert VAROLSPlugin().check(data, config) == []
    output = VAROLSPlugin().run(data, config)
    item = by_code(core.postfit_checks(data, config, output), "small_sample")
    assert item["level"] == "info" and item["nobs"] == 48 and item["parameters"] == 7
    assert item["phase"] == "post_estimation"
