"""Rebuild G2 model evidence and real-template results entirely from local inputs."""

from __future__ import annotations

import json
import platform
import runpy
from importlib.metadata import version
from pathlib import Path

from macrolab.analysis.engine import run_analysis
from macrolab.models.registry import get_plugin
from macrolab.models.var import validation_evidence as var_evidence

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/g2"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    linear = runpy.run_path(str(ROOT / "tests/reference/test_linear_models.py"))
    recovery = runpy.run_path(str(ROOT / "tests/synthetic/test_linear_recovery.py"))[
        "recovery_evidence"
    ]()
    models = linear["validation_evidence"]()
    for row in models:
        if row["model_id"] in recovery:
            row["recovery"] = recovery[row["model_id"]]
    models.extend(var_evidence())
    if any(row["reference_max_abs_difference"] > row["reference_tolerance"] for row in models):
        raise RuntimeError("A model exceeded its reference tolerance")
    templates = {}
    for path in sorted((ROOT / "configs/templates").glob("*.json")):
        result = run_analysis(json.loads(path.read_text()))
        (OUTPUT / f"{path.stem}.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )
        templates[path.stem] = {
            key: result[key]
            for key in [
                "status",
                "config_hash",
                "snapshot_id",
                "runtime_ms",
                "label",
                "checks",
                "actual_samples",
            ]
        }
        templates[path.stem]["results"] = [
            {
                key: row.get(key)
                for key in [
                    "country",
                    "model_id",
                    "status",
                    "coefficients_table",
                    "irf",
                    "sensitivity",
                ]
            }
            for row in result["results"]
        ]
    evidence = {
        "python": platform.python_version(),
        "packages": {
            name: version(name)
            for name in ["numpy", "pandas", "scipy", "statsmodels", "arch", "quantecon"]
        },
        "snapshot_id": "20261021-0025",
        "models": models,
        "templates": templates,
    }
    (OUTPUT / "validation.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    for row in models:
        plugin = get_plugin(row["model_id"])
        references = "\n".join(f"- [{r['title']}]({r['url']})" for r in plugin.references)
        outcomes = "\n".join(
            f"- {key}: {value:.8g}" for key, value in row["reference_outputs"].items()
        )
        text = (
            f"""# {plugin.id} — {plugin.title}

G2 validated, local only. Method: {plugin.summary}

Label: **{plugin.label}**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

"""
            + "\n".join(f"- {a}" for a in plugin.assumptions)
            + f"""

## Validation

Maximum absolute reference difference: **{row["reference_max_abs_difference"]:.8g}**;
required tolerance **{row["reference_tolerance"]:.1g}**. Fixture runtime:
**{row["runtime_ms"]:.2f} ms**. Detailed compared outputs:

{outcomes}

Recovery evidence (fixed seeds, thresholds set before the run):

```json
{json.dumps(row["recovery"], indent=2)}
```

Reproduce with `python scripts/g2_validate.py` and `python -m pytest tests/reference
tests/synthetic tests/analysis`. Numerical reference tests cover the primary
estimands, standard errors and intervals where supplied; descriptive and filter
models do not claim probabilistic coefficient recovery. VAR tests include FEVD
adding-up, variable renaming, identified-order dependence and independent normalized
asymptotic delta-method comparison. Rolling fits are checked against future leakage.
Filter reconstruction and reversible transformation identities are tested separately.

## Limits

"""
        )
        limitations = list(row.get("limitations", []))
        if plugin.id.startswith("filter."):
            limitations += [
                "Retrospective filter; the full selected sample influences the fitted trend. "
                "It is not a forecast or a real-time gap estimate."
            ]
        elif plugin.id.startswith("sing."):
            limitations += [
                "Association only; covariance corrections do not identify causal effects. "
                "HAC bandwidth and sample choices affect inference."
            ]
        elif plugin.id == "test.adf_kpss_pp":
            limitations += [
                "Unit-root tests have limited power and depend on trends and lag/bandwidth "
                "choices. Disagreement is retained."
            ]
        elif plugin.id == "test.granger":
            limitations += [
                "Predictive content conditional on selected lags; no causal interpretation."
            ]
        else:
            limitations += [
                "Interpret only the selected, transformed common sample; "
                "no omitted-country imputation or sample extrapolation."
            ]
        text += "\n".join("- " + s for s in limitations) + f"\n\n## References\n\n{references}\n"
        (ROOT / "docs/models" / f"{plugin.id}.md").write_text(text)
    print(
        json.dumps(
            {
                "models": len(models),
                "templates": {name: result["status"] for name, result in templates.items()},
                "evidence": str(OUTPUT / "validation.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
