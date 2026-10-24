"""Run actual panel browser Python downloads with network access OS-denied."""

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g11")
    confinement = out / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    rows = []
    for name in ("panel_fe_11", "panel_lp_4", "panel_lp_17"):
        completed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(out / "panel-downloads" / f"{name}.py"),
            ],
            cwd=out,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        )
        native = json.loads(completed.stdout)
        browser = json.loads((out / f"{name}.browser.json").read_text())
        delta = difference(browser, native)
        assert delta <= 1e-8
        (out / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
        csv = (out / "panel-downloads" / f"{name}.csv").read_text()
        assert "country_samples" in csv and "Country estimates:" in csv
        png = (out / "panel-downloads" / f"{name}.png").read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        rows.append(
            {
                "case": name,
                "maximum_difference": delta,
                "network": "OS-denied",
                "csv": True,
                "png": True,
                "passed": True,
            }
        )
    report = {"passed": True, "cases": rows}
    (out / "panel-export-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
