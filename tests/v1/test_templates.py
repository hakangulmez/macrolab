"""G7 estimand, calendar exclusions, metadata and fixed real-template contracts."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from statsmodels.api import OLS

from macrolab.analysis.config import validated_config
from macrolab.analysis.engine import run_analysis
from macrolab.ident.external_series import fit_excluding_window
from macrolab.models.lp import design, fit
from macrolab.models.var import _settings
from tests.v1.fixtures import lp_case, two_stage

ROOT = Path(__file__).resolve().parents[2]


def test_log_target_with_growth_controls_matches_independent_ols_and_fast_fit():
    data, c = lp_case()
    data.frame["y"] = 4 + data.frame.y.cumsum() / 100
    c["series"][0]["transform"] = "log"
    c["model"]["params"].update(
        response_mode="cumulative_log", lag_augmented=True, lag_difference_scales={"y": 400}
    )
    result = fit(data, c)
    fast = fit(data, c, point_only=True)
    d = design(data, c)
    for h, row in enumerate(result["local_projection"]["horizons"]):
        mask = d["masks"][h]
        x = d["x"].loc[mask]
        anchor = np.flatnonzero(mask)
        target = 100 * (data.frame.y.to_numpy()[anchor + h] - data.frame.y.to_numpy()[anchor - 1])
        expected = OLS(target, x.to_numpy()).fit(cov_type="HC1", use_t=False)
        assert row["estimate"] == pytest.approx(expected.params[1], abs=1e-10)
        assert row["std_error"] == pytest.approx(expected.bse[1], abs=1e-10)
    np.testing.assert_allclose(
        np.asarray(result["irf"]["values"])[:, 0], fast["estimates"], atol=1e-10
    )
    np.testing.assert_allclose(d["x"]["L1.y"].iloc[2:], 400 * data.frame.y.diff().shift().iloc[2:])


@pytest.mark.parametrize("control", [{"absent": 100}, {"y": float("nan")}, {"y": -1}])
def test_invalid_lag_control_blocks(control):
    data, c = lp_case()
    c["model"]["params"]["lag_difference_scales"] = control
    with pytest.raises(ValueError, match="Lag difference"):
        fit(data, c)


def test_exclusion_ols_never_bridges_calendar_window():
    data, c, _, _ = two_stage()
    c["model"]["params"]["exclude_window"] = {"start": "2014-Q1", "end": "2022-Q4"}
    settings = _settings(c, recursive=True)
    fitted, anchors = fit_excluding_window(data, c, settings)
    dates = pd.PeriodIndex(data.frame.index, freq="Q")
    blocked = (dates >= pd.Period("2014Q1")) & (dates <= pd.Period("2022Q4"))
    assert all(not blocked[t - 2 : t + 1].any() for t in anchors)
    y = data.frame.to_numpy()
    idx = np.array(anchors)
    x = np.column_stack([np.ones(len(idx)), y[idx - 1], y[idx - 2]])
    expected = OLS(y[idx], x).fit()
    np.testing.assert_allclose(fitted.params, expected.params, atol=1e-12)
    np.testing.assert_allclose(
        fitted.sigma_u, expected.resid.T @ expected.resid / expected.df_resid, atol=1e-12
    )


def test_both_new_templates_declared_and_old_defaults_unchanged():
    for name in ["same_ecb_shock", "tur_pass_through"]:
        c = validated_config(json.loads((ROOT / f"configs/templates/{name}.json").read_text()))
        assert c["model"]["params"]["lag_augmented"]
        assert c["model"]["params"]["covariance"] == "HC1"
    ecb = json.loads((ROOT / "configs/templates/same_ecb_shock.json").read_text())
    assert ecb["model"]["params"]["policy_measure"] == "dfr"
    old = json.loads((ROOT / "configs/templates/monetary_policy.json").read_text())
    assert not old["model"]["params"].get("template_id")


@pytest.mark.parametrize(
    "name,peaks",
    [
        ("same_ecb_shock", [-0.514219362381, -0.440664662514, 0.238759906049, -0.464581906066]),
        ("tur_pass_through", [1.597349844]),
    ],
)
def test_real_template_expected_result(name, peaks):
    if not (ROOT / "runs/g6/public/data/manifest.json").exists():
        pytest.skip("Local accepted snapshot not bundled with source")
    from scripts.g7_fixture import bundle

    c = json.loads((ROOT / f"configs/templates/{name}.json").read_text())
    c["comparison"]["enabled"] = False
    b = bundle()
    before = deepcopy(b)
    r = run_analysis(c, b)
    assert r["status"] == "ok" and b == before
    actual = [
        s["peak"]
        for s in r["template_summary"]
        if s["response"] == ("gdp_real" if name == "same_ecb_shock" else "cpi")
    ]
    # Fixed peak fixtures, rounded to 5 decimals; complete browser/native arrays checked separately.
    np.testing.assert_allclose(actual, peaks, atol=1e-5, rtol=0)
    for row in r["results"]:
        assert row["local_projection"]["seasonal_controls"]["columns"]
        assert row["actual_sample"]["nobs"] == (92 if name == "same_ecb_shock" else 294)
