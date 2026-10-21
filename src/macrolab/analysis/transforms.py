"""Explicit transformations on a regular period grid, never across compressed gaps."""

from __future__ import annotations

import math
from typing import Any, cast

import numpy as np
import pandas as pd
from statsmodels.tsa.filters.hp_filter import hpfilter  # type: ignore[import-untyped]

FORMULAS = {
    "level": "x[t]",
    "log": "ln(x[t])",
    "diff": "x[t] - x[t-1]",
    "log_diff": "100 * (ln(x[t]) - ln(x[t-1]))",
    "yoy_pct": "100 * (x[t] / x[t-s] - 1), s=12/4/1 at M/Q/A",
    "yoy_diff": "x[t] - x[t-s], s=12/4/1 at M/Q/A",
    "qoq_saar": "100 * ((x[t] / x[t-1])**4 - 1)",
    "index_to_base": "100 * x[t] / x[chosen base period]",
    "hp_cycle": "x[t] - HP_trend(x)[t]; log=true: 100*(ln(x)-HP_trend(ln(x)))",
    "hamilton_cycle": "x[t] on constant,x[t-h],...,x[t-h-p+1] residual; log=true scales by 100",
}


def period_frequency(frequency: str) -> str:
    if frequency not in {"M", "Q", "A"}:
        raise ValueError("Frequency must be M, Q or A")
    return "Y" if frequency == "A" else frequency


def label(period: pd.Period) -> str:
    value = str(period)
    return value.replace("Q", "-Q") if "Q" in value and "-Q" not in value else value


def period_index(series: pd.Series[Any]) -> pd.PeriodIndex:
    if not isinstance(series.index, pd.PeriodIndex):
        raise ValueError("Transformations require a regular calendar-period index")
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError("Calendar periods must be unique and increasing")
    return series.index


def _period_labels(index: pd.Index[Any]) -> set[str]:
    return {label(cast(pd.Period, item)) for item in index}


def apply_transform(
    series: pd.Series[Any],
    transform: str,
    frequency: str,
    params: dict[str, Any] | None = None,
) -> tuple[pd.Series[Any], dict[str, Any]]:
    if transform not in FORMULAS:
        raise ValueError("Unknown transformation")
    if transform == "qoq_saar" and frequency != "Q":
        raise ValueError("Annualised quarter-on-quarter growth requires quarterly data")
    p = params or {}
    index = period_index(series)
    if len(index) == 0:
        raise ValueError("No observations remain for transformation")
    expected = pd.period_range(index[0], index[-1], freq=period_frequency(frequency))
    if index.freq != expected.freq:
        raise ValueError("The series calendar frequency does not match the transformation")
    # Missing calendar periods remain missing; differencing cannot bridge a gap.
    x = series.astype(float).reindex(expected)
    if np.isinf(x.to_numpy(dtype=float)).any():
        raise ValueError("Transformations require finite observed values")
    s = {"M": 12, "Q": 4, "A": 1}[frequency]
    invalid: set[str] = set()
    metadata: dict[str, Any] = {
        "transform": transform,
        "formula": FORMULAS[transform],
        "params": dict(p),
    }
    if transform == "level":
        result = x.copy()
    elif transform in ("log", "log_diff"):
        bad = x <= 0
        if transform == "log_diff":
            bad = bad | (x.shift(1) <= 0)
        invalid = _period_labels(x.index[bad])
        logged = pd.Series(np.log(x.where(x > 0).to_numpy(dtype=float)), index=x.index)
        result = logged if transform == "log" else 100 * logged.diff()
    elif transform in ("diff", "yoy_diff"):
        result = x.diff(1 if transform == "diff" else s)
    elif transform in ("yoy_pct", "qoq_saar"):
        lag = s if transform == "yoy_pct" else 1
        denominator = x.shift(lag)
        invalid = _period_labels(x.index[(denominator <= 0) | (x <= 0)])
        ratio = x.where(x > 0) / denominator.where(denominator > 0)
        result = 100 * ((ratio**4 if transform == "qoq_saar" else ratio) - 1)
    elif transform == "index_to_base":
        if "base_period" not in p:
            raise ValueError("Index transformation requires an explicit base period")
        base = pd.Period(p["base_period"], freq=period_frequency(frequency))
        if base not in x.index:
            raise ValueError("The chosen index base must be an observed nonzero period")
        base_position = int(
            x.index.get_indexer(pd.PeriodIndex([base], freq=period_frequency(frequency)))[0]
        )
        base_observation = float(x.iloc[base_position])
        if not math.isfinite(base_observation) or base_observation == 0:
            raise ValueError("The chosen index base must be an observed nonzero period")
        result = 100 * x / base_observation
        metadata["base_value"] = base_observation
    else:
        if x.isna().any():
            raise ValueError(
                "Filters require a contiguous observed history; choose a gap-free sample"
            )
        logged_filter = bool(p.get("log", False))
        if logged_filter and (x <= 0).any():
            raise ValueError("Log filters require positive levels")
        values = pd.Series(np.log(x.to_numpy(dtype=float)), index=x.index) if logged_filter else x
        if transform == "hp_cycle":
            lamb = float(p.get("lamb", {"M": 129600, "Q": 1600, "A": 6.25}[frequency]))
            if not math.isfinite(lamb) or lamb <= 0 or len(values) < 4:
                raise ValueError(
                    "HP filter requires a positive finite penalty and four observations"
                )
            cycle, trend = hpfilter(values, lamb=lamb)
            result = pd.Series(cycle, index=x.index)
            metadata["params"]["lamb"] = lamb
            metadata["trend"] = [float(v) for v in trend]
        else:
            h = int(p.get("h", {"M": 24, "Q": 8, "A": 2}[frequency]))
            order = int(p.get("p", {"M": 12, "Q": 4, "A": 1}[frequency]))
            start = h + order - 1
            if h < 1 or order < 1 or len(values) <= start + order + 1:
                raise ValueError("Too few periods for this Hamilton filter horizon and lag order")
            z = np.column_stack(
                [np.ones(len(values) - start)]
                + [values.shift(h + j).iloc[start:].to_numpy() for j in range(order)]
            )
            if np.linalg.matrix_rank(z) != z.shape[1]:
                raise ValueError("Hamilton filter lag design is rank deficient")
            target = values.iloc[start:].to_numpy()
            trend = z @ np.linalg.lstsq(z, target, rcond=None)[0]
            result = pd.Series(np.nan, index=x.index)
            result.iloc[start:] = target - trend
            metadata["params"].update({"h": h, "p": order})
            metadata["trend"] = [None] * start + [float(v) for v in trend]
        if logged_filter:
            result = result * 100
        metadata["retrospective_filter"] = True
        metadata["input_start"] = label(expected[0])
        metadata["input_end"] = label(expected[-1])
    if np.isinf(result.to_numpy(dtype=float)).any():
        raise ValueError("Transformation overflow; choose a numerically valid scale")
    metadata["invalid_periods"] = sorted(invalid)
    return result, metadata


def invert_transform(
    values: list[float],
    transform: str,
    initial: list[float],
    frequency: str = "Q",
    base_value: float | None = None,
) -> list[float]:
    """Invert lossless transforms using their necessary initial observations."""
    period_frequency(frequency)
    if not np.isfinite(values).all() or not np.isfinite(initial).all():
        raise ValueError("Inversion requires finite values and initial conditions")
    if transform == "level":
        return list(values)
    if transform == "log":
        return [math.exp(v) for v in values]
    if transform == "index_to_base":
        if base_value is None or not math.isfinite(base_value) or base_value == 0:
            raise ValueError("Index inversion needs its recorded finite nonzero base value")
        return [v * base_value / 100 for v in values]
    if transform in ("hp_cycle", "hamilton_cycle"):
        raise ValueError("A cycle alone is lossy; retain its trend to reconstruct levels")
    if transform not in FORMULAS:
        raise ValueError("Unknown transformation")
    if transform == "qoq_saar" and frequency != "Q":
        raise ValueError("Annualised quarter-on-quarter growth requires quarterly data")
    lag = {"M": 12, "Q": 4, "A": 1}[frequency] if transform.startswith("yoy") else 1
    if len(initial) < lag:
        raise ValueError("Insufficient initial conditions for inversion")
    reconstructed = list(initial[-lag:])
    for value in values:
        prior = reconstructed[-lag]
        if transform in ("diff", "yoy_diff"):
            nxt = prior + value
        else:
            if prior <= 0 or (transform in ("yoy_pct", "qoq_saar") and value <= -100):
                raise ValueError("Growth inversion requires positive levels and valid growth rates")
            if transform == "log_diff":
                nxt = prior * math.exp(value / 100)
            elif transform == "yoy_pct":
                nxt = prior * (1 + value / 100)
            else:
                nxt = prior * (1 + value / 100) ** 0.25
        if not math.isfinite(nxt):
            raise ValueError("Inversion overflow")
        reconstructed.append(nxt)
    return reconstructed[lag:]
