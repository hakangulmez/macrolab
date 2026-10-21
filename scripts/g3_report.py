"""Validate G3 browser evidence and screenshot/download hashes without a browser."""

from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCREENS = {"home", "builder", "library", "results", "catalogue", "methods"}
TEMPLATES = {"monetary_policy", "taylor_rule", "phillips_curve", "okuns_law"}


def validate(evidence: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    gate = evidence.get("gate", "g3")
    if gate not in {"g3", "g31", "g4"}:
        raise ValueError("Unsupported review gate")
    screenshot_dir = (
        "docs/screenshots"
        if gate == "g3"
        else f"docs/screenshots/{'g3_1' if gate == 'g31' else 'g4'}"
    )
    expected_views = {
        (screen, viewport) for screen in SCREENS for viewport in ("desktop", "mobile")
    }
    views = evidence.get("screens", [])
    actual_views = {(view.get("screen"), view.get("viewport")) for view in views}
    if actual_views != expected_views or len(views) != 12:
        errors.append("Exactly six desktop and six mobile screenshots/audits are required")
    for view in views:
        relative = view.get("screenshot", "")
        expected = f"{screenshot_dir}/{view.get('screen')}-{view.get('viewport')}.png"
        if relative != expected:
            errors.append(f"Unexpected screenshot path: {relative}")
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"Screenshot absent: {relative}")
            continue
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != view.get("screenshot_sha256"):
            errors.append(f"Screenshot changed after audit: {relative}")
        if content[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"Not a PNG screenshot: {relative}")
        elif len(content) >= 24:
            width, height = struct.unpack(">II", content[16:24])
            expected_width = 375 if view.get("viewport") == "mobile" else 1440
            if width != expected_width or height < 300:
                errors.append(f"Unexpected screenshot dimensions: {relative} ({width}x{height})")
        if view.get("serious_or_critical") != 0 or view.get("horizontal_overflow") is not False:
            errors.append(f"Accessibility or overflow gate failed: {relative}")
    templates = evidence.get("templates", [])
    successful = {
        item.get("id")
        for item in templates
        if item.get("worker_observed") is True
        and item.get("result_status") == "ok"
        and item.get("config_hash")
        and item.get("snapshot_id")
        and item.get("chart_count", 0) > 0
    }
    if not TEMPLATES <= successful:
        errors.append("All four real-worker templates must complete with chart evidence")
    exports = evidence.get("exports", [])
    if {item.get("control") for item in exports} != {"export-csv", "export-png", "export-python"}:
        errors.append("CSV, PNG and Python downloads are required")
    for export in exports:
        name = export.get("filename", "")
        if Path(name).name != name:
            errors.append("Download filename must not contain a path")
            continue
        path = root / "runs" / gate / "downloads" / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != export.get(
            "sha256"
        ):
            errors.append(f"Export missing or changed: {name}")
    required_flows = {
        "Explore links preserve country, indicator, category and euro area",
        "Computed warnings remain visible and comparison curves are selectable",
        "Share URL roundtrip recomputes identical configuration",
        "Keyboard home to template to run and export",
        "Cancellation and subsequent worker recovery",
        "Editing during calculation cancels the stale request",
    }
    if gate in {"g31", "g4"}:
        required_flows.add("G3.1 mobile summary, chart switching and sensitivity cards")
        required_flows.add("G3.1 precise bootstrap control recomputes the real result")
    if gate == "g4":
        required_flows.add("Fresh default preserves first-run disclosure in screenshots")
        required_flows.add(
            "G4 severity and newly disclosed checks preserve their technical evidence"
        )
    if not required_flows <= {
        item.get("name") for item in evidence.get("flows", []) if item.get("passed")
    }:
        errors.append(
            "Required navigation, warnings, comparison, share and lifecycle evidence is absent"
        )
    for field in ("external_requests", "failed_requests", "page_errors", "assertions"):
        if evidence.get(field):
            errors.append(f"Browser evidence contains failures: {field}")
    if evidence.get("passed") is not True:
        errors.append("The complete browser run did not pass")
    return {
        "schema_version": 1,
        "passed": not errors,
        "browser_version": evidence.get("browser_version"),
        "template_ids": sorted(TEMPLATES & successful),
        "screen_audits": len(views),
        "screenshots_hash_verified": len(views) if not errors else None,
        "serious_or_critical_violations": sum(view.get("serious_or_critical", 0) for view in views),
        "all_axe_violations": sum(len(view.get("violations", [])) for view in views),
        "downloads": len(exports),
        "external_requests": len(evidence.get("external_requests", [])),
        "elapsed_ms": evidence.get("elapsed_ms"),
        "limitations": [
            "Automated axe and keyboard checks are not a complete WCAG conformance audit."
        ],
        "errors": errors,
    }


if __name__ == "__main__":
    gate = os.environ.get("MACROLAB_REVIEW_GATE", "g4")
    if gate not in {"g3", "g31", "g4"}:
        raise ValueError("Unsupported review gate")
    output = ROOT / "runs" / gate
    evidence = json.loads((output / "e2e.json").read_text())
    summary = validate(evidence)
    (output / "qa_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["passed"] else 1)
