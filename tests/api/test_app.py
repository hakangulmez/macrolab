"""Exercise the real local transport with portable synthetic observations."""

from __future__ import annotations

import ast
import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from macrolab.analysis.config import validated_config
from macrolab.api.app import create_app
from macrolab.export.script import standalone


@pytest.fixture
def inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    config = {
        "schema_version": 1,
        "snapshot_id": "api-fixture",
        "countries": ["USA"],
        "series": [{"concept_id": "unemp", "role": "response", "transform": "level"}],
        "frequency": "Q",
        "sample": {"start": "2000-Q1", "end": "2004-Q4"},
        "model": {"id": "desc.plot", "params": {}},
    }
    bundle = {
        "schema_version": 1,
        "snapshot_id": "api-fixture",
        "as_of_date": "2026-10-21",
        "countries": {
            "USA": {
                "metadata": {"iso3": "USA"},
                "series": {
                    "unemp": {
                        "metadata": {
                            "status": "available",
                            "frequency": "Q",
                            "flags": [],
                            "warnings": [],
                        },
                        "observations": [
                            [f"{2000 + t // 4}-Q{t % 4 + 1}", 4 + (t % 5) * 0.2] for t in range(20)
                        ],
                    }
                },
            }
        },
    }
    return config, bundle


def test_real_api_result_and_python_download_preserve_requested_sample(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    config, bundle = inputs
    client = TestClient(create_app(bundle))
    response = client.post("/run", json=config)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok"
    assert result["actual_samples"]["USA"]["nobs"] == 20
    assert result["actual_samples"]["USA"]["start"] == "2000-Q1"
    assert result["actual_samples"]["USA"]["end"] == "2004-Q4"
    exported = client.post("/export/python", json=config)
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    ast.parse(exported.text)
    assert result["config_hash"] in exported.text
    assert "api-fixture" in exported.text
    assert "publication_approved" in exported.text


def test_configuration_roundtrip_uses_same_canonical_validator(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    config, bundle = inputs
    client = TestClient(create_app(bundle))
    encoded = client.post("/config/encode", json=config)
    assert encoded.status_code == 200
    token = encoded.json()["token"]
    assert token.startswith("v1.")
    decoded = client.post("/config/decode", json={"token": token})
    assert decoded.status_code == 200
    assert decoded.json() == validated_config(config)
    assert client.post("/config/decode", json={"token": "v1.not-a-valid-config"}).status_code == 422
    assert client.post("/config/decode", json={"token": token, "extra": True}).status_code == 422


def test_snapshot_errors_and_loopback_boundary_are_explicit(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    config, bundle = inputs
    client = TestClient(create_app(bundle))
    config["snapshot_id"] = "different-vintage"
    response = client.post("/run", json=config)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_analysis"
    assert client.get("/health", headers={"host": "untrusted.example"}).status_code == 400
    capabilities = client.get("/capabilities").json()
    assert capabilities["publication_approved"] is False
    assert capabilities["local_only"] is True
    models = client.get("/models").json()["models"]
    assert len(models) == 12
    assert all(model["references"] and model["assumptions"] for model in models)


def test_export_allows_numerical_rounding_but_rejects_changed_sample(
    inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    config, bundle = inputs
    namespace: dict[str, Any] = {"__name__": "inspect_export"}
    exec(compile(standalone(config, bundle), "export.py", "exec"), namespace)
    expected: dict[str, Any] = {
        "start": "2000-Q1",
        "nobs": 20,
        "source_data_sha256": "source-input-hash",
        "transforms": {"gdp_real": {"trend": [100.123456789]}},
    }
    rounded = copy.deepcopy(expected)
    rounded["transforms"]["gdp_real"]["trend"][0] += 1e-12
    assert namespace["same_sample"](expected, rounded)
    changed_value = copy.deepcopy(expected)
    changed_value["transforms"]["gdp_real"]["trend"][0] += 1e-5
    assert not namespace["same_sample"](expected, changed_value)
    for key, changed in (("start", "2000-Q2"), ("nobs", 19), ("source_data_sha256", "other")):
        changed_sample = {**expected, key: changed}
        assert not namespace["same_sample"](expected, changed_sample)
