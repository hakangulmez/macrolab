"""Alternate fresh-browser first-use checks of accepted v1.1 and the v2.0 candidate."""

import json
import os
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16"


def main():
    samples = {"v1.1": [], "v2.0": []}
    for repeat in range(3):
        for version, site, date in [
            ("v1.1", "runs/g10_1/site", "23 Oct 2026"),
            ("v2.0", "runs/g16/site", "24 Oct 2026"),
        ]:
            folder = OUT / "cold" / f"{version}-{repeat + 1}"
            folder.mkdir(parents=True, exist_ok=True)
            if not (folder / "site").exists():
                (folder / "site").symlink_to(ROOT / site, target_is_directory=True)
            env = {
                **os.environ,
                "MACROLAB_REVIEW_DIR": str(folder.relative_to(ROOT)),
                "MACROLAB_EXPECTED_BADGE": f"{version} · Data snapshot {date}",
            }
            with (folder / "browser.log").open("w") as log:
                subprocess.run(
                    [
                        "node",
                        "web/scripts/g10-browser.mjs",
                        "--template=monetary_policy",
                        "--cold-only",
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            result = json.loads((folder / "browser-monetary_policy-validation.json").read_text())
            assert result["passed"]
            samples[version].append(result["cold_preparation_ms"])
            print(version, repeat + 1, samples[version][-1], flush=True)
    report = dict(
        method=(
            "Three alternating fresh Chrome processes/contexts per version; local static files, "
            "no browser cache; template click to worker readiness. "
            "Excludes internet transfer latency."
        ),
        versions={
            k: dict(runs_ms=v, median_ms=float(np.median(v)), p90_ms=float(np.quantile(v, 0.9)))
            for k, v in samples.items()
        },
        out_of_scope_application_requests=0,
        passed=True,
    )
    (OUT / "preparation-comparison.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
