"""Template orchestration; all estimates still use the validated v0 plugins."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from macrolab.models.base import AnalysisData, ModelPlugin
from macrolab.models.registry import get_plugin


def run_configured_plugin(
    data: AnalysisData,
    config: dict[str, Any],
    *,
    fixed_shock_size: float | None = None,
    plugin: ModelPlugin | None = None,
) -> dict[str, Any]:
    """Resolve a symbolic one-SD request on the fitted sample, then use v0 IRFs.

    The SD is the Cholesky own impact sqrt of the conditional residual variance,
    from the existing estimator's degrees-of-freedom-corrected covariance. It is
    not the empirical sample SD of its recovered physical shock time series.
    Derived floats are output metadata, never inputs to portable config hashes.
    """
    plugin = plugin or get_plugin(config["model"]["id"])
    if config["model"]["id"] in {
        "lp.ols",
        "out.hd",
        "ident.external_series",
        "cmp.common_shock",
        "bvar.minn",
    }:
        return plugin.run(data, config)
    requested = config.get("outputs", {}).get("irf", {})
    one_sd = requested.get("shock_mode", "fixed") == "one_sd"
    execution = deepcopy(config)
    normalisation: dict[str, Any] | None = None
    if one_sd and config["model"]["id"] not in {"out.hd", "ident.external_series"}:
        if config["model"]["id"] not in {"var.ols", "ident.recursive"}:
            raise ValueError("One-SD normalisation requires an identified VAR")
        if fixed_shock_size is None:
            pilot_config = deepcopy(config)
            pilot_config["outputs"]["irf"].update(
                {"shock_mode": "fixed", "shock_size": 1.0, "method": "asymptotic"}
            )
            pilot = plugin.run(data, pilot_config)
            if "irf" not in pilot:
                raise ValueError("One-SD normalisation requires recursive identification")
            diagnostics = pilot["diagnostics"]
            order = pilot["irf"]["variables"]
            shock = pilot["irf"]["shock"]
            impact = np.linalg.cholesky(np.asarray(diagnostics["residual_covariance"]))
            size = float(impact[order.index(shock), order.index(shock)])
            normalisation = {
                "mode": "one_sd",
                "requested_standard_deviations": 1.0,
                "basis": "own_sample_covariance_corrected_cholesky_impact",
                "formula": "L[k,k], where L L' = residual covariance SSE / residual df",
                "residual_degrees_of_freedom": diagnostics["residual_degrees_of_freedom"],
                "identification_order": list(order),
                "estimated_indices": diagnostics["estimated_indices"],
                "nobs": diagnostics["nobs"],
            }
        else:
            size = fixed_shock_size
            normalisation = {
                "mode": "one_sd",
                "requested_standard_deviations": 1.0,
                "basis": "baseline_one_sd_physical_size_held_fixed",
                "formula": "Baseline L[k,k], held fixed across lag/order alternatives",
            }
        if not np.isfinite(size) or size <= 0:
            raise ValueError("The fitted one-SD shock must be finite and positive")
        execution["outputs"]["irf"].update({"shock_mode": "fixed", "shock_size": size})
    result = plugin.run(data, execution)
    if "irf" in result:
        irf = result["irf"]
        if normalisation is None:
            normalisation = {"mode": "fixed", "basis": "requested_physical_size"}
        normalisation.update(
            {
                "resolved_size": irf["shock_size"],
                "shock": irf["shock"],
                "unit": "percentage points"
                if irf["shock"] == "policy_rate"
                else "transformed units",
            }
        )
        if irf["shock"] == "policy_rate":
            normalisation["resolved_percentage_points"] = irf["shock_size"]
        irf["shock_normalization"] = normalisation
        result["resolved_config"] = {
            "outputs": {"irf": {"shock_mode": "fixed", "shock_size": irf["shock_size"]}}
        }
    _notes(result, data, config)
    return result


def _notes(result: dict[str, Any], data: AnalysisData, config: dict[str, Any]) -> None:
    notes = result.setdefault("notes", [])
    specs = {row["concept_id"]: row for row in config["series"]}
    if specs.get("oil_brent", {}).get("role") == "exogenous":
        notes.append(
            "Brent oil enters as an exogenous log level after complete-period aggregation; "
            "this conditions on oil prices and does not identify an oil shock."
        )
    if "irf" in result and result["irf"]["shock"] == "policy_rate":
        irf = result["irf"]
        if irf["shock_normalization"]["mode"] == "fixed" and irf["shock_size"] >= 1:
            notes.append(
                "A +1 percentage-point policy shock is a large illustrative option; "
                "inspect the fitted shock-range check."
            )
        for variable, name in (("gdp_real", "output"), ("cpi", "price")):
            if irf["shock_size"] <= 0 or variable not in irf["variables"]:
                continue
            index = irf["variables"].index(variable)
            values = np.asarray(irf["values"], dtype=float)[:, index]
            horizon = int(np.argmax(values[1:])) + 1
            if values[horizon] > 0:
                lower = float(irf["lower"][horizon][index])
                notes.append(
                    f"The estimated {name} response rises after the tightening: its largest "
                    f"positive response is {values[horizon]:.4g} "
                    f"at horizon {irf['periods'][horizon]}. "
                    + (
                        "The pointwise band excludes zero there. "
                        if lower > 0
                        else "The pointwise band includes zero there. "
                    )
                    + "Recursive VARs can show output or price puzzles because policy reacts to "
                    "information omitted from the system, contemporaneous ordering is restrictive, "
                    "and estimates depend on the sample and controls. This result is retained; "
                    "it is not evidence that tightening reliably increases activity or prices."
                )
        if "reer" in specs:
            notes.append(
                "The real exchange-rate index remains in log levels; "
                "credit remains in its reported level/ratio units, "
                "rather than being treated as an activity flow."
            )
    if (
        data.country == "GBR"
        and specs.get("policy_rate", {}).get("role") == "dependent"
        and "cpi" in specs
        and "gdp_real" in specs
    ):
        notes.append(
            "The Taylor-rule template starts with 1999Q1–2008Q4 to limit lower-bound-era "
            "distortions. Full-sample and recent-half-of-full-sample alternatives show how "
            "the association changes when policy rates may be constrained by an effective "
            "lower bound; an unconstrained linear rule need not describe that regime."
        )
    if specs.get("unemp", {}).get("role") == "dependent" and "gdp_real" in specs:
        notes.append(
            "Okun's-law coefficients are associations. The default matches a year-over-year "
            "unemployment-rate change with year-over-year GDP growth; the quarterly "
            "alternative changes both horizons and is shown separately, not pooled in "
            "coefficient magnitude or sign-agreement summaries."
        )
