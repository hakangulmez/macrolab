"""Fresh offline references, recovery summaries and accepted G3.1 preservation."""

from __future__ import annotations

import hashlib
import json
import math
import runpy
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from macrolab import __version__
from macrolab.analysis.config import canonical_json, validated_config
from macrolab.analysis.engine import run_analysis
from macrolab.models.registry import PLUGINS
from macrolab.models.var import validation_evidence as var_evidence

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/g4/model-validation.json"
BASELINE = ROOT / "runs/g31/after.json"
SNAPSHOT = "20261021-0025"
EXCLUDED_KEYS = {"checks", "code_version", "runtime_ms"}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported evidence value: {type(value).__name__}")


def save(payload: dict[str, Any]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".pending.json")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False, default=json_scalar) + "\n")
    temporary.replace(OUTPUT)


def source_fingerprints() -> dict[str, str]:
    paths = [
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
        ROOT / "configs/templates/monetary_policy.json",
        Path(__file__).resolve(),
        ROOT / "tests/reference/test_linear_models.py",
        ROOT / "tests/synthetic/test_linear_recovery.py",
    ]
    for directory in ("models", "analysis", "checks"):
        paths.extend((ROOT / "src/macrolab" / directory).glob("*.py"))
    return {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in sorted(paths)}


def numerical_payload(value: Any) -> Any:
    """Keep all substantive fields, including sample, bands and variant statuses."""
    if isinstance(value, dict):
        return {
            key: numerical_payload(item) for key, item in value.items() if key not in EXCLUDED_KEYS
        }
    if isinstance(value, list):
        return [numerical_payload(item) for item in value]
    return value


def preservation() -> dict[str, Any]:
    content = BASELINE.read_bytes()
    baseline = json.loads(content)
    config = json.loads((ROOT / "configs/templates/monetary_policy.json").read_text())
    if validated_config(config) != baseline["config"]:
        raise ValueError("The current monetary template differs from the accepted G3.1 config")
    if baseline["snapshot_id"] != SNAPSHOT:
        raise ValueError("The accepted G3.1 snapshot is not the required frozen snapshot")
    current = run_analysis(config)
    before, after = numerical_payload(baseline), numerical_payload(current)
    countries = []
    for old, new in zip(baseline["results"], current["results"], strict=True):
        old_statuses = [(v["variant_id"], v["status"]) for v in old["sensitivity"]["variants"]]
        new_statuses = [(v["variant_id"], v["status"]) for v in new["sensitivity"]["variants"]]
        countries.append(
            {
                "country": new["country"],
                "actual_sample": new["actual_sample"],
                "variant_statuses_preserved": old_statuses == new_statuses,
                "variant_statuses": new_statuses,
                "before_checks": old["checks"],
                "after_checks": new["checks"],
            }
        )
    return {
        "passed": before == after,
        "baseline": BASELINE.relative_to(ROOT).as_posix(),
        "baseline_file_sha256": digest(content),
        "snapshot_id": current["snapshot_id"],
        "config_hash": current["config_hash"],
        "numerical_payload_identical": before == after,
        "comparison": "Exact Python value equality; no numerical tolerance or rounding",
        "excluded_keys_at_all_depths": sorted(EXCLUDED_KEYS),
        "before_payload_sha256": digest(canonical_json(before).encode()),
        "after_payload_sha256": digest(canonical_json(after).encode()),
        "countries": countries,
    }


def main() -> None:
    started = time.perf_counter()
    sources = source_fingerprints()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "code_version": __version__,
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": sources,
        "execution": "Offline native Python; existing frozen snapshot; no data fetch",
    }
    save(report)
    try:
        linear = runpy.run_path(str(ROOT / "tests/reference/test_linear_models.py"))[
            "validation_evidence"
        ]()
        rows = json.loads(json.dumps(linear + var_evidence(), allow_nan=False, default=json_scalar))
        if len(rows) != 12 or {row["model_id"] for row in rows} != set(PLUGINS):
            raise ValueError("Validation evidence must cover every released model exactly once")
        for row in rows:
            difference, tolerance = row["reference_max_abs_difference"], row["reference_tolerance"]
            row["reference_passed"] = bool(math.isfinite(difference) and difference <= tolerance)
        recovery = {
            row["model_id"]: row["recovery"]
            for row in rows
            if row["recovery"].get("status") != "not_applicable"
        }
        report.update(
            {
                "models": rows,
                "recovery_test_summaries": recovery,
                "recovery_interpretation": "OLS and ARDL use 120 fixed-seed datasets each. "
                "VAR and recursive identification share one 40-dataset, 199-draw recovery "
                "experiment, reported for both interfaces; they are not independent replications.",
                "numerical_preservation": preservation(),
                "source_unchanged_during_run": sources == source_fingerprints(),
            }
        )
        report["summary"] = {
            "model_count": len(rows),
            "references_passed": sum(row["reference_passed"] for row in rows),
            "recovery_models": len(recovery),
            "recovery_models_passed": sum(row["passed"] is True for row in recovery.values()),
            "reference_max_abs_difference": max(
                row["reference_max_abs_difference"] for row in rows
            ),
            "numerical_preservation_passed": report["numerical_preservation"]["passed"],
        }
        passed = (
            all(row["reference_passed"] for row in rows)
            and all(row["passed"] is True for row in recovery.values())
            and report["numerical_preservation"]["passed"]
            and report["source_unchanged_during_run"]
        )
        report["status"] = "passed" if passed else "failed"
    except Exception as exc:
        report.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        report.update(
            completed_at=datetime.now(UTC).isoformat(),
            elapsed_ms=1000 * (time.perf_counter() - started),
        )
        save(report)
    print(json.dumps({"status": report["status"], **report["summary"]}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
