"""Exact native comparison with the accepted v1.1 HD and crisis outputs."""

import json
import os
from pathlib import Path

from g9_fixture import bundle
from p2_validate import EXCLUDED, differences

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g11")


def main():
    EXCLUDED.clear()
    EXCLUDED.update({"runtime_ms", "code_version"})
    b = bundle()
    rows = []
    for name in ("hd", "crisis"):
        old = json.loads((ROOT / "runs/g10_1" / f"{name}.json").read_text())
        result = run_analysis(old["config"], b)
        delta, structural, count = differences(old, result)
        row = {
            "name": name,
            "numeric_fields": count,
            "max_difference": max((abs(x["difference"]) for x in delta), default=0),
            "structural": structural,
            "passed": not delta and not structural,
        }
        rows.append(row)
        (OUT / f"{name}.json").write_text(json.dumps(result) + "\n")
        print(row, flush=True)
    report = {"passed": all(x["passed"] for x in rows), "cases": rows}
    (OUT / "native-regression-v11.json").write_text(json.dumps(report, indent=2) + "\n")
    assert report["passed"]


if __name__ == "__main__":
    main()
