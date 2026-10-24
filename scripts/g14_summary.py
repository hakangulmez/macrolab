"""Collect the final G14 evidence without rebuilding or changing accepted inputs."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from g9_export import inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g14"


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
    browsers = [
        "browser-validation",
        "v0-browser-regression",
        "panel-browser-validation",
        "bvar-browser-validation",
        "forecast-browser-validation",
        "forecast-browser-validation-selected",
        "diagnostic-browser-validation",
        "diagnostic-browser-validation-selected",
    ]
    exports = [
        "export-verification",
        "panel-export-verification",
        "bvar-export-verification",
        "forecast-export-verification",
        "diagnostic-export-verification",
    ]
    for name in native + browsers + exports:
        assert read(name)["passed"], name
    assert read("native-regression")["numerical_fields"] == 4042
    assert read("native-regression-v101")["fields"] == 51472
    assert sum(r["numeric_fields"] for r in read("native-regression-v11")["cases"]) == 11851
    assert read("g12-regression")["fields"] == 23653
    assert read("native-regression-forecast")["fields"] == 4572
    assert read("browser-regression-models")["fields"] == 28225
    release = read("browser-validation")
    assert sum(r["count"] for r in release["cases"] + release["methods"]) == 51472
    assert sum(r["numeric_fields"] for r in release["extensions"]) == 11851
    assert sum(r["count"] for r in read("v0-browser-regression")["v0"]) == 4042
    audits = [r for name in browsers for r in read(name).get("accessibility", [])]
    for name in browsers:
        r = read(name)
        assert not r.get("external_requests") and not r.get("failed_requests")
        assert not r.get("errors")
    assert all(not r["violations"] for r in audits)
    suites = ET.parse(ROOT / "runs/checks/pytest.xml").getroot().findall("testsuite")
    assert all(int(s.get("failures", 0)) == int(s.get("errors", 0)) == 0 for s in suites)
    vitest = json.loads((ROOT / "runs/checks/vitest.json").read_text())
    assert vitest["numFailedTests"] == 0 and vitest["numPassedTests"] == 113
    current = inventory(OUT / "site")
    assert current == read("site-inventory")
    checked = read("diagnostic-browser-validation")
    report = dict(
        ready_for_local_review=True,
        stop_before="G15",
        publication_approved=False,
        frozen_fields=dict(
            v0=4042,
            v101=51472,
            hd=3906,
            crisis=7945,
            panel=10081,
            bvar=13572,
            forecasting=4572,
            total=95590,
            native_and_browser_exact=True,
        ),
        pre_g14_diagnostic="No estimation defect; additive origin-exclusion sensitivity only",
        new_diagnostic_fields=sum(r["count"] for r in checked["cases"]),
        new_diagnostic_max_difference=max(r["max"] for r in checked["cases"]),
        new_model_performance=checked["performance"],
        limitations=read("reference-validation")["no_break_size"],
        python_tests=sum(int(s.get("tests", 0)) for s in suites),
        web_tests=vitest["numPassedTests"],
        resolved_test_failures="Three registry-count expectations updated from 22 to 25; "
        "final full suite passed. Numerical conditioning fixes apply only to new break tests.",
        offline_python_exports=sum(
            len(read(n).get("cases", read(n).get("exports", []))) for n in exports
        ),
        axe_viewport_checks=len(audits),
        serious_or_critical_axe_findings=0,
        external_requests=0,
        screenshots="docs/screenshots/g14",
        preserved_inputs=read("export-verification")["accepted_trees"],
        data=read("unchanged-data"),
        site=dict(
            files=current["file_count"],
            bytes=current["total_bytes"],
            tree_sha256=current["tree_sha256"],
        ),
    )
    (OUT / "verification-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"data", "new_model_performance", "limitations"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
