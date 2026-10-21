"""Generate shareable G0 verification metadata without copying raw data."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from g0_check import CHECKS, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def command(*args: str) -> str:
    """Read local tool/version/repository metadata, without invoking a shell."""
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def source_verification() -> dict[str, Any]:
    """Read back every stored response and verify recorded checksum and size."""
    source_config = read_json("configs/source_probes.json")
    evidence = read_json("docs/probe_evidence.json")
    expected = {probe["id"] for probe in source_config["probes"]}
    actual = {probe["id"] for probe in evidence["probes"]}
    if expected != actual or len(actual) != len(evidence["probes"]):
        raise SystemExit("Missing or duplicate source probe evidence")
    for probe in evidence["probes"]:
        if probe["status"] not in {"unavailable", "verified_observations"}:
            raise SystemExit("Unresolved source probe status")
        if probe["status"] == "verified_observations":
            if not probe["fetch"]["body_complete"] or probe["parsed"]["observation_count"] <= 0:
                raise SystemExit("A source was marked verified without complete observations")
        elif not probe.get("error"):
            raise SystemExit("An unavailable source requires an explicit reason")
    records = [
        json.loads(line)
        for line in (ROOT / "data/manifests/raw_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]
    verified_files = 0
    for record in records:
        if record["raw_path"] is None:
            continue
        path = (ROOT / record["raw_path"]).resolve()
        if not path.is_relative_to(ROOT / "data/raw"):
            raise SystemExit("Raw manifest path escapes its data directory")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise SystemExit(f"Raw snapshot checksum mismatch: {record['raw_path']}")
        if len(body) != record["size_bytes"] or not record["body_complete"]:
            raise SystemExit(f"Raw snapshot size/completeness mismatch: {record['raw_path']}")
        verified_files += 1
    return {
        "snapshot_id": evidence["snapshot_id"],
        "provider_count": len({probe["provider"] for probe in evidence["probes"]}),
        "probe_count": len(actual),
        "verified_probes": sum(
            probe["status"] == "verified_observations" for probe in evidence["probes"]
        ),
        "statuses": {probe["id"]: probe["status"] for probe in evidence["probes"]},
        "manifest_records": len(records),
        "raw_file_hashes_verified": verified_files,
    }


def main() -> None:
    checks = read_json("runs/checks/commands.json")
    if (
        not checks["all_passed"]
        or checks.get("status") != "complete"
        or [row["command"] for row in checks["checks"]] != [f"make {target}" for target in CHECKS]
        or any(row["exit_code"] for row in checks["checks"])
        or checks.get("source_fingerprint") != source_fingerprint()
    ):
        raise SystemExit("G0 checks incomplete or stale; rerun scripts/g0_check.py")
    tree = ET.parse(ROOT / "runs/checks/pytest.xml")
    suites = list(tree.getroot().iter("testsuite"))
    python_tests = {
        name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    web_result = read_json("runs/checks/vitest.json")
    smoke = read_json("runs/quick/summary.json")
    if (
        python_tests["tests"] <= python_tests["skipped"]
        or python_tests["failures"]
        or python_tests["errors"]
        or web_result.get("numPassedTests", 0) <= 0
        or web_result.get("numFailedTests") != 0
        or not web_result.get("success")
        or smoke.get("status") != "passed"
        or smoke.get("synthetic") is not True
        or smoke["elapsed_seconds"] >= 120
    ):
        raise SystemExit("G0 test/smoke evidence is empty, failed or outside its time budget")
    started = datetime.fromisoformat(checks["started_utc"]).timestamp()
    for report_path in (
        "runs/checks/pytest.xml",
        "runs/checks/vitest.json",
        "runs/quick/summary.json",
    ):
        if (ROOT / report_path).stat().st_mtime < started:
            raise SystemExit(f"Stale check report: {report_path}")
    ignored = ["data/raw/probe.json", "data/processed/probe.parquet", "runs/quick/summary.json"]
    tracked = command("git", "ls-files").splitlines()
    forbidden = [name for name in tracked if name.startswith(("data/", "runs/", ".cache/"))]
    python_lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    python_urls = []
    for package in python_lock["package"]:
        if "registry" in package["source"]:
            python_urls.append(package["source"]["registry"])
        python_urls.extend(wheel["url"] for wheel in package.get("wheels", []))
        if "url" in package.get("sdist", {}):
            python_urls.append(package["sdist"]["url"])
    npm_lock = read_json("web/package-lock.json")
    npm_urls = [item["resolved"] for item in npm_lock["packages"].values() if "resolved" in item]
    registry_hosts = sorted({urlparse(url).hostname for url in python_urls + npm_urls})
    if not set(registry_hosts) <= {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}:
        raise SystemExit("Unexpected dependency registry host")
    payload = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "gate": "G0",
        "scope": "Scaffold and example source probes only",
        "versions": {
            "python": platform.python_version(),
            "node": command("node", "--version"),
            "npm": command("npm", "--version"),
            "git": command("git", "--version"),
            "python_packages": {
                name: version(name) for name in ("PyYAML", "openpyxl", "pytest", "ruff", "mypy")
            },
        },
        "checks": checks,
        "source_verification": source_verification(),
        "dependency_registry_hosts": registry_hosts,
        "node_engine": read_json("web/package.json")["engines"]["node"],
        "synthetic_smoke": smoke,
        "python_tests": python_tests,
        "web_tests": {
            key: web_result.get(key)
            for key in ("numTotalTests", "numPassedTests", "numFailedTests", "numPendingTests")
        },
        "git_root": command("git", "rev-parse", "--show-toplevel"),
        "git_remotes": command("git", "remote").splitlines(),
        "ignored_paths": command("git", "check-ignore", *ignored).splitlines(),
        "forbidden_tracked_paths": forbidden,
        "ui_gate": False,
        "screenshots_required": False,
    }
    if not checks["all_passed"] or forbidden or payload["git_remotes"]:
        raise SystemExit(
            "G0 verification incomplete: inspect command evidence and repository scope"
        )
    if len(payload["ignored_paths"]) != len(ignored):
        raise SystemExit("Data/results ignore rules failed")
    destination = ROOT / "docs" / "G0_VERIFICATION.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
