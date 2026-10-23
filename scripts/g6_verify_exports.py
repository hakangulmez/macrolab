"""Execute the actual browser downloads offline, under OS network denial."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "runs/g6"
    fixture = json.loads((out / "browser-fixture.json").read_text())
    confinement = out / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    records = []
    for item in fixture["cases"]:
        name = item["id"]
        path = out / f"{name}.browser-export.py"
        completed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(path),
            ],
            cwd=out,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        )
        actual = json.loads(completed.stdout)
        browser = json.loads((out / f"{name}.browser.json").read_text())
        diff = difference(browser, actual)
        if diff > 1e-8:
            raise AssertionError(f"{name} offline reproduction exceeds tolerance: {diff}")
        records.append({"id": name, "maximum_absolute_difference": diff, "passed": True})
        print(name, diff, flush=True)
    report = {"passed": True, "network": "OS sandbox denies all network", "cases": records}
    (out / "export-verification.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
