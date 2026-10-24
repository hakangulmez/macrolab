"""Local projections with explicit targets, calendar samples and robust inference."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm  # type: ignore[import-untyped]

from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import label as period_label
from macrolab.analysis.transforms import period_frequency
from macrolab.models.base import (
    AnalysisData,
    BasePlugin,
    check,
    parameters,
    roles,
    sample_size_check,
)
from macrolab.models.linear import choice, integer, schema


def settings(config: dict[str, Any]) -> dict[str, Any]:
    p = parameters(config)
    response, impulse = roles(config, "response", "dependent"), roles(config, "shock")
    if len(response) != 1 or len(impulse) != 1:
        raise ValueError("LP requires one response and one impulse")
    size = float(p.get("shock_size", 1))
    if not np.isfinite(size) or size == 0:
        raise ValueError("LP impulse size must be finite and nonzero")
    for name, scale in p.get("lag_difference_scales", {}).items():
        if (
            name not in roles(config, "response", "dependent", "endogenous", "regressor", "shock")
            or not isinstance(scale, (int, float))
            or not np.isfinite(scale)
            or scale <= 0
        ):
            raise ValueError(
                "Lag difference controls require selected variables and positive finite scales"
            )
    mode = p.get("response_mode", "level")
    if mode in {"cumulative_log", "growth_log"}:
        spec = next(s for s in config["series"] if s["concept_id"] == response[0])
        if spec["transform"] != "log":
            raise ValueError("Cumulative/growth log responses require original log levels")
    return {
        "response": response[0],
        "impulse": impulse[0],
        "lags": int(p.get("lags", 2)) + int(p.get("lag_augmented", False)),
        "horizon": int(p.get("horizon", 12)),
        "response_mode": mode,
        "sample_mode": p.get("sample_mode", "common"),
        "covariance": "HC1" if p.get("lag_augmented", False) else p.get("covariance", "HAC"),
        "size": float(p.get("shock_size", 1)),
        "growth_scale": float(p.get("growth_scale", 1)),
    }


def design(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    s = settings(config)
    data = with_seasonal_controls(data, config)
    frame = data.frame.astype(float)
    if not len(frame) or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("LP requires unique increasing dates")
    periods = pd.PeriodIndex(frame.index, freq=period_frequency(data.frequency))
    if periods.has_duplicates:
        raise ValueError("LP dates must identify distinct calendar periods")
    regular = pd.period_range(periods[0], periods[-1], freq=period_frequency(data.frequency))
    frame = frame.set_axis(periods).reindex(regular)
    controls = sorted(roles(config, "response", "dependent", "endogenous", "regressor", "shock"))
    lag_frame = frame.copy()
    for name, scale in parameters(config).get("lag_difference_scales", {}).items():
        lag_frame[name] = float(scale) * frame[name].diff()
    x = pd.DataFrame({"const": 1.0, "impulse": frame[s["impulse"]]}, index=regular)
    for lag in range(1, s["lags"] + 1):
        for name in controls:
            x[f"L{lag}.{name}"] = lag_frame[name].shift(lag)
    for name in sorted(roles(config, "exogenous")):
        x[name] = frame[name]
    if data.exog is not None:
        exog = data.exog.set_axis(periods).reindex(regular)
        if set(exog) & set(x):
            raise ValueError("LP fixed controls must have distinct names")
        x = pd.concat([x, exog], axis=1)
    y = frame[s["response"]]
    targets = []
    for h in range(s["horizon"] + 1):
        target = y.shift(-h)
        if s["response_mode"] in {"change", "cumulative_log"}:
            target = target - y.shift(1)
        if s["response_mode"] == "cumulative_log":
            target = 100 * target
        if s["response_mode"] == "growth_log":
            target = 100 * s["growth_scale"] * (target - y.shift(1 - h))
        targets.append(target)
    yy = pd.concat(targets, axis=1)
    yy.columns = range(s["horizon"] + 1)
    valid_x = np.isfinite(x).all(axis=1)
    masks = [valid_x & np.isfinite(yy[h]) for h in yy]
    if s["sample_mode"] == "common":
        common = np.logical_and.reduce(masks)
        masks = [pd.Series(common, index=x.index) for _ in masks]
    result = {"x": x, "y": yy, "masks": masks, "settings": s, "data": data}
    if parameters(config).get("crisis_mode"):
        from macrolab.analysis.crisis import apply_design

        result = apply_design(result, config)
    return result


def _active(x: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    # A generated indicator outside this horizon's sample is identically zero.
    omitted = [
        str(c)
        for c in x
        if (str(c).startswith(("covid_", "season_", "crisis_"))) and not np.any(x[c])
    ]
    return x.drop(columns=omitted), omitted


def _point_fit(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    """Common-window point estimates for bootstrap draws, same design as fit()."""
    s = settings(config)
    fixed_data = with_seasonal_controls(data, config)
    frame = fixed_data.frame
    calendar = pd.PeriodIndex(frame.index, freq=period_frequency(data.frequency))
    if not calendar.is_unique or not calendar.equals(
        pd.period_range(calendar[0], calendar[-1], freq=period_frequency(data.frequency))
    ):
        raise ValueError("Bootstrap point-fit requires a regular common calendar")
    start = max(s["lags"], int(s["response_mode"] != "level"))
    anchors = np.arange(start, len(frame) - s["horizon"])
    controls = sorted(roles(config, "response", "dependent", "endogenous", "regressor", "shock"))
    lag_frame = frame.copy()
    for name, scale in parameters(config).get("lag_difference_scales", {}).items():
        lag_frame[name] = float(scale) * frame[name].diff()
    columns = [np.ones(len(anchors)), frame[s["impulse"]].to_numpy()[anchors]]
    for lag in range(1, s["lags"] + 1):
        for name in controls:
            columns.append(lag_frame[name].to_numpy()[anchors - lag])
    for name in sorted(roles(config, "exogenous")):
        columns.append(frame[name].to_numpy()[anchors])
    if fixed_data.exog is not None:
        for fixed_name in fixed_data.exog:
            col = fixed_data.exog[fixed_name].to_numpy()[anchors]
            if str(fixed_name).startswith(("covid_", "season_")) and not np.any(col):
                continue
            columns.append(col)
    x = np.column_stack(columns)
    y = frame[s["response"]].to_numpy()
    target = np.column_stack([y[anchors + h] for h in range(s["horizon"] + 1)])
    if s["response_mode"] in {"change", "cumulative_log"}:
        target -= y[anchors - 1, None]
    if s["response_mode"] == "cumulative_log":
        target *= 100
    if s["response_mode"] == "growth_log":
        target = (
            100
            * s["growth_scale"]
            * (target - np.column_stack([y[anchors + h - 1] for h in range(s["horizon"] + 1)]))
        )
    mask = np.isfinite(x).all(axis=1) & np.isfinite(target).all(axis=1)
    x, target = x[mask], target[mask]
    rank = int(np.linalg.matrix_rank(x))
    if len(x) < 20 or len(x) <= rank or rank == np.linalg.matrix_rank(np.delete(x, 1, axis=1)):
        raise ValueError("LP bootstrap impulse is not estimable")
    return {"estimates": ((np.linalg.pinv(x, rcond=1e-15)[1] @ target) * s["size"]).tolist()}


def fit(data: AnalysisData, config: dict[str, Any], *, point_only: bool = False) -> dict[str, Any]:
    if (
        point_only
        and parameters(config).get("sample_mode", "common") == "common"
        and not parameters(config).get("crisis_mode")
    ):
        return _point_fit(data, config)
    d = design(data, config)
    s = d["settings"]
    rows: list[dict[str, Any]] = []
    if point_only and s["sample_mode"] == "common":
        mask = d["masks"][0]
        x, _ = _active(d["x"].loc[mask])
        a = x.to_numpy()
        rank = int(np.linalg.matrix_rank(a))
        if len(a) < 20 or len(a) <= rank or rank == np.linalg.matrix_rank(np.delete(a, 1, axis=1)):
            raise ValueError(
                "LP bootstrap design lacks observations or an identified impulse coefficient"
            )
        estimates = (np.linalg.pinv(a, rcond=1e-15)[1] @ d["y"].loc[mask].to_numpy()) * s["size"]
        return {"estimates": estimates.tolist()}
    for h, mask in enumerate(d["masks"]):
        x, omitted = _active(d["x"].loc[mask])
        y = d["y"].loc[mask, h].to_numpy()
        a = x.to_numpy()
        n, columns = a.shape
        k = int(np.linalg.matrix_rank(a))
        if n < 20 or n <= k:
            raise ValueError(
                "LP horizon requires at least 20 observations and positive residual df"
            )
        if k == np.linalg.matrix_rank(np.delete(a, 1, axis=1)):
            raise ValueError("LP impulse is collinear with the controls")
        pinv = np.linalg.pinv(a, rcond=1e-15)
        beta = pinv @ y
        coefficient = float(beta[1] * s["size"])
        if point_only:
            rows.append({"estimate": coefficient})
            continue
        residual = y - a @ beta
        # The impulse row of the pseudoinverse yields the exact coefficient sandwich.
        score = pinv[1] * residual
        variance = float(score @ score)
        bandwidth = h + 1
        if s["covariance"] == "HAC":
            if bandwidth >= n:
                raise ValueError("HAC bandwidth must be shorter than the estimation sample")
            for lag in range(1, bandwidth + 1):
                variance += 2 * (1 - lag / (bandwidth + 1)) * float(score[lag:] @ score[:-lag])
        else:
            variance *= n / (n - k)
        se = float(np.sqrt(max(0, variance)) * abs(s["size"]))
        bands = {}
        for level in (0.68, 0.90):
            critical = float(norm.ppf((1 + level) / 2))
            bands[str(level)] = {
                "lower": coefficient - critical * se,
                "upper": coefficient + critical * se,
            }
        idx = [period_label(p) for p in x.index]
        rows.append(
            {
                "horizon": h,
                "estimate": coefficient,
                "std_error": se,
                "bands": bands,
                "nobs": n,
                "start": idx[0],
                "end": idx[-1],
                "periods": idx,
                "parameters": k,
                "design_columns": columns,
                "redundant_nuisance_dimensions": columns - k,
                "omitted_zero_indicators": omitted,
                "dropped_periods": [period_label(p) for p in d["x"].index[~mask]],
                "hac_bandwidth": bandwidth if s["covariance"] == "HAC" else None,
            }
        )
    if point_only:
        return {"estimates": [r["estimate"] for r in rows]}
    identified = data.metadata.get(s["impulse"], {}).get("identified_shock", False)
    labels = {
        "level": "level",
        "change": "change from the pre-impulse level",
        "cumulative_log": "cumulative % change in the level",
        "growth_log": "log growth rate (%)",
    }
    move = "one-unit" if s["size"] == 1 else f"{s['size']:g}-unit"
    label = (
        "Model-based shock response, conditional on recursive identification"
        if identified
        else f"Conditional association to a {move} move in {s['impulse']}, controlling for lags"
    )
    irf = {
        "periods": list(range(len(rows))),
        "variables": [s["response"]],
        "values": [[r["estimate"]] for r in rows],
        "lower": [[r["bands"]["0.68"]["lower"]] for r in rows],
        "upper": [[r["bands"]["0.68"]["upper"]] for r in rows],
        "shock": s["impulse"],
        "shock_size": s["size"],
        "band_level": 0.68,
        "band_method": s["covariance"],
        "band_interpretation": "pointwise, not simultaneous",
    }
    return {
        "label": label,
        "irf": irf,
        "local_projection": {
            **({"crisis": d["crisis"]} if "crisis" in d else {}),
            "response_definition": labels[s["response_mode"]],
            "response_mode": s["response_mode"],
            "sample_mode": s["sample_mode"],
            "covariance": s["covariance"],
            "horizons": rows,
            "growth_scale": s["growth_scale"],
            "seasonal_controls": d["data"].sample.get("seasonal_controls", {}),
            "generated_regressor_uncertainty": "ignored in conditional bands"
            if identified
            else "not applicable",
        },
        "diagnostics": {
            "estimated_indices": rows[0]["periods"],
            "nobs": rows[0]["nobs"],
            "nobs_by_horizon": [r["nobs"] for r in rows],
        },
        "notes": [
            "Overlapping horizon residuals motivate HAC bandwidth h+1; bands are pointwise.",
            "Lag augmentation adds one lag and uses HC1 errors.",
        ]
        + (["Conditional bands ignore first-stage estimation uncertainty."] if identified else []),
    }


class LPPlugin(BasePlugin):
    id, family, title = "lp.ols", "multivariate", "Local projections"
    summary = "Estimate a separate response at each horizon with explicit controls and samples."
    label = "Conditional association, unless an identified shock is supplied"
    inputs = {
        "min_series": 2,
        "max_series": 20,
        "required_roles": {"shock": 1},
        "frequencies": ["M", "Q", "A"],
        "cross_country": False,
    }
    assumptions = [
        "Impulse exogeneity is required for a causal interpretation.",
        "HAC inference is asymptotic; intervals are pointwise.",
    ]
    params = schema(
        crisis_extension={"type": "boolean"},
        crisis_mode={"type": "string", "enum": ["dummies", "exclude"]},
        template_id=choice("", "", "same_ecb_shock", "tur_pass_through"),
        policy_measure=choice("dfr", "dfr", "rate_3m", "bis"),
        country_window=choice("own", "own", "common"),
        displayed_band=choice("conditional", "conditional", "joint"),
        lag_difference_scales={"type": "object", "default": {}},
        shared_controls={"type": "object", "default": {}},
        lags=integer(2, 0, 24),
        horizon=integer(12, 0, 60),
        response_mode=choice("level", "level", "change", "cumulative_log", "growth_log"),
        sample_mode=choice("common", "common", "horizon_specific"),
        covariance=choice("HAC", "HAC", "HC1"),
        lag_augmented={"type": "boolean", "default": False},
        seasonal={"type": "boolean", "default": False},
        shock_size={"type": "number", "default": 1.0},
        growth_scale={"type": "number", "default": 1.0, "minimum": 1, "maximum": 12},
    )
    references = [
        {
            "title": (
                "Jordà (2005), Estimation and Inference of Impulse Responses by Local Projections"
            ),
            "url": "https://doi.org/10.1257/0002828053828518",
        },
        {
            "title": (
                "Montiel Olea and Plagborg-Møller (2021), Local Projection Inference "
                "Is Simpler and More Robust Than You Think"
            ),
            "url": "https://doi.org/10.3982/ECTA18756",
        },
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            d = design(data, config)
            output = [
                check(
                    "info",
                    "lp_overlap_note",
                    (
                        "Lag-augmented LP uses HC1 pointwise intervals; finite-sample coverage "
                        "can differ from nominal."
                    )
                    if d["settings"]["covariance"] == "HC1"
                    else "Horizon residuals overlap; HAC uses bandwidth h+1.",
                )
            ]
            for h, mask in enumerate(d["masks"]):
                x, _ = _active(d["x"].loc[mask])
                n, columns = x.shape
                k = int(np.linalg.matrix_rank(x.to_numpy())) if n else columns
                if h == len(d["masks"]) - 1 and n < 40:
                    output.append(
                        check(
                            "block" if n < 20 else "warn",
                            "lp_short_horizon_sample",
                            "The longest horizon has fewer than 40 observations (20 required).",
                            nobs=n,
                        )
                    )
                size = sample_size_check(n, k, minimum_observations=20, horizon=h)
                if size:
                    output.append(size)
                if n and k == np.linalg.matrix_rank(np.delete(x.to_numpy(), 1, axis=1)):
                    output.append(
                        check(
                            "block",
                            "lp_rank",
                            "LP impulse is collinear with the controls.",
                            horizon=h,
                        )
                    )
            impulse = d["settings"]["impulse"]
            if not data.metadata.get(impulse, {}).get("identified_shock", False):
                output.append(
                    check(
                        "info",
                        "lp_impulse_not_shock",
                        f"Conditional association to a one-unit move in {impulse}, "
                        "controlling for lags.",
                    )
                )
            else:
                output.append(
                    check(
                        "info",
                        "generated_regressor",
                        "Conditional bands ignore first-stage uncertainty.",
                    )
                )
            if d["data"].sample.get("seasonal_controls"):
                output.append(
                    check(
                        "info",
                        "seasonal_controls",
                        "Calendar seasonal dummies included; observations unchanged.",
                    )
                )
            return output
        except (ValueError, KeyError) as exc:
            return [check("block", "lp_inputs", str(exc))]

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return fit(data, config)
