"""Run local G3 browser checks; own and clean up a foreground preview if needed."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = dict(os.environ)
    env["TMPDIR"] = str(ROOT / ".cache/tmp")
    supplied = env.get("G3_BASE_URL")
    base = supplied or "http://127.0.0.1:5174/"
    if urlparse(base).hostname != "127.0.0.1":
        raise ValueError("G3 checks require a loopback-only preview")
    env["G3_BASE_URL"] = base
    gate = env.get("MACROLAB_REVIEW_GATE", "g4")
    if gate not in {"g3", "g31", "g4"}:
        raise ValueError("Unsupported review gate")
    env["MACROLAB_REVIEW_GATE"] = gate
    output = ROOT / "runs" / gate
    output.mkdir(parents=True, exist_ok=True)
    server = None
    with (output / "preview.log").open("w") as log:
        try:
            if not supplied:
                subprocess.run(
                    ["make", "web-build"]
                    if gate == "g4"
                    else [sys.executable, "scripts/g3_prepare.py"],
                    cwd=ROOT,
                    env=env,
                    check=True,
                )
                server = subprocess.Popen(
                    [sys.executable, "-m", "macrolab.api", "--port", "5174"]
                    if gate == "g4"
                    else [
                        "node",
                        "node_modules/vite/bin/vite.js",
                        "--port",
                        "5174",
                        "--strictPort",
                    ],
                    cwd=ROOT if gate == "g4" else ROOT / "web",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            for _ in range(50):
                if server and server.poll() is not None:
                    raise RuntimeError(f"Preview failed; see runs/{gate}/preview.log")
                try:
                    with urllib.request.urlopen(base, timeout=1) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local preview did not become ready")
            browser = subprocess.run(
                ["node", "web/scripts/g3-e2e.mjs"],
                cwd=ROOT,
                env=env,
                timeout=360,
            )
            report = subprocess.run(
                [sys.executable, "scripts/g3_report.py"],
                cwd=ROOT,
                env=env,
                timeout=30,
            )
            return browser.returncode or report.returncode
        finally:
            if server:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
