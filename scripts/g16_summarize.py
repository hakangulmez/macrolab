"""Aggregate release checks without estimating or changing any result."""

import json
from pathlib import Path

from g9_export import inventory
from g15_verify_exports import without_timing
from p2_validate import differences

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16"


def read(name):
    return json.loads((OUT / name).read_text())


def main():
    fixed = read("old/frozen-regression.json")
    assert fixed["passed"] and fixed["total_required_fields"] == 160952
    checks = {}
    views = []
    maximum = 0.0
    for name in [
        "browser-validation",
        "panel-browser-validation",
        "bvar-browser-validation",
        "forecast-browser-validation",
        "diagnostic-browser-validation",
        "template-browser-validation",
    ]:
        r = read(name + ".json")
        assert r["passed"], name
        assert not any(r.get(k) for k in ["external_requests", "failed_requests", "errors"]), name
        for row in r.get("accessibility", []):
            assert not row["violations"], (name, row)
            views.append(dict(group=name, **row))
        for case in r["cases"] + r.get("methods", []) + r.get("extensions", []):
            maximum = max(maximum, case.get("max", case.get("max_difference", 0)))
        checks[name] = dict(passed=True, cases=len(r["cases"]), views=len(r["accessibility"]))
    assert maximum <= 1e-8
    assert len(read("template-browser-validation.json")["validation_cards"]) == 6
    manifest = read("site/data/manifest.json")
    comparisons = []
    for t in manifest["templates"]:
        name = t["id"]
        delta, structural, count = differences(
            without_timing(read("old/" + name + ".browser.json")),
            without_timing(read(name + ".browser.json")),
        )
        assert not delta, (name, delta[:3])
        assert all(x["path"].endswith("/first_stage_input_sha256") for x in structural), (
            name,
            structural[:3],
        )
        comparisons.append(
            dict(
                template=name,
                fields=count,
                maximum_difference=0,
                provenance_hash_changes=structural,
            )
        )
    integrity = read("integrity.json")
    assert integrity["passed"]
    exports = read("all-export-verification.json")
    assert exports["passed"] and exports["python_replays"] == 34
    performance = read("performance.json")
    assert performance["passed"]
    metrics = performance["performance"]
    for name, p in read("template-browser-validation.json")["performance"].items():
        metrics[name] = dict(
            repetitions=len(p["runs_ms"]),
            baseline_median_ms=p["baseline_median_ms"],
            baseline_p90_ms=p["baseline_p90_ms"],
            full_median_ms=p["median_ms"],
            full_p90_ms=p["p90_ms"],
        )
    assert len(metrics) == 9 and all(x["repetitions"] == 5 for x in metrics.values())
    cold = read("preparation-comparison.json")
    site = inventory(OUT / "site")
    (OUT / "site-inventory.json").write_text(json.dumps(site, indent=2) + "\n")
    testlog = (OUT / "full-suite.log").read_text()
    web = (OUT / "full-web-final.log").read_text()
    assert "678 passed" in testlog and "117 passed" in web
    lint = (OUT / "static-checks-final.log").read_text()
    assert "Success: no issues found in 75 source files" in lint and "tsc --noEmit" in lint
    result = dict(
        passed=True,
        snapshot_id=manifest["snapshot_id"],
        version="v2.0",
        python_tests=678,
        web_tests=117,
        lint_typecheck="passed",
        frozen_fields=fixed["total_required_fields"],
        same_runtime_maximum_difference=0,
        new_snapshot_browser_comparisons=comparisons,
        browser_native_maximum_difference=maximum,
        browser_checks=checks,
        axe_serious_critical=0,
        accessibility_views=views,
        out_of_scope_application_requests=0,
        validation_cards=6,
        v2_items_linked=9,
        python_exports=exports["python_replays"],
        download_count=exports["download_count"],
        offline_replay_maximum_difference=max(r["maximum_difference"] for r in exports["cases"]),
        offline_network="OS-denied",
        integrity=integrity,
        performance=metrics,
        preparation=cold,
        site={k: v for k, v in site.items() if k != "files"},
        country_narratives="withheld",
        publication_approved=False,
        deviations=[
            "Five disclosed G15 verification-output overwrites; "
            "no archived data or frozen input changes"
        ],
    )
    (OUT / "verification-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (OUT / "template-performance.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k
                not in [
                    "integrity",
                    "accessibility_views",
                    "performance",
                    "new_snapshot_browser_comparisons",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
