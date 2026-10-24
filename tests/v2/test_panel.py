from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from linearmodels.panel import PanelOLS

from macrolab.analysis.config import validated_config
from macrolab.analysis.engine import run_analysis
from macrolab.models.lp import fit as lp_fit
from macrolab.models.panel import fit_panel, within_fit
from tests.v1.fixtures import bundle_from, lp_case


@pytest.mark.parametrize("two_way", [False, True])
@pytest.mark.parametrize("unbalanced", [False, True])
def test_panelols_reference_all_covariances(two_way, unbalanced):
    rng = np.random.default_rng(812)
    n, t = 11, 100
    entity = np.repeat(np.arange(n), t)
    time = np.tile(np.arange(t), n)
    x = rng.normal(size=(n * t, 3))
    y = (
        x @ np.array([0.4, -0.7, 0.2])
        + rng.normal(size=n)[entity]
        + rng.normal(size=t)[time]
        + rng.normal(size=n * t)
    )
    keep = rng.random(n * t) > 0.18 if unbalanced else np.ones(n * t, dtype=bool)
    x, y, entity, time = x[keep], y[keep], entity[keep], time[keep]
    ours = within_fit(y, x, entity, time, two_way=two_way)
    index = pd.MultiIndex.from_arrays([entity, time])
    xx = pd.DataFrame(x, index=index)
    model = PanelOLS(pd.Series(y, index=index), xx, entity_effects=True, time_effects=two_way)
    for name, options in [
        ("conventional", {"cov_type": "unadjusted"}),
        ("country-clustered", {"cov_type": "clustered", "cluster_entity": True}),
        ("Driscoll-Kraay", {"cov_type": "kernel", "kernel": "bartlett"}),
    ]:
        ref = model.fit(**options)
        np.testing.assert_allclose(ours["beta"], ref.params, atol=1e-8, rtol=0)
        np.testing.assert_allclose(ours["covariances"][name], ref.cov, atol=1e-8, rtol=0)
        assert ours["within_r_squared"] == pytest.approx(ref.rsquared_within, abs=1e-8)


@pytest.mark.parametrize("mode", ["level", "change", "cumulative_log", "growth_log"])
@pytest.mark.parametrize("augmented", [False, True])
@pytest.mark.parametrize("sample", ["common", "horizon_specific"])
def test_n1_identity(mode, augmented, sample):
    data, c = lp_case()
    c["model"]["params"].update(response_mode=mode, lag_augmented=augmented, sample_mode=sample)
    if "log" in mode:
        c["series"][0]["transform"] = "log"
    expected = lp_fit(data, c)
    panel = deepcopy(c)
    panel["model"]["id"] = "panel.lp"
    panel["model"]["params"]["covariance"] = "HC1" if augmented else "HAC"
    actual = fit_panel({"SYN": data}, panel)
    assert (
        actual["local_projection"]["growth_scale"] == expected["local_projection"]["growth_scale"]
    )
    assert actual["irf"]["values"] == expected["irf"]["values"]
    assert actual["irf"]["lower"] == expected["irf"]["lower"]
    assert actual["irf"]["upper"] == expected["irf"]["upper"]
    for ours, ref in zip(
        actual["local_projection"]["horizons"],
        expected["local_projection"]["horizons"],
        strict=True,
    ):
        assert ours["samples"]["SYN"]["periods"] == ref["periods"]


def test_gaps_and_common_window_and_common_shock_guard():
    d, c = lp_case(160)
    d2 = deepcopy(d)
    d2.country = "AAA"
    d2.frame = d2.frame.drop(d2.frame.index[[25, 80]])
    c["model"] = {
        "id": "panel.lp",
        "params": {
            "lags": 2,
            "horizon": 12,
            "country_window": "common",
            "lag_augmented": True,
            "response_mode": "change",
        },
    }
    c = validated_config(c)
    r = fit_panel({"SYN": d, "AAA": d2}, c)
    for h in r["local_projection"]["horizons"]:
        assert h["samples"]["SYN"]["periods"] == h["samples"]["AAA"]["periods"]
        assert "2019-Q1" not in h["samples"]["AAA"]["periods"]
    c["model"]["params"]["effects"] = "two_way"
    with pytest.raises(ValueError, match="absorb"):
        fit_panel({"SYN": d, "AAA": d2}, c)
    c["model"]["params"]["effects"] = "country"
    d2.frame["shock"] += 0.1
    with pytest.raises(ValueError, match="differ across"):
        fit_panel({"SYN": d, "AAA": d2}, c)


def test_fe_recovery_unbalanced_and_warnings():
    rng = np.random.default_rng(477)
    frames = {}
    for i in range(12):
        x = rng.normal(size=180)
        y = 0.7 * x + i + rng.normal(scale=0.2, size=180)
        dates = [
            str(p).replace("Q", "-Q") for p in pd.period_range("1999Q1", periods=180, freq="Q")
        ]
        frames[f"C{i:02}"] = pd.DataFrame({"y": y, "x": x}, index=dates).iloc[i:]
    c = {
        "schema_version": 1,
        "snapshot_id": "g6-synthetic",
        "countries": list(frames),
        "frequency": "Q",
        "series": [
            {"concept_id": "y", "role": "dependent", "transform": "level"},
            {"concept_id": "x", "role": "regressor", "transform": "level"},
        ],
        "model": {"id": "panel.fe", "params": {}},
        "comparison": {"enabled": True},
    }
    r = run_analysis(c, bundle_from(frames))
    assert r["status"] == "ok", r["checks"]
    p = r["results"][0]
    assert abs(p["coefficients_table"][0]["estimate"] - 0.7) < 0.02
    assert p["panel"]["N"] == 12 and p["panel"]["T_min"] == 169 and p["panel"]["T_max"] == 180
    assert len(p["panel"]["country_estimates"]) == 12
    c["countries"] = list(frames)[:4]
    c["sample"] = {"start": "1999-Q1", "end": "2007-Q4"}
    c["model"]["params"] = {"dependent_lags": 1, "covariance": "country-clustered"}
    short = run_analysis(c, bundle_from(frames))
    assert short["status"] == "ok", short["checks"]
    assert {"nickell_bias", "few_clusters"} <= {x["code"] for x in short["checks"]}


@pytest.mark.parametrize("two_way", [False, True])
def test_panel_lp_independent_reference_and_overlay(two_way):
    rng = np.random.default_rng(741)
    countries = {}
    for i in range(4):
        d, c = lp_case(150, seed=20 + i)
        # Independent noisy shocks avoid exact finite-order redundant controls.
        d.frame["shock"] = rng.normal(size=150)
        d.frame["y"] += i + rng.normal(size=150) * 0.2
        d.country = f"C{i:02}"
        countries[d.country] = d
    config = deepcopy(c)
    config["countries"] = list(countries)
    config["model"] = {
        "id": "panel.lp",
        "params": {
            "horizon": 6,
            "lags": 2,
            "lag_augmented": True,
            "response_mode": "change",
            "shock_type": "country_specific",
            "effects": "two_way" if two_way else "country",
        },
    }
    r = fit_panel(countries, config)
    for h in range(7):
        ys = []
        xs = []
        idx = []
        for country, d in countries.items():
            a = np.arange(3, 150 - 6)
            xs.append(
                np.column_stack(
                    [d.frame.shock.iloc[a]]
                    + [
                        d.frame[name].iloc[a - lag]
                        for lag in (1, 2, 3)
                        for name in ["shock", "x", "y"]
                    ]
                )
            )
            ys.append(d.frame.y.iloc[a + h].to_numpy() - d.frame.y.iloc[a - 1].to_numpy())
            idx.extend((country, int(t)) for t in a)
        index = pd.MultiIndex.from_tuples(idx)
        ref = PanelOLS(
            pd.Series(np.concatenate(ys), index=index),
            pd.DataFrame(np.concatenate(xs), index=index),
            entity_effects=True,
            time_effects=two_way,
        ).fit(cov_type="kernel", kernel="bartlett")
        row = r["local_projection"]["horizons"][h]
        assert row["estimate"] == pytest.approx(ref.params.iloc[0], abs=1e-8)
        assert row["std_error"] == pytest.approx(ref.std_errors.iloc[0], abs=1e-8)
    for country, d in countries.items():
        single = deepcopy(config)
        single["model"] = {
            "id": "lp.ols",
            "params": {"horizon": 6, "lags": 2, "lag_augmented": True, "response_mode": "change"},
        }
        own = lp_fit(d, single)["local_projection"]["horizons"]
        for a, b in zip(r["panel"]["country_estimates"][country], own, strict=True):
            assert a["estimate"] == b["estimate"] and a["periods"] == b["periods"]


def test_missing_input_does_not_silently_remove_country():
    d, c = lp_case()
    c["countries"] = ["SYN", "MISSING"]
    c["model"] = {"id": "panel.lp", "params": {"horizon": 12}}
    b = bundle_from({"SYN": d.frame})
    result = run_analysis(c, b)
    assert result["status"] == "blocked"
    assert any(
        x["code"] == "missing_coverage" and x["country"] == "MISSING" for x in result["checks"]
    )


def test_panel_cancellation_and_progress():
    from macrolab.ident.bootstrap import CancelledError

    d, c = lp_case()
    c["model"] = {"id": "panel.lp", "params": {"horizon": 12, "lag_augmented": True}}
    progress = []
    with pytest.raises(CancelledError):
        fit_panel({"SYN": d}, c, progress=progress.append, cancelled=lambda: len(progress) == 3)
    assert [x["completed"] for x in progress] == [1, 2, 3]


def test_seasonal_controls_and_rank_guard():
    d, c = lp_case()
    d.metadata["y"] = {"sa_flag": "NSA"}
    c["model"] = {"id": "panel.lp", "params": {"horizon": 12, "lag_augmented": True}}
    result = fit_panel({"SYN": d}, c)
    assert all(
        x in result["panel"]["coefficient_terms"] for x in ["season_2", "season_3", "season_4"]
    )
    assert result["panel"]["seasonal_controls"]["SYN"]["columns"] == [
        "season_2",
        "season_3",
        "season_4",
    ]
    d.frame["shock"] = 1
    with pytest.raises(ValueError, match="impulse"):
        fit_panel({"SYN": d}, c)


def test_country_ols_default_hac4_and_preserved_conventional():
    from statsmodels.api import OLS, add_constant

    from macrolab.models.panel import fe_design

    d, c = lp_case()
    c["series"] = [
        dict(concept_id="y", role="dependent", transform="level"),
        dict(concept_id="x", role="regressor", transform="level"),
    ]
    c["model"] = dict(id="panel.fe", params={})
    c = validated_config(c)
    result = fit_panel({"SYN": d}, c)
    x = fe_design(d, c)["x"]
    y = d.frame.y
    fit = OLS(y.to_numpy(), add_constant(x).to_numpy()).fit()
    hac = fit.get_robustcov_results(cov_type="HAC", maxlags=4, use_t=True)
    rows = result["panel"]["country_estimates"]["SYN"]
    conventional = result["panel"]["country_estimates_conventional"]["SYN"]
    np.testing.assert_allclose([v["std_error"] for v in rows], hac.bse, atol=1e-14, rtol=0)
    np.testing.assert_allclose([v["std_error"] for v in conventional], fit.bse, atol=1e-14, rtol=0)
    assert [v["estimate"] for v in rows] == [v["estimate"] for v in conventional]
    assert all(v["covariance"] == "HAC(4)" for v in rows)
