"""Replay every release-candidate Python download under OS-denied networking."""

import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference
from g15_verify_exports import without_timing

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16"


def main():
    sandbox = OUT / "no-network.sb"
    sandbox.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    rows = []
    folders = [
        "downloads",
        "panel-downloads",
        "bvar-downloads",
        "forecast-downloads",
        "diagnostic-downloads",
        "template-downloads",
    ]
    for folder in folders:
        scripts = sorted((OUT / folder).glob("*.py"))
        assert scripts, folder
        for path in scripts:
            name = path.stem
            completed = subprocess.run(
                [
                    "sandbox-exec",
                    "-f",
                    str(sandbox),
                    str(ROOT / ".venv/bin/python"),
                    "-I",
                    str(path),
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
            if name.endswith("-methods"):
                native = native["method_pair"]
                native.pop("shock_fingerprint", None)
                browser.pop("shock_fingerprint", None)
            delta = difference(without_timing(browser), without_timing(native))
            assert delta <= 1e-8, (name, delta)
            (OUT / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
            rows.append(
                dict(
                    name=name,
                    folder=folder,
                    maximum_difference=delta,
                    network="OS-denied",
                    passed=True,
                )
            )
            print(name, delta, flush=True)
    downloaded = []
    for folder in folders:
        for path in sorted((OUT / folder).glob("*")):
            assert path.stat().st_size > 0, path
            if path.suffix == ".png":
                assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path
            if path.suffix == ".json":
                json.loads(path.read_text())
            downloaded.append(str(path.relative_to(OUT)))
    result = dict(
        passed=True,
        python_replays=len(rows),
        cases=rows,
        downloads=downloaded,
        download_count=len(downloaded),
    )
    (OUT / "all-export-verification.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
