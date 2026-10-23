from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from statsmodels.api import OLS

from macrolab.analysis.engine import run_analysis
from macrolab.models.lp import LPPlugin, design, fit
from tests.v1.fixtures import bundle_from, lp_case


@pytest.mark.parametrize("mode", ["common", "horizon_specific"])
@pytest.mark.parametrize("augmented", [False, True])
def test_independent_statsmodels_reference(mode, augmented):
    data, config = lp_case()
    config["model"]["params"].update(sample_mode=mode, lag_augmented=augmented)
    result = fit(data, config)
    p = 2 + int(augmented)
    for h in range(13):
        stop = len(data.frame) - (12 if mode == "common" else h)
        anchors = np.arange(p, stop)
        x = np.column_stack(
            [np.ones(len(anchors)), data.frame["shock"].iloc[anchors]]
            + [
                data.frame[name].iloc[anchors - lag]
                for lag in range(1, p + 1)
                for name in ["shock", "x", "y"]
            ]
        )
        y = data.frame["y"].iloc[anchors + h]
        reference = OLS(y.to_numpy(), x).fit(
            cov_type="HC1" if augmented else "HAC",
            cov_kwds={} if augmented else {"maxlags": h + 1, "use_correction": False},
            use_t=False,
        )
        row = result["local_projection"]["horizons"][h]
        assert row["estimate"] == pytest.approx(reference.params[1], abs=1e-8)
        assert row["std_error"] == pytest.approx(reference.bse[1], abs=1e-8)
        assert row["nobs"] == len(anchors)


def test_h0_identity_and_control_permutation_and_rename():
    data, config = lp_case()
    config["model"]["params"].update(lags=0, horizon=0)
    result = fit(data, config)
    reference = OLS(
        data.frame.y, np.column_stack([np.ones(len(data.frame)), data.frame.shock])
    ).fit()
    assert result["irf"]["values"][0][0] == pytest.approx(reference.params.iloc[1], abs=1e-12)
    config["model"]["params"].update(lags=2, horizon=12)
    original = fit(data, config)
    config["series"].reverse()
    assert original == fit(data, config)
    rename = {"x": "aa", "y": "zz", "shock": "ss"}
    renamed = deepcopy(data)
    renamed.frame = renamed.frame.rename(columns=rename)
    for s in config["series"]:
        s["concept_id"] = rename[s["concept_id"]]
    other = fit(renamed, config)
    np.testing.assert_allclose(
        original["irf"]["values"], other["irf"]["values"], atol=1e-12, rtol=0
    )


def test_cumulative_log_and_growth_use_levels_not_overlapping_growth():
    data, config = lp_case()
    data.frame["y"] = np.log(100) + np.cumsum(data.frame.y) / 100
    next(s for s in config["series"] if s["concept_id"] == "y")["transform"] = "log"
    config["model"]["params"]["response_mode"] = "cumulative_log"
    d = design(data, config)
    assert d["y"].iloc[50, 4] == pytest.approx(
        100 * (data.frame.y.iloc[54] - data.frame.y.iloc[49])
    )
    config["model"]["params"].update(response_mode="growth_log", growth_scale=4)
    d = design(data, config)
    assert d["y"].iloc[50, 4] == pytest.approx(
        400 * (data.frame.y.iloc[54] - data.frame.y.iloc[53])
    )
    config["series"][0]["transform"] = "yoy_pct"
    with pytest.raises(ValueError, match="original log levels"):
        fit(data, config)


def test_internal_calendar_gap_not_bridged_and_sample_rules():
    data, config = lp_case(100)
    data.frame = data.frame.drop(index=data.frame.index[50])
    d = design(data, config)
    assert len(d["x"]) == 100
    assert not d["masks"][0].iloc[50]
    assert not d["masks"][0].iloc[51]
    for n, expected in [(45, "warn"), (30, "block")]:
        data, config = lp_case(n)
        checks = LPPlugin().check(data, config)
        assert (
            next(c for c in checks if c["code"] == "lp_short_horizon_sample")["level"] == expected
        )


def test_seasonality_monthly_quarterly_and_yoy_sensitivity():
    data, config = lp_case()
    data.frame = data.frame.rename(columns={"y": "cpi"})
    config["series"][0]["concept_id"] = "cpi"
    data.metadata["cpi"] = {"sa_flag": "NSA"}
    assert design(data, config)["data"].sample["seasonal_controls"]["columns"] == [
        "season_2",
        "season_3",
        "season_4",
    ]
    data.frequency = "M"
    data.frame.index = [
        str(p) for p in pd.period_range("1999-01", periods=len(data.frame), freq="M")
    ]
    config["frequency"] = "M"
    assert len(design(data, config)["data"].sample["seasonal_controls"]["columns"]) == 11
    # Full engine: log prices receive a visibly different y/y inflation sensitivity.
    data, config = lp_case()
    data.frame["y"] = np.exp(data.frame["y"] / 100 + 4)
    data.frame = data.frame.rename(columns={"y": "cpi"})
    config["series"][0].update(concept_id="cpi", transform="log")
    config["model"]["params"]["response_mode"] = "cumulative_log"
    config["comparison"] = {"enabled": True}
    result = run_analysis(config, bundle_from({"SYN": data.frame}))
    assert result["status"] == "ok"
    rows = result["results"][0]["sensitivity"]["variants"]
    assert next(r for r in rows if r["variant_id"] == "year_on_year_inflation")["status"] == "ok"


def test_annual_calendar_and_unidentified_impulse_block():
    data, config = lp_case(100)
    data.frequency = "A"
    data.frame.index = [str(year) for year in range(1900, 2000)]
    config["frequency"] = "A"
    assert fit(data, config)["diagnostics"]["nobs"] == 86
    data.frame["shock"] = 1.0
    assert any(c["level"] == "block" for c in LPPlugin().check(data, config))
