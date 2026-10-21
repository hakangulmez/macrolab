"""Fixed-seed coefficient recovery and interval coverage; thresholds are not tuned."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from macrolab.models.base import AnalysisData
from macrolab.models.linear import ARDLPlugin, OLSPlugin


def recovery_evidence(output_path: Path | None = None) -> dict[str, dict[str, Any]]:
    # Independent Monte Carlo seeds, 250 observations, and nominal 95% intervals.
    # A wide prespecified binomial acceptance region avoids tuning to one seed.
    repetitions, nobs, seed = 120, 250, 504019
    rng = np.random.default_rng(seed)
    counts = {"sing.ols": 0, "sing.ardl": 0}
    errors: dict[str, list[float]] = {key: [] for key in counts}
    for _ in range(repetitions):
        x = rng.normal(size=nobs)
        noise = rng.normal(size=nobs)
        error = np.zeros(nobs)
        for t in range(1, nobs):
            error[t] = 0.4 * error[t - 1] + noise[t]
        ols_y = 1 + 2 * x + error
        ardl_y = np.zeros(nobs)
        for t in range(1, nobs):
            ardl_y[t] = 0.5 + 0.35 * ardl_y[t - 1] + 1.2 * x[t] + 0.25 * x[t - 1] + noise[t]
        for model_id, plugin, y, term, truth in (
            ("sing.ols", OLSPlugin(), ols_y, "x", 2.0),
            ("sing.ardl", ARDLPlugin(), ardl_y, "x.L0", 1.2),
        ):
            frame = pd.DataFrame(
                {"y": y, "x": x}, index=pd.period_range("1960Q1", periods=nobs, freq="Q")
            )
            config = {
                "series": [
                    {"concept_id": "y", "role": "dependent"},
                    {"concept_id": "x", "role": "regressor"},
                ],
                "model": {
                    "id": model_id,
                    "params": {"covariance": "HAC", "hac_lags": 4, "confidence": 0.95},
                },
            }
            result = plugin.run(AnalysisData(frame), config)
            coefficient = next(row for row in result["coefficients_table"] if row["term"] == term)
            counts[model_id] += coefficient["lower"] <= truth <= coefficient["upper"]
            errors[model_id].append(coefficient["estimate"] - truth)
    evidence = {
        model_id: {
            "passed": 0.85 <= count / repetitions <= 1.0
            and abs(float(np.mean(errors[model_id]))) < 0.05,
            "coverage": count / repetitions,
            "coverage_count": count,
            "repetitions": repetitions,
            "nominal_coverage": 0.95,
            "acceptance_interval": [0.85, 1.0],
            "mean_coefficient_error": float(np.mean(errors[model_id])),
            "rmse": float(np.sqrt(np.mean(np.square(errors[model_id])))),
            "seed": seed,
            "nobs": nobs,
            "covariance": "HAC",
            "hac_lags": 4,
        }
        for model_id, count in counts.items()
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    return evidence


def test_known_coefficients_and_fixed_seed_coverage() -> None:
    results = recovery_evidence()
    assert all(result["passed"] for result in results.values()), results
