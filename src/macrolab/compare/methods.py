"""On-demand matched-window VAR/LP comparison; never alters a baseline result.

Both estimates use one recursively identified innovation from a VAR fitted on
the LP anchor dates. Future observations supply LP targets only. Conditional LP
bands hold that generated innovation fixed. A raw-impulse LP baseline is a
different estimand and is explicitly excluded from this pair's agreement count.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from macrolab.analysis.config import config_hash
from macrolab.analysis.data import input_fingerprint, prepare_country
from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import label, period_frequency
from macrolab.compare.common_shock import method_comparison
from macrolab.models.base import check, sample_size_check
from macrolab.models.lp import LPPlugin, design, fit
from macrolab.models.var import (
    _estimate,
    _inputs,
    _normalized_response,
    _settings,
    _stable,
    residual_bootstrap,
)


def matched_pair(
    config: dict[str, Any], bundle: dict[str, Any], response: str, country: str
) -> dict[str, Any]:
    """Return a separate comparison or an explicit block, with reproducible inputs."""
    try:
        return _pair(config, bundle, response, country)
    except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
        return {
            "status": "blocked",
            "reason": str(exc),
            "response": response,
            "country": country,
            "include_in_baseline_agreement_counts": False,
        }


def _pair(
    config: dict[str, Any], bundle: dict[str, Any], response: str, country: str
) -> dict[str, Any]:
    if config["model"]["id"] not in {"var.ols", "ident.recursive", "lp.ols"}:
        raise ValueError(
            "Matched recursive comparisons require a single-country VAR or LP. "
            "The ECB national VAR retains its different identification label."
        )
    if country not in config["countries"]:
        raise ValueError("Comparison country must belong to the selected result")
    original = deepcopy(config)
    p = original["model"]["params"]
    is_lp = original["model"]["id"] == "lp.ols"
    mode = p.get("response_mode", "level") if is_lp else "level"
    if mode not in {"level", "cumulative_log", "growth_log"}:
        raise ValueError("This comparison supports level and log-growth response definitions")
    names = [
        s["concept_id"]
        for s in original["series"]
        if s["role"] in {"response", "endogenous", "shock", "regressor"}
    ]
    if response not in names:
        raise ValueError("Select an endogenous response")
    impulse = next(s["concept_id"] for s in original["series"] if s["role"] == "shock")
    if response == impulse:
        raise ValueError("Select a response other than the impulse")
    order = (original.get("identification") or {}).get("params", {}).get("order")
    order = order or [impulse, *[n for n in names if n != impulse]]
    horizon = int(p.get("horizon", 12) if is_lp else original["outputs"]["irf"]["horizon"])
    lags = int(p.get("lags", 2))
    if (
        lags < 1
        or p.get("trend", "c") != "c"
        or p.get("lag_selection", "fixed") not in {None, "fixed"}
    ):
        raise ValueError("Choose a fixed positive lag length and a constant for matched comparison")
    original["countries"] = [country]
    original["comparison"] = {"enabled": False}
    data, checks = prepare_country(original, bundle, country)
    if any(c["level"] == "block" for c in checks):
        raise ValueError(
            "Input checks block the matched comparison: "
            + "; ".join(c["message"] for c in checks if c["level"] == "block")
        )
    baseline_data = deepcopy(data)
    data = with_seasonal_controls(data, original)
    calendar = pd.PeriodIndex(data.frame.index, freq=period_frequency(data.frequency))
    if not calendar.equals(pd.period_range(calendar[0], calendar[-1], freq=calendar.freq)):
        raise ValueError("Matched comparison requires an uninterrupted calendar")
    var_config = deepcopy(original)
    var_config["model"] = {"id": "var.ols", "params": {"lags": lags, "trend": "c"}}
    var_config["identification"] = {"id": "recursive", "params": {"order": order}}
    var_config["outputs"]["irf"] = {
        "horizon": horizon,
        "bands": 0.68,
        "draws": 200,
        "method": "bootstrap",
        "shock_size": 1.0,
    }
    var_data = deepcopy(data)
    for spec in var_config["series"]:
        if spec["concept_id"] in names:
            spec["role"] = "shock" if spec["concept_id"] == impulse else "endogenous"
        if (
            is_lp
            and mode in {"cumulative_log", "growth_log"}
            and spec["transform"] == "log"
            and spec["concept_id"] in names
        ):
            var_data.frame[spec["concept_id"]] = 100 * data.frame[spec["concept_id"]].diff()
    finite = pd.Series(
        np.isfinite(var_data.frame.to_numpy()).all(axis=1), index=var_data.frame.index
    )
    var_data.frame = var_data.frame.loc[finite]
    if var_data.exog is not None:
        var_data.exog = var_data.exog.loc[finite]
    s = _settings(var_config)
    lp_config = deepcopy(original)
    lp_config["model"] = {
        "id": "lp.ols",
        "params": {
            "lags": lags,
            "lag_augmented": True,
            "covariance": "HC1",
            "horizon": horizon,
            "sample_mode": "common",
            "response_mode": mode,
            "shock_size": 1.0,
            "growth_scale": p.get("growth_scale", 1),
            "lag_difference_scales": p.get("lag_difference_scales", {}) if is_lp else {},
        },
    }
    for spec in lp_config["series"]:
        if spec["concept_id"] in names:
            spec["role"] = "response" if spec["concept_id"] == response else "endogenous"
    lp_config["series"].append(
        {
            "concept_id": "paired_innovation",
            "role": "shock",
            "transform": "level",
            "transform_params": {},
        }
    )
    lp_data = deepcopy(data)
    lp_data.frame["paired_innovation"] = np.nan
    valid_shock_dates = var_data.frame.index[lags:]
    # Placeholder establishes a sample mask only; no estimate uses these values.
    lp_data.frame.loc[valid_shock_dates, "paired_innovation"] = 0.0
    d = design(lp_data, lp_config)
    anchors = [label(t) for t in d["x"].index[d["masks"][0]]]
    if len(anchors) < 20:
        raise ValueError("Fewer than 20 common estimation dates")
    start = int(var_data.frame.index.get_indexer(pd.Index([anchors[0]]))[0]) - lags
    end = int(var_data.frame.index.get_indexer(pd.Index([anchors[-1]]))[0]) + 1
    fit_data = deepcopy(var_data)
    fit_data.frame = var_data.frame.iloc[start:end]
    if var_data.exog is not None:
        fit_data.exog = var_data.exog.iloc[start:end]
    fitted = _estimate(fit_data, var_config, s)
    stable, radius = _stable(fitted.coefs)
    if not stable:
        raise ValueError(
            f"Matched VAR dynamics are unstable (largest root {radius:.6f}); "
            "VAR responses are blocked. The original LP result remains available."
        )
    frame, exog = _inputs(var_data, var_config, s)
    x = pd.DataFrame({"const": 1.0}, index=frame.index)
    if exog is not None:
        x = pd.concat([x, exog], axis=1)
    for lag in range(1, lags + 1):
        for name in order:
            x[f"L{lag}.{name}"] = frame[name].shift(lag)
    residuals = (
        frame.loc[valid_shock_dates] - x.loc[valid_shock_dates, fitted.params.index] @ fitted.params
    )
    impact = np.linalg.cholesky(np.asarray(fitted.sigma_u))
    j = order.index(impulse)
    innovations = np.linalg.solve(impact, residuals.to_numpy().T).T[:, j]
    physical = (
        float(p.get("shock_size", 1))
        if is_lp
        else float(original["outputs"]["irf"].get("shock_size", 1))
    )
    if not is_lp and original["outputs"]["irf"].get("shock_mode") == "one_sd":
        # Keep the baseline physical normalization, even though the pair refits a shorter window.
        baseline_fit = _estimate(baseline_data, var_config, s)
        physical = float(np.linalg.cholesky(baseline_fit.sigma_u)[j, j])
    lp_data.frame.loc[valid_shock_dates, "paired_innovation"] = innovations
    lp_data.metadata["paired_innovation"] = {"identified_shock": True}
    lp_config["model"]["params"]["shock_size"] = physical / float(impact[j, j])
    pair_checks = LPPlugin().check(lp_data, lp_config)
    if any(c["level"] == "block" for c in pair_checks):
        raise ValueError(
            "Matched LP checks block estimation: "
            + "; ".join(c["message"] for c in pair_checks if c["level"] == "block")
        )
    size_check = sample_size_check(int(fitted.nobs), fitted.endog_lagged.shape[1])
    if size_check:
        pair_checks.append({**size_check, "model": "VAR"})
    if radius >= 0.98:
        pair_checks.append(
            check(
                "warn",
                "near_unit_root",
                "The matched VAR is near a unit root; responses can be persistent.",
                largest_root=radius,
            )
        )
    # Common-window horizon checks often repeat the identical precision finding.
    # Retain every affected horizon in details while showing one warning.
    grouped_checks: dict[str, dict[str, Any]] = {}
    for finding in pair_checks:
        entry = {k: v for k, v in finding.items() if k != "horizon"}
        key = input_fingerprint(entry)
        if key not in grouped_checks:
            grouped_checks[key] = entry
        if "horizon" in finding:
            grouped_checks[key].setdefault("horizons", []).append(finding["horizon"])
    pair_checks = list(grouped_checks.values())
    lp = fit(lp_data, lp_config)
    var_dates = list(map(str, fit_data.frame.index[lags:]))
    if lp["diagnostics"]["estimated_indices"] != anchors or var_dates != anchors:
        raise ValueError("VAR and LP estimation dates differ; no comparison returned")
    values = _normalized_response(fitted.coefs, np.asarray(fitted.sigma_u), horizon, j, physical)
    draws, bootstrap = residual_bootstrap(
        fitted, horizon=horizon, shock=j, size=physical, draws=200, seed=int(original["seed"])
    )
    k = order.index(response)
    if mode == "cumulative_log":
        values[:, k] = np.cumsum(values[:, k])
        draws[:, :, k] = np.cumsum(draws[:, :, k], axis=1)
    elif mode == "growth_log":
        values[:, k] *= p.get("growth_scale", 1)
        draws[:, :, k] *= p.get("growth_scale", 1)
    low, high = np.quantile(draws, [0.16, 0.84], axis=0)
    var = {
        "irf": {
            "periods": list(range(horizon + 1)),
            "variables": [response],
            "values": values[:, k, None].tolist(),
            "lower": low[:, k, None].tolist(),
            "upper": high[:, k, None].tolist(),
            "shock": impulse,
            "shock_size": physical,
            "band_level": 0.68,
            "band_method": "residual bootstrap (200 draws)",
        },
        "diagnostics": {
            "estimated_indices": var_dates,
            "nobs": len(var_dates),
            "largest_root": radius,
        },
        "bootstrap": bootstrap,
    }
    lp["irf"].update(shock=impulse, shock_size=physical)
    comparison = method_comparison(lp, var, same_estimand=True)
    shock_record = {
        "periods": list(map(str, valid_shock_dates)),
        "values": innovations.tolist(),
        "order": order,
        "physical_size": physical,
    }
    return {
        "status": "ok",
        "country": country,
        "response": response,
        "baseline_config_hash": config_hash(config),
        "snapshot_id": config.get("snapshot_id"),
        "checks": pair_checks,
        "var": var,
        "lp": lp,
        "comparison": comparison,
        "shock": shock_record,
        "shock_fingerprint": input_fingerprint(shock_record),
        "include_in_baseline_agreement_counts": False,
        "sample": {
            "start": anchors[0],
            "end": anchors[-1],
            "nobs": len(anchors),
            "periods": anchors,
            "dropped_periods": [t for t in data.frame.index if t not in anchors],
            "frequency_conversion": data.sample.get("frequency_conversion", {}),
            "future_target_end": str(data.frame.index[-1]),
            "seasonal_controls": data.sample.get("seasonal_controls", {}),
        },
        "note": "A separate matched-window comparison, not a replacement for the baseline. "
        "Both methods use the same recursive innovation, physical shock and anchor dates; "
        "Calendar controls for NSA inputs apply to both matched estimates. "
        "LP future outcomes extend beyond those dates. LP uses lag augmentation and "
        "conditional HC1 bands; VAR uses a 200-draw residual bootstrap. "
        "Agreement is counted only inside this pair. "
        + (
            "This recursive identification differs from the raw-impulse LP baseline."
            if is_lp
            else "The shorter window refits the baseline recursive ordering."
        ),
    }
