"""Run local G1 checks and bind measured results to the current source files."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from g0_check import CHECKS, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    destination = ROOT / "runs/g1/checks"
    destination.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []
    fingerprint = source_fingerprint()
    result = {
        "gate": "G1",
        "started_utc": datetime.now(UTC).isoformat(),
        "checks": checks,
        "all_passed": False,
        "source_fingerprint": fingerprint,
        "status": "in_progress",
    }
    report = destination / "commands.json"
    report.write_text(json.dumps(result, indent=2) + "\n")
    for target in CHECKS:
        start = time.perf_counter()
        logfile = destination / f"{target}.log"
        print(f"Running make {target}", flush=True)
        with logfile.open("w") as handle:
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
        report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(entry), flush=True)
        if completed.returncode:
            print(logfile.read_text()[-12000:], flush=True)
            break
    passed = (
        len(checks) == len(CHECKS)
        and all(row["exit_code"] == 0 for row in checks)
        and source_fingerprint() == fingerprint
    )
    result.update({"all_passed": passed, "status": "complete" if passed else "failed"})
    report.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
