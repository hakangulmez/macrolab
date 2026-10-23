"""Country-specific LP samples under one dated shock; descriptive comparisons only."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np

from macrolab.ident.bootstrap import CancelledError
from macrolab.ident.external_series import attach
from macrolab.models.base import AnalysisData, check
from macrolab.models.lp import LPPlugin, fit


def compare_countries(
    shock: dict[str, Any],
    countries: dict[str, AnalysisData],
    configs: dict[str, dict[str, Any]],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if set(countries) != set(configs) or not countries:
        raise ValueError("Every country/response needs its own LP configuration")
    entries: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for i, (key, data) in enumerate(countries.items()):
        if cancelled and cancelled():
            raise CancelledError("Country comparison cancelled; no complete comparison returned")
        config = configs[key]
        try:
            aligned = attach(data, shock)
            checks = LPPlugin().check(aligned, config)
            if any(c["level"] == "block" for c in checks):
                entries.append(
                    {"key": key, "country": data.country, "status": "blocked", "checks": checks}
                )
            else:
                result = fit(aligned, config)
                rows = result["local_projection"]["horizons"]
                peak = max(rows, key=lambda row: abs(row["estimate"]))
                interval = peak["bands"]["0.68"]
                summary.append(
                    {
                        "key": key,
                        "country": data.country,
                        "response": result["irf"]["variables"][0],
                        "peak": peak["estimate"],
                        "horizon": peak["horizon"],
                        "lower": interval["lower"],
                        "upper": interval["upper"],
                        "band_excludes_zero": interval["lower"] > 0 or interval["upper"] < 0,
                        "band_level": 0.68,
                        "nobs": peak["nobs"],
                        "sample_start": rows[0]["start"],
                        "sample_end": rows[0]["end"],
                    }
                )
                entries.append(
                    {
                        "key": key,
                        "country": data.country,
                        "status": "ok",
                        "checks": checks,
                        "result": result,
                    }
                )
        except (ValueError, KeyError) as exc:
            entries.append(
                {
                    "key": key,
                    "country": data.country,
                    "status": "blocked",
                    "checks": [check("block", "shock_alignment", str(exc))],
                }
            )
        if progress:
            progress(
                {
                    "phase": "country_comparison",
                    "country": data.country,
                    "completed": i + 1,
                    "total": len(countries),
                }
            )
    return {
        "entries": entries,
        "summary": summary,
        "label": "Descriptive cross-country differences under the same identified shock",
        "ranking_note": (
            "Selected-peak ranking is descriptive; overlapping intervals do not support "
            "a ranking. No cross-country equality test is performed."
        ),
        "samples": "each country's own valid sample; no forced cross-country intersection",
        "shock": deepcopy(shock),
    }


def method_comparison(
    lp: dict[str, Any], var: dict[str, Any], *, same_estimand: bool
) -> dict[str, Any]:
    a, b = lp["irf"], var["irf"]
    response = a["variables"][0]
    j = b["variables"].index(response)
    if a["periods"] != b["periods"]:
        raise ValueError("Method comparisons require the same horizons")
    if same_estimand and (
        lp["diagnostics"]["estimated_indices"] != var["diagnostics"]["estimated_indices"]
        or a["shock"] != b["shock"]
        or a["shock_size"] != b["shock_size"]
    ):
        raise ValueError(
            "Same-estimand comparison requires the same sample and shock normalization"
        )
    rows = []
    for h in range(len(a["periods"])):
        av, bv = a["values"][h][0], b["values"][h][j]
        rows.append(
            {
                "horizon": h,
                "lp": av,
                "var": bv,
                "sign_agreement": bool(np.sign(av) == np.sign(bv)),
                "band_overlap": max(a["lower"][h][0], b["lower"][h][j])
                <= min(a["upper"][h][0], b["upper"][h][j]),
            }
        )
    return {
        "label": "same sample and identified shock, different method"
        if same_estimand
        else "different method and different identification",
        "same_estimand": same_estimand,
        "include_in_agreement_counts": same_estimand,
        "horizons": rows,
        "lp_peak": max(rows, key=lambda r: abs(r["lp"])),
        "var_peak": max(rows, key=lambda r: abs(r["var"])),
    }


class CommonShockPlugin(LPPlugin):
    id, family, title = "cmp.common_shock", "comparison", "Common-shock country comparison"
    summary = "Reuse one identified shock in country-specific LPs and show actual samples."
    params = deepcopy(LPPlugin.params)
    params["properties"].update(
        {
            "first_stage": {"type": "object"},
            "response_modes": {"type": "object", "default": {}},
            "joint_bootstrap": {"type": "boolean", "default": False},
            "bootstrap_draws": {"type": "integer", "default": 200, "minimum": 20, "maximum": 5000},
        }
    )

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        if "first_stage" not in config.get("model", {}).get("params", {}):
            return [
                check(
                    "block", "missing_first_stage", "Specify the common first-stage recursive VAR."
                )
            ]
        return super().check(data, config)
