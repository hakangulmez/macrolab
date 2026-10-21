"""Bounded G3.1 specification evidence using the existing VAR selection method."""

from __future__ import annotations

from typing import Any

import numpy as np
from statsmodels.tsa.api import VAR  # type: ignore[import-untyped]

from macrolab.models.base import AnalysisData
from macrolab.models.var import _inputs, _omit_inactive_covid, _settings


def lag_criteria_evidence(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    """Expose the existing statsmodels IC candidates on a shared holdback sample.

    No default is selected here. At most lags 0..4 are compared; each requested
    criterion alternative is subsequently estimated by the unchanged plugin.
    """
    settings = _settings(config, recursive=config["model"]["id"] == "ident.recursive")
    maximum = min(4, settings["maxlags"])
    frame, exog = _inputs(data, config, settings)
    active, omitted = _omit_inactive_covid(data, exog, maximum)
    selection = VAR(frame, exog=active).select_order(maximum, trend=settings["trend"])
    criteria = {name: list(map(float, selection.ics[name])) for name in ("aic", "bic", "hqic")}
    if not all(np.isfinite(values).all() for values in criteria.values()):
        raise ValueError("Lag-selection criteria must be finite")
    first_lag = maximum + 1 - len(criteria["aic"])
    periods = list(map(str, frame.index[maximum:]))
    return {
        "status": "available",
        "method": "statsmodels VAR.select_order; unchanged v0 selector",
        "candidate_lags": list(range(first_lag, maximum + 1)),
        "candidates": [
            {"lag": first_lag + i, **{name: values[i] for name, values in criteria.items()}}
            for i in range(len(criteria["aic"]))
        ],
        "selected_lags": {name: int(selection.selected_orders[name]) for name in criteria},
        "comparison_sample": {
            "start": periods[0] if periods else None,
            "end": periods[-1] if periods else None,
            "nobs": len(periods),
            "periods": periods,
            "common_holdback": maximum,
        },
        "omitted_inactive_covid_regressors": omitted,
        "default_lags_unchanged": config["model"].get("params", {}).get("lags", 2),
        "interpretation": "Lower is preferred within each criterion. Candidate scores share "
        "one maximum-lag holdback; each selected model is refitted on its own effective sample. "
        "Criteria are sensitivity evidence and do not replace the configured default lag.",
    }
