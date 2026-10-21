"""Seeded recovery and invariance tests for recursive VAR scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
import pytest

from macrolab.models.base import AnalysisData
from macrolab.models.var import VAROLSPlugin, synthetic_recovery


def example() -> tuple[AnalysisData, dict[str, Any]]:
    generator = np.random.default_rng(6041)
    transition = np.array([[0.45, 0.18], [-0.08, 0.3]])
    impact = np.array([[0.7, 0.0], [0.2, 0.4]])
    values = np.zeros((320, 2))
    for t in range(1, len(values)):
        values[t] = transition @ values[t - 1] + impact @ generator.normal(size=2)
    data = AnalysisData(
        frame=pd.DataFrame(values[120:], columns=["activity", "rate"], index=pd.RangeIndex(200))
    )
    config: dict[str, Any] = {
        "seed": 10421,
        "series": [
            {"concept_id": "activity", "role": "endogenous"},
            {"concept_id": "rate", "role": "shock"},
        ],
        "model": {"id": "var.ols", "params": {"lags": 1, "trend": "c"}},
        "identification": {"id": "recursive", "params": {"order": ["activity", "rate"]}},
        "outputs": {
            "irf": {
                "horizon": 6,
                "bands": 0.68,
                "shock_size": 1.0,
                "method": "bootstrap",
                "draws": 80,
            }
        },
    }
    return data, config


def test_fixed_seed_monte_carlo_reports_untuned_coverage_and_dgp_recovery() -> None:
    report = synthetic_recovery(replications=40, draws=199)
    assert report["passed"] is True
    assert report["replications"] == 40
    assert report["nominal_coverage"] == 0.68
    assert 0 <= report["coverage"] <= 1
    assert report["large_sample_coefficient_max_abs_error"] < 0.06
    assert len(report["coverage_by_horizon_variable"]) == 4


def test_bootstrap_is_repeatable_with_fixed_seed_and_changes_with_new_seed() -> None:
    data, config = example()
    first = VAROLSPlugin().run(data, config)
    second = VAROLSPlugin().run(data, config)
    np.testing.assert_array_equal(first["irf"]["lower"], second["irf"]["lower"])
    config["seed"] += 1
    third = VAROLSPlugin().run(data, config)
    assert not np.array_equal(first["irf"]["lower"], third["irf"]["lower"])
    np.testing.assert_array_equal(first["irf"]["values"], third["irf"]["values"])


def test_bootstrap_requires_an_explicit_seed() -> None:
    data, config = example()
    del config["seed"]
    with pytest.raises(ValueError, match="seed"):
        VAROLSPlugin().run(data, config)


def test_bootstrap_normalizes_every_draw_and_signed_shock_rescales_bands() -> None:
    data, config = example()
    positive = VAROLSPlugin().run(data, config)
    config["outputs"]["irf"]["shock_size"] = -0.5
    negative = VAROLSPlugin().run(data, config)
    np.testing.assert_allclose(
        negative["irf"]["values"], -0.5 * np.asarray(positive["irf"]["values"]), atol=1e-12
    )
    np.testing.assert_allclose(
        negative["irf"]["lower"], -0.5 * np.asarray(positive["irf"]["upper"]), atol=1e-12
    )
    np.testing.assert_allclose(
        negative["irf"]["upper"], -0.5 * np.asarray(positive["irf"]["lower"]), atol=1e-12
    )
    for key in ("values", "lower", "upper"):
        assert negative["irf"][key][0][1] == pytest.approx(-0.5, abs=1e-12)


def test_column_and_series_listing_order_cannot_override_explicit_identification_order() -> None:
    data, config = example()
    original = VAROLSPlugin().run(data, config)
    reordered = AnalysisData(frame=data.frame[["rate", "activity"]])
    config["series"] = list(reversed(config["series"]))
    result = VAROLSPlugin().run(reordered, config)
    np.testing.assert_array_equal(original["irf"]["values"], result["irf"]["values"])
    np.testing.assert_array_equal(original["irf"]["lower"], result["irf"]["lower"])


def test_variable_renaming_changes_labels_but_not_estimates_or_seeded_bands() -> None:
    data, config = example()
    original = VAROLSPlugin().run(data, config)
    rename = {"activity": "x", "rate": "z"}
    renamed = AnalysisData(frame=data.frame.rename(columns=rename))
    changed = deepcopy(config)
    for series in changed["series"]:
        series["concept_id"] = rename[series["concept_id"]]
    changed["identification"]["params"]["order"] = ["x", "z"]
    result = VAROLSPlugin().run(renamed, changed)
    for key in ("values", "lower", "upper"):
        np.testing.assert_array_equal(original["irf"][key], result["irf"][key])
    assert result["irf"]["variables"] == ["x", "z"]
    assert result["irf"]["shock"] == "z"


def test_changing_identification_order_changes_contemporaneous_restrictions() -> None:
    data, config = example()
    original = VAROLSPlugin().run(data, config)
    config["identification"]["params"]["order"] = ["rate", "activity"]
    changed = VAROLSPlugin().run(data, config)
    assert original["irf"]["values"][0][0] == 0
    assert abs(changed["irf"]["values"][0][1]) > 0.05
