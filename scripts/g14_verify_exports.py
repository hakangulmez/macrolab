"""Replay every G14 diagnostic download under an OS-level network denial."""

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g14")


def main():
    confinement = OUT / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    fixture = json.loads((OUT / "diagnostic-fixture.json").read_text())
    rows = []
    for name in fixture["cases"]:
        completed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(OUT / "diagnostic-downloads" / f"{name}.py"),
            ],
            cwd=OUT,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        )
        native = json.loads(completed.stdout)
        browser = json.loads((OUT / f"{name}.browser.json").read_text())
        delta = difference(browser, native)
        assert delta <= 1e-8, (name, delta)
        (OUT / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
        csv = (OUT / "diagnostic-downloads" / f"{name}.csv").read_text()
        assert "Johansen" in csv or "Sup-F candidate path" in csv
        assert (OUT / "diagnostic-downloads" / f"{name}.png").read_bytes()[
            :8
        ] == b"\x89PNG\r\n\x1a\n"
        rows.append(dict(name=name, maximum_difference=delta, network="OS-denied", passed=True))
        print(name, delta, flush=True)
    (OUT / "diagnostic-export-verification.json").write_text(
        json.dumps(dict(passed=True, cases=rows), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
