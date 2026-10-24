"""Preserve all accepted G13 fields; only add the requested origin sensitivity."""

import json
import os
from copy import deepcopy
from pathlib import Path

from g12_fixture import numbers

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g14")


def accepted_projection(result):
    result = deepcopy(result)
    for country in result["results"]:
        if country["model_id"] == "fc.eval":
            variants = country["sensitivity"]["variants"]
            assert len(variants) == 2
            assert variants[-1]["id"] == "exclude_2020_2021_origins"
            variants.pop()
    return result


def main():
    source = ROOT / "runs/g13/forecast-fixture.json"
    fixture = json.loads(source.read_text())
    (OUT / source.name).write_text(source.read_text())
    rows = []
    for name, config in fixture["cases"].items():
        result = run_analysis(config, fixture["bundle"])
        assert result["status"] == "ok", name
        (OUT / f"{name}.json").write_text(json.dumps(result) + "\n")
        accepted = json.loads((ROOT / "runs/g13" / f"{name}.json").read_text())
        delta = numbers(accepted, accepted_projection(result))
        assert max(delta) == 0, name
        rows.append(dict(name=name, fields=len(delta), max_difference=0, exact=True))
        print(name, len(delta), "exact", flush=True)
    report = dict(passed=True, fields=sum(r["fields"] for r in rows), cases=rows)
    assert report["fields"] == 4572
    (OUT / "native-regression-forecast.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
