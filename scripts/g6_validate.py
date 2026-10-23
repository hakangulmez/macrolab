"""Fixed G6 Monte Carlo experiments; no network, selection or retuning."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from statsmodels.api import OLS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macrolab.ident.bootstrap import joint_bootstrap  # noqa: E402
from macrolab.ident.external_series import attach, recover  # noqa: E402
from macrolab.models.lp import fit  # noqa: E402
from macrolab.models.var import moving_average  # noqa: E402
from tests.v1.fixtures import A, P, lp_case, two_stage  # noqa: E402


def summaries(estimates, covers, truth):
    matrix = np.asarray(estimates)
    bias = matrix.mean(axis=0) - truth
    se = matrix.std(axis=0, ddof=1) / np.sqrt(len(matrix))
    rates = np.asarray(covers).mean(axis=0)
    return [
        {
            "horizon": h,
            "truth": float(truth[h]),
            "mean_estimate": float(matrix[:, h].mean()),
            "bias": float(bias[h]),
            "monte_carlo_se": float(se[h]),
            "coverage_90": float(rates[h]),
            "bias_pass": bool(abs(bias[h]) <= max(0.10, 3 * se[h])),
            "coverage_floor_pass": bool(rates[h] >= 0.75),
        }
        for h in range(len(truth))
    ]


def run(kind, n, replications=200):
    started = time.perf_counter()
    estimates, coverage, joint_coverage = [], [], []
    reference_diff = {"coefficient": 0.0, "standard_error": 0.0}
    boot_failures = 0
    truth = (moving_average(A, 12) @ P[:, 0])[:, 1]
    if kind == "two_stage":
        truth = np.zeros(13)
        truth[0] = 0.6
        for h in range(1, 13):
            truth[h] = 0.5 * truth[h - 1] - (0.1 * truth[h - 2] if h >= 2 else 0)
    for rep in range(replications):
        if kind == "lp":
            data, config = lp_case(n, seed=20261022 + rep)
            result = fit(data, config)
            # Independent direct statsmodels construction, all horizons.
            anchors = np.arange(2, n - 12)
            x = np.column_stack(
                [np.ones(len(anchors)), data.frame.shock.iloc[anchors]]
                + [
                    data.frame[name].iloc[anchors - lag]
                    for lag in [1, 2]
                    for name in ["shock", "x", "y"]
                ]
            )
            for h, row in enumerate(result["local_projection"]["horizons"]):
                reference = OLS(data.frame.y.iloc[anchors + h].to_numpy(), x).fit(
                    cov_type="HAC",
                    cov_kwds={"maxlags": h + 1, "use_correction": False},
                    use_t=False,
                )
                reference_diff["coefficient"] = max(
                    reference_diff["coefficient"], abs(float(reference.params[1]) - row["estimate"])
                )
                reference_diff["standard_error"] = max(
                    reference_diff["standard_error"],
                    abs(float(reference.bse[1]) - row["std_error"]),
                )
        else:
            first, fc, country, config = two_stage(n, seed=20261023 + rep)
            shock, _ = recover(first, fc)
            result = fit(attach(country, shock), config)
            boot = joint_bootstrap(
                first,
                fc,
                {"AAA": country},
                {"AAA": config},
                draws=200,
                seed=20261023 + rep + 1000 * n,
            )
            band = boot["bands"]["AAA"]["0.9"]
            joint_coverage.append(
                (np.asarray(band["lower"]) <= truth) & (truth <= np.asarray(band["upper"]))
            )
            boot_failures += boot["failed_draws"]
        rows = result["local_projection"]["horizons"]
        estimates.append([r["estimate"] for r in rows])
        coverage.append(
            [
                r["bands"]["0.9"]["lower"] <= truth[h] <= r["bands"]["0.9"]["upper"]
                for h, r in enumerate(rows)
            ]
        )
        if rep % 10 == 0 or rep == replications - 1:
            print(
                f"{kind} T={n}: {rep + 1}/{replications}, {time.perf_counter() - started:.1f}s",
                flush=True,
            )
    report = {
        "experiment": kind,
        "T": n,
        "replications": replications,
        "horizon": 12,
        "protocol": "docs/G6_VALIDATION_PROTOCOL.md",
        "seconds": time.perf_counter() - started,
        "conditional": summaries(estimates, coverage, truth),
        "reference_maximum_absolute_difference": reference_diff,
        "joint_bootstrap_draws": 200 if kind == "two_stage" else None,
        "failed_bootstrap_draws": boot_failures,
    }
    if joint_coverage:
        report["joint"] = summaries(estimates, joint_coverage, truth)
    report["passed"] = (
        all(r["bias_pass"] and r["coverage_floor_pass"] for r in report["conditional"])
        and all(r["coverage_floor_pass"] for r in report.get("joint", []))
        and max(reference_diff.values()) < 1e-8
    )
    output = ROOT / "runs/g6"
    output.mkdir(exist_ok=True, parents=True)
    (output / f"recovery-{kind}-{n}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["lp", "two_stage"], required=True)
    parser.add_argument("--n", type=int, choices=[120, 240], required=True)
    options = parser.parse_args()
    report = run(options.kind, options.n)
    if not report["passed"]:
        raise SystemExit("Fixed validation diagnostics flagged: report retained; do not retune.")
