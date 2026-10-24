"""Read-only aggregation of the bounded G14.1 verification evidence."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from g9_export import inventory
from g12_fixture import numbers

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g14_1"


def read(name):
    return json.loads((OUT / f"{name}.json").read_text())


def main():
    native = [
        "native-regression",
        "native-regression-v101",
        "native-regression-v11",
        "g12-regression",
        "native-regression-forecast",
        "browser-regression-models",
    ]
    browser = [
        "browser-validation",
        "v0-browser-regression",
        "panel-browser-validation",
        "bvar-browser-validation",
        "forecast-browser-validation",
        "diagnostic-browser-validation",
    ]
    for name in native + browser + ["diagnostic-export-verification"]:
        assert read(name)["passed"], name
    counts = [
        read("native-regression")["numerical_fields"],
        read("native-regression-v101")["fields"],
        sum(r["numeric_fields"] for r in read("native-regression-v11")["cases"]),
        read("g12-regression")["fields"],
        read("native-regression-forecast")["fields"],
    ]
    assert counts == [4042, 51472, 11851, 23653, 4572]
    b = read("browser-validation")
    assert sum(r["count"] for r in b["cases"] + b["methods"]) == 51472
    assert sum(r["numeric_fields"] for r in b["extensions"]) == 11851
    assert sum(r["count"] for r in read("v0-browser-regression")["v0"]) == 4042
    assert read("browser-regression-models")["fields"] == 28225
    comparisons = []
    for name in [
        "cointegration_three",
        "cointegration_two",
        "vecm_point",
        "vecm_bootstrap",
        "forecast_evaluation",
    ]:
        for suffix in ["", ".browser"]:
            a = json.loads((ROOT / "runs/g14" / f"{name}{suffix}.json").read_text())
            c = json.loads((OUT / f"{name}{suffix}.json").read_text())
            d = numbers(a, c)
            assert max(d) == 0, (name, suffix, max(d))
            comparisons.append(
                dict(
                    name=name,
                    runtime="browser" if suffix else "native",
                    fields=len(d),
                    difference=0,
                )
            )
    audits = []
    for name in browser:
        report = read(name)
        for key in ["external_requests", "failed_requests", "errors"]:
            assert not report.get(key), (name, key)
        audits.extend(report.get("accessibility", []))
    assert all(not r["violations"] for r in audits)
    suites = ET.parse(ROOT / "runs/checks/pytest.xml").getroot().findall("testsuite")
    assert all(int(s.get("failures", 0)) == int(s.get("errors", 0)) == 0 for s in suites)
    vitest = json.loads((ROOT / "runs/checks/vitest.json").read_text())
    assert vitest["numFailedTests"] == 0
    assert all(r["passed"] for r in read("scale-validation"))
    assert (
        read("size-validation")["protocol_sha256"]
        == hashlib.sha256((ROOT / "docs/G14_1_PROTOCOL.md").read_bytes()).hexdigest()
    )
    protected = read("accepted-files-before")
    for path, sha in protected.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
    (OUT / "accepted-files-after.json").write_text(json.dumps(protected, indent=2) + "\n")
    site = inventory(OUT / "site")
    assert site == read("site-inventory")
    diagnostics = read("diagnostic-browser-validation")
    report = dict(
        passed=True,
        stop_before="G15",
        published=False,
        frozen_fields=sum(counts),
        native_and_browser_exact=True,
        accepted_g14_comparisons=comparisons,
        diagnostic_fields=sum(r["count"] for r in diagnostics["cases"]),
        maximum_cross_runtime_difference=max(r["max"] for r in diagnostics["cases"]),
        bootstrap_performance=read("bootstrap-browser-performance"),
        size=read("size-validation"),
        scale=read("scale-validation"),
        changed_existing_break_numbers=sum(
            r["count"] for r in read("break-number-changes")["changed"]
        ),
        python_tests=sum(int(s.get("tests", 0)) for s in suites),
        web_tests=vitest["numPassedTests"],
        offline_diagnostic_exports=len(read("diagnostic-export-verification")["cases"]),
        axe_viewport_checks=len(audits),
        serious_critical_findings=0,
        external_requests=0,
        protected_files=len(protected),
        site={k: site[k] for k in ["file_count", "total_bytes", "tree_sha256"]},
    )
    (OUT / "verification-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ["size", "scale", "accepted_g14_comparisons"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
