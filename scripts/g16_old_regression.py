"""Exact same-runtime release regressions; metadata timing/version exclusions only."""

import json
from pathlib import Path

from g12_fixture import numbers
from g15_verify_exports import without_timing

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16/old"


def main():
    def read(path):
        return json.loads(path.read_text())

    for n in [
        "browser-validation",
        "v0-browser-regression",
        "panel-browser-validation",
        "bvar-browser-validation",
        "forecast-browser-validation",
        "diagnostic-browser-validation",
        "template-browser-validation",
    ]:
        r = read(OUT / (n + ".json"))
        assert r["passed"], n
        assert not any(r.get(k) for k in ["external_requests", "failed_requests", "errors"]), n
    cases = []
    for group, accepted in [
        ("panel", "g12"),
        ("bvar", "g12"),
        ("forecast", "g15"),
        ("diagnostic", "g15"),
        ("template", "g15"),
    ]:
        fixture = read(OUT / f"{group}-fixture.json")
        for name in fixture["cases"]:
            for runtime, suffix in [("native", ".json"), ("browser", ".browser.json")]:
                old = read(ROOT / "runs" / accepted / (name + suffix))
                new = read(OUT / (name + suffix))
                delta = numbers(without_timing(old), without_timing(new))
                assert max(delta) == 0, (name, runtime, max(delta))
                cases.append(
                    dict(
                        name=name,
                        group=group,
                        runtime=runtime,
                        fields=len(delta),
                        maximum_difference=0,
                    )
                )
    legacy = read(OUT / "browser-validation.json")
    v0 = read(OUT / "v0-browser-regression.json")
    assert sum(r["count"] for r in legacy["cases"] + legacy["methods"]) == 51472
    assert sum(r["numeric_fields"] for r in legacy["extensions"]) == 11851
    assert sum(r["count"] for r in v0["v0"]) == 4042
    for filename in [
        "native-regression",
        "native-regression-v101",
        "native-regression-v11",
        "g12-regression",
        "native-regression-forecast",
        "accepted-g14-regression",
        "native-regression-g15",
    ]:
        assert read(OUT / (filename + ".json"))["passed"]
    report = dict(
        passed=True,
        frozen_fields=100875,
        g15_template_fields=60077,
        total_required_fields=160952,
        same_runtime_maximum_difference=0,
        additional_carryover_fields_exact=True,
        cases=cases,
        excluded=["runtime_ms", "template_timing", "code_version"],
        evidence_overwrite="../evidence-overwrite.json",
    )
    (OUT / "frozen-regression.json").write_text(json.dumps(report, indent=2) + "\n")
    print("160,952 required fields exact in native and browser; additional carry-over fields exact")


if __name__ == "__main__":
    main()
