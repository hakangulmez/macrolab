"""Forecast-only preparation, origin-local transformations and original-unit inversion."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm  # type: ignore[import-untyped]

from macrolab.analysis.data import prepare_country
from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import apply_transform, label, period_frequency
from macrolab.ident.bootstrap import CancelledError
from macrolab.models.base import AnalysisData, check

IDS = {"uni.arima", "fc.var", "fc.eval"}
VINTAGE = "Final-vintage data; real-time performance may be worse."
EVALUATION_LABEL = "pseudo-out-of-sample, final-vintage data; real-time performance may be worse"
Progress = Callable[[dict[str, Any]], None] | None
Cancelled = Callable[[], bool] | None


def tick(progress: Progress, cancelled: Cancelled, phase: str, done: int, total: int) -> None:
    if cancelled and cancelled():
        raise CancelledError("Computation cancelled")
    if progress:
        progress({"phase": phase, "completed": done, "total": total})


def names(config: dict[str, Any]) -> list[str]:
    return [s["concept_id"] for s in config["series"] if s["role"] != "exogenous"]


def prepare_forecast(
    config: dict[str, Any], bundle: dict[str, Any], country: str
) -> tuple[AnalysisData, list[dict[str, Any]]]:
    raw = deepcopy(config)
    if config["model"]["params"].get("evaluation_scale") == "transformed":
        # Causal y/y transforms need prehistory; it is not counted as training.
        start = pd.Period(config["sample"]["start"], freq=config["frequency"])
        raw["sample"]["start"] = label(start - (12 if config["frequency"] == "M" else 4))
    for s in raw["series"]:
        s.update(transform="level", transform_params={})
    data, checks = prepare_country(raw, bundle, country)
    data.sample["preparation_config"] = deepcopy(
        {k: config[k] for k in ("frequency", "sample", "series", "aggregation", "special_periods")}
    )
    data.sample["forecast_preparation"] = (
        "Raw frequency-converted observations; transformations and "
        "estimated scales recomputed on each training prefix."
    )
    if any(c["code"] == "sample_fragmented" for c in checks):
        checks.append(
            check(
                "block",
                "forecast_gaps",
                (
                    "Choose an explicitly contiguous sample. Forecasting and "
                    "evaluation do not choose a training window using later gaps."
                ),
            )
        )
    checks.extend(forecast_checks(data, config))
    return data, checks


def forecast_checks(data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    p = config["model"]["params"]
    if data.frequency not in {"M", "Q"}:
        issues.append(
            check(
                "block", "forecast_frequency", "Forecasting supports monthly and quarterly samples."
            )
        )
    if any(s["transform"] in {"hp_cycle", "hamilton_cycle"} for s in config["series"]):
        issues.append(
            check(
                "block",
                "forecast_lossy_filter",
                (
                    "HP and Hamilton cycles are lossy and cannot be inverted to "
                    "original units. They are blocked for forecasting and evaluation; "
                    "select levels or a lossless transform. No full-sample filter or "
                    "scaling enters an origin."
                ),
            )
        )
    if (
        any(s["role"] == "exogenous" for s in config["series"])
        and p.get("future_exog", "unspecified") == "unspecified"
    ):
        issues.append(
            check(
                "block",
                "forecast_exog_path",
                (
                    "Select an explicit future path for exogenous regressors before "
                    "forecasting (held at last transformed value or zero). Future "
                    "observations are never used."
                ),
            )
        )
    if not names(config) or (config["model"]["id"] == "uni.arima" and len(names(config)) != 1):
        issues.append(
            check(
                "block",
                "forecast_variables",
                (
                    "ARIMA needs exactly one target; VAR/evaluation need one or more "
                    "targets. Other selected series must have an explicit exogenous "
                    "role."
                ),
            )
        )
    if len(names(config)) > 8:
        issues.append(
            check("block", "forecast_variables", "Select at most eight forecast variables.")
        )
    if p.get("horizon", 8) > (24 if data.frequency == "M" else 12):
        issues.append(
            check("block", "forecast_horizon", "The maximum horizon is 12 quarters or 24 months.")
        )
    if config["special_periods"]["covid"] == "exclude":
        issues.append(
            check(
                "block",
                "forecast_calendar",
                (
                    "Excluding historical periods breaks forecast lags; use COVID "
                    "dummies or an explicit pre-COVID sample."
                ),
            )
        )
    if len(data.frame) < 20:
        issues.append(
            check("block", "forecast_sample", "At least 20 contiguous observations are required.")
        )
    if config["model"]["id"] == "fc.eval" and len(data.frame) <= (
        120 if data.frequency == "M" else 40
    ):
        issues.append(
            check(
                "block",
                "forecast_origins",
                "Evaluation needs observations beyond its initial 120 months or 40 quarters.",
            )
        )
    return issues


def training(raw: AnalysisData, config: dict[str, Any], stop: int | None = None) -> AnalysisData:
    """The only transformation entry point: sees no data after the origin."""
    prefix = raw.frame.iloc[:stop].copy() if stop is not None else raw.frame.copy()
    calendar = pd.PeriodIndex(prefix.index, freq=period_frequency(raw.frequency))
    if not len(calendar) or not calendar.equals(
        pd.period_range(calendar[0], calendar[-1], freq=calendar.freq)
    ):
        raise ValueError("Training observations must form a regular contiguous calendar")
    columns, details = {}, {}
    for spec in config["series"]:
        name = spec["concept_id"]
        values, detail = apply_transform(
            pd.Series(prefix[name].to_numpy(), index=calendar),
            spec["transform"],
            raw.frequency,
            spec.get("transform_params", {}),
        )
        values.index = pd.Index([label(i) for i in values.index])
        columns[name], details[name] = values, detail
    frame = pd.DataFrame(columns)
    if config["model"]["params"].get("evaluation_scale") == "transformed":
        frame = frame.loc[frame.index >= config["sample"]["start"]]
    finite = np.isfinite(frame.to_numpy()).all(axis=1)
    good = np.flatnonzero(finite)
    if not len(good) or not finite[good[0] :].all():
        raise ValueError("Transformations leave internal missing or invalid values at this origin")
    frame = frame.iloc[int(good[0]) :]
    if len(frame) < 12:
        raise ValueError("Too few transformed training observations at this origin")
    result = AnalysisData(
        frame,
        raw.country,
        raw.frequency,
        deepcopy(raw.sample),
        raw.metadata,
        None if raw.exog is None else raw.exog.reindex(frame.index),
    )
    result.sample["transforms"] = details
    result.sample["origin"] = str(prefix.index[-1])
    return with_seasonal_controls(result, config)


def future_controls(
    data: AnalysisData, config: dict[str, Any], horizon: int
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    selected = [s["concept_id"] for s in config["series"] if s["role"] == "exogenous"]
    columns = selected + ([] if data.exog is None else list(data.exog))
    past = data.frame[selected].copy()
    if data.exog is not None:
        past = pd.concat([past, data.exog], axis=1)
    # A future-only COVID dummy must not create a singular historical column.
    columns = [c for c in columns if not c.startswith("covid_") or past[c].any()]
    past = past[columns]
    future = np.zeros((horizon, len(columns)))
    periods = pd.period_range(
        pd.Period(data.frame.index[-1], freq=data.frequency) + 1,
        periods=horizon,
        freq=data.frequency,
    )
    assumption = config["model"]["params"].get("future_exog", "unspecified")
    notes = [
        "Future COVID dummies are zero.",
        "Seasonal controls follow the known future calendar.",
    ]
    if selected:
        if assumption == "unspecified":
            raise ValueError("An explicit future exogenous path is required")
        notes.append(
            "Selected exogenous regressors: "
            + (
                "held at last transformed value."
                if assumption == "hold_last"
                else "set to zero in transformed units."
            )
        )
    else:
        notes.append("No selected exogenous regressors.")
    for j, name in enumerate(columns):
        if name in selected and assumption == "hold_last":
            future[:, j] = float(past[name].iloc[-1])
        elif name.startswith("season_"):
            season = int(name.split("_")[1])
            future[:, j] = (
                (periods.month if data.frequency == "M" else periods.quarter) == season
            ).astype(float)
    return past.to_numpy(), future, columns, notes


def invert_paths(
    paths: np.ndarray, spec: dict[str, Any], raw: np.ndarray, frequency: str, detail: dict[str, Any]
) -> np.ndarray:
    """Vectorized lossless inversion. Never clip or discard out-of-domain draws."""
    transform = spec["transform"]
    result = np.array(paths, dtype=float, copy=True)
    if transform == "log":
        result = np.exp(result)
    elif transform == "index_to_base":
        result *= detail["base_value"] / 100
    elif transform != "level":
        lag = (12 if frequency == "M" else 4) if transform.startswith("yoy") else 1
        for h in range(result.shape[1]):
            prior = raw[-lag + h] if h < lag else result[:, h - lag]
            v = result[:, h].copy()
            if transform in {"diff", "yoy_diff"}:
                result[:, h] = prior + v
            elif transform == "log_diff":
                result[:, h] = prior * np.exp(v / 100)
            elif transform in {"yoy_pct", "qoq_saar"}:
                if np.any(v <= -100) or np.any(np.asarray(prior) <= 0):
                    raise ValueError(
                        "Simulated growth leaves the inverse-transform domain (≤ −100% or "
                        "nonpositive level); no draws were dropped. Choose log "
                        "differences or a valid alternative specification."
                    )
                result[:, h] = prior * ((1 + v / 100) ** (0.25 if transform == "qoq_saar" else 1))
            else:
                raise ValueError("Unsupported lossless inverse transformation")
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite predictive paths; no explosive paths were dropped")
    return result


def original_distribution(
    mean: np.ndarray,
    covariance: np.ndarray | None,
    paths: np.ndarray | None,
    spec: dict[str, Any],
    raw: np.ndarray,
    frequency: str,
    detail: dict[str, Any],
    seed: int,
    draws: int = 10000,
) -> dict[str, Any]:
    transform = spec["transform"]
    analytic = covariance is not None and transform in {
        "level",
        "diff",
        "yoy_diff",
        "index_to_base",
    }
    if analytic:
        h = len(mean)
        origin = invert_paths(np.zeros((1, h)), spec, raw, frequency, detail)[0]
        jacobian = (invert_paths(np.eye(h), spec, raw, frequency, detail) - origin).T
        central = invert_paths(mean[None, :], spec, raw, frequency, detail)[0]
        sd = np.sqrt(np.maximum(0, np.diag(jacobian @ covariance @ jacobian.T)))
        bands = {
            str(level): {
                "lower": (central - norm.ppf((1 + level) / 2) * sd).tolist(),
                "upper": (central + norm.ppf((1 + level) / 2) * sd).tolist(),
            }
            for level in (0.68, 0.9)
        }
        method = "Analytic Gaussian linear inverse, using the full joint horizon covariance."
    else:
        if paths is None:
            if covariance is None:
                raise ValueError("Predictive paths or joint covariance are required")
            # Positive definite joint forecast covariance; Cholesky order fixed across runtimes.
            paths = (
                mean
                + np.random.default_rng(seed).normal(size=(draws, len(mean)))
                @ np.linalg.cholesky(covariance).T
            )
        original = invert_paths(paths, spec, raw, frequency, detail)
        central = original.mean(axis=0)
        bands = {
            str(level): {
                "lower": np.quantile(original, (1 - level) / 2, axis=0).tolist(),
                "upper": np.quantile(original, (1 + level) / 2, axis=0).tolist(),
            }
            for level in (0.68, 0.9)
        }
        method = (
            f"Seeded predictive simulation; {len(original)} paths, original-unit mean "
            "and equal-tail quantiles; no path exclusion."
        )
    return {
        "mean": central.tolist(),
        "bands": bands,
        "inverse_method": method,
        "transform": transform,
    }


def original_unit(raw: AnalysisData, name: str) -> str:
    card = raw.metadata.get(name, {})
    units = {
        str(v.get("unit_label") or v.get("unit"))
        for v in card.get("source_segments", [])
        if v.get("unit_label") or v.get("unit")
    }
    return str(
        card.get("unit_label")
        or card.get("unit")
        or (next(iter(units)) if len(units) == 1 else "Original source units; see series card")
    )


def forecast_payload(
    raw: AnalysisData,
    data: AnalysisData,
    config: dict[str, Any],
    distributions: dict[str, Any],
    method: str,
    notes: list[str],
    **extra: Any,
) -> dict[str, Any]:
    horizon = len(next(iter(distributions.values()))["mean"])
    periods = pd.period_range(
        pd.Period(data.frame.index[-1], freq=data.frequency) + 1,
        periods=horizon,
        freq=data.frequency,
    )
    return {
        "forecast": {
            "method": method,
            "variables": list(distributions),
            "periods": [label(p) for p in periods],
            "origin": str(data.frame.index[-1]),
            "distributions": distributions,
            "history": {
                n: {
                    "periods": list(map(str, raw.frame.index[-20:])),
                    "values": raw.frame[n].iloc[-20:].tolist(),
                }
                for n in distributions
            },
            "units": {n: original_unit(raw, n) for n in distributions},
            "assumptions": [VINTAGE, *notes],
            **extra,
        },
        "diagnostics": {
            "estimated_indices": list(map(str, data.frame.index)),
            "transforms": data.sample["transforms"],
            "future_covid": "zero",
        },
        "checks": [],
        "sensitivity": {
            "status": "ok",
            "variants": [],
            "interpretation": "Descriptive specification sensitivity, not a joint test.",
        },
    }
