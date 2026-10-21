"""Portable browser cases plus API/export transport verification for all v0 models."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from macrolab.analysis.config import MODEL_IDS, required_concepts
from macrolab.analysis.data import snapshot_bundle
from macrolab.analysis.engine import run_analysis
from macrolab.api.app import create_app
from macrolab.export.script import DEPENDENCIES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/g2"


def cases() -> dict[str, Any]:
    """Fixture values are generated once natively and transported unchanged to both runtimes."""
    generator = np.random.default_rng(19021)
    coefficients = np.array([[0.45, 0.08, 0.0], [0.05, 0.35, -0.1], [0.0, 0.1, 0.3]])
    impact = np.array([[0.6, 0.0, 0.0], [0.12, 0.4, 0.0], [0.08, 0.07, 0.25]])
    values = np.zeros((260, 3))
    for t in range(1, len(values)):
        values[t] = coefficients @ values[t - 1] + impact @ generator.normal(size=3)
    values = values[100:]
    periods = [f"{p.year}-Q{p.quarter}" for p in pd.period_range("1986Q1", periods=160, freq="Q")]
    concepts = ("output", "prices", "rate")
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": "g2-synthetic-19021",
        "as_of_date": "2026-10-21",
        "countries": {},
    }
    for country, multiplier in (("SYN", 1.0), ("SYB", 1.2)):
        bundle["countries"][country] = {
            "metadata": {
                "iso3": country,
                "name": "Synthetic validation fixture",
                "euro_adoption": None,
            },
            "series": {
                cid: {
                    "metadata": {
                        "concept_id": cid,
                        "status": "available",
                        "frequency": "Q",
                        "unit": "synthetic units",
                        "sa_flag": "SA",
                        "flags": [],
                        "warnings": [],
                        "reason_codes": [],
                        "source_segments": [],
                        "stale": False,
                        "first_date": periods[0],
                        "last_date": periods[-1],
                    },
                    "observations": [
                        [period, float(values[i, j] * multiplier)]
                        for i, period in enumerate(periods)
                    ],
                }
                for j, cid in enumerate(concepts)
            },
        }
    tests: list[dict[str, Any]] = []
    for model_id in MODEL_IDS:
        roles = ["dependent", "regressor"]
        selected = list(concepts[:2])
        params: dict[str, Any] = {}
        if model_id in {"var.ols", "ident.recursive"}:
            roles, selected = ["endogenous", "response", "shock"], list(concepts)
            params = {"lags": 2, "trend": "c", "lag_selection": "fixed"}
        elif model_id == "test.adf_kpss_pp":
            params = {"adf_lags": 3, "kpss_lags": 3, "pp_lags": 3, "trend": "c"}
        elif model_id in {"sing.ols", "sing.ardl", "sing.rolling"}:
            params = {"covariance": "HAC", "hac_lags": 3, "confidence": 0.95}
            if model_id == "sing.ardl":
                params |= {"lags": 2, "order": 2}
            if model_id == "sing.rolling":
                params |= {"window": 40, "mode": "rolling"}
        elif model_id == "test.granger":
            params = {"lags": 3}
        elif model_id == "desc.corr":
            params = {"window": 20}
        config: dict[str, Any] = {
            "schema_version": 1,
            "snapshot_id": bundle["snapshot_id"],
            "countries": ["SYN", "SYB"] if model_id == "desc.compare" else ["SYN"],
            "series": [
                {"concept_id": cid, "role": role, "transform": "level"}
                for cid, role in zip(selected, roles, strict=True)
            ],
            "frequency": "Q",
            "sample": {"start": "1986-Q1", "end": "2025-Q4"},
            "model": {"id": model_id, "params": params},
            "seed": 109,
        }
        if model_id in {"var.ols", "ident.recursive"}:
            config["identification"] = {"id": "recursive", "params": {"order": selected}}
            config["outputs"] = {
                "irf": {
                    "horizon": 8,
                    "bands": 0.68,
                    "shock_size": 1.0,
                    "method": "asymptotic",
                    "draws": 20,
                }
            }
        tests.append({"id": model_id, "config": config, "tolerance": 1e-8, "kind": "synthetic"})
    bootstrap = copy.deepcopy(next(item for item in tests if item["id"] == "var.ols"))
    bootstrap["id"] = "var.ols.bootstrap"
    bootstrap["config"]["outputs"]["irf"]["method"] = "bootstrap"
    tests.append(bootstrap)
    for name in ("monetary_policy", "taylor_rule", "phillips_curve", "okuns_law"):
        config = json.loads((ROOT / f"configs/templates/{name}.json").read_text())
        native = snapshot_bundle(
            config["snapshot_id"],
            config["countries"],
            required_concepts(config),
        )
        tests.append(
            {
                "id": f"template.{name}",
                "config": config,
                "bundle": native,
                "tolerance": 1e-8,
                "kind": "real_template",
            }
        )
    return {
        "schema_version": 1,
        "description": "Seed19021 stable three-variable VAR; 160 quarterly observations, "
        "two synthetic countries; all twelve v0 models plus seeded bootstrap. "
        "Four canonical templates use the accepted local snapshot unchanged.",
        "bundle": bundle,
        "cases": tests,
        "native_versions": {
            "python": platform.python_version(),
            **{name: version(name) for name in DEPENDENCIES},
        },
    }


def difference(expected: Any, actual: Any, path: str = "$") -> float:
    """Compare every result field, ignoring only measured execution time and export metadata."""
    if type(expected) in (int, float) and type(actual) in (int, float):
        return float(abs(expected - actual))
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = set(expected) - {"runtime_ms", "export_metadata"}
        if keys != set(actual) - {"runtime_ms", "export_metadata"}:
            raise AssertionError(f"Different result fields at {path}")
        return max((difference(expected[k], actual[k], f"{path}.{k}") for k in keys), default=0.0)
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            raise AssertionError(f"Different result lengths at {path}")
        return max(
            (
                difference(a, b, f"{path}[{i}]")
                for i, (a, b) in enumerate(zip(expected, actual, strict=True))
            ),
            default=0.0,
        )
    if expected != actual:
        raise AssertionError(f"Different result at {path}: {expected!r} != {actual!r}")
    return 0.0


def verify_exports(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    isolated = OUTPUT / "standalone_reproduction"
    isolated.mkdir(parents=True, exist_ok=True)
    evidence = []
    for item in fixture["cases"]:
        config, bundle = item["config"], item.get("bundle", fixture["bundle"])
        expected = run_analysis(config, bundle=bundle)
        if expected["status"] != "ok":
            raise AssertionError(f"Blocked parity fixture {item['id']}: {expected['checks']}")
        client = TestClient(create_app(bundle=bundle))
        response = client.post("/run", json=config)
        if response.status_code != 200:
            raise AssertionError(response.text)
        api_difference = difference(expected, response.json())
        script = isolated / f"{item['id']}.py"
        exported = client.post("/export/python", json=config)
        if exported.status_code != 200 or "attachment" not in exported.headers.get(
            "content-disposition", ""
        ):
            raise AssertionError(f"Python export endpoint failed: {exported.text}")
        script.write_text(exported.text)
        environment = {**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")}
        environment.pop("PYTHONPATH", None)
        # The subprocess has no project imports and cannot connect to a network.
        runner = (
            "import runpy, socket, sys; "
            "socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw("
            "RuntimeError('Network forbidden during reproduction')); "
            "runpy.run_path(sys.argv[1], run_name='__main__')"
        )
        process = subprocess.run(
            [sys.executable, "-I", "-c", runner, str(script)],
            cwd=isolated,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
        actual = json.loads(process.stdout)
        export_difference = difference(expected, actual)
        evidence.append(
            {
                "id": item["id"],
                "model_id": config["model"]["id"],
                "api_max_abs_difference": api_difference,
                "export_max_abs_difference": export_difference,
                "config_hash": expected["config_hash"],
                "actual_samples": expected["actual_samples"],
                "source_archive_sha256": actual["export_metadata"]["source_archive_sha256"],
                "passed": api_difference <= 1e-8 and export_difference <= 1e-8,
            }
        )
        print(f"Verified API and standalone export: {item['id']}", flush=True)
    client = TestClient(create_app(bundle=fixture["bundle"]))
    invalid = copy.deepcopy(fixture["cases"][0]["config"])
    invalid["model"]["id"] = "future.unreleased"
    if client.post("/run", json=invalid).status_code != 422:
        raise AssertionError("Invalid analysis did not return explicit422")
    if client.get("/health", headers={"host": "untrusted.example"}).status_code != 400:
        raise AssertionError("Nonlocal Host header was not rejected")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-exports", action="store_true")
    options = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fixture = cases()
    (OUTPUT / "browser_fixture.json").write_text(json.dumps(fixture, allow_nan=False) + "\n")
    print(f"Wrote {len(fixture['cases'])} portable runtime cases", flush=True)
    if options.verify_exports:
        evidence = verify_exports(fixture)
        (OUTPUT / "export_parity.json").write_text(
            json.dumps(
                {
                    "cases": evidence,
                    "native_versions": fixture["native_versions"],
                    "isolated_execution": True,
                    "network_connections_forbidden": True,
                    "passed": all(item["passed"] for item in evidence),
                },
                indent=2,
            )
            + "\n"
        )
