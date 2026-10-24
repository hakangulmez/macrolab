"""Frozen native suites and the bounded additive break-display change."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from g12_fixture import numbers

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g15")


def prior_break_projection(value):
    if isinstance(value, dict):
        return {
            k: prior_break_projection(v)
            for k, v in value.items()
            if k
            not in {"minimum_segment_observations", "minimum_segment_observations_per_coefficient"}
        }
    if isinstance(value, list):
        return [
            prior_break_projection(v)
            for v in value
            if not (isinstance(v, dict) and v.get("code") == "break_segment_thin")
        ]
    return value


def main():
    OUT.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "runs/g14_1/accepted-files-before.json", OUT / "accepted-files-before.json")
    env = {**os.environ, "MACROLAB_REVIEW_DIR": str(OUT.relative_to(ROOT))}
    for script, args in [
        (
            "regress_v0.py",
            [
                "--output",
                str(OUT.relative_to(ROOT)),
                "--allow-version-change",
                "--allow-shadow-copy-change",
            ],
        ),
        ("g10_fixture.py", []),
        ("g11_regress_extensions.py", []),
        ("g13_regress_existing.py", []),
        ("g14_regress_forecast.py", []),
        ("g15_fixture.py", []),
    ]:
        print("Running", script, flush=True)
        with (OUT / (script + ".log")).open("w") as log:
            subprocess.run(
                [str(ROOT / ".venv/bin/python"), "scripts/" + script, *args],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    source = ROOT / "runs/g14_1/diagnostic-fixture.json"
    fixture = json.loads(source.read_text())
    shutil.copy2(source, OUT / source.name)
    rows = []
    for name, config in fixture["cases"].items():
        result = run_analysis(config, fixture["bundle"])
        old = json.loads((ROOT / "runs/g14_1" / (name + ".json")).read_text())
        delta = numbers(old, prior_break_projection(result))
        assert max(delta) == 0, (name, max(delta))
        (OUT / (name + ".json")).write_text(json.dumps(result) + "\n")
        rows.append(dict(name=name, fields=len(delta), max_difference=0, exact=True))
        print(name, len(delta), "exact", flush=True)
    old = json.loads((ROOT / "runs/g14_1/forecast_evaluation.json").read_text())
    delta = numbers(old, json.loads((OUT / "forecast_evaluation.json").read_text()))
    assert max(delta) == 0
    report = dict(
        passed=True,
        diagnostics=rows,
        diagnostic_fields=sum(r["fields"] for r in rows),
        accepted_forecast_fields=len(delta),
        additive_display_only=[
            "break_segment_thin warning",
            "minimum_segment_observations",
            "minimum_segment_observations_per_coefficient",
        ],
    )
    (OUT / "accepted-g14-regression.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
