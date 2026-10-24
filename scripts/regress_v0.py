"""Exact native-to-native P2/P3.1 regression; browser counterpart uses the same fixtures."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from p2_validate import EXCLUDED, bundle, differences, save

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]


def approved_shadow_copy(change: dict) -> bool:
    return change.get("before") == (
        "Rates were near or below zero; consider a shorter sample. Shadow "
        "rates are not available in v0."
    ) and change.get("after") == (
        "Rates were near or below zero; consider a shorter sample. Shadow "
        "rates are not available in MacroLab."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/g6")
    parser.add_argument("--allow-version-change", action="store_true")
    parser.add_argument("--allow-shadow-copy-change", action="store_true")
    args = parser.parse_args()
    directory = args.output.resolve()
    if not directory.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("Regression evidence must stay inside ignored runs")
    # The accepted P3.1 contract includes numerical check details, excluding timing only.
    EXCLUDED.clear()
    EXCLUDED.add("runtime_ms")
    if args.allow_version_change:
        EXCLUDED.add("code_version")
    manifest = json.loads((ROOT / "runs/p2/public/data/manifest.json").read_text())
    report = {
        "passed": True,
        "code_version_change_allowed": args.allow_version_change,
        "templates": [],
        "numerical_fields": 0,
        "maximum_absolute_difference": 0,
    }
    for template in manifest["templates"]:
        name, config = template["id"], template["config"]
        before = json.loads((ROOT / "runs/p2/results" / f"{name}.json").read_text())
        start = time.perf_counter()
        after = run_analysis(config, bundle(config))
        delta, structural, count = differences(before, after)
        approved = [
            d for d in structural if args.allow_shadow_copy_change and approved_shadow_copy(d)
        ]
        structural = [d for d in structural if d not in approved]
        maximum = max((abs(d["difference"]) for d in delta), default=0)
        report["templates"].append(
            {
                "id": name,
                "code_version_before": before["code_version"],
                "code_version_after": after["code_version"],
                "numeric_fields": count,
                "changed_fields": len(delta),
                "maximum_absolute_difference": maximum,
                "structural_changes": structural,
                "approved_text_changes": approved,
                "seconds": time.perf_counter() - start,
            }
        )
        report["numerical_fields"] += count
        report["maximum_absolute_difference"] = max(report["maximum_absolute_difference"], maximum)
        report["passed"] = report["passed"] and not delta and not structural
        save(directory / "native" / f"{name}.json", after)
    save(directory / "native-regression.json", report)
    print(json.dumps(report, indent=2))
    if not report["passed"] or report["numerical_fields"] != 4042:
        raise SystemExit("Exact accepted v0 regression failed")


if __name__ == "__main__":
    main()
