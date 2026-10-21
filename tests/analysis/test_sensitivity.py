"""Sensitivity comparisons preserve estimands and expose unavailable alternatives."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
import pytest

from macrolab.analysis import sensitivity
from macrolab.models.base import AnalysisData, check
from macrolab.models.linear import OLSPlugin


def data_and_config(nobs: int = 120) -> tuple[AnalysisData, dict[str, Any]]:
    rng = np.random.default_rng(772)
    x = rng.normal(size=nobs)
    frame = pd.DataFrame(
        {"y": 1 + 1.5 * x + rng.normal(size=nobs), "x": x},
        index=pd.period_range("1980Q1", periods=nobs, freq="Q"),
    )
    cfg = {
        "series": [
            {"concept_id": "y", "role": "dependent"},
            {"concept_id": "x", "role": "regressor"},
        ],
        "model": {"id": "sing.ols", "params": {"covariance": "HAC", "hac_lags": 4}},
        "comparison": {"enabled": True, "methods": []},
        "sample": {"start": "1980-Q1", "end": "latest"},
        "seed": 91,
    }
    return AnalysisData(frame), cfg


def test_covariance_only_inference_not_counted_as_robust_point_estimates() -> None:
    data, cfg = data_and_config()
    data.sample = {
        "source_data_sha256": "f" * 64,
        "frequency_conversion": {"x": {"method": "mean"}},
        "transforms": {"x": {"transform": "level"}},
        "dropped_periods": [{"period": "1979Q4", "reasons": ["initial_transform"]}],
    }
    baseline = OLSPlugin().run(data, cfg)
    result = sensitivity.build_sensitivity(data, cfg, baseline)
    variants = {v["variant_id"]: v for v in result["variants"]}
    assert variants["covariance_HC1"]["status"] == "available"
    assert not variants["covariance_HC1"]["informative_point_comparison"]
    assert variants["recent_half"]["sample"]["nobs"] == 60
    assert variants["recent_half"]["sample"]["common_nobs"] == 60
    assert (
        variants["recent_half"]["sample"]["frequency_conversion"]
        == data.sample["frequency_conversion"]
    )
    assert len(variants["recent_half"]["sample"]["dropped_periods"]) == 61
    assert len(data.sample["dropped_periods"]) == 1
    assert (
        variants["covariance_HC1"]["prepared_inputs_sha256"]
        == variants["baseline"]["prepared_inputs_sha256"]
    )
    assert (
        variants["recent_half"]["prepared_inputs_sha256"]
        != variants["baseline"]["prepared_inputs_sha256"]
    )
    assert (
        variants["baseline"]["prepared_inputs_hash_basis"]
        == "portable_source_inputs_rules_and_selected_periods"
    )
    assert variants["recent_half"]["sample"]["periods"] == list(map(str, data.frame.index[60:]))
    summary = result["summary"][0]
    assert summary["term"] == "x" and summary["comparable_alternatives"] == 1
    assert summary["variant_ids"] == ["recent_half"]
    assert summary["sign_agreement_share"] == 1.0
    baseline_coefficient = baseline["coefficients_table"][1]
    hc_coefficient = variants["covariance_HC1"]["metrics"]["coefficients"][1]
    assert hc_coefficient["estimate"] == baseline_coefficient["estimate"]
    assert hc_coefficient["lower"] != baseline_coefficient["lower"]


def test_recent_half_adjusts_exog_and_blocks_short_alternative() -> None:
    data, cfg = data_and_config(70)
    data.exog = pd.DataFrame({"old_event": [1.0] + [0.0] * 69}, index=data.frame.index)
    before = data.exog.copy()
    result = sensitivity.build_sensitivity(data, cfg, OLSPlugin().run(data, cfg))
    recent = next(v for v in result["variants"] if v["variant_id"] == "recent_half")
    assert recent["status"] == "blocked"
    assert any(c["code"] == "small_sample" for c in recent["checks"])
    pd.testing.assert_frame_equal(data.exog, before)
    assert result["summary"][0]["sign_agreement_share"] is None


def test_requested_rolling_runs_and_incompatible_method_is_explicit() -> None:
    data, cfg = data_and_config()
    cfg["comparison"]["methods"] = ["sing.rolling", "filter.hp", "not.released"]
    result = sensitivity.build_sensitivity(data, cfg, OLSPlugin().run(data, cfg))
    variants = {v["variant_id"]: v for v in result["variants"]}
    assert variants["requested_sing.rolling"]["status"] == "available"
    assert variants["requested_sing.rolling"]["config"]["model"]["params"]["window"] == 40
    assert variants["requested_filter.hp"]["status"] == "unsupported"
    assert variants["requested_not.released"]["status"] == "unsupported"


def test_failed_alternative_remains_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    data, cfg = data_and_config()
    baseline = OLSPlugin().run(data, cfg)

    class FailingPlugin(OLSPlugin):
        def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("Synthetic fit failure")

    monkeypatch.setattr(sensitivity, "get_plugin", lambda _: FailingPlugin())
    result = sensitivity.build_sensitivity(data, cfg, baseline)
    assert result["variants"][0]["status"] == "available"
    assert all(
        v["status"] == "failed" and "Synthetic fit failure" in v["reason"]
        for v in result["variants"][1:]
    )
    assert result["summary"][0]["comparable_alternatives"] == 0


def test_portable_input_fingerprint_excludes_computed_filter_roundoff() -> None:
    data, _ = data_and_config()
    data.sample = {
        "source_data_sha256": "a" * 64,
        "preparation_config": {"frequency": "Q", "sample": {"end": "2009-Q4"}},
        "transforms": {
            "y": {
                "transform": "hp_cycle",
                "params": {"lamb": 1600},
                "trend": [100.1],
                "base_value": 40.2,
                "input_end": "2009-Q4",
            }
        },
    }
    original, basis = sensitivity._inputs_hash(data)
    assert basis == "portable_source_inputs_rules_and_selected_periods"
    changed = deepcopy(data)
    changed.frame += 3.6e-10
    changed.sample["transforms"]["y"]["trend"][0] += 3.6e-10
    changed.sample["transforms"]["y"]["base_value"] += 3.6e-10
    assert sensitivity._inputs_hash(changed)[0] == original
    changed.sample["transforms"]["y"]["params"]["lamb"] = 400
    assert sensitivity._inputs_hash(changed)[0] != original
    assert sensitivity._inputs_hash(sensitivity._recent(data))[0] != original
    direct, _ = data_and_config()
    direct_hash, direct_basis = sensitivity._inputs_hash(direct)
    assert direct_basis == "runtime_specific_direct_analysis_data_values"
    direct.frame += 3.6e-10
    assert sensitivity._inputs_hash(direct)[0] != direct_hash


@pytest.mark.parametrize(
    "model_id",
    [
        "desc.plot",
        "desc.corr",
        "desc.compare",
        "test.adf_kpss_pp",
        "test.granger",
        "filter.hp",
        "filter.hamilton",
        "var.ols",
    ],
)
def test_explicit_not_applicable_and_disable_status(model_id: str) -> None:
    data, cfg = data_and_config()
    cfg["model"]["id"] = model_id
    assert sensitivity.build_sensitivity(data, cfg, {})["status"] == "not_applicable"
    cfg["comparison"]["enabled"] = False
    assert sensitivity.build_sensitivity(data, cfg, {})["status"] == "disabled"


def test_var_sensitivity_keeps_physical_shock_bands_seed_and_visible_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data, _ = data_and_config()
    data.frame["rate"] = np.random.default_rng(55).normal(size=len(data.frame))
    cfg = {
        "series": [
            {"concept_id": "rate", "role": "shock"},
            {"concept_id": "y", "role": "response"},
            {"concept_id": "x", "role": "endogenous"},
        ],
        "model": {"id": "ident.recursive", "params": {"lags": 1}},
        "identification": {"id": "recursive", "params": {"order": ["y", "x", "rate"]}},
        "outputs": {
            "irf": {
                "horizon": 2,
                "bands": 0.68,
                "shock_size": 0.25,
                "draws": 500,
                "method": "bootstrap",
            }
        },
        "comparison": {"methods": []},
        "seed": 4401,
    }
    seen = []

    class FakeVAR:
        inputs: dict[str, Any] = {"min_series": 2, "max_series": 6}
        params: dict[str, Any] = {"properties": {"lags": {}, "lag_selection": {}}}

        def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
            return (
                [check("block", "small_sample", "Synthetic lag-four block")]
                if config["model"]["params"]["lags"] == 4
                else []
            )

        def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
            seen.append(deepcopy(config))
            names = config["identification"]["params"]["order"]
            mapping = {"rate": [0.25, 0.1, 0.02], "y": [0, -1, -0.5], "x": [0, 0.2, 0.1]}
            if names[0] == "rate":
                mapping["y"] = [0, 0.3, 0.2]
            matrix = np.column_stack([mapping[name] for name in names])
            return {
                "irf": {
                    "periods": [0, 1, 2],
                    "variables": names,
                    "values": matrix.tolist(),
                    "lower": (matrix - 0.1).tolist(),
                    "upper": (matrix + 0.1).tolist(),
                    "shock": "rate",
                    "shock_size": 0.25,
                    "band_level": 0.68,
                    "band_method": "bootstrap",
                },
                "diagnostics": {
                    "nobs": len(data.frame) - config["model"]["params"]["lags"],
                    "estimated_indices": list(
                        map(str, data.frame.index[config["model"]["params"]["lags"] :])
                    ),
                },
            }

    fake = FakeVAR()
    monkeypatch.setattr(sensitivity, "get_plugin", lambda _: fake)
    baseline = fake.run(data, cfg)
    original = deepcopy(cfg)
    result = sensitivity.build_sensitivity(data, cfg, baseline)
    assert cfg == original
    assert all(c["outputs"] == cfg["outputs"] and c["seed"] == 4401 for c in seen)
    assert all(
        next(s["concept_id"] for s in c["series"] if s["role"] == "shock") == "rate" for c in seen
    )
    blocked = next(v for v in result["variants"] if v["variant_id"] == "lags_4")
    assert blocked["status"] == "blocked"
    y = next(r for r in result["summary"] if r["variable"] == "y")
    assert y["sign_comparison_horizon"] == 1
    assert y["comparable_alternatives"] == 3
    assert y["sign_agreement_share"] == pytest.approx(2 / 3)
    assert y["peak_absolute_response_range"] == [0.3, 1.0]
