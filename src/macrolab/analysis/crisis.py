"""Explicit, opt-in Türkiye crisis controls; frozen template paths stay unchanged."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

WINDOWS = (("2001-02", "2001-12"), ("2018-08", "2018-12"), ("2021-09", "2023-06"))


def magnitude_change(baseline: float, ratio: float) -> dict[str, Any]:
    """Descriptive sensitivity only; retain signed estimates and full precision."""
    relative = abs(ratio - baseline) / abs(baseline) if baseline else None
    material = (relative > 0.5) if relative is not None else ratio != 0
    return {"relative_change": relative, "changes_answer_materially": bool(material)}


def crisis_periods() -> pd.PeriodIndex:
    return pd.PeriodIndex([p for a, b in WINDOWS for p in pd.period_range(a, b, freq="M")])


def apply_design(d: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Apply controls/masks before fitting both CPI and cumulative FX equations."""
    mode = config["model"]["params"].get("crisis_mode")
    if not mode:
        return d
    if config["frequency"] != "M":
        raise ValueError("Türkiye crisis options require monthly data")
    x = d["x"]
    periods = crisis_periods()
    excluded: dict[str, list[str]] = {}
    if mode == "dummies":
        for period in periods:
            x[f"crisis_{period}"] = (x.index == period).astype(float)
    else:
        # Difference controls at t-L use t-L-1 too. Cumulative FX uses every
        # month t..t+h: reject crossings, not merely endpoints in a crisis.
        back = max(
            1,
            d["settings"]["lags"]
            + int(bool(config["model"]["params"].get("lag_difference_scales"))),
        )
        masks = []
        for h, mask in enumerate(d["masks"]):
            touches = np.array([any((p - back <= q <= p + h) for q in periods) for p in x.index])
            excluded[str(h)] = [str(p) for p in x.index[touches & mask]]
            masks.append(mask & ~touches)
        if d["settings"]["sample_mode"] == "common":
            common = np.logical_and.reduce(masks)
            masks = [pd.Series(common, index=x.index) for _ in masks]
        d["masks"] = masks
    d["crisis"] = {
        "mode": mode,
        "windows": [{"start": a, "end": b} for a, b in WINDOWS],
        "controls": [str(c) for c in x if str(c).startswith("crisis_")],
        "excluded_anchors_by_horizon": excluded,
        "rule": "One impulse dummy per crisis month"
        if mode == "dummies"
        else (
            "Exclude any anchor whose cumulative target or lag/difference footprint "
            "touches a crisis; keep calendar gaps"
        ),
    }
    return d


def extension(
    config: dict[str, Any], bundle: dict[str, Any], *, progress: Any = None, cancelled: Any = None
) -> dict[str, Any]:
    from macrolab.analysis.config import validated_config
    from macrolab.analysis.templates_v1 import base_run, run_template

    legacy = deepcopy(config)
    legacy["model"]["params"].pop("crisis_extension")
    legacy["model"]["params"].pop("crisis_mode", None)
    result = run_template(legacy, bundle, progress=progress, cancelled=cancelled)
    rows: list[dict[str, Any]] = []
    for mode in ("dummies", "exclude"):
        if cancelled and cancelled():
            raise ValueError("Crisis analysis cancelled")
        if progress:
            progress(
                {
                    "phase": "template_sensitivity",
                    "variant": "crisis_" + mode,
                    "completed": len(rows),
                    "total": 2,
                }
            )
        c = deepcopy(legacy)
        c["model"]["params"]["crisis_mode"] = mode
        run = base_run(validated_config(c), bundle, cancelled=cancelled)
        rows.append(
            {
                "variant_id": "crisis_" + mode,
                "label": "Monthly crisis dummies"
                if mode == "dummies"
                else "Exclude crisis footprints",
                "same_estimand": True,
                "include_in_agreement_counts": True,
                "config": c,
                **{k: run[k] for k in ("status", "results", "checks")},
            }
        )
    # Reuse the accepted sample row and its intervals exactly, not a second fit.
    existing = result.get("template_sensitivity", [])
    sample = next((r for r in existing if r["variant_id"] == "sample_2003"), None)
    ratios = []
    base = result["results"][0].get("pass_through", {})
    comparisons = [
        (r["variant_id"], r.get("pass_through", []))
        for r in existing
        if r.get("include_in_agreement_counts")
    ]
    comparisons.extend(
        (r["variant_id"], [v.get("pass_through", {}) for v in r["results"] if v["status"] == "ok"])
        for r in rows
    )
    for h in (point["horizon"] for point in base.get("horizons", [])):
        baseline = next((r for r in base.get("horizons", []) if r["horizon"] == h), None)
        matches = []
        if baseline and baseline["ratio"] is not None:
            for name, values in comparisons:
                for item in values:
                    point = next((r for r in item.get("horizons", []) if r["horizon"] == h), None)
                    if point and point["ratio"] is not None:
                        matches.append(
                            {
                                "variant_id": name,
                                "ratio": point["ratio"],
                                **magnitude_change(baseline["ratio"], point["ratio"]),
                                "same_sign": bool(
                                    np.sign(point["ratio"]) == np.sign(baseline["ratio"])
                                ),
                                "denominator_weak": point["denominator_weak"],
                            }
                        )
        values = [r["ratio"] for r in matches]
        if baseline and baseline["ratio"] is not None:
            values.append(baseline["ratio"])
        ratios.append(
            {
                "horizon": h,
                "same_sign": sum(r["same_sign"] for r in matches),
                "eligible": len(matches),
                "ratio_min": min(values) if values else None,
                "ratio_max": max(values) if values else None,
                "variants": matches,
            }
        )
    result["crisis_analysis"] = {
        "rows": rows,
        "sample_2003": sample,
        "agreement": ratios,
        "agreement_rule": (
            "Ratio ranges include the baseline and eligible same-estimand specifications; "
            "USD and national VAR are excluded. A ratio moving more than 50% from the "
            "baseline changes the answer materially. Descriptive, not a significance test. "
            "Weak denominators remain flagged; a nonzero ratio against a zero baseline "
            "is material, with relative change undefined."
        ),
        "windows": [{"start": a, "end": b} for a, b in WINDOWS],
    }
    # Only this separate request has a new identity; every legacy result stays intact.
    from macrolab.analysis.config import config_hash

    result["config"] = config
    result["config_hash"] = config_hash(config)
    return result
