"""Ratio reference inference, extraction stability and progressive-result contracts."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from statsmodels.api import OLS

from macrolab.analysis.pass_through import response_ratio
from macrolab.ident.bootstrap import joint_bootstrap
from macrolab.ident.external_series import ExternalSeriesPlugin, attach, recover
from macrolab.models.lp import design, fit
from macrolab.outputs.hd import decompose
from tests.v1.fixtures import lp_case, two_stage


@pytest.mark.parametrize("covariance", ["HC1", "HAC"])
def test_ratio_joint_covariance_matches_independent_statsmodels(covariance):
    data, c = lp_case(n=500)
    data.frame = data.frame.rename(columns={"shock": "neer"})
    data.frame["y"] = (
        -0.4 * data.frame.neer + 0.2 * np.random.default_rng(611).normal(size=len(data.frame))
    ).cumsum() / 100
    c["series"][0]["transform"] = "log"
    c["series"][2].update(concept_id="neer", transform="log_diff")
    c["model"]["params"].update(
        response_mode="cumulative_log",
        covariance=covariance,
        shock_size=-1,
        lag_difference_scales={"y": 100},
    )
    ratio = response_ratio(data, c)
    ordinary = fit(data, c)
    d = design(data, c)
    for h in [0, 6, 12]:
        row = ratio["horizons"][h]
        mask = d["masks"][h]
        anchors = np.flatnonzero(mask)
        # Independently cumulate raw growth observations, not the ratio implementation's target.
        raw = data.frame.neer.to_numpy()
        fx = np.array([sum(raw[t : t + h + 1]) for t in anchors])
        price = d["y"].loc[mask, h].to_numpy()
        x = d["x"].loc[mask].to_numpy()
        kw = {"maxlags": h + 1, "use_correction": False} if covariance == "HAC" else {}

        def reference(y, x=x, kw=kw):
            return OLS(y, x).fit(cov_type=covariance, cov_kwds=kw, use_t=False)

        p, e, total = reference(price), reference(fx), reference(price + fx)
        cross = (total.cov_params()[1, 1] - p.cov_params()[1, 1] - e.cov_params()[1, 1]) / 2
        expected = np.array([[p.bse[1] ** 2, cross], [cross, e.bse[1] ** 2]])
        np.testing.assert_allclose(row["joint_covariance"], expected, atol=1e-12)
        assert row["cpi_cumulative"] == pytest.approx(ordinary["irf"]["values"][h][0], abs=1e-12)
        assert row["ratio"] == pytest.approx(-p.params[1] / e.params[1], abs=1e-12)
        # Numerical derivative of the signed ratio verifies both delta gradient components.
        b = -np.array([p.params[1], e.params[1]])
        eps = 1e-5
        derivative = np.array(
            [
                (-(b[0] + eps) / b[1] + (b[0] - eps) / b[1]) / (2 * eps),
                (-b[0] / (b[1] + eps) + b[0] / (b[1] - eps)) / (2 * eps),
            ]
        )
        assert row["std_error"] == pytest.approx(
            np.sqrt(derivative @ expected @ derivative), abs=1e-8
        )
    assert ratio["horizons"][12]["ratio"] == pytest.approx(0.4, abs=0.07)


def test_unstable_residuals_allowed_but_dynamic_outputs_blocked(monkeypatch):
    first, config, country, national = two_stage(n=160)
    rng = np.random.default_rng(881)
    y = np.zeros((160, 2))
    for t in range(1, 160):
        y[t] = np.diag([1.025, 0.4]) @ y[t - 1] + rng.normal(size=2)
    first.frame.iloc[:, :] = y
    shock, fitted = recover(first, config)
    assert not shock["stable"]
    assert any(
        c["level"] == "warn" and c["code"] == "first_stage_persistence"
        for c in ExternalSeriesPlugin().check(first, config)
    )
    np.testing.assert_allclose(
        np.asarray(shock["all_values"]) @ np.linalg.cholesky(fitted.sigma_u).T,
        fitted.resid,
        atol=1e-12,
    )
    assert len(attach(country, shock).frame) == len(country.frame)
    # v1 national-VAR IRFs are guarded; legacy v0 behavior stays frozen.
    from macrolab.analysis import templates_v1

    renamed = deepcopy(first)
    renamed.frame.columns = ["neer", "cpi"]
    c = deepcopy(config)
    c["series"] = [
        {"concept_id": "neer", "role": "shock", "transform": "log_diff"},
        {"concept_id": "cpi", "role": "response", "transform": "log"},
    ]
    c["model"]["params"].update(template_id="tur_pass_through", shock_size=-1, horizon=12)
    monkeypatch.setattr(templates_v1, "prepare_country", lambda *_: (renamed, []))
    dynamic = templates_v1.national_var(
        c,
        {},
        {
            "results": [
                {
                    "country": "EA",
                    "status": "ok",
                    "actual_sample": {"periods": list(first.frame.index[2:])},
                }
            ]
        },
    )
    assert dynamic["results"][0]["status"] == "blocked"
    assert "stable" in dynamic["results"][0]["reason"]
    assert "irf" not in dynamic["results"][0]
    with pytest.raises(ValueError, match="stable"):
        decompose(fitted, list(first.frame.index))
    with pytest.raises(ValueError, match="stable"):
        joint_bootstrap(first, config, {"AAA": country}, {"AAA": national}, draws=20)


def test_zero_cumulative_denominator_is_undefined_not_infinity():
    data, c = lp_case(n=160)
    data.frame = data.frame.rename(columns={"shock": "neer"})
    data.frame["neer"] = (-1.0) ** np.arange(len(data.frame))
    data.frame["y"] = data.frame.y.cumsum() / 100
    c["series"][0]["transform"] = "log"
    c["series"][2].update(concept_id="neer", transform="log_diff")
    c["model"]["params"].update(response_mode="cumulative_log", lags=0, horizon=1)
    result = response_ratio(data, c)
    assert result["horizons"][1]["status"] == "undefined"
    assert result["horizons"][1]["ratio"] is None
    assert result["horizons"][1]["bands"]["0.68"] == {"lower": None, "upper": None}
    json.dumps(result, allow_nan=False)


def test_real_baseline_emitted_before_sensitivity_and_points_unchanged():
    from macrolab.analysis.engine import run_analysis
    from scripts.g7_fixture import bundle

    root = Path(__file__).resolve().parents[2]
    if not (root / "runs/g7/same_ecb_shock.json").exists():
        pytest.skip("Accepted local baseline unavailable")
    c = json.loads((root / "configs/templates/same_ecb_shock.json").read_text())
    c["comparison"]["enabled"] = False
    events = []
    result = run_analysis(c, bundle(), progress=lambda x: events.append(deepcopy(x)))
    partial = next(e["result"] for e in events if e["phase"] == "template_result")
    assert partial["config"] == result["config"]
    assert partial["template_summary"] == result["template_summary"]
    assert not partial["sensitivity_pending"]
    old = json.loads((root / "runs/g7/same_ecb_shock.json").read_text())
    for a, b in zip(result["results"], old["results"], strict=True):
        assert a["irf"] == b["irf"]
