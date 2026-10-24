"""Sequential same-host fresh-profile A/B and warm-template timing; no network."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g10"


def main():
    rows = []
    for i in range(5):
        for before in [True, False]:
            args = [
                "node",
                "web/scripts/g10-browser.mjs",
                "--template=monetary_policy",
                "--cold-only",
            ] + (["--before"] if before else [])
            log = OUT / f"cold-{i}-{before}.log"
            with log.open("w") as f:
                subprocess.run(args, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=True)
            path = OUT / ("before" if before else "") / "browser-monetary_policy-validation.json"
            r = json.loads(path.read_text())
            assert r["passed"]
            rows.append({"accepted_v101": before, "iteration": i, "ms": r["cold_preparation_ms"]})
            print(rows[-1], flush=True)
    stats = {}
    for label, before in [("v101", True), ("g10", False)]:
        values = [r["ms"] for r in rows if r["accepted_v101"] == before]
        stats[label] = {
            "median_ms": float(np.median(values)),
            "p90_ms": float(np.quantile(values, 0.9)),
            "runs_ms": values,
        }
    stats["median_change_ms"] = stats["g10"]["median_ms"] - stats["v101"]["median_ms"]
    stats["within_500ms"] = stats["median_change_ms"] <= 500
    (OUT / "preparation-performance.json").write_text(
        json.dumps({"rows": rows, **stats}, indent=2) + "\n"
    )
    with (OUT / "benchmark.log").open("w") as f:
        subprocess.run(
            ["node", "web/scripts/g10-browser.mjs", "--benchmark"],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
        )
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
