"""Independent numerical references for the ten v0 linear/descriptive plugins."""

from __future__ import annotations

import json
import runpy
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from arch.unitroot import PhillipsPerron
from quantecon import hamilton_filter
from statsmodels.api import OLS, add_constant
from statsmodels.datasets import longley
from statsmodels.regression.rolling import RollingOLS
from statsmodels.tsa.ardl import ARDL, UECM
from statsmodels.tsa.filters.hp_filter import hpfilter
from statsmodels.tsa.stattools import adfuller, grangercausalitytests, kpss

from macrolab.models.base import AnalysisData
from macrolab.models.linear import PLUGINS, phillips_perron

MODELS = {plugin.id: plugin for plugin in PLUGINS}


def fixture_data() -> AnalysisData:
    rng = np.random.default_rng(94017)
    x, z, noise = rng.normal(size=(3, 160))
    y = 1.0 + 2.0 * x - 0.6 * z + noise
    frame = pd.DataFrame(
        {"y": y, "x": x, "z": z}, index=pd.period_range("1980Q1", periods=len(y), freq="Q")
    )
    return AnalysisData(frame=frame, country="SYN", frequency="Q")


def config(model_id: str, **params: Any) -> dict[str, Any]:
    return {
        "series": [
            {"concept_id": "y", "role": "dependent"},
            {"concept_id": "x", "role": "regressor"},
        ],
        "model": {"id": model_id, "params": params},
    }


def coefficient_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray(
        [[r[k] for k in ("estimate", "std_error", "lower", "upper", "p_value")] for r in rows]
    )


def reference_coefficients(result: Any) -> np.ndarray:
    return np.column_stack((result.params, result.bse, result.conf_int(), result.pvalues))


def validation_evidence(output_path: Path | None = None) -> list[dict[str, Any]]:
    """Run references and optionally persist the measured maximum differences as JSON."""
    data = fixture_data()
    frame = data.frame
    evidence = []
    recovery = runpy.run_path(str(Path(__file__).parents[1] / "synthetic/test_linear_recovery.py"))[
        "recovery_evidence"
    ]()
    for model_id, plugin in MODELS.items():
        started = time.perf_counter()
        params: dict[str, Any] = {}
        if model_id == "test.adf_kpss_pp":
            params = {"adf_lags": 3, "kpss_lags": 3, "pp_lags": 3, "trend": "c"}
        elif model_id in {"sing.ols", "sing.ardl", "sing.rolling"}:
            params = {"covariance": "HAC", "hac_lags": 3, "confidence": 0.95}
        if model_id == "sing.ardl":
            params |= {"lags": 2, "order": 2}
        if model_id == "sing.rolling":
            params |= {"window": 40, "mode": "rolling"}
        if model_id == "test.granger":
            params = {"lags": 3}
        if model_id == "desc.corr":
            params = {"window": 20}
        result = plugin.run(data, config(model_id, **params))
        runtime_ms = (time.perf_counter() - started) * 1000
        json.dumps(result, allow_nan=False)
        differences: dict[str, float] = {}
        if model_id == "desc.plot":
            actual = [r["value"] for r in result["filtered_series"] if r["series"] == "y"]
            differences["plot_values"] = float(np.max(np.abs(actual - frame["y"].to_numpy())))
        elif model_id == "desc.corr":
            differences["correlation"] = abs(
                result["test_results"][0]["statistic"] - np.corrcoef(frame.y, frame.x)[0, 1]
            )
            rolling = [r["value"] for r in result["filtered_series"]]
            expected = frame.y.rolling(20).corr(frame.x).dropna().to_numpy()
            differences["rolling_correlation"] = float(np.max(np.abs(rolling - expected)))
        elif model_id == "desc.compare":
            actual = {r["series"]: r["statistic"] for r in result["test_results"]}
            differences["country_means"] = max(abs(actual[c] - frame[c].mean()) for c in actual)
        elif model_id == "test.adf_kpss_pp":
            tests = {r["test"]: r for r in result["test_results"] if r["series"] == "y"}
            adf = adfuller(frame.y, maxlag=3, autolag=None, regression="c")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                kp = kpss(frame.y, nlags=3, regression="c")
            pp = PhillipsPerron(frame.y, lags=3, trend="c")
            for name, values in {
                "ADF": adf[:2],
                "KPSS": kp[:2],
                "PP": (pp.stat, pp.pvalue),
            }.items():
                differences[name] = max(
                    abs(tests[name][key] - expected)
                    for key, expected in zip(("statistic", "p_value"), values, strict=True)
                )
        elif model_id == "sing.ols":
            ref = OLS(frame.y, add_constant(frame[["x"]])).fit(
                cov_type="HAC", cov_kwds={"maxlags": 3}, use_t=True
            )
            differences["coefficients_se_bands_pvalues"] = float(
                np.max(
                    np.abs(
                        coefficient_matrix(result["coefficients_table"])
                        - reference_coefficients(ref)
                    )
                )
            )
            textbook = longley.load_pandas().data.rename(columns={"TOTEMP": "y", "GNP": "x"})
            textbook_fit = plugin.run(AnalysisData(textbook), config(model_id, **params))
            textbook_ref = OLS(textbook.y, add_constant(textbook[["x"]])).fit(
                cov_type="HAC", cov_kwds={"maxlags": 3}, use_t=True
            )
            differences["Longley_coefficients_se_bands_pvalues"] = float(
                np.max(
                    np.abs(
                        coefficient_matrix(textbook_fit["coefficients_table"])
                        - reference_coefficients(textbook_ref)
                    )
                )
            )
        elif model_id == "sing.ardl":
            model = ARDL(frame.y, 2, frame[["x"]], 2, trend="c")
            ref = model.fit(cov_type="HAC", cov_kwds={"maxlags": 3}, use_t=True)
            ecm = UECM.from_ardl(model).fit(cov_type="HAC", cov_kwds={"maxlags": 3}, use_t=True)
            for name, rows, fitted in (
                ("levels", result["coefficients_table"], ref),
                ("error_correction", result["error_correction_table"], ecm),
            ):
                differences[name] = float(
                    np.max(np.abs(coefficient_matrix(rows) - reference_coefficients(fitted)))
                )
        elif model_id == "sing.rolling":
            ref = RollingOLS(frame.y, add_constant(frame[["x"]]), window=40).fit()
            rows = result["filtered_series"]
            actual = np.asarray([r["estimate"] for r in rows]).reshape(-1, 2)
            differences["rolling_coefficients"] = float(
                np.max(np.abs(actual - ref.params.dropna()))
            )
            last = OLS(frame.y.iloc[-40:], add_constant(frame[["x"]].iloc[-40:])).fit(
                cov_type="HAC", cov_kwds={"maxlags": 3}, use_t=True
            )
            differences["last_window_se_bands"] = float(
                np.max(np.abs(coefficient_matrix(rows[-2:]) - reference_coefficients(last)))
            )
        elif model_id == "test.granger":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                ref = grangercausalitytests(frame[["y", "x"]], maxlag=[3], verbose=False)[3][0][
                    "ssr_ftest"
                ]
            row = result["test_results"][0]
            differences["F_and_p_value"] = max(
                abs(row["statistic"] - ref[0]), abs(row["p_value"] - ref[1])
            )
        elif model_id in {"filter.hp", "filter.hamilton"}:
            if model_id == "filter.hp":
                expected_cycle, expected_trend = hpfilter(frame.y, lamb=1600)
            else:
                expected_cycle, expected_trend = hamilton_filter(frame.y, h=8, p=4)
            rows = [r for r in result["filtered_series"] if r["series"] == "y"]
            valid = np.isfinite(expected_cycle)
            differences["cycle"] = float(
                np.max(
                    np.abs(
                        np.asarray([r["cycle"] for r in rows]) - np.asarray(expected_cycle)[valid]
                    )
                )
            )
            differences["trend"] = float(
                np.max(
                    np.abs(
                        np.asarray([r["trend"] for r in rows]) - np.asarray(expected_trend)[valid]
                    )
                )
            )
        evidence.append(
            {
                "model_id": model_id,
                "reference_max_abs_difference": max(differences.values()),
                "reference_tolerance": 1e-8,
                "reference_outputs": differences,
                "recovery": recovery.get(model_id, {"status": "not_applicable"}),
                "runtime_ms": runtime_ms,
                "fixture": "Seed 94017, 160 synthetic quarters; "
                "Longley packaged dataset additionally for OLS.",
            }
        )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    return evidence


def test_all_ten_plugins_match_independent_references() -> None:
    evidence = validation_evidence()
    assert len(evidence) == 10
    for item in evidence:
        assert item["reference_max_abs_difference"] <= item["reference_tolerance"], item


@pytest.mark.parametrize("covariance", ["HAC", "HC1"])
def test_ols_renaming_and_robust_covariance(covariance: str) -> None:
    data = fixture_data()
    cfg = config("sing.ols", covariance=covariance, hac_lags=3)
    result = MODELS["sing.ols"].run(data, cfg)
    kwargs = {"maxlags": 3} if covariance == "HAC" else {}
    expected = OLS(data.frame.y, add_constant(data.frame[["x"]])).fit(
        cov_type=covariance, cov_kwds=kwargs, use_t=True
    )
    np.testing.assert_allclose(
        coefficient_matrix(result["coefficients_table"]),
        reference_coefficients(expected),
        atol=1e-8,
    )
    renamed = data.frame.rename(columns={"y": "outcome", "x": "driver"})
    cfg["series"][0]["concept_id"], cfg["series"][1]["concept_id"] = "outcome", "driver"
    changed = MODELS["sing.ols"].run(AnalysisData(renamed), cfg)
    np.testing.assert_allclose(
        coefficient_matrix(result["coefficients_table"]),
        coefficient_matrix(changed["coefficients_table"]),
        atol=1e-12,
    )


def test_recursive_coefficients_and_no_future_window_leakage() -> None:
    data = fixture_data()
    cfg = config("sing.rolling", window=40, mode="recursive", hac_lags=3)
    result = MODELS["sing.rolling"].run(data, cfg)
    reference = RollingOLS(
        data.frame.y,
        add_constant(data.frame[["x"]]),
        window=len(data.frame),
        min_nobs=40,
        expanding=True,
    ).fit()
    actual = np.asarray([r["estimate"] for r in result["filtered_series"]]).reshape(-1, 2)
    np.testing.assert_allclose(actual, reference.params.dropna(), atol=1e-8)
    truncated = MODELS["sing.rolling"].run(AnalysisData(data.frame.iloc[:80]), cfg)
    assert (
        result["filtered_series"][: len(truncated["filtered_series"])]
        == truncated["filtered_series"]
    )


def test_compare_country_order_is_invariant() -> None:
    data = fixture_data()
    panels = {"BBB": data.frame * 2, "AAA": data.frame}
    first = MODELS["desc.compare"].run(
        AnalysisData(data.frame, panels=panels), config("desc.compare")
    )
    second = MODELS["desc.compare"].run(
        AnalysisData(data.frame, panels=dict(reversed(list(panels.items())))),
        config("desc.compare"),
    )
    assert first == second


def test_constant_and_insufficient_inputs_are_blocked() -> None:
    constant = fixture_data()
    constant.frame.loc[:, "y"] = 1
    assert any(
        row["level"] == "block"
        for row in MODELS["test.adf_kpss_pp"].check(constant, config("test.adf_kpss_pp"))
    )


@pytest.mark.parametrize("trend", ["n", "c", "ct"])
@pytest.mark.parametrize("bandwidth", [0, 5, None])
def test_phillips_perron_trends_bandwidths_and_critical_values(
    trend: str, bandwidth: int | None
) -> None:
    values = np.random.default_rng(308).normal(size=180).cumsum()
    actual = phillips_perron(values, lags=bandwidth, trend=trend)
    expected = PhillipsPerron(values, lags=bandwidth, trend=trend)
    assert actual["statistic"] == pytest.approx(expected.stat, abs=1e-8)
    assert actual["p_value"] == pytest.approx(expected.pvalue, abs=1e-8)
    assert actual["critical_values"] == pytest.approx(expected.critical_values, abs=1e-8)


def test_actual_ardl_sample_and_fixed_regressors() -> None:
    data = fixture_data()
    data.exog = pd.DataFrame(
        {"dummy": (np.arange(len(data.frame)) > 80).astype(float)}, index=data.frame.index
    )
    cfg = config("sing.ardl", lags=2, order=3, covariance="HC1")
    result = MODELS["sing.ardl"].run(data, cfg)
    expected = ARDL(data.frame.y, 2, data.frame[["x"]], 3, fixed=data.exog).fit(
        cov_type="HC1", use_t=True
    )
    np.testing.assert_allclose(
        coefficient_matrix(result["coefficients_table"]),
        reference_coefficients(expected),
        atol=1e-8,
    )
    assert result["diagnostics"]["estimated_indices"] == list(map(str, data.frame.index[3:]))
    assert result["diagnostics"]["nobs"] == len(data.frame) - 3


def test_rank_deficiency_and_constant_outcomes_do_not_emit_nonfinite_results() -> None:
    data = fixture_data()
    data.frame["y"] = 1.0
    for model_id in ("sing.ols", "sing.ardl"):
        cfg = config(model_id)
        assert any(row["level"] == "block" for row in MODELS[model_id].check(data, cfg))
        with pytest.raises(ValueError):
            MODELS[model_id].run(data, cfg)
    # The intercept plus one regressor leaves no residual degrees of freedom.
    # A low observations/parameter ratio alone is a precision warning in G4.
    short = AnalysisData(fixture_data().frame.iloc[:2])
    assert any(
        row["level"] == "block" for row in MODELS["sing.ols"].check(short, config("sing.ols"))
    )
