"""Iterated reduced-form forecasts with re-estimation or NIW predictive draws."""

from __future__ import annotations

from typing import Any

import numpy as np

from macrolab.models.arima import COMMON_PARAMS
from macrolab.models.base import AnalysisData, BasePlugin
from macrolab.models.bvar import draw_parameters, posterior
from macrolab.models.forecast_common import (
    Cancelled,
    Progress,
    forecast_checks,
    forecast_payload,
    future_controls,
    invert_paths,
    names,
    original_distribution,
    tick,
    training,
)
from macrolab.models.linear import choice, integer, schema


def var_design(data: AnalysisData, config: dict[str, Any], horizon: int) -> dict[str, Any]:
    selected = names(config)
    p = int(config["model"]["params"].get("lags", 2))
    y = data.frame[selected].to_numpy()
    controls, future, control_names, notes = future_controls(data, config, horizon)
    # Columns that become inactive after lag holdback carry no estimated effect.
    active = [
        j
        for j, name in enumerate(control_names)
        if not name.startswith("covid_") or np.any(controls[p:, j])
    ]
    controls, future = controls[:, active], future[:, active]
    deterministic = np.column_stack([np.ones(len(y)), controls])
    q = deterministic.shape[1]
    x = np.column_stack([deterministic[p:], *[y[p - i : len(y) - i] for i in range(1, p + 1)]])
    scales = []
    for j in range(y.shape[1]):
        arx = np.column_stack(
            [np.ones(len(y) - p), *[y[p - i : len(y) - i, j] for i in range(1, p + 1)]]
        )
        rank = np.linalg.matrix_rank(arx)
        if len(arx) <= rank:
            raise ValueError("Insufficient AR(p) residual degrees of freedom at this origin")
        error = y[p:, j] - arx @ np.linalg.lstsq(arx, y[p:, j], rcond=None)[0]
        scales.append(np.sqrt(error @ error / (len(arx) - rank)))
    if not np.isfinite(scales).all() or min(scales) <= np.finfo(float).eps:
        raise ValueError("Nonpositive AR(p) residual scale")
    transforms = {s["concept_id"]: s["transform"] for s in config["series"]}
    return {
        "x": x,
        "y": y[p:],
        "history": y,
        "sigmas": np.asarray(scales),
        "own_means": np.array(
            [1 if transforms[n] in {"level", "log", "index_to_base"} else 0 for n in selected]
        ),
        "n": len(selected),
        "p": p,
        "deterministic": q,
        "initial_mean": y[:p].mean(axis=0),
        "past_controls": deterministic,
        "future_controls": np.column_stack([np.ones(horizon), future]),
        "notes": notes,
        "control_names": [control_names[j] for j in active],
        "names": selected,
    }


def iterate(
    beta: np.ndarray,
    history: np.ndarray,
    future: np.ndarray,
    p: int,
    innovations: np.ndarray | None = None,
) -> np.ndarray:
    # A single or batched coefficient matrix; fixed lag-major ordering.
    single = beta.ndim == 2
    if single:
        beta = beta[None, :]
    count, _, n = beta.shape
    h = len(future)
    values = np.empty((count, p + h, n))
    values[:, :p] = history[-p:]
    for i in range(h):
        row = np.concatenate(
            [
                np.broadcast_to(future[i], (count, len(future[i]))),
                *[values[:, p + i - lag] for lag in range(1, p + 1)],
            ],
            axis=1,
        )
        values[:, p + i] = np.einsum("di,dij->dj", row, beta)
        if innovations is not None:
            values[:, p + i] += innovations[:, i]
    return values[0, p:] if single else values[:, p:]


def predict_var(
    data: AnalysisData,
    config: dict[str, Any],
    horizon: int,
    *,
    intervals: bool = True,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> tuple[np.ndarray, np.ndarray | None, dict[str, Any]]:
    d = var_design(data, config, horizon)
    p, x, y = d["p"], d["x"], d["y"]
    options = config["model"]["params"]
    kind = options.get("estimator", "ols")
    draws = int(options.get("draws", 500))
    rng = np.random.default_rng(config["seed"])
    if kind == "bvar":
        post = posterior(d, float(options.get("lambda", 0.2)), {})
        beta = post["mean"]
        paths = None
        if intervals:
            coefficients, covariances = draw_parameters(post, draws, config["seed"])
            # Independent deterministic seed stream for future shocks.
            shocks = np.random.default_rng(config["seed"] + 1).normal(size=(draws, horizon, d["n"]))
            shocks = np.einsum("dhi,dji->dhj", shocks, np.linalg.cholesky(covariances))
            paths = iterate(coefficients, d["history"], d["future_controls"], p, shocks)
        detail = {
            "lambda": float(options.get("lambda", 0.2)),
            "ar_residual_scales": d["sigmas"].tolist(),
            "posterior_df": post["df"],
            "coefficient_mean": beta.tolist(),
            "draws": draws if intervals else 0,
            "uncertainty": (
                "NIW posterior coefficient and covariance draws plus future "
                "Gaussian innovations; no draws dropped."
            ),
        }
    else:
        if np.linalg.matrix_rank(x) != x.shape[1] or len(y) <= x.shape[1]:
            raise ValueError(
                "OLS forecast design is rank deficient or has no residual degrees of freedom"
            )
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        errors = y - x @ beta
        errors -= errors.mean(axis=0)
        paths = None
        if intervals:
            # Residual bootstrap training histories, re-estimation, then future shocks.
            training_shocks = errors[rng.integers(0, len(errors), size=(draws, len(y)))]
            training_paths = iterate(
                np.broadcast_to(beta, (draws, *beta.shape)),
                d["history"][:p],
                d["past_controls"][p:],
                p,
                training_shocks,
            )
            betas, residuals = [], []
            for b in range(draws):
                if b % 20 == 0:
                    tick(progress, cancelled, "forecast_bootstrap", b, draws)
                pseudo = np.vstack([d["history"][:p], training_paths[b]])
                bx = np.column_stack(
                    [
                        d["past_controls"][p:],
                        *[pseudo[p - i : len(pseudo) - i] for i in range(1, p + 1)],
                    ]
                )
                if np.linalg.matrix_rank(bx) != bx.shape[1]:
                    raise ValueError(
                        "A bootstrap re-estimation is rank deficient; no draw was discarded"
                    )
                bb = np.linalg.lstsq(bx, pseudo[p:], rcond=None)[0]
                resid = pseudo[p:] - bx @ bb
                betas.append(bb)
                residuals.append(resid - resid.mean(axis=0))
            innovations = np.asarray([e[rng.integers(0, len(e), size=horizon)] for e in residuals])
            paths = iterate(np.asarray(betas), d["history"], d["future_controls"], p, innovations)
            tick(progress, cancelled, "forecast_bootstrap", draws, draws)
        detail = {
            "coefficient_mean": beta.tolist(),
            "draws": draws if intervals else 0,
            "uncertainty": (
                "Residual bootstrap: simulated training histories, full "
                "coefficient re-estimation and future residual draws; no draws "
                "dropped."
            ),
        }
    point = iterate(beta, d["history"], d["future_controls"], p)
    if not np.isfinite(point).all() or (paths is not None and not np.isfinite(paths).all()):
        raise ValueError("Nonfinite predictions; explosive paths are not silently removed")
    return (
        point,
        paths,
        {
            **detail,
            "estimator": kind,
            "lags": p,
            "control_names": d["control_names"],
            "notes": d["notes"],
            "estimated_indices": list(map(str, data.frame.index[p:])),
            "point_method": "Iterated posterior-mean coefficients"
            if kind == "bvar"
            else "Iterated OLS coefficients",
        },
    )


def run_var_forecast(
    raw: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    data = training(raw, config)
    horizon = config["model"]["params"].get("horizon", 8)
    mean, paths, detail = predict_var(data, config, horizon, progress=progress, cancelled=cancelled)
    assert paths is not None
    distributions = {}
    for j, name in enumerate(names(config)):
        spec = next(s for s in config["series"] if s["concept_id"] == name)
        distributions[name] = original_distribution(
            mean[:, j],
            None,
            paths[:, :, j],
            spec,
            raw.frame[name].to_numpy(),
            data.frequency,
            data.sample["transforms"][name],
            config["seed"],
        )
        if detail["estimator"] == "ols" and spec["transform"] in {
            "level",
            "diff",
            "yoy_diff",
            "index_to_base",
        }:
            # Retain the iterated OLS point forecast, not Monte Carlo noise in
            # the bootstrap mean. Bootstrap paths determine the intervals.
            distributions[name]["mean"] = invert_paths(
                mean[:, j][None, :],
                spec,
                raw.frame[name].to_numpy(),
                data.frequency,
                data.sample["transforms"][name],
            )[0].tolist()
            distributions[name]["inverse_method"] = (
                "Analytic inverse of the iterated OLS point forecast; "
                f"{detail['draws']} seeded re-estimated predictive paths for "
                "equal-tail intervals; no path exclusion."
            )
    result = forecast_payload(
        raw,
        data,
        config,
        distributions,
        "BVAR posterior predictive" if detail["estimator"] == "bvar" else "OLS VAR bootstrap",
        detail.pop("notes"),
        var=detail,
        model_space={n: {"mean": mean[:, j].tolist()} for j, n in enumerate(names(config))},
        interval_scope=detail["uncertainty"],
    )
    result["diagnostics"]["estimated_indices"] = detail["estimated_indices"]
    return result


class VARForecastPlugin(BasePlugin):
    id = "fc.var"
    family = "Forecasting"
    title = "VAR / BVAR forecasts"
    summary = "Iterated forecasts with re-estimated bootstrap or posterior predictive uncertainty."
    label = "Forecast"
    inputs = {"min_series": 1, "max_series": 8, "frequencies": ["M", "Q"]}
    params = schema(
        **COMMON_PARAMS,
        estimator=choice("ols", "ols", "bvar"),
        lags=integer(2, 1, 12),
        draws=integer(500, 100, 5000),
        **{"lambda": {"type": "number", "default": 0.2, "minimum": 0.001, "maximum": 100}},
    )
    assumptions = [
        "Final-vintage observations and an explicit future exogenous path.",
        (
            "Parameter uncertainty and future innovations are included; COVID "
            "dummies are zero in the future."
        ),
    ]
    references = [
        {
            "title": "statsmodels VAR forecasting",
            "url": "https://www.statsmodels.org/stable/vector_ar.html#forecasting",
        }
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        return forecast_checks(data, config)

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return run_var_forecast(data, config)
