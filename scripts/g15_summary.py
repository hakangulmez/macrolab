"""Verify the complete local G15 evidence bundle without running models again."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from g9_export import inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g15"


def read(name):
    return json.loads((OUT / (name + ".json")).read_text())


def main():
    browser_names = [
        "browser-validation",
        "v0-browser-regression",
        "panel-browser-validation",
        "bvar-browser-validation",
        "forecast-browser-validation",
        "diagnostic-browser-validation",
        "template-browser-validation",
    ]
    if (OUT / "template-browser-validation-selected.json").exists():
        browser_names.append("template-browser-validation-selected")
    reports = {name: read(name) for name in browser_names}
    for name, report in reports.items():
        assert report["passed"], name
        for key in ["external_requests", "failed_requests", "errors"]:
            assert not report.get(key), (name, key)
        for row in report.get("accessibility", []):
            assert not row["violations"], (name, row)
    for name in [
        "native-regression",
        "native-regression-v101",
        "native-regression-v11",
        "g12-regression",
        "native-regression-forecast",
        "accepted-g14-regression",
        "browser-regression-models",
        "browser-regression-g14",
        "template-reference-validation",
        "template-export-verification",
        "diagnostic-export-verification",
        "export-verification",
        "legacy-csv-regression",
    ]:
        assert read(name)["passed"], name

    frozen = {
        "v0_original_snapshot": 4042,
        "v101_current_snapshot": 51472,
        "v11_hd_crisis": 11851,
        "panel_bvar": 23653,
        "forecast_g13": 4572,
        "g14_diagnostics": 5080,
        "g14_additional_forecast_fields": 205,
    }
    assert read("native-regression")["numerical_fields"] == frozen["v0_original_snapshot"]
    assert read("native-regression-v101")["fields"] == frozen["v101_current_snapshot"]
    assert sum(r["numeric_fields"] for r in read("native-regression-v11")["cases"]) == 11851
    assert read("g12-regression")["fields"] == 23653
    assert read("native-regression-forecast")["fields"] == 4572
    assert read("accepted-g14-regression")["diagnostic_fields"] == 5080
    assert read("browser-regression-models")["fields"] == 28225
    assert read("browser-regression-g14")["diagnostic_fields"] == 5080
    assert read("browser-regression-g14")["accepted_forecast_fields"] == 3131
    assert sum(r["count"] for r in reports["v0-browser-regression"]["v0"]) == 4042
    legacy = reports["browser-validation"]
    assert sum(r["count"] for r in legacy["cases"] + legacy["methods"]) == 51472
    assert sum(r["numeric_fields"] for r in legacy["extensions"]) == 11851

    protected = read("accepted-files-before")
    assert all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in protected.items()
    )
    inv = inventory(OUT / "site")
    assert inv == read("site-inventory")
    manifest = json.loads((OUT / "site/data/manifest.json").read_text())
    performance = read("template-performance")
    assert manifest["runtime"]["wheel_sha256"] == performance["runtime_wheel"]["wheel_sha256"]
    pinned = []
    for folder in ["runtime/pyodide", "licences/runtime"]:
        for source in (ROOT / "runs/p2/site" / folder).rglob("*"):
            if source.is_file():
                relative = source.relative_to(ROOT / "runs/p2/site")
                assert source.read_bytes() == (OUT / "site" / relative).read_bytes()
                pinned.append(str(relative))
    for relative in read("unchanged-data")["byte_identical_files"]:
        assert (ROOT / "runs/g10_1/site" / relative).read_bytes() == (
            OUT / "site" / relative
        ).read_bytes()
    tests = ET.parse(ROOT / "runs/checks/pytest.xml").getroot().findall("testsuite")
    assert sum(int(s.attrib["failures"]) + int(s.attrib["errors"]) for s in tests) == 0
    web = json.loads((ROOT / "runs/checks/vitest.json").read_text())
    assert web["success"]
    parity = reports["template-browser-validation"]["cases"]
    exports = read("template-export-verification")["cases"]
    assert max(r["max"] for r in parity) <= 1e-8
    assert max(r["max_difference"] for r in exports) <= 1e-8
    result = dict(
        passed=True,
        preregistration_commit="82ff653ecb72582c0a7c62b938116d5d2523cc1a",
        snapshot="20261023-1634",
        frozen_fields=frozen,
        total_distinct_frozen_fields=sum(frozen.values()),
        frozen_native_and_browser_max_difference=0,
        additive_break_display=[
            "minimum_segment_observations",
            "minimum_segment_observations_per_coefficient",
            "break_segment_thin",
        ],
        python_tests=sum(int(s.attrib["tests"]) for s in tests),
        web_tests=web["numPassedTests"],
        new_template_numeric_fields=sum(r["count"] for r in parity),
        new_template_browser_native_max_difference=max(r["max"] for r in parity),
        new_template_offline_max_difference=max(r["max_difference"] for r in exports),
        offline_downloads=3
        + len(read("diagnostic-export-verification")["cases"])
        + len(read("export-verification")["exports"]),
        accessibility_checks=sum(len(r.get("accessibility", [])) for r in reports.values()),
        serious_critical_axe_findings=0,
        external_application_requests=0,
        protected_files=len(protected),
        protected_files_changed=0,
        unchanged_observation_policy_schema_files=len(
            read("unchanged-data")["byte_identical_files"]
        ),
        unchanged_pinned_runtime_notice_files=len(pinned),
        performance=performance["performance"],
        performance_scope="Five isolated warm runs; final UI fixes share the same model wheel.",
        site={k: v for k, v in inv.items() if k != "files"},
        screenshots=sorted(
            str(p.relative_to(ROOT)) for p in (ROOT / "docs/screenshots/g15").glob("*.png")
        ),
        published=False,
    )
    (OUT / "verification-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"performance", "screenshots", "frozen_fields"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
