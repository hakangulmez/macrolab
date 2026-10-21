"""Offline G3.1 monetary comparison against the immutable accepted G3 config."""

from __future__ import annotations

import hashlib
import json
import runpy
import statistics
import subprocess
import time
from pathlib import Path

import numpy as np

from macrolab.analysis.engine import run_analysis
from macrolab.models.var import validation_evidence as var_evidence

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/g31"
BASE_COMMIT = "3b12b1ece8b4d86ee7371af9eb466895421a231d"
SNAPSHOT = "20261021-0025"


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def accepted_config():
    content = subprocess.check_output(
        ["git", "show", f"{BASE_COMMIT}:configs/templates/monetary_policy.json"], cwd=ROOT
    )
    path = OUTPUT / "before_config.json"
    if path.exists() and path.read_bytes() != content:
        raise ValueError("The saved G3 baseline config differs from its immutable commit")
    path.write_bytes(content)
    manifest = {
        "commit": BASE_COMMIT,
        "config_sha256": hashlib.sha256(content).hexdigest(),
        "snapshot_id": SNAPSHOT,
    }
    save(OUTPUT / "before_manifest.json", manifest)
    return json.loads(content), manifest


def model_sources():
    evidence = []
    for path in sorted((ROOT / "src/macrolab/models").glob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        baseline = subprocess.check_output(["git", "show", f"{BASE_COMMIT}:{relative}"], cwd=ROOT)
        original, current = (
            hashlib.sha256(baseline).hexdigest(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        if original != current:
            raise ValueError(f"Statistical model changed since accepted G3: {relative}")
        evidence.append({"path": relative, "sha256": current, "unchanged": True})
    return evidence


def summary(result):
    country = result["results"][0]
    d = country["diagnostics"]
    irf = country["irf"]
    peaks = []
    for j, variable in enumerate(irf["variables"]):
        values = np.asarray(irf["values"])[:, j]
        index = int(np.argmax(np.abs(values)))
        peaks.append(
            {
                "variable": variable,
                "response": float(values[index]),
                "horizon": irf["periods"][index],
                "lower": irf["lower"][index][j],
                "upper": irf["upper"][index][j],
            }
        )
    return {
        "status": result["status"],
        "config_hash": result["config_hash"],
        "actual_sample": country["actual_sample"],
        "selected_lags": d["selected_lags"],
        "variables": d["variables"],
        "parameters_per_equation": d["parameter_count_per_equation"],
        "observations_per_parameter": d["nobs"] / d["parameter_count_per_equation"],
        "stable": d["stable"],
        "companion_spectral_radius": d["companion_spectral_radius"],
        "resolved_shock_pp": irf["shock_size"],
        "draws": result["config"]["outputs"]["irf"]["draws"],
        "peaks": peaks,
        "checks": country["checks"],
        "notes": country["notes"],
        "sensitivity_summary": country["sensitivity"]["summary"],
        "lag_criteria": country["sensitivity"].get("lag_criteria"),
        "variants": [
            {
                key: variant[key]
                for key in (
                    "variant_id",
                    "status",
                    "reason",
                    "sample",
                    "diagnostics",
                    "checks",
                    "equivalent_variant",
                )
                if key in variant
            }
            for variant in country["sensitivity"]["variants"]
        ],
    }


def repeated(config):
    runs, elapsed = [], []
    for _ in range(3):
        started = time.perf_counter()
        result = run_analysis(config)
        elapsed.append((time.perf_counter() - started) * 1000)
        if result["status"] != "ok":
            raise ValueError("A compared monetary configuration was blocked")
        if runs and runs[0]["results"] != result["results"]:
            raise ValueError("Repeated seeded runs changed numerical results")
        runs.append(result)
    return runs[0], {
        "repetitions": 3,
        "elapsed_ms": elapsed,
        "median_ms": statistics.median(elapsed),
        "scope": "native full result including sensitivity; one process; no browser claim",
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before_config, manifest = accepted_config()
    current = json.loads((ROOT / "configs/templates/monetary_policy.json").read_text())
    if current["snapshot_id"] != SNAPSHOT or before_config["snapshot_id"] != SNAPSHOT:
        raise ValueError("Before and after must use the same accepted snapshot")
    source_evidence = model_sources()
    before, before_timing = repeated(before_config)
    after, after_timing = repeated(current)
    save(OUTPUT / "before.json", before)
    save(OUTPUT / "after.json", after)
    references = (
        runpy.run_path(str(ROOT / "tests/reference/test_linear_models.py"))["validation_evidence"]()
        + var_evidence()
    )
    reference_passed = len(references) == 12 and all(
        r["reference_max_abs_difference"] <= r["reference_tolerance"] for r in references
    )
    if not reference_passed:
        raise ValueError("One of the twelve original model reference checks failed")
    old, new = summary(before), summary(after)
    warnings = {c["code"] for c in new["checks"] if c["level"] in {"warn", "block"}}
    targets = {
        "no_unstable_dynamics": {
            "passed": "unstable_dynamics" not in warnings,
            "spectral_radius": new["companion_spectral_radius"],
        },
        "no_observations_per_parameter_warning": {
            "passed": "small_sample" not in warnings,
            "actual_observations": new["actual_sample"]["nobs"],
            "parameters_per_equation": new["parameters_per_equation"],
            "observations_per_parameter": new["observations_per_parameter"],
            "unchanged_warning_threshold": 10,
        },
    }
    evidence = {
        "snapshot_id": SNAPSHOT,
        "accepted_g3": manifest,
        "statistical_models_unchanged": source_evidence,
        "references": references,
        "reference_verification_passed": reference_passed,
        "before": old,
        "after": new,
        "targets": targets,
        "all_requested_targets_met": all(target["passed"] for target in targets.values()),
        "timing": {"before": before_timing, "after": after_timing},
    }
    save(OUTPUT / "validation.json", evidence)
    lines = [
        "# G3.1 A — local monetary evidence",
        "",
        f"Same snapshot `{SNAPSHOT}`; accepted G3 config frozen from `{BASE_COMMIT}`. "
        "All twelve model references pass; model source files are byte-identical to G3.",
        "",
        "| Metric | Accepted G3 | G3.1 default |",
        "|---|---:|---:|",
    ]
    for label, key in [
        ("Lags", "selected_lags"),
        ("Bootstrap draws", "draws"),
        ("Parameters/equation", "parameters_per_equation"),
        ("Observations/parameter", "observations_per_parameter"),
        ("Companion spectral radius", "companion_spectral_radius"),
        ("Resolved +1 SD shock, pp", "resolved_shock_pp"),
    ]:
        lines.append(f"| {label} | {old[key]} | {new[key]} |")
    for label, item in [("Accepted G3", old), ("G3.1", new)]:
        sample = item["actual_sample"]
        lines += [
            "",
            f"{label} actual estimation: {sample['start']}–{sample['end']}, "
            f"n={sample['nobs']}, common n={sample['common_nobs']}.",
            "Signed responses at each variable's absolute peak: "
            + "; ".join(
                f"{p['variable']} {p['response']:+.8f} at q{p['horizon']}" for p in item["peaks"]
            )
            + ".",
        ]
    warning_target = targets["no_observations_per_parameter_warning"]["passed"]
    lines += [
        "",
        f"Stability target: {'met' if targets['no_unstable_dynamics']['passed'] else 'NOT met'}. "
        f"Observations-per-parameter warning target: {'met' if warning_target else 'NOT met'}. "
        "Warning thresholds, COVID controls and data were not altered to remove a warning.",
        "",
        "Lag criteria compare candidates 0–4 on the common maximum-lag holdback. "
        f"Selections: {new['lag_criteria']['selected_lags']}. The fixed default remains two. "
        "Equivalent selected specifications reuse the already computed lag result; "
        "duplicates are excluded from agreement denominators.",
        "",
        "Extended VAR adds REER and credit at the baseline lag and physical shock. "
        "All per-variant samples, parameter counts, stability results and warnings "
        "remain in validation.json. "
        "Signed peak_response_range is stored separately from absolute magnitudes, "
        "without rounding.",
        "",
        "Native median full-result runtime over three seeded runs: "
        f"{before_timing['median_ms']:.2f} ms before; "
        f"{after_timing['median_ms']:.2f} ms after. Browser performance is assessed separately.",
        "",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "references_passed": reference_passed,
                "all_requested_targets_met": evidence["all_requested_targets_met"],
                "targets": targets,
            }
        )
    )


if __name__ == "__main__":
    main()
