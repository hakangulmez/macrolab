"""Accepted G12 panel/BVAR results are immutable inputs to this G13 regression."""

import json
import os
from pathlib import Path

from g12_fixture import numbers

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g13")
rows = []
for group in ["panel", "bvar"]:
    path = ROOT / "runs/g12" / f"{group}-fixture.json"
    fixture = json.loads(path.read_text())
    (OUT / path.name).write_text(path.read_text())
    for name, config in fixture["cases"].items():
        result = run_analysis(config, fixture["bundle"])
        accepted = json.loads((ROOT / "runs/g12" / f"{name}.json").read_text())
        differences = numbers(accepted, result)
        assert result["status"] == "ok" and max(differences) == 0, name
        (OUT / f"{name}.json").write_text(json.dumps(result) + "\n")
        rows.append(
            dict(
                name=name, fields=len(differences), max_abs_difference=max(differences), exact=True
            )
        )
        print(name, len(differences), "exact", flush=True)
(OUT / "g12-regression.json").write_text(
    json.dumps(dict(passed=True, fields=sum(r["fields"] for r in rows), cases=rows), indent=2)
    + "\n"
)
