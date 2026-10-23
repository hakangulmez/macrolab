"""Seasonal controls for v1; never alter observed values or v0 defaults."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from macrolab.models.base import AnalysisData


def with_seasonal_controls(data: AnalysisData, config: dict[str, Any]) -> AnalysisData:
    result = deepcopy(data)
    if data.frequency not in {"M", "Q"}:
        return result
    needed = []
    for spec in config.get("series", []):
        if spec.get("transform") in {"yoy_pct", "yoy_diff"}:
            continue
        card = data.metadata.get(spec["concept_id"], {})
        flags = {str(card.get("sa_flag", "")).upper()}
        flags.update(str(s.get("sa_flag", "")).upper() for s in card.get("source_segments", []))
        if "NSA" in flags:
            needed.append(spec["concept_id"])
    forced = config.get("model", {}).get("params", {}).get("seasonal", False)
    if not needed and not forced:
        return result
    periods = pd.PeriodIndex(data.frame.index, freq=data.frequency)
    seasons = periods.month if data.frequency == "M" else periods.quarter
    count = 12 if data.frequency == "M" else 4
    controls = pd.DataFrame(
        {f"season_{s}": (seasons == s).astype(float) for s in range(2, count + 1)},
        index=data.frame.index,
    )
    if data.exog is not None:
        overlap = set(data.exog) & set(controls)
        for name in overlap:
            if not np.array_equal(data.exog[name], controls[name]):
                raise ValueError("Existing seasonal controls differ from calendar indicators")
        controls = pd.concat([data.exog, controls.drop(columns=list(overlap))], axis=1)
    result.exog = controls
    result.sample["seasonal_controls"] = {
        "reference": 1,
        "frequency": data.frequency,
        "inputs": needed,
        "columns": [f"season_{s}" for s in range(2, count + 1)],
        "method": "calendar dummies; original observations unchanged",
    }
    return result


def require_regular_calendar(data: AnalysisData) -> None:
    """A VAR must not treat observations across an internal gap as adjacent."""
    from macrolab.analysis.transforms import period_frequency

    frequency = period_frequency(data.frequency)
    periods = pd.PeriodIndex(data.frame.index, freq=frequency)
    if not len(periods) or not periods.equals(
        pd.period_range(periods[0], periods[-1], freq=frequency)
    ):
        raise ValueError(
            "First-stage/HD VAR requires a complete regular calendar with unique dates"
        )
