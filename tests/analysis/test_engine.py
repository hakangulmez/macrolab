"""End-to-end contracts, calendar accounting and country isolation."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from jsonschema import validate

from macrolab.analysis.engine import compatibility, run_analysis

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    random = np.random.default_rng(729)
    periods = [str(p).replace("Q", "-Q") for p in pd.period_range("1999Q1", periods=100, freq="Q")]
    x = random.normal(size=100)
    y = 1 + 2 * x + random.normal(size=100)
    bundle = {"snapshot_id": "synthetic", "countries": {}}
    for country in ["AAA", "BBB"]:
        bundle["countries"][country] = {"metadata": {"iso3": country}, "series": {}}
        for name, values in [("x", x), ("y", y)]:
            bundle["countries"][country]["series"][name] = {
                "metadata": {
                    "concept_id": name,
                    "frequency": "Q",
                    "status": "available",
                    "flags": [],
                    "warnings": [],
                    "first_date": periods[0],
                    "last_date": periods[-1],
                },
                "observations": list(zip(periods, values.tolist(), strict=True)),
            }
    config = {
        "schema_version": 1,
        "snapshot_id": "synthetic",
        "countries": ["AAA", "BBB"],
        "frequency": "Q",
        "series": [
            {"concept_id": "y", "role": "dependent", "transform": "level"},
            {"concept_id": "x", "role": "regressor", "transform": "level"},
        ],
        "model": {"id": "sing.ols", "params": {}},
        "sample": {"start": "1999-Q1", "end": "latest"},
    }
    return config, bundle


def test_result_schema_determinism_country_order_and_samples():
    config, bundle = inputs()
    first = run_analysis(config, bundle)
    validate(first, json.loads((ROOT / "schemas/model_result.schema.json").read_text()))
    assert first["status"] == "ok"
    repeated = run_analysis(config, bundle)
    assert first["results"] == repeated["results"]
    config["countries"].reverse()
    reversed_result = run_analysis(config, bundle)
    for original in first["results"]:
        other = next(r for r in reversed_result["results"] if r["country"] == original["country"])
        for key in ("coefficients_table", "actual_sample", "checks"):
            assert original[key] == other[key]
        assert original["sensitivity"]["summary"] == other["sensitivity"]["summary"]
    for result in first["results"]:
        assert result["actual_sample"]["nobs"] == 100
        assert result["actual_sample"]["frequency_conversion"]["x"]["method"] == "none"
        assert result["sensitivity"]["variants"]


def test_one_missing_country_blocks_only_that_country():
    config, bundle = inputs()
    bundle["countries"]["BBB"]["series"]["x"]["metadata"]["status"] = "missing"
    bundle["countries"]["BBB"]["series"]["x"]["observations"] = []
    result = run_analysis(config, bundle)
    assert result["status"] == "partial"
    assert [r["status"] for r in result["results"]] == ["ok", "blocked"]
    assert "coefficients_table" not in result["results"][1]


def test_compatibility_explains_unavailable_models():
    config, bundle = inputs()
    result = compatibility(config, bundle)
    assert len(result["models"]) == 25
    assert next(m for m in result["models"] if m["id"] == "sing.ols")["available"]
    unavailable = next(m for m in result["models"] if m["id"] == "ident.recursive")
    assert not unavailable["available"] and unavailable["checks"]


def test_var_lag_initialisation_is_in_sample_accounting():
    config, bundle = inputs()
    config["countries"] = ["AAA"]
    config["series"][0]["role"] = "endogenous"
    config["series"][1]["role"] = "shock"
    config["model"] = {"id": "var.ols", "params": {"lags": 2}}
    config["comparison"] = {"enabled": False}
    result = run_analysis(config, bundle)["results"][0]
    assert result["status"] == "ok"
    sample = result["actual_sample"]
    assert sample["nobs"] == 98 and sample["common_nobs"] == 100
    assert sample["start"] == "1999-Q3"
    assert sum(p.get("reason") == "model_initialisation" for p in sample["dropped_periods"]) == 2


def test_source_bundle_cannot_change_requested_vintage():
    import pytest

    config, bundle = inputs()
    bundle = deepcopy(bundle)
    bundle["snapshot_id"] = "different"
    with pytest.raises(ValueError, match="snapshot"):
        run_analysis(config, bundle)


def test_disjoint_cross_country_windows_block_with_no_claimed_estimation():
    config, bundle = inputs()
    config["model"] = {"id": "desc.compare", "params": {}}
    for series in bundle["countries"]["AAA"]["series"].values():
        series["observations"] = series["observations"][:30]
    for series in bundle["countries"]["BBB"]["series"].values():
        series["observations"] = series["observations"][60:]
    result = run_analysis(config, bundle)
    assert result["status"] == "blocked"
    for row in result["results"]:
        assert row["actual_sample"]["nobs"] == 0
        assert any(c["code"] == "missing_coverage" for c in row["checks"])
