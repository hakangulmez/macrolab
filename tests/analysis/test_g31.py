"""G3.1 changes bounded specification defaults, never estimators or warning thresholds."""

import runpy
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.api import VAR

from macrolab.analysis.config import required_concepts, validated_config
from macrolab.analysis.engine import run_analysis
from macrolab.analysis.g31 import lag_criteria_evidence
from macrolab.analysis.sensitivity import _response_summary
from macrolab.models.base import AnalysisData
from macrolab.models.registry import get_plugin

FIXTURE = runpy.run_path(str(Path(__file__).with_name("test_g21.py")))


def configuration():
    config = FIXTURE["template"]("monetary_policy")
    config["outputs"]["irf"]["method"] = "asymptotic"
    config["comparison"]["scenarios"] = ["extended_var", "lag_criteria"]
    return validated_config(config)


def test_required_bundle_concepts_do_not_promote_controls_to_baseline():
    config = configuration()
    original = deepcopy(config)
    assert required_concepts(config) == [
        "policy_rate",
        "gdp_real",
        "cpi",
        "unemp",
        "oil_brent",
        "reer",
        "credit_pnfs",
    ]
    assert config == original
    config["comparison"]["enabled"] = False
    assert required_concepts(config) == [s["concept_id"] for s in config["series"]]


def test_criteria_match_reference_common_holdback_without_changing_fixed_default():
    config = configuration()
    rng = np.random.default_rng(9303)
    names = config["identification"]["params"]["order"]
    frame = pd.DataFrame(
        rng.normal(size=(150, 5)),
        columns=names + ["oil_brent"],
        index=pd.period_range("1990Q1", periods=150, freq="Q"),
    )
    exog = pd.DataFrame({"covid_2020-Q1": (np.arange(150) == 120).astype(float)}, index=frame.index)
    data = AnalysisData(frame, exog=exog)
    before = deepcopy(config)
    evidence = lag_criteria_evidence(data, config)
    reference = VAR(
        frame[names], exog=pd.concat([frame[["oil_brent"]], exog], axis=1)
    ).select_order(4, trend="c")
    assert evidence["candidate_lags"] == [0, 1, 2, 3, 4]
    assert evidence["comparison_sample"]["nobs"] == 146
    assert evidence["comparison_sample"]["periods"] == list(map(str, frame.index[4:]))
    for criterion in ("aic", "bic", "hqic"):
        np.testing.assert_allclose(
            [row[criterion] for row in evidence["candidates"]],
            reference.ics[criterion],
            atol=1e-12,
            rtol=0,
        )
        assert evidence["selected_lags"][criterion] == reference.selected_orders[criterion]
    assert config == before and config["model"]["params"]["lags"] == 2


def test_extended_var_keeps_baseline_physical_shock_and_records_actual_sample():
    config = configuration()
    output = run_analysis(config, FIXTURE["source"]())["results"][0]
    assert output["status"] == "ok"
    assert output["diagnostics"]["variables"] == ["gdp_real", "cpi", "unemp", "policy_rate"]
    variants = {v["variant_id"]: v for v in output["sensitivity"]["variants"]}
    extended = variants["extended_var"]
    assert extended["status"] == "available"
    assert extended["diagnostics"]["selected_lags"] == 2
    assert extended["metrics"]["shock_size"] == output["irf"]["shock_size"]
    assert (
        extended["metrics"]["shock_normalization"]["basis"]
        == "baseline_one_sd_physical_size_held_fixed"
    )
    assert extended["config"]["identification"]["params"]["order"] == [
        "gdp_real",
        "cpi",
        "unemp",
        "reer",
        "credit_pnfs",
        "policy_rate",
    ]
    assert extended["sample"]["nobs"] == len(extended["sample"]["periods"])
    assert extended["sample"]["transforms"]["reer"]["transform"] == "log"
    assert output["sensitivity"]["lag_criteria"]["default_lags_unchanged"] == 2
    assert all(f"lag_{criterion}" in variants for criterion in ("aic", "bic", "hqic"))
    assert all(
        "diagnostics" in variants[f"lag_{criterion}"] for criterion in ("aic", "bic", "hqic")
    )


def test_missing_extended_input_is_visible_without_filling_or_replacing_baseline():
    bundle = FIXTURE["source"]()
    del bundle["countries"]["USA"]["series"]["credit_pnfs"]
    output = run_analysis(configuration(), bundle)["results"][0]
    assert output["status"] == "ok"
    extended = next(
        v for v in output["sensitivity"]["variants"] if v["variant_id"] == "extended_var"
    )
    assert extended["status"] == "blocked"
    assert any(c["level"] == "block" for c in extended["checks"])


def test_signed_peak_range_retains_negative_positive_and_full_precision():
    def variant(identifier, value):
        return {
            "variant_id": identifier,
            "status": "available",
            "informative_point_comparison": True,
            "metrics": {
                "responses": [
                    {
                        "variable": "gdp_real",
                        "peak_horizon": 1,
                        "peak_response": value,
                        "peak_absolute_response": abs(value),
                        "periods": [0, 1],
                        "values": [0, value],
                        "band_excludes_zero_at_peak": False,
                    }
                ]
            },
        }

    negative, positive = -0.400000000123, 0.300000000456
    summary = _response_summary([variant("baseline", negative), variant("alternative", positive)])[
        0
    ]
    assert summary["peak_response_range"] == [negative, positive]
    assert summary["peak_absolute_response_range"] == [positive, -negative]
    assert summary["sign_agreement_share"] == 0


def test_g31_sample_is_information_under_g4_precision_rule():
    config = configuration()
    rng = np.random.default_rng(20)
    names = [s["concept_id"] for s in config["series"]]
    frame = pd.DataFrame(rng.normal(size=(107, 5)), columns=names)
    fixed = pd.DataFrame(
        {f"covid_2020-Q{q}": (np.arange(107) == 80 + q).astype(float) for q in (1, 2, 3)}
    )
    checks = get_plugin("var.ols").check(AnalysisData(frame, exog=fixed), config)
    assert any(c["code"] == "small_sample" and c["level"] == "info" for c in checks)
    assert not any(c["level"] == "block" for c in checks)


def test_native_bundle_loader_includes_extended_inputs(monkeypatch: pytest.MonkeyPatch):
    from macrolab.analysis import engine

    config = configuration()
    seen = []
    monkeypatch.setattr(
        engine,
        "snapshot_bundle",
        lambda snapshot, countries, concepts: seen.extend(concepts) or FIXTURE["source"](),
    )
    assert run_analysis(config)["status"] == "ok"
    assert "reer" in seen and "credit_pnfs" in seen
