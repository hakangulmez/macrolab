"""Independent NIW calculations and recovery; no additional runtime library."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from scipy.special import gammaln
from statsmodels.tsa.api import VAR

from macrolab.analysis.config import validated_config
from macrolab.models.base import AnalysisData
from macrolab.models.bvar import (
    BVARPlugin,
    design,
    draw_parameters,
    dummy_prior,
    fit_bvar,
    posterior,
    select_prior,
)
from tests.v1.fixtures import A, dates, simulate


def fixture(n=200, seed=44):
    z, _, _ = simulate(n, seed)
    data = AnalysisData(pd.DataFrame(z, index=dates(n), columns=["x", "policy"]))
    c = validated_config(
        dict(
            schema_version=1,
            snapshot_id="g6-synthetic",
            countries=["SYN"],
            frequency="Q",
            series=[
                dict(concept_id="x", role="response", transform="level"),
                dict(concept_id="policy", role="shock", transform="diff"),
            ],
            model=dict(id="bvar.minn", params=dict(lags=2)),
            identification=dict(id="recursive", params=dict(order=["x", "policy"])),
            outputs=dict(irf=dict(horizon=12, bands=0.68, shock_mode="one_sd")),
            seed=491,
            comparison=dict(enabled=True),
        )
    )
    return data, c


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"sum_of_coefficients": True},
        {"co_persistence": True},
        {"sum_of_coefficients": True, "co_persistence": True},
    ],
)
def test_direct_posterior_and_marginal_likelihood(options):
    data, c = fixture()
    d = design(data, c)
    prior = dummy_prior(d, 0.2, options)
    x, y, n = d["x"], d["y"], d["n"]
    # Independent closed form, using neither augmented regression nor its residuals.
    v0 = np.linalg.inv(prior["precision"])
    v = np.linalg.inv(np.linalg.inv(v0) + x.T @ x)
    mean = v @ (np.linalg.solve(v0, prior["mean"]) + x.T @ y)
    scale = (
        prior["scale"]
        + y.T @ y
        + prior["mean"].T @ np.linalg.solve(v0, prior["mean"])
        - mean.T @ np.linalg.solve(v, mean)
    )
    p = posterior(d, 0.2, options)
    np.testing.assert_allclose(p["mean"], mean, atol=1e-12, rtol=0)
    np.testing.assert_allclose(p["variance"], v, atol=1e-12, rtol=0)
    np.testing.assert_allclose(p["scale"], scale, atol=1e-9, rtol=0)

    # Multivariate gamma written as scalar gamma products; marginal density normalizer.
    def constant(vv, ss, df):
        lgamma = n * (n - 1) / 4 * np.log(np.pi) + sum(
            gammaln((df + 1 - j) / 2) for j in range(1, n + 1)
        )
        return n / 2 * np.linalg.slogdet(vv)[1] - df / 2 * np.linalg.slogdet(ss)[1] + lgamma

    expected = (
        -len(y) * n / 2 * np.log(np.pi)
        + constant(v, scale, p["df"])
        - constant(v0, prior["scale"], prior["df"])
    )
    assert abs(p["log_marginal_likelihood"] - expected) < 1e-9
    assert prior["df"] == n + 2 + (n if options.get("sum_of_coefficients") else 0) + bool(
        options.get("co_persistence")
    )
    assert d["own_means"].tolist() == [1, 0]


def test_ols_limit_and_scales_and_matched_comparison():
    data, c = fixture()
    d = design(data, c)
    p = posterior(d, 1e8, {})
    ref = VAR(data.frame).fit(2)
    np.testing.assert_allclose(p["mean"], ref.params, atol=1e-6, rtol=0)
    for j in range(2):
        xx = np.column_stack([np.ones(198), data.frame.iloc[1:-1, j], data.frame.iloc[:-2, j]])
        residual = d["y"][:, j] - xx @ np.linalg.lstsq(xx, d["y"][:, j], rcond=None)[0]
        assert d["sigmas"][j] == pytest.approx(np.sqrt(residual @ residual / 195), abs=1e-14)
    r = fit_bvar(data, c)
    assert r["bvar"]["matched_ols"]["status"] == "ok"
    np.testing.assert_array_equal(r["bvar"]["matched_ols"]["coefficient_mean"], ref.params)
    assert r["bvar"]["draws"]["requested"] == r["bvar"]["draws"]["retained"] == 1000
    np.testing.assert_allclose(np.asarray(r["fevd"]["values"]).sum(axis=2), 1, atol=1e-14)


def test_niw_draw_moments_and_seed():
    data, c = fixture()
    p = posterior(design(data, c), 0.2, {})
    beta, sigma = draw_parameters(p, 30000, 81)
    np.testing.assert_allclose(beta.mean(axis=0), p["mean"], atol=0.003, rtol=0)
    np.testing.assert_allclose(sigma.mean(axis=0), p["covariance_mean"], atol=0.003, rtol=0)
    expected = np.diag(p["variance"])[:, None] * np.diag(p["covariance_mean"])[None, :]
    np.testing.assert_allclose(beta.var(axis=0), expected, atol=0.0002, rtol=0.04)
    a = draw_parameters(p, 1000, 81)
    b = draw_parameters(p, 1000, 81)
    for x, y in zip(a, b, strict=True):
        np.testing.assert_array_equal(x, y)
    assert not np.array_equal(a[0], draw_parameters(p, 1000, 82)[0])


def test_recovery_and_grid_selection():
    data, c = fixture(4000)
    d = design(data, c)
    p = posterior(d, 0.2, {})
    np.testing.assert_allclose(
        p["mean"][1:].reshape(2, 2, 2).transpose(0, 2, 1), A, atol=0.04, rtol=0
    )
    _, rows, selected = select_prior(d, dict(lambda_selection="grid", lambda_grid=[0.1, 0.2, 1]))
    assert selected == max(rows, key=lambda r: r["log_marginal_likelihood"])["lambda"]
    with pytest.raises(ValueError, match="unique"):
        select_prior(d, dict(lambda_selection="grid", lambda_grid=[0.2, 0.2]))


def test_explosive_draws_kept_and_filter_is_explicit():
    data, c = fixture(60)
    rng = np.random.default_rng(99)
    data.frame.iloc[:, 0] = np.cumsum(rng.normal(size=60))
    data.frame.iloc[:, 1] = np.cumsum(rng.normal(size=60))
    c["series"][1]["transform"] = "level"
    c["model"]["params"]["lambda"] = 0.4
    r = fit_bvar(data, c)
    draws = r["bvar"]["draws"]
    assert draws["explosive_share"] > 0.1
    assert draws["dropped"] == 0 and draws["retained"] == 1000
    assert any(a["code"] == "bvar_explosive_draws" for a in r["checks"])
    c["model"]["params"]["drop_explosive"] = True
    filtered = fit_bvar(data, c)["bvar"]["draws"]
    assert filtered["dropped"] == draws["explosive"]
    assert filtered["largest_roots"] == draws["largest_roots"]


def test_gaps_cancel_and_no_mutation():
    from macrolab.ident.bootstrap import CancelledError

    data, c = fixture()
    before = deepcopy(c)
    frame = data.frame.copy()
    with pytest.raises(CancelledError):
        fit_bvar(data, c, cancelled=lambda: True)
    assert c == before
    pd.testing.assert_frame_equal(frame, data.frame)
    data.frame = data.frame.drop(data.frame.index[30])
    assert BVARPlugin().check(data, c)[0]["level"] == "block"


def test_irrelevant_series_is_not_silently_ignored():
    data, c = fixture()
    c["series"].append(dict(concept_id="unused", role="dependent", transform="level"))
    with pytest.raises(ValueError, match="roles"):
        design(data, c)
