"""Read back G1 outputs and checks; write shareable metadata without observations."""

from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml
from g0_check import CHECKS, source_fingerprint

from macrolab.data.pipeline import processing_inputs
from macrolab.data.snapshot import sha256_file, verify_raw_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    checks = json.loads((ROOT / "runs/g1/checks/commands.json").read_text())
    if not (
        checks["all_passed"]
        and checks["status"] == "complete"
        and checks["source_fingerprint"] == source_fingerprint()
        and [item["command"] for item in checks["checks"]] == [f"make {name}" for name in CHECKS]
        and all(item["exit_code"] == 0 for item in checks["checks"])
    ):
        raise SystemExit("G1 command evidence is incomplete or stale")
    directory = ROOT / "data/processed/current"
    manifest = json.loads((directory / "processed_manifest.json").read_text())
    catalogue = yaml.safe_load((ROOT / "configs/indicators.yaml").read_text())
    if processing_inputs(ROOT, catalogue["concepts"]) != manifest["processing_inputs"]:
        raise SystemExit("Processed snapshot predates current processing inputs")
    if not manifest.get("validation_passed") or not manifest["audit_summary"]["passed"]:
        raise SystemExit("Data audit or validation did not pass")
    replay = manifest.get("replay_comparison", {})
    offline_guard = json.loads((ROOT / "runs/g1/offline_guard.json").read_text())
    if (
        offline_guard.get("processed_destination") != manifest["destination"]
        or offline_guard.get("http_attempts") != 0
        or not offline_guard.get("raw_manifest_unchanged")
    ):
        raise SystemExit("Offline network-blocking proof is missing or stale")
    if not (
        manifest["offline_rebuild"]
        and replay.get("same_processing_inputs")
        and replay.get("observations_match")
        and replay.get("coverage_match")
    ):
        raise SystemExit("An exact offline rebuild with unchanged inputs is required")
    verified_files = 0
    for name, expected in manifest["files"].items():
        path = directory / name
        if sha256_file(path) != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise SystemExit(f"Processed file verification failed: {name}")
        verified_files += 1
    raw = verify_raw_manifest(ROOT, manifest["snapshot_id"])
    cards = json.loads((directory / "series_cards.json").read_text())
    countries = json.loads((directory / "countries.json").read_text())
    if len(cards) != len(countries) * len(catalogue["concepts"]):
        raise SystemExit("Incomplete country by concept coverage matrix")
    for card in cards:
        for segment in card["source_segments"]:
            if not segment["attribution"] or not segment["source_url"]:
                raise SystemExit("Missing per-series attribution")
            if segment["source"] in {"WorldBank", "IMF"} and segment["terms_status"] != (
                "unresolved – no redistribution of raw data"
            ):
                raise SystemExit("Incorrect unresolved terms status")
    validation = json.loads((directory / "validation.json").read_text())
    if validation["duplicates"] or validation["interpolated_observations"]:
        raise SystemExit("Duplicate or interpolated observations")
    suites = list(ET.parse(ROOT / "runs/checks/pytest.xml").getroot().iter("testsuite"))
    python_tests = {
        key: sum(int(s.attrib.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    web = json.loads((ROOT / "runs/checks/vitest.json").read_text())
    quick = json.loads((ROOT / "runs/quick/summary.json").read_text())
    if (
        python_tests["failures"]
        or python_tests["errors"]
        or not python_tests["tests"]
        or not web["success"]
        or web["numFailedTests"]
        or quick["status"] != "passed"
        or not quick["synthetic"]
        or quick["elapsed_seconds"] >= 120
    ):
        raise SystemExit("Checks failed or quick exceeded its time budget")
    started = datetime.fromisoformat(checks["started_utc"]).timestamp()
    for report in ("runs/checks/pytest.xml", "runs/checks/vitest.json", "runs/quick/summary.json"):
        if (ROOT / report).stat().st_mtime < started:
            raise SystemExit(f"Stale check evidence: {report}")
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    forbidden = [p for p in tracked if p.startswith(("data/", "runs/", ".cache/"))]
    remotes = subprocess.check_output(["git", "remote"], cwd=ROOT, text=True).splitlines()
    if forbidden or remotes:
        raise SystemExit("Repository scope guardrail failed")
    records = [
        json.loads(line)
        for line in (ROOT / "data/manifests/raw_manifest.jsonl").read_text().splitlines()
    ]
    records = [r for r in records if r["snapshot_id"] == manifest["snapshot_id"]]
    if any(r["source"].upper() == "FRED" for r in records):
        raise SystemExit("FRED must remain unavailable and unused")
    payload = {
        "gate": "G1",
        "generated_utc": datetime.now(UTC).isoformat(),
        "snapshot_id": manifest["snapshot_id"],
        "as_of_date": manifest["as_of_date"],
        "processing_inputs": manifest["processing_inputs"],
        "checks": checks,
        "python_tests": python_tests,
        "web_tests": {
            key: web[key] for key in ("numTotalTests", "numPassedTests", "numFailedTests")
        },
        "quick": quick,
        "observations": manifest["observations"],
        "countries": len(countries),
        "national_concepts": manifest["national_concepts"],
        "global_factors": manifest["global_factors"],
        "coverage": manifest["coverage_summary"],
        "audit": manifest["audit_summary"],
        "offline_replay": replay,
        "offline_network_guard": offline_guard,
        "raw_verification": raw,
        "processed_files_verified": verified_files,
        "raw_requests_by_source": dict(Counter(r["source"] for r in records)),
        "failed_requests": [
            {key: r[key] for key in ("source", "probe_id", "status", "error")}
            for r in records
            if r["status"] != 200
        ],
        "validation": {
            "duplicates": len(validation["duplicates"]),
            "series_with_gaps": len(validation["gaps"]),
            "outlier_flags": len(validation["outlier_flags"]),
            "interpolated_observations": validation["interpolated_observations"],
        },
        "stale_cells": [
            {key: c[key] for key in ("country", "concept_id", "last_date")}
            for c in cards
            if c["stale"]
        ],
        "git_remotes": remotes,
        "forbidden_tracked_paths": forbidden,
        "publication_approved": False,
        "ui_gate": False,
        "screenshots_required": False,
    }
    (ROOT / "docs/process/G1_VERIFICATION.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: payload[key]
                for key in ("snapshot_id", "python_tests", "web_tests", "audit", "validation")
            }
        )
    )


if __name__ == "__main__":
    main()
