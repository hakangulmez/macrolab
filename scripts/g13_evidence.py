"""Collect verified G13 evidence without rebuilding or changing accepted artifacts."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g13"


def read(name):
    return json.loads((OUT / (name + ".json")).read_text())


def main():
    browsers = {
        name: read(name)
        for name in (
            "browser-validation",
            "panel-browser-validation",
            "bvar-browser-validation",
            "forecast-browser-validation",
            "v0-browser-regression",
        )
    }
    for report in browsers.values():
        assert report["passed"]
        assert not report.get("external_requests")
        assert not report.get("failed_requests")
        assert not report.get("errors")
        assert all(not row["violations"] for row in report.get("accessibility", []))
    exports = []
    for name in (
        "export-verification",
        "panel-export-verification",
        "bvar-export-verification",
        "forecast-export-verification",
    ):
        report = read(name)
        assert report["passed"]
        exports += report.get("exports", report.get("cases", []))
    assert len(exports) == 24
    assert max(row["maximum_difference"] for row in exports) <= 1e-8
    for name in (
        "native-regression",
        "native-regression-v101",
        "native-regression-v11",
        "g12-regression",
        "g12-browser-regression",
    ):
        assert read(name)["passed"]
    assert read("native-regression")["maximum_absolute_difference"] == 0
    for name in ("g12-regression", "g12-browser-regression"):
        assert read(name)["fields"] == 23653
        assert all(row["exact"] for row in read(name)["cases"])
    log = (OUT / "final-checks.log").read_text()
    assert "648 passed" in log and "109 passed" in log
    assert "Success: no issues found" in (OUT / "static-checks.log").read_text()
    inventory = read("site-inventory")
    timing = browsers["forecast-browser-validation"]["performance"]
    summary = {
        "ready_for_local_review": True,
        "numerical_verification_passed": True,
        "performance_targets_passed": False,
        "stop_before": "G14",
        "frozen_fields": {
            "v0": 4042,
            "v101": 51472,
            "v11_hd": 3906,
            "v11_crisis": 7945,
            "panel": 10081,
            "bvar": 13572,
            "total": 91018,
            "native_and_browser_exact": True,
        },
        "new_forecast_browser_native": browsers["forecast-browser-validation"]["cases"],
        "native_references": read("reference-validation"),
        "exports": {
            "count": len(exports),
            "maximum_absolute_difference": max(row["maximum_difference"] for row in exports),
            "network": "OS-denied",
        },
        "tests": {
            "python": 648,
            "web": 109,
            "final_affected_python": 31,
            "lint_typecheck_build": "pass",
        },
        "accessibility": {
            "viewport_checks": sum(len(r.get("accessibility", [])) for r in browsers.values()),
            "serious_critical": 0,
            "out_of_scope_requests": 0,
        },
        "browser_performance": {
            name: {**timing[name], "target_ms": target, "met": timing[name]["median_ms"] < target}
            for name, target in (("arima_search", 3000), ("forecast_evaluation", 25000))
        },
        "data": read("unchanged-data"),
        "protected_accepted_files": read("export-verification")["accepted_trees"],
        "preserved_scientific_runtime_files": len(
            read("export-verification")["preserved_input_runtime_files"]
        ),
        "site": {key: inventory[key] for key in ("file_count", "total_bytes", "tree_sha256")},
        "source_archive_sha256": read("runtime_wheel")["source_archive_sha256"],
        "publication": "none; local review only",
    }
    (OUT / "verification-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "ready_for_local_review",
                    "numerical_verification_passed",
                    "performance_targets_passed",
                    "exports",
                    "accessibility",
                    "site",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
