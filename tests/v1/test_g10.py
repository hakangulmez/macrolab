"""Opt-in crisis samples/covariance and HD persistence without legacy mutations."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from statsmodels.api import OLS

from macrolab.analysis.config import validated_config
from macrolab.models.lp import _active, design, fit
from tests.v1.fixtures import lp_case


@pytest.mark.parametrize(
    "baseline,ratio,relative,material",
    [
        (1, 0.5, 0.5, False),
        (1, 0.499, 0.501, True),
        (-1, -1.6, 0.6, True),
        (1, -0.1, 1.1, True),
        (0, 0, None, False),
        (0, 0.1, None, True),
    ],
)
def test_crisis_materiality_is_descriptive_and_strictly_above_half(
    baseline, ratio, relative, material
):
    from macrolab.analysis.crisis import magnitude_change

    result = magnitude_change(baseline, ratio)
    if relative is None:
        assert result["relative_change"] is None
    else:
        assert result["relative_change"] == pytest.approx(relative)
    assert result["changes_answer_materially"] is material


def monthly_case():
    data, c = lp_case()
    data.frequency = c["frequency"] = "M"
    data.frame.index = pd.period_range("1999-01", periods=len(data.frame), freq="M").astype(str)
    c["sample"] = {"start": "1999-01", "end": "latest"}
    c.pop("special_periods", None)
    data.frame["y"] = 4 + data.frame.y.cumsum() / 100
    c["series"][0]["transform"] = "log"
    c["model"]["params"].update(
        response_mode="cumulative_log",
        lag_augmented=True,
        lag_difference_scales={"y": 100},
        horizon=24,
    )
    return data, c


def test_optional_crisis_parameters_do_not_enter_legacy_configs():
    _, c = monthly_case()
    assert "crisis_mode" not in validated_config(c)["model"]["params"]
    assert "crisis_extension" not in validated_config(c)["model"]["params"]


def test_crisis_dummy_estimates_and_hc1_match_independent_reference():
    data, c = monthly_case()
    c["model"]["params"]["crisis_mode"] = "dummies"
    before = deepcopy(data.frame)
    d = design(data, c)
    result = fit(data, c)
    fast = fit(data, c, point_only=True)
    np.testing.assert_allclose(
        fast["estimates"], np.asarray(result["irf"]["values"])[:, 0], atol=1e-10
    )
    for h in (0, 6, 12, 24):
        x, _ = _active(d["x"].loc[d["masks"][h]])
        y = d["y"].loc[d["masks"][h], h]
        reference = OLS(y, x).fit(cov_type="HC1")
        row = result["local_projection"]["horizons"][h]
        assert row["estimate"] == pytest.approx(reference.params.iloc[1], abs=1e-10)
        assert row["std_error"] == pytest.approx(reference.bse.iloc[1], abs=1e-10)
    pd.testing.assert_frame_equal(data.frame, before)


def test_crisis_exclusion_checks_full_footprint_and_preserves_calendar():
    from macrolab.analysis.crisis import WINDOWS

    data, c = monthly_case()
    c["model"]["params"]["crisis_mode"] = "exclude"
    d = design(data, c)
    blocked = {p for start, end in WINDOWS for p in pd.period_range(start, end, freq="M")}
    for h, mask in enumerate(d["masks"]):
        for anchor in d["x"].index[mask]:
            used = set(pd.period_range(anchor - d["settings"]["lags"] - 1, anchor + h, freq="M"))
            assert not used & blocked
    assert all(np.array_equal(mask, d["masks"][0]) for mask in d["masks"])
    assert len(d["x"]) == len(data.frame)
    assert d["crisis"]["excluded_anchors_by_horizon"]["24"]


def test_crisis_fx_and_cpi_use_same_anchors_and_joint_delta_covariance():
    from macrolab.analysis.pass_through import response_ratio

    data, c = monthly_case()
    # This test uses the generic impulse as a depreciation-positive FX series.
    c["model"]["params"]["crisis_mode"] = "exclude"
    d = design(data, c)
    result = response_ratio(data, c)
    for h in (6, 12, 24):
        row = result["horizons"][h]
        assert row["periods"] == list(map(str, d["x"].index[d["masks"][h]]))
        gradient = np.array(
            [1 / row["fx_cumulative"], -row["cpi_cumulative"] / row["fx_cumulative"] ** 2]
        )
        assert row["std_error"] ** 2 == pytest.approx(gradient @ row["joint_covariance"] @ gradient)


def test_hd_requested_from_var_preserves_its_exact_fit():
    from macrolab.models.var import _estimate, _settings, _stable
    from macrolab.outputs.hd import HistoricalDecompositionPlugin
    from tests.v1.fixtures import two_stage

    data, c, _, _ = two_stage()
    c["model"]["id"] = "out.hd"
    c["model"]["params"]["hd_match_var"] = True
    c["model"]["params"]["seasonal"] = True
    original = _estimate(data, c, _settings(c, recursive=True))
    hd = HistoricalDecompositionPlugin().run(data, c)["historical_decomposition"]
    assert hd["companion_spectral_radius"] == _stable(np.asarray(original.coefs))[1]
    np.testing.assert_allclose(hd["reconstructed"], original.endog, atol=1e-8)
