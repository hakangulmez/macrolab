"""Frozen browser checks on one fixed local candidate; screenshots only changed views."""

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g15"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["legacy", "models", "templates"])
    group = parser.parse_args().group
    env = {
        **os.environ,
        "MACROLAB_REVIEW_DIR": "runs/g15",
        "MACROLAB_ACCEPTED_DIR": "runs/g10_1",
        "MACROLAB_G11_PRESENTATION": "1",
        "MACROLAB_SKIP_SCREENSHOTS": "1",
        "MACROLAB_EXTENSION_RUNS": "1",
        "MACROLAB_PANEL_RUNS": "1",
        "MACROLAB_PANEL_ACCEPTED_DIR": "runs/g12",
        "MACROLAB_FORECAST_RUNS": "1",
        "MACROLAB_DIAGNOSTIC_RUNS": "1",
        "MACROLAB_SCREENSHOT_GATE": "g15",
        "MACROLAB_SCREENSHOT_CASES": "break_ecb,break-ecb-source-cards",
        "MACROLAB_TEMPLATE_RUNS": "1",
    }
    groups = {
        "legacy": ["g10-browser.mjs", "g10-v0.mjs"],
        "models": [
            "g11-panel-browser.mjs",
            "g12-bvar-browser.mjs",
            "g13-forecast-browser.mjs",
            "g14-browser.mjs",
        ],
        "templates": ["g15-browser.mjs"],
    }
    for script in groups[group]:
        print("Running", script, flush=True)
        with (OUT / (script + ".log")).open("w") as log:
            subprocess.run(
                ["node", "web/scripts/" + script],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        print("Passed", script, flush=True)


if __name__ == "__main__":
    main()
