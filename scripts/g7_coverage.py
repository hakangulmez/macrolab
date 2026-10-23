"""Paired, fixed-DGP G6 HAC versus lag-augmented HC1 recovery; no tuning."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from statsmodels.api import OLS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from g6_validate import summaries  # noqa: E402

from macrolab.models.lp import fit  # noqa: E402
from macrolab.models.var import moving_average  # noqa: E402
from tests.v1.fixtures import A, P, lp_case  # noqa: E402


def main():
    started = time.perf_counter()
    truth = (moving_average(A, 12) @ P[:, 0])[:, 1]
    results = []
    for n in (120, 240):
        for augmented in (False, True):
            estimates = []
            covers = []
            max_beta = 0.0
            max_se = 0.0
            for rep in range(200):
                data, config = lp_case(n, seed=20261022 + rep)
                config["model"]["params"]["lag_augmented"] = augmented
                rows = fit(data, config)["local_projection"]["horizons"]
                p = 2 + int(augmented)
                anchors = np.arange(p, n - 12)
                x = np.column_stack(
                    [np.ones(len(anchors)), data.frame.shock.iloc[anchors]]
                    + [
                        data.frame[name].iloc[anchors - lag]
                        for lag in range(1, p + 1)
                        for name in ["shock", "x", "y"]
                    ]
                )
                for h, row in enumerate(rows):
                    ref = OLS(data.frame.y.iloc[anchors + h].to_numpy(), x).fit(
                        cov_type="HC1" if augmented else "HAC",
                        cov_kwds={} if augmented else {"maxlags": h + 1, "use_correction": False},
                        use_t=False,
                    )
                    max_beta = max(max_beta, abs(float(ref.params[1]) - row["estimate"]))
                    max_se = max(max_se, abs(float(ref.bse[1]) - row["std_error"]))
                estimates.append([r["estimate"] for r in rows])
                covers.append(
                    [
                        r["bands"]["0.9"]["lower"] <= truth[h] <= r["bands"]["0.9"]["upper"]
                        for h, r in enumerate(rows)
                    ]
                )
            summary = summaries(estimates, covers, truth)
            results.append(
                {
                    "T": n,
                    "inference": "lag_augmented_HC1" if augmented else "HAC",
                    "replications": 200,
                    "horizons": summary,
                    "mean_absolute_coverage_error_pp": float(
                        np.mean([abs(r["coverage_90"] - 0.9) for r in summary]) * 100
                    ),
                    "reference_beta_max": max_beta,
                    "reference_se_max": max_se,
                }
            )
            print(
                n,
                results[-1]["inference"],
                results[-1]["mean_absolute_coverage_error_pp"],
                flush=True,
            )
    selected = all(
        next(r for r in results if r["T"] == n and r["inference"] == "lag_augmented_HC1")[
            "mean_absolute_coverage_error_pp"
        ]
        < next(r for r in results if r["T"] == n and r["inference"] == "HAC")[
            "mean_absolute_coverage_error_pp"
        ]
        for n in (120, 240)
    )
    report = {
        "selection_rule": (
            "Before running: lower mean absolute deviation from 90% over all 13 "
            "horizons, separately at both T values; same seeds/DGP, no tuning."
        ),
        "default": "lag_augmented_HC1" if selected else "HAC",
        "results": results,
        "seconds": time.perf_counter() - started,
    }
    (ROOT / "runs/g7/coverage.json").write_text(json.dumps(report, indent=2) + "\n")
    assert all(h["bias_pass"] and h["coverage_floor_pass"] for r in results for h in r["horizons"])
    assert all(max(r["reference_beta_max"], r["reference_se_max"]) < 1e-8 for r in results)


if __name__ == "__main__":
    main()
