"""Panel orchestration, isolated from accepted single-country numerical paths."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from macrolab import __version__
from macrolab.analysis.config import canonical_json, config_hash
from macrolab.analysis.data import prepare_country
from macrolab.checks.core import evaluate_checks
from macrolab.ident.external_series import attach
from macrolab.models.base import AnalysisData, check
from macrolab.models.panel import PanelFEPlugin, PanelLPPlugin, fit_panel, panel_checks


def prepare_panel(
    config: dict[str, Any], bundle: dict[str, Any]
) -> tuple[dict[str, AnalysisData], list[dict[str, Any]], Any]:
    from macrolab.analysis.engine import run_analysis

    p = config["model"]["params"]
    is_lp = config["model"]["id"] == "panel.lp"
    plugin = PanelLPPlugin() if is_lp else PanelFEPlugin()
    checks: list[dict[str, Any]] = []
    prepared = {}
    stage = None
    if is_lp and p.get("shock_type") == "common" and p.get("effects") == "two_way":
        return (
            {},
            [
                check(
                    "block",
                    "common_shock_time_effects",
                    "Time effects are disabled with a common shock because they absorb the shock.",
                )
            ],
            None,
        )
    if p.get("first_stage_source") == "ecb_dfr":
        from macrolab.analysis.templates_v1 import variant_bundle

        if not p.get("first_stage") or "variants" not in bundle:
            return (
                {},
                [
                    check(
                        "block",
                        "panel_first_stage",
                        "The selected ECB DFR and SA HICP variants are unavailable",
                    )
                ],
                None,
            )
        bundle = variant_bundle(bundle, "dfr")
    first = p.get("first_stage")
    shock = None
    if first:
        c = deepcopy(first)
        c["model"]["id"] = "ident.external_series"
        c["comparison"] = {"enabled": False}
        stage = run_analysis(c, bundle)
        checks.extend(stage["checks"])
        if stage["status"] != "ok":
            return {}, checks, stage
        shock = stage["results"][0]["identified_shock"]
        checks.append(
            check(
                "info",
                "generated_regressor",
                (
                    "Panel bands condition on the estimated first-stage shock "
                    "and ignore its estimation uncertainty."
                ),
            )
        )
    for country in config["countries"]:
        if country not in bundle["countries"]:
            checks.append(
                check(
                    "block", "missing_coverage", "No data bundle for this country.", country=country
                )
            )
            continue
        c = deepcopy(config)
        if shock:
            c["series"] = [s for s in c["series"] if s["concept_id"] != "identified_impulse"]
            adoption = bundle["countries"][country]["metadata"].get("euro_adoption")
            if (
                adoption
                and c["sample"]["start"]
                == {"Q": "1999-Q1", "M": "1999-01", "A": "1999"}[c["frequency"]]
            ):
                adopted = pd.Period(adoption, freq=c["frequency"])
                if pd.Timestamp(adoption) > adopted.start_time:
                    adopted += 1
                c["sample"]["start"] = max(c["sample"]["start"], str(adopted).replace("Q", "-Q"))
        data, findings = prepare_country(c, bundle, country)
        if shock and not any(x["level"] == "block" for x in findings):
            initial = set(shock["first_stage_sample"].get("periods", [])) - set(shock["periods"])
            removed = data.frame.index.isin(initial)
            data.sample["dropped_periods"].extend(
                {"period": str(x), "reason": "first_stage_initialisation"}
                for x in data.frame.index[removed]
            )
            data.frame = data.frame.loc[~removed]
            if data.exog is not None:
                data.exog = data.exog.loc[data.frame.index]
            try:
                assert stage is not None
                data = attach(data, shock)
                data.sample["generated_shock"] = {
                    "first_stage_config": first,
                    "first_stage_input_sha256": stage["results"][0]["actual_sample"][
                        "source_data_sha256"
                    ],
                    "definition": "inverse Cholesky times first-stage residual",
                }
            except ValueError as exc:
                findings.append(check("block", "shock_alignment", str(exc)))
        if not any(x["level"] == "block" for x in findings):
            findings.extend(evaluate_checks(data, config, bundle))
            findings.extend(plugin.check(data, config))
        checks.extend({**item, "country": country} for item in findings)
        prepared[country] = data
    if prepared and not any(c["level"] == "block" for c in checks):
        checks.extend(
            panel_checks(
                {k: {"nobs": len(d.frame)} for k, d in prepared.items()},
                lagged=is_lp or p.get("dependent_lags", 0) > 0,
                covariance=p.get("covariance", "Driscoll-Kraay"),
            )
        )
    return prepared, checks, stage


def run_panel(
    config: dict[str, Any],
    bundle: dict[str, Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    data, checks, stage = prepare_panel(config, bundle)
    payload: dict[str, Any] = {}
    status = "blocked"
    actual: dict[str, dict[str, Any]] = {}
    if not any(c["level"] == "block" for c in checks):
        try:
            effective = deepcopy(config)
            if stage:
                effective["model"]["params"]["shock_size"] = stage["results"][0][
                    "identified_shock"
                ]["requested_structural_size"]
            payload = fit_panel(data, effective, progress=progress, cancelled=cancelled)
            if stage:
                source_shock = stage["results"][0]["identified_shock"]
                payload["panel"]["first_stage_largest_root"] = source_shock[
                    "companion_spectral_radius"
                ]
                payload["panel"]["generated_regressor_uncertainty"] = (
                    "Conditional bands ignore first-stage estimation uncertainty."
                )
                payload["irf"].update(
                    shock=source_shock["shock"], shock_size=source_shock["requested_physical_size"]
                )
            checks.extend(payload.pop("checks"))
            status = "ok"
            for country, sample in payload["panel"]["country_samples"].items():
                original = deepcopy(data[country].sample)
                dropped = original.get("dropped_periods", [])
                extra = [
                    {"period": p, "reason": "panel_lag_or_horizon_initialisation"}
                    for p in sample["dropped_periods"]
                ]
                original.update(sample)
                original["seasonal_controls"] = payload["panel"]["seasonal_controls"][country]
                original["dropped_periods"] = dropped + extra
                original["common_nobs"] = len(data[country].frame)
                actual[country] = original
            payload["panel"]["country_samples"] = actual
        except (ValueError, KeyError, IndexError, np.linalg.LinAlgError) as exc:
            checks.append(check("block", "panel_fit_failed", str(exc), phase="post_estimation"))
    # No country is silently removed from a pooled request.
    if status == "blocked":
        for country, d in data.items():
            actual[country] = {
                **d.sample,
                "start": None,
                "end": None,
                "nobs": 0,
                "periods": [],
                "estimation_performed": False,
            }
    periods = sorted({p for sample in actual.values() for p in sample.get("periods", [])})
    sample = {
        "start": periods[0] if periods else None,
        "end": periods[-1] if periods else None,
        "nobs": sum(s.get("nobs", 0) for s in actual.values()),
        "common_nobs": sum(len(d.frame) for d in data.values()),
        "periods": periods,
        "frequency": config["frequency"],
        "dropped_periods": [
            {"country": country, **r}
            for country, s in actual.items()
            for r in s.get("dropped_periods", [])
        ],
        "frequency_conversion": {
            country: s.get("frequency_conversion", {}) for country, s in actual.items()
        },
        "transforms": next(iter(actual.values()), {}).get("transforms", {}),
        "countries": actual,
        "rule": (
            "Country-specific complete calendar samples; no "
            "interpolation; no country silently dropped"
        ),
    }
    entry = {
        "country": "POOLED",
        "model_id": config["model"]["id"],
        "status": status,
        "label": "Conditional pooled association",
        "checks": checks,
        "actual_sample": sample,
        "sensitivity": {"status": "blocked", "variants": [], "summary": []},
        **payload,
    }
    result = {
        "schema_version": 1,
        "status": status,
        "config": config,
        "config_hash": config_hash(config),
        "snapshot_id": config["snapshot_id"],
        "code_version": os.environ.get("MACROLAB_CODE_VERSION", __version__),
        "runtime_ms": (time.perf_counter() - started) * 1000,
        "label": entry["label"],
        "checks": checks,
        "results": [entry],
        "actual_samples": actual,
    }
    if stage:
        result["first_stage"] = stage
    canonical_json(result)
    return result
