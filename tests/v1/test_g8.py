"""Matched comparisons share dates and innovations and match independent references."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.stats import norm
from statsmodels.api import OLS
from statsmodels.tsa.api import VAR

from macrolab.compare import methods
from macrolab.models.lp import design
from tests.v1.fixtures import two_stage


def test_matched_reference_sample_shock_and_nonmutation(monkeypatch):
    data, c, _, _ = two_stage(n=320)
    c["model"]["id"] = "var.ols"
    c["model"]["params"] = {"lags": 2, "trend": "c"}
    c["countries"] = ["EA"]
    c["outputs"]["irf"].update(horizon=12, shock_size=0.25, shock_mode="fixed")
    original = deepcopy(c)
    frame = data.frame.copy()
    monkeypatch.setattr(methods, "prepare_country", lambda *_: (deepcopy(data), []))
    original_fit = methods.fit
    captured = {}

    def capture(d, config):
        captured.update(data=deepcopy(d), config=deepcopy(config))
        return original_fit(d, config)

    monkeypatch.setattr(methods, "fit", capture)
    response = next(n for n in frame if n != c["series"][0]["concept_id"])
    # Use the actual non-shock name, independent of fixture order.
    shock = next(s["concept_id"] for s in c["series"] if s["role"] == "shock")
    response = next(n for n in frame if n != shock)
    result = methods.matched_pair(c, {}, response, "EA")
    assert result["status"] == "ok", result
    assert c == original
    assert frame.equals(data.frame)
    assert (
        result["lp"]["diagnostics"]["estimated_indices"]
        == result["var"]["diagnostics"]["estimated_indices"]
        == result["sample"]["periods"]
    )
    order = result["shock"]["order"]
    dates = result["sample"]["periods"]
    start = frame.index.get_loc(dates[0]) - 2
    end = frame.index.get_loc(dates[-1]) + 1
    ref = VAR(frame[order].iloc[start:end]).fit(2, trend="c")
    impact = np.linalg.cholesky(ref.sigma_u)
    j = order.index(shock)
    expected = ref.irf(12).orth_irfs[:, :, j] * 0.25 / impact[j, j]
    np.testing.assert_allclose(
        np.array(result["var"]["irf"]["values"])[:, 0],
        expected[:, order.index(response)],
        atol=1e-12,
    )
    positions = [result["shock"]["periods"].index(t) for t in dates]
    np.testing.assert_allclose(
        np.array(result["shock"]["values"])[positions],
        np.linalg.solve(impact, ref.resid.to_numpy().T).T[:, j],
        atol=1e-12,
    )
    d = design(captured["data"], captured["config"])
    scale = captured["config"]["model"]["params"]["shock_size"]
    for h in [0, 6, 12]:
        x, y = d["x"].loc[d["masks"][h]], d["y"].loc[d["masks"][h], h]
        fitted = OLS(y, x).fit(cov_type="HC1", use_t=False)
        estimate = fitted.params["impulse"] * scale
        lower = estimate - norm.ppf(0.84) * fitted.bse["impulse"] * abs(scale)
        assert result["lp"]["irf"]["values"][h][0] == pytest.approx(estimate, abs=1e-12)
        assert result["lp"]["irf"]["lower"][h][0] == pytest.approx(lower, abs=1e-12)
    assert result["comparison"]["same_estimand"]
    assert not result["include_in_baseline_agreement_counts"]


def test_unstable_matched_var_blocks_without_dynamic_output(monkeypatch):
    data, c, _, _ = two_stage(n=180)
    c["countries"] = ["EA"]
    c["model"].update(id="var.ols", params={"lags": 2})
    c["outputs"]["irf"]["horizon"] = 12
    rng = np.random.default_rng(803)
    for i in range(1, len(data.frame)):
        data.frame.iloc[i] = np.diag([1.04, 0.4]) @ data.frame.iloc[i - 1] + rng.normal(size=2)
    monkeypatch.setattr(methods, "prepare_country", lambda *_: (deepcopy(data), []))
    shock = next(s["concept_id"] for s in c["series"] if s["role"] == "shock")
    response = next(n for n in data.frame if n != shock)
    r = methods.matched_pair(c, {}, response, "EA")
    assert r["status"] == "blocked"
    assert "unstable" in r["reason"]
    assert "var" not in r


def test_common_shock_not_relabelled_recursive():
    r = methods.matched_pair({"model": {"id": "cmp.common_shock"}}, {}, "gdp_real", "DEU")
    assert r["status"] == "blocked"
    assert "different identification" in r["reason"]


@pytest.mark.parametrize("mode", ["level", "cumulative_log", "growth_log"])
def test_lp_response_units_match_var_target(monkeypatch, mode):
    data, c, _, _ = two_stage(n=320)
    c["model"] = {
        "id": "lp.ols",
        "params": {
            "lags": 2,
            "horizon": 12,
            "response_mode": mode,
            "shock_size": 0.25,
            "lag_difference_scales": {},
        },
    }
    c["countries"] = ["EA"]
    impulse = next(s["concept_id"] for s in c["series"] if s["role"] == "shock")
    response = next(n for n in data.frame if n != impulse)
    for spec in c["series"]:
        if spec["concept_id"] == response:
            spec.update(role="response", transform="log")
    monkeypatch.setattr(methods, "prepare_country", lambda *_: (deepcopy(data), []))
    r = methods.matched_pair(c, {}, response, "EA")
    assert r["status"] == "ok", r
    order = r["shock"]["order"]
    frame = data.frame[order].copy()
    if mode != "level":
        frame[response] = 100 * frame[response].diff()
        frame = frame.dropna()
    dates = r["sample"]["periods"]
    start, end = frame.index.get_loc(dates[0]) - 2, frame.index.get_loc(dates[-1]) + 1
    ref = VAR(frame.iloc[start:end]).fit(2)
    j = order.index(impulse)
    expected = (
        ref.irf(12).orth_irfs[:, order.index(response), j]
        * 0.25
        / np.linalg.cholesky(ref.sigma_u)[j, j]
    )
    if mode == "cumulative_log":
        expected = np.cumsum(expected)
    np.testing.assert_allclose(np.asarray(r["var"]["irf"]["values"])[:, 0], expected, atol=1e-11)


def test_one_sd_size_retains_baseline_before_pair_seasonal_controls(monkeypatch):
    data, c, _, _ = two_stage(n=320)
    c["countries"] = ["EA"]
    c["model"].update(id="var.ols", params={"lags": 2})
    c["outputs"]["irf"].update(horizon=12, shock_mode="one_sd", shock_size=1)
    shock = next(s["concept_id"] for s in c["series"] if s["role"] == "shock")
    response = next(n for n in data.frame if n != shock)
    data.metadata[response] = {"sa_flag": "NSA"}
    monkeypatch.setattr(methods, "prepare_country", lambda *_: (deepcopy(data), []))
    r = methods.matched_pair(c, {}, response, "EA")
    assert r["status"] == "ok", r
    order = r["shock"]["order"]
    fitted = VAR(data.frame[order]).fit(2)
    j = order.index(shock)
    assert r["shock"]["physical_size"] == np.linalg.cholesky(fitted.sigma_u)[j, j]
    assert r["sample"]["seasonal_controls"]["columns"] == ["season_2", "season_3", "season_4"]
