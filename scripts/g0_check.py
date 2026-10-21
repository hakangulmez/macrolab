"""Run the actual G0 checks and retain logs and measured exit statuses locally."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ("setup", "quick", "test", "lint", "typecheck", "web-build")


def source_fingerprint() -> str:
    """Bind verification to source, tests, configs and locks, excluding generated output."""
    files: set[Path] = {
        ROOT / name for name in ("Makefile", "pyproject.toml", "uv.lock", ".python-version")
    }
    for directory in (
        "src",
        "tests",
        "scripts",
        "configs",
        "schemas",
        "web/src",
        "web/tests",
        "web/scripts",
    ):
        files.update(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".mjs", ".ts", ".tsx", ".json", ".yaml", ".css"}
        )
    files.update(path for path in (ROOT / "web").iterdir() if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def main() -> int:
    """Fail the gate if any command fails; do not substitute a no-op check."""
    destination = ROOT / "runs" / "checks"
    destination.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []
    started = datetime.now(UTC).isoformat()
    fingerprint = source_fingerprint()
    result = {
        "started_utc": started,
        "checks": checks,
        "all_passed": False,
        "source_fingerprint": fingerprint,
        "status": "in_progress",
    }
    report = destination / "commands.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for target in CHECKS:
        start = time.perf_counter()
        logfile = destination / f"{target}.log"
        print(f"Running make {target}", flush=True)
        with logfile.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                ["make", target], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=False
            )
        entry = {
            "command": f"make {target}",
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "log": str(logfile.relative_to(ROOT)),
        }
        checks.append(entry)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(entry), flush=True)
        if completed.returncode:
            print(logfile.read_text(encoding="utf-8")[-12000:], flush=True)
            break
    passed = (
        len(checks) == len(CHECKS)
        and all(row["exit_code"] == 0 for row in checks)
        and source_fingerprint() == fingerprint
    )
    result.update({"all_passed": passed, "status": "complete" if passed else "failed"})
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
