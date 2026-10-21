"""G2.1 changes orchestration and horizons, leaving the v0 estimators intact."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import validate

from macrolab.analysis.config import ConfigError, validated_config
from macrolab.analysis.data import prepare_country
from macrolab.analysis.engine import run_analysis
from macrolab.analysis.g21 import run_configured_plugin
from macrolab.checks.core import evaluate_checks
from macrolab.models.base import AnalysisData
from macrolab.models.registry import get_plugin

ROOT = Path(__file__).resolve().parents[2]


def source():
    rng = np.random.default_rng(941)
    periods = [str(p).replace("Q", "-Q") for p in pd.period_range("1998Q1", periods=116, freq="Q")]
    names = ["unemp", "gdp_real", "policy_rate", "cpi", "reer", "credit_pnfs", "oil_brent"]
    series = {}
    for name in names:
        values = (
            (100 + np.cumsum(rng.normal(0.2, 0.5, len(periods))))
            if name in {"gdp_real", "cpi", "reer", "oil_brent"}
            else (2 + rng.normal(0, 0.5, len(periods)))
        )
        series[name] = {
            "metadata": {
                "concept_id": name,
                "frequency": "Q",
                "status": "available",
                "flags": [],
                "warnings": [],
                "first_date": periods[0],
                "last_date": periods[-1],
                "unit": "PERCENT",
            },
            "observations": list(zip(periods, values.tolist(), strict=True)),
        }
    return {
        "snapshot_id": "synthetic",
        "countries": {"USA": {"metadata": {"iso3": "USA"}, "series": series}},
    }


def template(name):
    config = json.loads((ROOT / "configs/templates" / f"{name}.json").read_text())
    config.update(snapshot_id="synthetic", countries=["USA"])
    return config


def test_six_endogenous_plus_exogenous_and_exact_covid_window():
    config = template("monetary_policy")
    config["series"].extend(
        [
            {"concept_id": "reer", "role": "endogenous", "transform": "log"},
            {"concept_id": "credit_pnfs", "role": "endogenous", "transform": "level"},
        ]
    )
    config["aggregation"].update({"reer": "mean", "credit_pnfs": "mean"})
    config["identification"]["params"]["order"] = [
        "gdp_real",
        "cpi",
        "unemp",
        "reer",
        "credit_pnfs",
        "policy_rate",
    ]
    config = validated_config(config)
    data, checks = prepare_country(config, source(), "USA")
    assert len(data.frame.columns) == 7
    assert list(data.exog.columns) == ["covid_2020-Q1", "covid_2020-Q2", "covid_2020-Q3"]
    assert data.exog.sum().tolist() == [1.0, 1.0, 1.0]
    assert not any(c["level"] == "block" for c in checks + evaluate_checks(data, config))
    assert data.sample["transforms"]["gdp_real"]["transform"] == "qoq_saar"


def test_one_sd_is_fitted_covariance_impact_not_fixed_constant():
    rng = np.random.default_rng(141)
    values = rng.normal(size=(150, 2)) @ np.array([[1.0, 0.3], [0.0, 0.4]])
    frame = pd.DataFrame(
        values, columns=["y", "policy_rate"], index=pd.period_range("1980Q1", periods=150, freq="Q")
    )
    data = AnalysisData(frame)
    config = {
        "series": [
            {"concept_id": "y", "role": "response"},
            {"concept_id": "policy_rate", "role": "shock"},
        ],
        "model": {"id": "ident.recursive", "params": {"lags": 2}},
        "identification": {"id": "recursive", "params": {"order": ["y", "policy_rate"]}},
        "outputs": {
            "irf": {
                "shock_mode": "one_sd",
                "shock_size": 1,
                "method": "asymptotic",
                "horizon": 4,
                "bands": 0.68,
                "draws": 500,
            }
        },
        "seed": 42,
    }
    before = deepcopy(config)
    result = run_configured_plugin(data, config)
    size = np.linalg.cholesky(result["diagnostics"]["residual_covariance"])[1, 1]
    assert result["irf"]["shock_size"] == pytest.approx(size, abs=1e-12)
    assert result["irf"]["values"][0][1] == pytest.approx(size, abs=1e-12)
    assert result["irf"]["shock_normalization"]["nobs"] == 148
    assert "residual df" in result["irf"]["shock_normalization"]["formula"]
    fixed = deepcopy(config)
    fixed["outputs"]["irf"].update(shock_mode="fixed", shock_size=float(size))
    reference = get_plugin("ident.recursive").run(data, fixed)
    np.testing.assert_allclose(result["irf"]["values"], reference["irf"]["values"], atol=1e-12)
    second = run_configured_plugin(AnalysisData(frame.iloc[75:]), config)
    assert second["irf"]["shock_size"] != result["irf"]["shock_size"]
    assert second["irf"]["shock_normalization"]["nobs"] == 73
    assert config == before


def test_sample_and_covid_scenarios_reprepare_and_keep_visible_checks():
    config = template("monetary_policy")
    config["model"]["params"]["lags"] = 2
    config["outputs"]["irf"]["method"] = "asymptotic"
    result = run_analysis(config, source())["results"][0]
    assert result["status"] == "ok"
    variants = {v["variant_id"]: v for v in result["sensitivity"]["variants"]}
    assert variants["covid_include"]["status"] == "available"
    assert variants["end_2019"]["sample"]["end"] == "2019-Q4"
    assert (
        variants["end_2019"]["metrics"]["shock_normalization"]["basis"]
        == "own_sample_covariance_corrected_cholesky_impact"
    )
    assert variants["reverse_order"]["metrics"]["shock_size"] == result["irf"]["shock_size"]
    assert (
        variants["baseline"]["prepared_inputs_sha256"]
        != variants["covid_include"]["prepared_inputs_sha256"]
    )
    assert all("checks" in v for v in variants.values())


@pytest.mark.parametrize("shock_size", [-0.25, 0.0, 0.25])
def test_positive_output_after_easing_is_not_called_a_tightening_puzzle(shock_size):
    rng = np.random.default_rng(723)
    policy = rng.normal(size=250)
    direction = -1 if shock_size < 0 else 1
    output = 0.8 * direction * np.roll(policy, 1) + rng.normal(scale=0.05, size=250)
    data = AnalysisData(
        pd.DataFrame(
            {"gdp_real": output, "policy_rate": policy},
            index=pd.period_range("1960Q1", periods=250, freq="Q"),
        )
    )
    config = {
        "series": [
            {"concept_id": "gdp_real", "role": "response"},
            {"concept_id": "policy_rate", "role": "shock"},
        ],
        "model": {"id": "ident.recursive", "params": {"lags": 1}},
        "identification": {"id": "recursive", "params": {"order": ["gdp_real", "policy_rate"]}},
        "outputs": {
            "irf": {
                "shock_mode": "fixed",
                "shock_size": shock_size,
                "method": "asymptotic",
                "horizon": 4,
            }
        },
        "seed": 42,
    }
    result = run_configured_plugin(data, config)
    assert result["irf"]["shock_normalization"]["resolved_percentage_points"] == shock_size
    if shock_size != 0:
        assert result["irf"]["values"][1][0] > 0.15
    puzzle_notes = [note for note in result["notes"] if "after the tightening" in note]
    assert bool(puzzle_notes) is (shock_size > 0)


def test_taylor_full_sample_recomputes_filter_then_recent_half_retains_it():
    config = template("taylor_rule")
    result = run_analysis(config, source())["results"][0]
    assert result["actual_sample"]["end"] == "2008-Q4"
    assert result["actual_sample"]["nobs"] == 40
    variants = {v["variant_id"]: v for v in result["sensitivity"]["variants"]}
    assert (
        variants["full_sample"]["status"]
        == variants["recent_half_full_sample"]["status"]
        == "available"
    )
    full = variants["full_sample"]["sample"]
    recent = variants["recent_half_full_sample"]["sample"]
    assert full["end"] == recent["end"] == "2026-Q4"
    assert recent["nobs"] == full["nobs"] // 2
    assert full["transforms"] == recent["transforms"]
    assert (
        full["transforms"]["gdp_real"]["input_end"]
        != result["actual_sample"]["transforms"]["gdp_real"]["input_end"]
    )


def test_okun_horizons_match_and_quarterly_is_not_pooled_as_same_estimand():
    config = template("okuns_law")
    result = run_analysis(config, source())["results"][0]
    baseline = result["actual_sample"]["transforms"]
    assert baseline["unemp"]["transform"] == "yoy_diff"
    assert baseline["gdp_real"]["transform"] == "yoy_pct"
    variant = next(
        v for v in result["sensitivity"]["variants"] if v["variant_id"] == "quarterly_okun"
    )
    assert variant["status"] == "available"
    assert variant["sample"]["transforms"]["unemp"]["transform"] == "diff"
    assert variant["sample"]["transforms"]["gdp_real"]["transform"] == "log_diff"
    assert not variant["informative_point_comparison"]
    assert "quarterly_okun" not in result["sensitivity"]["summary"][0]["variant_ids"]


def test_schema_and_runtime_accept_new_options_and_reject_invalid_requests():
    config = validated_config(template("monetary_policy"))
    validate(config, json.loads((ROOT / "schemas/analysis_config.schema.json").read_text()))
    bad = deepcopy(config)
    bad["outputs"]["irf"]["shock_size"] = 0.25
    with pytest.raises(ConfigError, match="exactly"):
        validated_config(bad)
    bad = deepcopy(config)
    bad["special_periods"]["covid_window"]["end"] = "2019-Q4"
    with pytest.raises(ConfigError, match="window"):
        validated_config(bad)
