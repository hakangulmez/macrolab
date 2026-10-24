"""Run the downloaded BVAR scripts with OS networking denied."""

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g12")


def main():
    confinement = OUT / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    rows = []
    for name in ("bvar_fixed", "bvar_grid", "bvar_optional"):
        run = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(OUT / "bvar-downloads" / f"{name}.py"),
            ],
            cwd=OUT,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        )
        actual = json.loads(run.stdout)
        browser = json.loads((OUT / f"{name}.browser.json").read_text())
        delta = difference(browser, actual)
        assert delta <= 1e-8
        (OUT / f"{name}.export-result.json").write_text(json.dumps(actual) + "\n")
        csv = (OUT / "bvar-downloads" / f"{name}.csv").read_text()
        assert "90% posterior credible bands" in csv and "Posterior draw accounting" in csv
        assert "largest_roots" in csv and "log_marginal_likelihood" in csv
        for suffix in ("", "-90"):
            assert (OUT / "bvar-downloads" / f"{name}{suffix}.png").read_bytes()[
                :8
            ] == b"\x89PNG\r\n\x1a\n"
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
    (OUT / "bvar-export-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
