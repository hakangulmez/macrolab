"""Recover a dated structural shock once, then enforce exact second-stage alignment."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

from macrolab.analysis.seasonality import require_regular_calendar, with_seasonal_controls
from macrolab.analysis.transforms import label as period_label
from macrolab.analysis.transforms import period_frequency
from macrolab.models.base import AnalysisData, check
from macrolab.models.var import VAROLSPlugin, _estimate, _settings, _stable


def fit_excluding_window(
    data: AnalysisData, config: dict[str, Any], settings: dict[str, Any]
) -> tuple[Any, list[int]]:
    """OLS on intact calendar lag rows, never bridge the excluded regime."""
    window = config["model"]["params"]["exclude_window"]
    p = settings["lags"]
    y = data.frame[settings["names"]].to_numpy()
    dates = pd.PeriodIndex(data.frame.index, freq=period_frequency(data.frequency))
    excluded = (dates >= pd.Period(window["start"], freq=period_frequency(data.frequency))) & (
        dates <= pd.Period(window["end"], freq=period_frequency(data.frequency))
    )
    anchors = [t for t in range(p, len(y)) if not excluded[t - p : t + 1].any()]
    fixed = [np.ones((len(y), 1))]
    if settings["trend"] != "c":
        raise ValueError("Excluded-window first stage currently requires a constant")
    exog = [s["concept_id"] for s in config["series"] if s["role"] == "exogenous"]
    if exog:
        fixed.append(data.frame[exog].to_numpy())
    if data.exog is not None:
        fixed.append(data.exog.to_numpy())
    z = np.column_stack(fixed)[anchors]
    z = z[:, np.any(z, axis=0)]
    x = np.column_stack([z] + [y[np.asarray(anchors) - lag] for lag in range(1, p + 1)])
    if np.linalg.matrix_rank(x) != x.shape[1] or len(x) <= x.shape[1]:
        raise ValueError(
            "Excluded-window first-stage design lacks rank or residual degrees of freedom"
        )
    params = np.linalg.lstsq(x, y[anchors], rcond=1e-15)[0]
    residual = y[anchors] - x @ params
    df = len(x) - x.shape[1]
    return SimpleNamespace(
        coefs=params[z.shape[1] :]
        .reshape(p, len(settings["names"]), len(settings["names"]))
        .swapaxes(1, 2),
        sigma_u=residual.T @ residual / df,
        resid=residual,
        k_ar=p,
        names=settings["names"],
        nobs=len(x),
        df_resid=df,
        k_exog=z.shape[1],
        endog_lagged=x,
        params=params,
    ), anchors


def recover(data: AnalysisData, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    data = with_seasonal_controls(data, config)
    require_regular_calendar(data)
    calendar = pd.PeriodIndex(data.frame.index, freq=period_frequency(data.frequency))
    data.frame.index = calendar
    if data.exog is not None:
        data.exog.index = calendar
    settings = _settings(config, recursive=True)
    if config["model"]["params"].get("exclude_window"):
        fitted, anchors = fit_excluding_window(data, config, settings)
    else:
        fitted = _estimate(data, config, settings)
        anchors = list(range(fitted.k_ar, len(data.frame)))
    stable, radius = _stable(np.asarray(fitted.coefs))
    impact = np.linalg.cholesky(np.asarray(fitted.sigma_u))
    structural = np.linalg.solve(impact, np.asarray(fitted.resid).T).T
    index = settings["names"].index(settings["shock"])
    own_impact = float(impact[index, index])
    options = config.get("outputs", {}).get("irf", {})
    size = (
        1.0
        if options.get("shock_mode", "one_sd") == "one_sd"
        else float(options.get("shock_size", 1.0)) / own_impact
    )
    periods = [period_label(data.frame.index[i]) for i in anchors]
    return {
        "periods": periods,
        "values": structural[:, index].tolist(),
        "all_values": structural.tolist(),
        "order": settings["names"],
        "shock": settings["shock"],
        "frequency": data.frequency,
        "unit": "structural standard deviations (residual covariance corrected for df)",
        "own_impact": own_impact,
        "requested_structural_size": size,
        "requested_physical_size": size * own_impact,
        "physical_values": (structural[:, index] * own_impact).tolist(),
        "stable": stable,
        "companion_spectral_radius": radius,
        "first_stage_sample": deepcopy(data.sample),
        "nobs": len(periods),
        "seasonal_controls": data.sample.get("seasonal_controls", {}),
        "identification": "recursive contemporaneous ordering",
        "uncertainty": "conditional second-stage bands ignore first-stage estimation uncertainty",
    }, fitted


def attach(
    data: AnalysisData, shock: dict[str, Any], name: str = "identified_impulse"
) -> AnalysisData:
    if shock.get("frequency") != data.frequency:
        raise ValueError("Shock requires the same frequency")
    dates = pd.PeriodIndex(shock["periods"], freq=period_frequency(data.frequency))
    target = pd.PeriodIndex(data.frame.index, freq=period_frequency(data.frequency))
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Identified shock dates must be unique and increasing")
    if len(shock["values"]) != len(dates) or not np.isfinite(shock["values"]).all():
        raise ValueError("Identified shock values must be finite and match their dates")
    if not target.isin(dates).all():
        raise ValueError(
            "Identified shock does not cover every second-stage input date; "
            "restrict the sample explicitly"
        )
    result = deepcopy(data)
    result.frame[name] = pd.Series(shock["values"], index=dates).loc[target].to_numpy()
    result.metadata[name] = {
        "identified_shock": True,
        "status": "available_note",
        "source": "first-stage recursive VAR",
        "first_stage": {
            key: deepcopy(shock[key])
            for key in ("shock", "order", "own_impact", "frequency", "nobs")
        },
    }
    result.sample["identified_shock"] = {
        k: shock[k] for k in ("shock", "own_impact", "requested_structural_size", "frequency")
    }
    return result


class ExternalSeriesPlugin(VAROLSPlugin):
    id, family, title = "ident.external_series", "identification", "Reusable identified shock"
    summary = "Expose dated orthogonalised residuals from a first-stage recursive VAR."
    label = "Generated shock; conditional on the stated recursive identification"
    params = deepcopy(VAROLSPlugin.params)
    params["properties"]["exclude_window"] = {"type": "object", "default": {}}

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            data = with_seasonal_controls(data, config)
            checks = super().check(data, config)
            if not any(c["level"] == "block" for c in checks):
                shock, _ = recover(data, config)
                if shock["companion_spectral_radius"] >= 0.98:
                    checks.append(
                        check(
                            "warn",
                            "first_stage_persistence",
                            "First-stage VAR is unstable or near a "
                            "unit root; orthogonalised residuals "
                            "remain usable, but persistence and identification warrant caution.",
                            companion_spectral_radius=shock["companion_spectral_radius"],
                        )
                    )
            return checks
        except (ValueError, np.linalg.LinAlgError) as exc:
            return [check("block", "external_shock_inputs", str(exc))]

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        shock, _ = recover(data, config)
        return {
            "label": self.label,
            "identified_shock": shock,
            "diagnostics": {
                "estimated_indices": shock["periods"],
                "nobs": shock["nobs"],
                "stable": shock["stable"],
                "companion_spectral_radius": shock["companion_spectral_radius"],
            },
            "notes": [shock["uncertainty"]],
        }
