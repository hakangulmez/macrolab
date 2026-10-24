"""Independent regressions for G14.1 fixed-regressor calibration and scale."""

import numpy as np
import pytest
from statsmodels.api import OLS

from macrolab.ident.bootstrap import CancelledError
from macrolab.models.break_bootstrap import calibrate, designs, statistics
from macrolab.models.break_tests import critical_values, hansen_probability


@pytest.mark.parametrize("q", [1, 11])
def test_batched_wald_matches_plain_statsmodels(q):
    rng = np.random.default_rng(147)
    x = np.column_stack([np.ones(110), rng.normal(size=(110, q - 1))])
    y = rng.normal(size=(7, 110))
    d = designs(x, list(range(q)))[20]
    conventional, hac, _ = statistics(y, d, 4)
    restriction = np.column_stack([np.zeros((q, q)), np.eye(q)])
    for j in range(7):
        for covariance, actual in [("nonrobust", conventional), ("HAC", hac)]:
            fit = OLS(y[j], d["a"]).fit(
                cov_type=covariance, **({"cov_kwds": {"maxlags": 4}} if covariance == "HAC" else {})
            )
            reference = float(fit.wald_test(restriction, scalar=True, use_f=False).statistic) / q
            assert actual[j] == pytest.approx(reference, abs=1e-10)
    for cv in critical_values(q)[0].values():
        assert 0.001 < hansen_probability(cv * q, q) < 0.2


def test_hansen_bootstrap_independent_seeded_reference():
    rng = np.random.default_rng(123)
    x = np.column_stack([np.ones(45), rng.normal(size=45)])
    y = 1 + x[:, 1] + rng.normal(size=45) * np.sqrt(1 + 4 * x[:, 1] ** 2)
    b = calibrate(y, x, [0, 1], draws=19, seed=43)
    prep = designs(x, [0, 1])
    fits = [OLS(y, d["a"]).fit() for d in prep]
    errors = fits[np.argmin([f.ssr for f in fits])].resid
    ys = np.random.default_rng(43).normal(size=(19, 45)) * errors
    restriction = np.column_stack([np.zeros((2, 2)), np.eye(2)])
    for cov, key in [("nonrobust", "hc_bootstrap"), ("HAC", "hac_bootstrap")]:
        maxima = []
        for yy in ys:
            values = []
            for d in prep:
                fit = OLS(yy, d["a"]).fit(
                    cov_type=cov, **({"cov_kwds": {"maxlags": 4}} if cov == "HAC" else {})
                )
                values.append(
                    float(fit.wald_test(restriction, scalar=True, use_f=False).statistic) / 2
                )
            maxima.append(max(values))
        np.testing.assert_allclose(
            list(b[key]["critical_values"].values()),
            np.quantile(maxima, [0.9, 0.95, 0.99]),
            atol=1e-10,
            rtol=0,
        )
        assert b[key]["p_value"] == (1 + sum(v >= b[key]["statistic"] for v in maxima)) / 20
    assert b == calibrate(y, x, [0, 1], draws=19, seed=43)
    with pytest.raises(CancelledError):
        calibrate(y, x, [0, 1], draws=19, cancelled=lambda: True)


def test_boundary_warning_and_all_calibration_rows():
    from macrolab.models.break_tests import run_break_tests
    from tests.v2.test_cointegration_breaks import break_fixture

    data, config = break_fixture(False)
    data.frame.loc[data.frame.index[17] :, "y"] += 30
    result = run_break_tests(data, config)
    assert abs(result["break_tests"]["supremum"]["split"] - 17) <= 2
    assert any(c["code"] == "break_boundary_peak" for c in result["checks"])
    assert len(result["break_tests"]["inference_variants"]) == 4
    assert result["break_tests"]["statistic_scale"] == "Wald/q"
    assert result["break_tests"]["bootstrap"]["draws"] == 499


def test_trimmed_segment_warning_uses_tested_coefficient_dimension():
    from macrolab.models.break_tests import run_break_tests
    from tests.v2.test_cointegration_breaks import break_fixture

    data, config = break_fixture(False)
    rng = np.random.default_rng(4)
    for i in range(9):
        name = f"control_{i}"
        data.frame[name] = rng.normal(size=len(data.frame))
        config["series"].append(dict(concept_id=name, role="regressor", transform="level"))
    result = run_break_tests(data, config)
    b = result["break_tests"]
    assert b["tested_coefficients"] == 11
    assert b["minimum_segment_observations"] == 17
    assert b["minimum_segment_observations_per_coefficient"] == 17 / 11
    assert any(c["code"] == "break_segment_thin" for c in result["checks"])
