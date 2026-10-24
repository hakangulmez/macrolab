"""Preregistered G15 contracts and new opt-in target-scale invariants."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from macrolab.analysis.config import required_countries, validated_config
from macrolab.analysis.templates_v2 import FOUNDERS, alternatives, materially_changed
from macrolab.models.forecast_common import training
from macrolab.models.forecast_eval import origin_forecast, run_evaluation
from tests.v2.test_forecast import fixture

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("ea_phillips_pooled", [-0.6449381394495046, 0.013685219017560396]),
        ("same_ecb_shock_pooled", [-0.5860699386295264, -1.178516726328793]),
        ("ea_inflation_horse_race", [0.550430295932637, 2.2328737217700936, 2.6439309837228078]),
    ],
)
def test_preregistered_real_template_expected_results(name, expected):
    from macrolab.analysis.engine import run_analysis

    path = ROOT / "runs/g15/template-fixture.json"
    if not path.exists():
        pytest.skip("Accepted local snapshot is not bundled with source")
    f = json.loads(path.read_text())
    c = json.loads((ROOT / f"configs/templates/{name}.json").read_text())
    assert c == f["cases"][name]
    r = run_analysis(c, f["bundle"])
    assert r["status"] == "ok"
    if name == "ea_phillips_pooled":
        estimates = {x["term"]: x["estimate"] for x in r["results"][0]["coefficients_table"]}
        actual = [estimates["unemp"], estimates["oil_brent"]]
        assert r["effective_config"]["sample"]["end"] == "2026-Q2"
        assert len(r["template_sensitivity"]) == 7
    elif name == "same_ecb_shock_pooled":
        actual = [max((x[0] for x in row["irf"]["values"]), key=abs) for row in r["results"]]
        assert len(r["template_sensitivity"]) == 4
        assert all(row["panel"]["N"] == 4 for row in r["results"])
        for row in r["results"]:
            periods = [s["periods"] for s in row["panel"]["country_samples"].values()]
            assert all(p == periods[0] for p in periods)
    else:
        e = r["results"][0]["evaluation"]
        actual = [min(x["rmse"] for x in e["metrics"] if x["horizon"] == h) for h in (1, 4, 8)]
        assert e["origins"][0]["training_nobs"] == 40
        assert e["origins"][0]["origin"] == "2008-Q4"
        assert len(r["results"][0]["sensitivity"]["variants"]) == 3
    np.testing.assert_allclose(actual, expected, atol=1e-8, rtol=0)


def test_material_threshold_is_descriptive_and_strict():
    assert not materially_changed(1, 1.5)
    assert materially_changed(1, 1.5001)
    assert materially_changed(0.01, -0.01)
    assert not materially_changed(0, 0)


def test_preregistered_panel_rows_and_sensitivity_country_loading():
    c = validated_config(
        dict(
            schema_version=1,
            snapshot_id="fixture",
            countries=FOUNDERS,
            frequency="Q",
            series=[
                dict(concept_id="cpi", role="dependent", transform="yoy_pct"),
                dict(concept_id="unemp", role="regressor", transform="hp_cycle"),
                dict(concept_id="oil_brent", role="exogenous", transform="yoy_pct"),
            ],
            aggregation=dict(cpi="mean", unemp="mean", oil_brent="mean"),
            model=dict(id="panel.fe", params=dict(template_id="ea_phillips_pooled")),
        )
    )
    rows = {r["id"]: r["config"] for r in alternatives(c)}
    assert len(rows) == 7
    assert rows["two_way"]["model"]["params"]["effects"] == "two_way"
    assert "oil_brent" not in rows["two_way"]["aggregation"]
    assert rows["lagged_inflation"]["model"]["params"]["dependent_lags"] == 1
    c["countries"] = ["DEU", "FRA", "ITA", "ESP"]
    c["model"]["params"]["template_id"] = "same_ecb_shock_pooled"
    assert set(required_countries(c)) == set(FOUNDERS)


def test_transformed_target_prefix_identity_and_no_lookahead():
    raw, c = fixture(
        model="fc.eval",
        count=57,
        transform="yoy_pct",
        evaluation_scale="transformed",
        order_selection="fixed",
        p=1,
        d=0,
        q=0,
        draws=100,
    )
    c["sample"]["start"] = "2000-Q1"  # 1999 is transformation prehistory only.
    stop = 44
    expected = 100 * (raw.frame.x.iloc[stop - 1] / raw.frame.x.iloc[stop - 5] - 1)
    values, detail = origin_forecast(raw, c, stop, 8)
    assert detail["training_start"] == "2000-Q1"
    assert detail["training_nobs"] == 40
    assert values["Random walk"][0] == pytest.approx(expected, abs=1e-12)
    later = deepcopy(raw)
    later.frame.iloc[stop:] = later.frame.iloc[stop:] * 100 + 30
    changed, other = origin_forecast(later, c, stop, 8)
    assert detail == other
    for model in values:
        np.testing.assert_array_equal(values[model], changed[model])
    evaluated = run_evaluation(raw, c)
    first = evaluated["evaluation"]["origins"][0]
    assert first["training_nobs"] == 40
    assert first["origin"] == str(raw.frame.index[stop - 1])
    for r in evaluated["evaluation"]["predictions"]:
        assert r["actual"] == training(raw, c).frame.loc[r["target"], "x"]
    assert all(
        "template_id" not in fixture(model=m)[1]["model"]["params"]
        for m in ("fc.eval", "uni.arima", "fc.var")
    )


def test_transformed_first_origin_never_uses_full_sample_scaling(monkeypatch):
    # Every BVAR scale, ARIMA test and coefficient is already compared above;
    # here additionally prevent accidental full-sample training in origin_forecast.
    import macrolab.models.forecast_eval as module

    raw, c = fixture(
        model="fc.eval",
        count=80,
        transform="yoy_pct",
        evaluation_scale="transformed",
        order_selection="fixed",
        p=1,
        d=0,
        q=0,
        draws=100,
    )
    c["sample"]["start"] = "2000-Q1"
    actual = module.training

    def guarded(data, config, stop=None):
        assert len(data.frame) <= 44
        return actual(data, config, stop)

    monkeypatch.setattr(module, "training", guarded)
    origin_forecast(raw, c, 44, 8)
