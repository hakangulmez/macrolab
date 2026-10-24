"""Replay all new forecasting Python downloads with OS networking denied."""

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g13")


def main():
    confinement = OUT / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    rows = []
    fixture = json.loads((OUT / "forecast-fixture.json").read_text())
    for name in fixture["cases"]:
        completed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(OUT / "forecast-downloads" / f"{name}.py"),
            ],
            cwd=OUT,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=300,
        )
        native = json.loads(completed.stdout)
        browser = json.loads((OUT / f"{name}.browser.json").read_text())
        delta = difference(browser, native)
        assert delta <= 1e-8
        (OUT / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
        csv = (OUT / "forecast-downloads" / f"{name}.csv").read_text()
        assert fixture["cases"][name]["sample"]["end"] in csv
        assert "Forecast" in csv or "forecast" in csv
        assert (OUT / "forecast-downloads" / f"{name}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        rows.append(
            dict(
                name=name,
                maximum_difference=delta,
                network="OS-denied",
                csv=True,
                png=True,
                passed=True,
            )
        )
    report = dict(passed=True, cases=rows)
    (OUT / "forecast-export-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
