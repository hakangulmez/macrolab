"""Independent G14 reference, recovery and finite-sample diagnostics."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2
from statsmodels.api import OLS, RecursiveLS
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

from macrolab.analysis.config import validated_config
from macrolab.ident.bootstrap import CancelledError
from macrolab.models.base import AnalysisData
from macrolab.models.break_calibration import ANDREWS_15, HANSEN_15
from macrolab.models.break_tests import (
    critical_values,
    hansen_probability,
    run_break_tests,
    split_test,
)
from macrolab.models.cointegration import CASES, CointegrationPlugin, fit_vecm, impulse_responses
from macrolab.models.cointegration import test_cointegration as run_coint


def coint_fixture(count=240, **params):
    rng = np.random.default_rng(20261024)
    z = np.cumsum(rng.normal(size=count))
    independent = np.cumsum(rng.normal(size=count))
    y = np.column_stack(
        [z + rng.normal(size=count) * 0.25, 2 * z + rng.normal(size=count) * 0.25, independent]
    )
    frame = pd.DataFrame(
        y,
        columns=["x", "y", "z"],
        index=[str(p).replace("Q", "-Q") for p in pd.period_range("1960", periods=count, freq="Q")],
    )
    c = validated_config(
        dict(
            schema_version=1,
            snapshot_id="fixture",
            countries=["SYN"],
            frequency="Q",
            series=[dict(concept_id=s, role="endogenous", transform="level") for s in frame],
            model=dict(id="vecm", params=dict(draws=10, **params)),
            special_periods={"covid": "include"},
            seed=42,
        )
    )
    return AnalysisData(frame, frequency="Q"), c


@pytest.mark.parametrize("case", list(CASES))
def test_johansen_native_and_matched_deterministic_cases(case):
    data, config = coint_fixture(deterministic=case)
    result = run_coint(data, config)["cointegration"]
    ref = coint_johansen(data.frame.to_numpy(), CASES[case][0], 1)
    np.testing.assert_array_equal([r["trace"] for r in result["johansen"]], ref.lr1)
    np.testing.assert_array_equal([r["maximum_eigenvalue"] for r in result["johansen"]], ref.lr2)
    np.testing.assert_array_equal(
        [list(r["trace_critical"].values()) for r in result["johansen"]], ref.cvt
    )
    assert result["vecm_deterministic"] == CASES[case][1]
    assert result["suggested_rank"] == 1


def test_engle_granger_both_normalisations_and_trend():
    data, config = coint_fixture(eg_trend="ct")
    data.frame = data.frame.iloc[:, :2]
    config["series"] = config["series"][:2]
    result = run_coint(data, config)["cointegration"]
    for i, row in enumerate(result["engle_granger"]):
        reference = coint(
            data.frame.iloc[:, i], data.frame.iloc[:, 1 - i], trend="ct", maxlag=4, autolag=None
        )
        assert row["statistic"] == reference[0]
        assert row["p_value"] == reference[1]
        assert row["trend"] == "ct"


def test_rank_beta_recovery_and_vecm_var_identity():
    data, config = coint_fixture()
    result = fit_vecm(data, config)
    native = VECM(data.frame.to_numpy(), k_ar_diff=1, coint_rank=1, deterministic="co").fit()
    v = result["vecm"]
    np.testing.assert_array_equal(v["alpha"], native.alpha)
    np.testing.assert_array_equal(v["beta"], native.beta)
    np.testing.assert_array_equal(v["alpha_std_error"], native.stderr_alpha)
    np.testing.assert_allclose(np.array(v["beta"])[:, 0], [1, -0.5, 0], atol=0.025, rtol=0)
    np.testing.assert_allclose(
        np.eye(3) + native.alpha @ native.beta.T + native.gamma, native.var_rep[0], atol=1e-14
    )
    np.testing.assert_allclose(-native.gamma, native.var_rep[1], atol=1e-14)
    np.testing.assert_allclose(
        impulse_responses(native.var_rep, native.sigma_u, 20), native.irf(20).orth_irfs, atol=1e-12
    )
    second = fit_vecm(data, config)
    assert v == second["vecm"]
    config["seed"] += 1
    assert fit_vecm(data, config)["vecm"]["bands"] != v["bands"]


def test_differences_controls_and_invalid_rank_block():
    data, config = coint_fixture()
    config["series"][0]["transform"] = "qoq_saar"
    assert any(
        c["code"] == "cointegration_levels" for c in CointegrationPlugin().check(data, config)
    )
    config["series"][0]["transform"] = "level"
    data.exog = pd.DataFrame({"covid": np.zeros(len(data.frame))}, index=data.frame.index)
    assert any(
        c["code"] == "cointegration_controls" for c in CointegrationPlugin().check(data, config)
    )


@pytest.mark.parametrize("rank", [0, 3])
def test_vecm_user_rank_extremes_are_retained(rank):
    data, config = coint_fixture(rank=rank)
    result = fit_vecm(data, config)["vecm"]
    assert result["rank"] == rank
    assert np.asarray(result["beta"]).shape == (3, rank)
    assert np.asarray(result["bands"]["0.9"]["lower"]).shape == (21, 3, 3)


def test_johansen_dimension_limit_and_bootstrap_cancellation():
    data, config = coint_fixture()
    data.frame = pd.DataFrame(np.ones((240, 13)), index=data.frame.index)
    assert any(
        c["code"] == "cointegration_dimension" for c in CointegrationPlugin().check(data, config)
    )
    data, config = coint_fixture()
    with pytest.raises(CancelledError):
        fit_vecm(data, config, cancelled=lambda: True)


def break_fixture(broken=True, seed=88):
    rng = np.random.default_rng(seed)
    n = 110
    x = rng.normal(size=n)
    y = 1 + (0.6 + (np.arange(n) >= 55) * (2 if broken else 0)) * x + rng.normal(size=n) * 0.35
    frame = pd.DataFrame(
        dict(y=y, x=x),
        index=[str(p).replace("Q", "-Q") for p in pd.period_range("1990", periods=n, freq="Q")],
    )
    config = validated_config(
        dict(
            schema_version=1,
            snapshot_id="fixture",
            countries=["SYN"],
            frequency="Q",
            series=[
                dict(concept_id="y", role="dependent", transform="level"),
                dict(concept_id="x", role="regressor", transform="level"),
            ],
            model=dict(
                id="test.break", params={"break_date": str(frame.index[55]), "covariance": "HAC"}
            ),
            special_periods={"covid": "include"},
        )
    )
    return AnalysisData(frame), config


def test_known_break_chow_and_hac_sup_wald_reference():
    data, config = break_fixture()
    result = run_break_tests(data, config)["break_tests"]
    assert abs(result["supremum"]["split"] - 55) <= 5
    assert result["supremum"]["approximate_p_value"] < 0.001
    assert result["chow"]["classical_chow_p"] < 0.001
    x = np.column_stack([np.ones(len(data.frame)), data.frame.x])
    z = x.copy()
    z[:55] = 0
    fit = OLS(data.frame.y.to_numpy(), np.column_stack([x, z])).fit(
        cov_type="HAC", cov_kwds={"maxlags": 4}
    )
    ref = fit.wald_test(np.column_stack([np.zeros((2, 2)), np.eye(2)]), scalar=True)
    assert result["chow"]["wald"] == pytest.approx(float(ref.statistic), abs=1e-9)
    rec = RecursiveLS(data.frame.y.to_numpy(), x).fit()
    np.testing.assert_allclose(
        [r["cusum"] for r in result["recursive"]], rec.cusum, atol=1e-10, rtol=0
    )
    np.testing.assert_allclose(
        [r["cusum_squares"] for r in result["recursive"]], rec.cusum_squares, atol=1e-10, rtol=0
    )
    assert result["covariance"] == "HAC"


def test_short_chow_segment_blocks_and_calendar_nuisance_stays_fixed():
    data, config = break_fixture()
    config["model"]["params"]["break_date"] = str(data.frame.index[1])
    with pytest.raises(ValueError, match="Too few"):
        run_break_tests(data, config)
    y = data.frame.y.to_numpy()
    x = np.column_stack([np.ones(len(y)), data.frame.x, np.arange(len(y)) == 10])
    result = split_test(y, x, 55, [0, 1], "HAC", 4)
    assert result["residual_df"] == len(y) - 5


def test_published_hansen_calibration_and_corrected_andrews_scaling():
    for q in range(1, 21):
        critical, source = critical_values(q)
        np.testing.assert_allclose(
            np.array(list(critical.values())) * q, np.array(ANDREWS_15[q - 1]), atol=1e-14, rtol=0
        )
        assert "2003" in source
        a, b, df = HANSEN_15[q - 1]
        for value in [3, 10, 30]:
            assert hansen_probability(value, q) == chi2.sf(max(0, a + b * value), df)
    assert ANDREWS_15[7] == [21.55, 23.82, 28.55]  # corrected p=8, not the erroneous 1993 row


def test_no_break_size_diagnostic():
    rejected = 0
    for seed in range(100):
        data, config = break_fixture(False, seed=1000 + seed)
        config["model"]["params"].update(covariance="conventional", break_date="")
        r = run_break_tests(data, config)["break_tests"]
        rejected += r["supremum"]["f_statistic"] > r["critical_values"]["95"]
    assert rejected <= 15, (rejected, "100 replications; report finite-sample rejection rate")
