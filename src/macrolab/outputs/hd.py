"""Historical accounting including deterministic and initial-condition components."""

from __future__ import annotations

from typing import Any

import numpy as np

from macrolab.analysis.seasonality import require_regular_calendar, with_seasonal_controls
from macrolab.models.base import AnalysisData, check
from macrolab.models.var import VAROLSPlugin, _estimate, _settings, _stable

LABEL = (
    "Model-based accounting of the past under the recursive identification, "
    "not evidence of what caused each movement."
)


def decompose(fitted: Any, dates: list[str]) -> dict[str, Any]:
    a, y = np.asarray(fitted.coefs), np.asarray(fitted.endog)
    stable, radius = _stable(a)
    if not stable:
        raise ValueError("Historical decomposition requires a stable VAR")
    p, k = fitted.k_ar, fitted.neqs
    impact = np.linalg.cholesky(np.asarray(fitted.sigma_u))
    structural = np.linalg.solve(impact, np.asarray(fitted.resid).T).T
    deterministic_input = (
        np.asarray(fitted.endog_lagged[:, : fitted.k_exog])
        @ np.asarray(fitted.params)[: fitted.k_exog]
    )
    contributions = np.zeros((len(y), k, k))
    initial, deterministic = np.zeros_like(y), np.zeros_like(y)
    initial[:p] = y[:p]
    for t in range(p, len(y)):
        contributions[t] = impact * structural[t - p][None, :]
        deterministic[t] = deterministic_input[t - p]
        for lag in range(1, p + 1):
            contributions[t] += a[lag - 1] @ contributions[t - lag]
            initial[t] += a[lag - 1] @ initial[t - lag]
            deterministic[t] += a[lag - 1] @ deterministic[t - lag]
    reconstructed = contributions.sum(axis=2) + initial + deterministic
    error = float(np.max(np.abs(reconstructed - y)))
    if error > 1e-8:
        raise ValueError("Historical accounting identity exceeds 1e-8")
    return {
        "label": LABEL,
        "periods": dates,
        "variables": list(fitted.names),
        "shocks": list(fitted.names),
        "contributions": contributions.tolist(),
        "initial_condition": initial.tolist(),
        "deterministic": deterministic.tolist(),
        "actual": y.tolist(),
        "deviation_from_deterministic": (y - deterministic).tolist(),
        "reconstructed": reconstructed.tolist(),
        "maximum_identity_error": error,
        "stable": True,
        "companion_spectral_radius": radius,
        "initial_periods": dates[:p],
        "uncertainty": "accounting point estimates; no causal attribution",
    }


class HistoricalDecompositionPlugin(VAROLSPlugin):
    id, family, title = "out.hd", "output", "Historical decomposition"
    summary = "Account for past movements under an explicitly ordered stable recursive VAR."
    label = LABEL
    params = {
        **VAROLSPlugin.params,
        "properties": {
            **VAROLSPlugin.params["properties"],
            "hd_match_var": {"type": "boolean"},
        },
    }

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            if not config["model"]["params"].get("hd_match_var"):
                data = with_seasonal_controls(data, config)
            require_regular_calendar(data)
            checks = super().check(data, config)
            if any(c["level"] == "block" for c in checks):
                return checks
            fitted = _estimate(data, config, _settings(config, recursive=True))
            stable, radius = _stable(np.asarray(fitted.coefs))
            if not stable:
                checks.append(
                    check(
                        "block",
                        "hd_unstable",
                        "Historical decomposition is unavailable for an unstable VAR.",
                        phase="post_estimation",
                    )
                )
            elif radius >= 0.98:
                checks.append(
                    check(
                        "warn",
                        "hd_persistent",
                        (
                            "The VAR is near a unit root; historical contributions "
                            "are sensitive to persistence."
                        ),
                        phase="post_estimation",
                        largest_root=radius,
                    )
                )
            return checks
        except (ValueError, np.linalg.LinAlgError) as exc:
            return [check("block", "hd_inputs", str(exc))]

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        if not config["model"]["params"].get("hd_match_var"):
            data = with_seasonal_controls(data, config)
        require_regular_calendar(data)
        fitted = _estimate(data, config, _settings(config, recursive=True))
        return {
            "label": LABEL,
            "historical_decomposition": decompose(fitted, list(map(str, data.frame.index))),
            "diagnostics": {
                "estimated_indices": list(map(str, data.frame.index[fitted.k_ar :])),
                "nobs": int(fitted.nobs),
                "stable": True,
            },
            "notes": [LABEL],
        }
