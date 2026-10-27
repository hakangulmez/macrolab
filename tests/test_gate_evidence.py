"""Regression checks for stale or failed gate evidence, using local fixtures only."""

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture
def evidence_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, ModuleType, Path]:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    modules = []
    for name in ("g0_check", "g0_evidence"):
        spec = importlib.util.spec_from_file_location(name, scripts / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "ROOT", tmp_path)
        modules.append(module)
    checks, evidence = modules
    for directory in ("web", "docs/process", "runs/checks", "runs/quick"):
        (tmp_path / directory).mkdir(parents=True)
    for filename in ("Makefile", "pyproject.toml", ".python-version"):
        (tmp_path / filename).write_text("fixture\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("package = []\n", encoding="utf-8")
    (tmp_path / "web/package-lock.json").write_text('{"packages": {}}', encoding="utf-8")
    (tmp_path / "web/package.json").write_text('{"engines": {"node": "fixture"}}', encoding="utf-8")
    commands = {
        "all_passed": True,
        "status": "complete",
        "source_fingerprint": checks.source_fingerprint(),
        "started_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
        "checks": [{"command": f"make {target}", "exit_code": 0} for target in checks.CHECKS],
    }
    (tmp_path / "runs/checks/commands.json").write_text(json.dumps(commands), encoding="utf-8")
    (tmp_path / "runs/checks/pytest.xml").write_text(
        '<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>',
        encoding="utf-8",
    )
    (tmp_path / "runs/checks/vitest.json").write_text(
        json.dumps({"numPassedTests": 2, "numFailedTests": 0, "success": True}), encoding="utf-8"
    )
    (tmp_path / "runs/quick/summary.json").write_text(
        json.dumps({"status": "passed", "synthetic": True, "elapsed_seconds": 0.1}),
        encoding="utf-8",
    )

    def local_command(*args: str) -> str:
        if args == ("git", "ls-files"):
            return "README.md"
        if args == ("git", "remote"):
            return ""
        if args == ("git", "rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args[:2] == ("git", "check-ignore"):
            return "\n".join(args[2:])
        if len(args) == 2 and args[1] == "--version":
            return "fixture-version"
        raise AssertionError(f"Unexpected external command: {args}")

    monkeypatch.setattr(evidence, "command", local_command)
    monkeypatch.setattr(evidence, "version", lambda name: "fixture-version")
    monkeypatch.setattr(evidence, "source_verification", lambda: {"fixture": True})
    return checks, evidence, tmp_path


def test_current_successful_evidence_can_be_emitted(
    evidence_state: tuple[ModuleType, ModuleType, Path],
) -> None:
    _, evidence, root = evidence_state
    evidence.main()
    output = json.loads((root / "docs/process/G0_VERIFICATION.json").read_text())
    assert output["checks"]["status"] == "complete"
    assert output["python_tests"]["failures"] == 0


@pytest.mark.parametrize("scenario", ["in_progress", "source_changed", "old_report"])
def test_stale_or_in_progress_checks_cannot_emit_verification(
    evidence_state: tuple[ModuleType, ModuleType, Path], scenario: str
) -> None:
    _, evidence, root = evidence_state
    report = root / "runs/checks/commands.json"
    commands = json.loads(report.read_text())
    if scenario == "in_progress":
        commands.update({"status": "in_progress", "all_passed": False})
        report.write_text(json.dumps(commands), encoding="utf-8")
    elif scenario == "source_changed":
        (root / "Makefile").write_text("changed after checks\n", encoding="utf-8")
    else:
        old = datetime.fromisoformat(commands["started_utc"]).timestamp() - 1
        os.utime(root / "runs/checks/pytest.xml", (old, old))
    with pytest.raises(SystemExit, match="[Ss]tale|incomplete"):
        evidence.main()
    assert not (root / "docs/process/G0_VERIFICATION.json").exists()


@pytest.mark.parametrize("failed_suite", ["python", "web"])
def test_failed_reports_override_previous_successful_commands(
    evidence_state: tuple[ModuleType, ModuleType, Path], failed_suite: str
) -> None:
    _, evidence, root = evidence_state
    if failed_suite == "python":
        (root / "runs/checks/pytest.xml").write_text(
            '<testsuites><testsuite tests="2" failures="1" errors="0" skipped="0"/></testsuites>',
            encoding="utf-8",
        )
    else:
        (root / "runs/checks/vitest.json").write_text(
            json.dumps({"numPassedTests": 1, "numFailedTests": 1, "success": False}),
            encoding="utf-8",
        )
    with pytest.raises(SystemExit, match="test/smoke evidence is empty, failed"):
        evidence.main()
    assert not (root / "docs/process/G0_VERIFICATION.json").exists()


def test_interrupted_rerun_invalidates_previous_success_before_first_command(
    evidence_state: tuple[ModuleType, ModuleType, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    checks, evidence, root = evidence_state

    def interrupted_command(*args: Any, **kwargs: Any) -> None:
        recorded = json.loads((root / "runs/checks/commands.json").read_text())
        assert recorded["status"] == "in_progress"
        assert recorded["all_passed"] is False
        raise KeyboardInterrupt

    monkeypatch.setattr(checks.subprocess, "run", interrupted_command)
    with pytest.raises(KeyboardInterrupt):
        checks.main()
    with pytest.raises(SystemExit, match="incomplete or stale"):
        evidence.main()
    assert not (root / "docs/process/G0_VERIFICATION.json").exists()
