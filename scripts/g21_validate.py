"""Re-run revised templates locally without replacing the accepted G2 evidence."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import numpy as np

from macrolab.analysis.engine import run_analysis
from macrolab.models.var import validation_evidence as var_evidence

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/g21"
SNAPSHOT = "20261021-0025"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def summary(result):
    row = result["results"][0]
    sample = row["actual_sample"]
    item = {
        "status": result["status"],
        "config_hash": result["config_hash"],
        "sample": {key: sample[key] for key in ("start", "end", "nobs", "common_nobs")},
        "warnings": sorted({c["code"] for c in row["checks"] if c["level"] == "warn"}),
        "blocking_checks": [c for c in row["checks"] if c["level"] == "block"],
        "coefficients": [
            {key: c[key] for key in ("term", "estimate", "lower", "upper")}
            for c in row.get("coefficients_table", [])
            if c["term"] not in {"const", "trend"} and "equation" not in c
        ],
        "notes": row.get("notes", []),
        "sensitivity": [
            {
                key: v[key]
                for key in ("variant_id", "status", "sample", "checks", "metrics", "reason")
                if key in v
            }
            for v in row["sensitivity"]["variants"]
        ],
    }
    if "irf" in row:
        irf = row["irf"]
        item["shock_size_pp"] = irf["shock_size"]
        item["shock_normalization"] = irf.get("shock_normalization", {"mode": "fixed"})
        item["peaks"] = []
        for variable in ("gdp_real", "cpi"):
            index = irf["variables"].index(variable)
            values = np.asarray(irf["values"])[:, index]
            peak = int(np.argmax(np.abs(values)))
            item["peaks"].append(
                {
                    "variable": variable,
                    "horizon": irf["periods"][peak],
                    "value": float(values[peak]),
                    "lower": irf["lower"][peak][index],
                    "upper": irf["upper"][peak][index],
                }
            )
    return item


def brief(item):
    if "peaks" in item:
        return "; ".join(
            f"{p['variable']} {p['value']:+.4f} at q{p['horizon']} "
            f"[{p['lower']:+.4f}, {p['upper']:+.4f}]"
            for p in item["peaks"]
        )
    return "; ".join(
        f"{c['term']} {c['estimate']:+.4f} [{c['lower']:+.4f}, {c['upper']:+.4f}]"
        for c in item["coefficients"]
    )


def sample(item):
    s = item["sample"]
    return f"{s['start']}–{s['end']}, n={s['nobs']} (common {s['common_nobs']})"


def main():
    manifest = json.loads((OUTPUT / "before_manifest.json").read_text())
    for paths in manifest.values():
        for key in ("source", "saved"):
            path = (ROOT / paths[key]).resolve()
            if not path.is_relative_to(OUTPUT.parent.resolve()):
                raise ValueError("G2 evidence must stay within local runs")
            if hashlib.sha256(path.read_bytes()).hexdigest() != paths["sha256"]:
                raise ValueError(f"Accepted G2 evidence changed: {paths[key]}")
    linear = runpy.run_path(str(ROOT / "tests/reference/test_linear_models.py"))
    models = linear["validation_evidence"]() + var_evidence()
    if len(models) != 12 or any(
        m["reference_max_abs_difference"] > m["reference_tolerance"] for m in models
    ):
        raise RuntimeError("The 12-method reference check did not pass")
    templates = {}
    for path in sorted((ROOT / "configs/templates").glob("*.json")):
        before = json.loads((ROOT / manifest[path.stem]["saved"]).read_text())
        config = json.loads(path.read_text())
        if config["snapshot_id"] != SNAPSHOT or before["snapshot_id"] != SNAPSHOT:
            raise ValueError("Before/after comparison requires the same accepted snapshot")
        after = run_analysis(config)
        write(OUTPUT / "after" / path.name, after)
        if after["status"] != "ok":
            raise RuntimeError(f"Revised template blocked: {path.stem}")
        templates[path.stem] = {"before": summary(before), "after": summary(after)}
    evidence = {
        "snapshot_id": SNAPSHOT,
        "g2_preserved": manifest,
        "reference_models": models,
        "templates": templates,
    }
    write(OUTPUT / "validation.json", evidence)
    lines = [
        "# G2.1 template-default comparison",
        "",
        f"Local DRAFT review on the unchanged accepted snapshot `{SNAPSHOT}`. "
        "All four revised templates pass their blocking checks. "
        "All 12 original method reference checks pass; "
        "no statistical model implementation changed.",
        "",
        "Original G2 JSON files remain byte-identical; checksums and complete results are in "
        "`runs/g21/before_manifest.json`, `runs/g21/before/`, `runs/g21/after/` and "
        "`runs/g21/validation.json`. All intervals below are pointwise: 68% for IRFs, "
        "95% for regression coefficients. Peaks are selected absolute maxima, including impact.",
        "",
        "| Template | Before sample | After sample | Before peaks/coefficient [interval] "
        "| After peaks/coefficient [interval] |",
        "|---|---|---|---|---|",
    ]
    for name, comparison in templates.items():
        before, after = comparison["before"], comparison["after"]
        lines.append(
            f"| {name} | {sample(before)} | {sample(after)} | {brief(before)} | {brief(after)} |"
        )
    monetary = templates["monetary_policy"]["after"]
    lines += [
        "",
        f"Monetary normalization: the former +1 pp request becomes a fitted +1 SD, "
        f"**+{monetary['shock_size_pp']:.6f} pp**. The SD is L[k,k] for "
        "L L′ = SSE / residual df, using the stated recursive order and actual fitted sample; "
        "it is not the empirical ddof=1 SD of recovered shocks. The bands condition on this "
        "resolved physical size. +0.25 pp and +1 pp remain explicit fixed-size options.",
        "",
        "GDP and CPI now use quarter-on-quarter annualised growth, so the before/after "
        "response magnitudes are not the same estimand. Brent is an exogenous log level; "
        "three intervention dummies apply exactly to 2020Q1–Q3. Lag/order comparisons retain "
        "the baseline physical shock; COVID-included and end-2019 scenarios resolve their "
        "own fitted one-SD sizes. The output/price puzzles and unstable-system warning are "
        "retained, not tuned away.",
    ]
    lines += [
        "",
        *[
            note
            for note in monetary["notes"]
            if "estimated output" in note or "estimated price" in note
        ],
    ]
    lines += [
        "",
        "Taylor now starts with 1999Q1–2008Q4. Full-sample comparison recomputes the "
        "HP gap through the full endpoint; recent-half-of-full-sample retains those full-sample "
        "filter values and changes only the estimation sample. Effective-lower-bound periods "
        "can distort an unconstrained linear interest-rate rule. The HP gap is retrospective.",
        "",
        "Okun now matches year-over-year unemployment-rate changes to year-over-year GDP "
        "growth. The quarterly alternative uses quarterly unemployment changes and "
        "100×quarterly log GDP changes (not annualised). Different horizons are displayed "
        "separately and excluded from same-estimand coefficient agreement. Phillips is unchanged.",
        "",
        "| Template | After warning codes | Sensitivity alternatives |",
        "|---|---|---|",
    ]
    for name, comparison in templates.items():
        after = comparison["after"]
        statuses = "; ".join(f"{v['variant_id']}: {v['status']}" for v in after["sensitivity"])
        lines.append(f"| {name} | {', '.join(after['warnings']) or 'none'} | {statuses} |")
    lines += [
        "",
        "These are conditional model results and descriptive associations. "
        "No additional source data were fetched, no v1 method was enabled, and nothing "
        "was pushed, deployed or published. G2.1 flows directly into G3 review.",
        "",
    ]
    (ROOT / "docs/G2_1_RESULTS.md").write_text("\n".join(lines))
    print(json.dumps({"templates": len(templates), "references": len(models), "status": "passed"}))


if __name__ == "__main__":
    main()
