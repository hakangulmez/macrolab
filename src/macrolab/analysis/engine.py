"""One offline numerical engine for native Python, local API and browser workers."""

from __future__ import annotations

import copy
import os
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from macrolab import __version__
from macrolab.analysis.config import (
    canonical_json,
    config_hash,
    required_concepts,
    required_countries,
    validated_config,
)
from macrolab.analysis.data import prepare_country, snapshot_bundle
from macrolab.analysis.g21 import run_configured_plugin
from macrolab.models.base import AnalysisData, check
from macrolab.models.registry import PLUGINS, catalogue, get_plugin


def _inputs(config: dict[str, Any], bundle: dict[str, Any] | None) -> dict[str, Any]:
    if bundle is None:
        bundle = snapshot_bundle(
            config["snapshot_id"], required_countries(config), required_concepts(config)
        )
        if config["model"]["params"].get("template_id") == "same_ecb_shock_pooled" or (
            config["model"]["id"] == "test.break"
            and config["model"]["params"].get("source_variant", "none") != "none"
        ):
            import json
            from pathlib import Path

            path = (
                Path(__file__).resolve().parents[3]
                / "data/processed/snapshots"
                / config["snapshot_id"]
                / "browser/global-variants.json"
            )
            variants = json.loads(path.read_text())
            if variants["snapshot_id"] != config["snapshot_id"]:
                raise ValueError("Source variants must match the selected snapshot")
            bundle["variants"] = variants["variants"]
    if bundle.get("snapshot_id") != config["snapshot_id"]:
        raise ValueError("The input bundle does not match the requested snapshot")
    if not isinstance(bundle.get("countries"), dict):
        raise ValueError("Invalid country bundle")
    return bundle


def _dedupe(checks: list[dict[str, Any]], country: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in checks:
        item = {**item, "country": country}
        key = canonical_json(item)
        if key not in seen:
            output.append(item)
            seen.add(key)
    return output


def _prepare(
    config: dict[str, Any], bundle: dict[str, Any], country: str
) -> tuple[AnalysisData, list[dict[str, Any]]]:
    from macrolab.checks.core import evaluate_checks

    if country not in bundle["countries"]:
        import pandas as pd

        return AnalysisData(pd.DataFrame(), country=country), [
            check("block", "missing_coverage", "No data bundle for this country.", country=country)
        ]
    if config["model"]["id"] in {"uni.arima", "fc.var", "fc.eval"}:
        from macrolab.models.forecast_common import prepare_forecast

        data, checks = prepare_forecast(config, bundle, country)
        return data, _dedupe(checks, country)
    data, checks = prepare_country(config, bundle, country)
    if not any(c["level"] == "block" for c in checks):
        checks.extend(evaluate_checks(data, config, bundle))
    if not any(c["level"] == "block" for c in checks):
        checks.extend(get_plugin(config["model"]["id"]).check(data, config))
    return data, _dedupe(checks, country)


def actual_sample(data: AnalysisData, payload: dict[str, Any]) -> dict[str, Any]:
    sample = copy.deepcopy(data.sample)
    common = list(map(str, data.frame.index))
    estimated = list(map(str, payload.get("diagnostics", {}).get("estimated_indices", common)))
    sample.update(
        {
            "common_nobs": len(common),
            "nobs": len(estimated),
            "periods": estimated,
            "start": estimated[0] if estimated else None,
            "end": estimated[-1] if estimated else None,
        }
    )
    if "local_projection" in payload:
        sample["horizon_sample_mode"] = payload["local_projection"]["sample_mode"]
        sample["nobs_by_horizon"] = payload["diagnostics"]["nobs_by_horizon"]
    if "forecast" in payload:
        sample["transforms"] = copy.deepcopy(payload["diagnostics"]["transforms"])
    sample.setdefault("frequency", data.frequency)
    sample.setdefault("frequency_conversion", {})
    sample.setdefault("transforms", {})
    sample.setdefault("dropped_periods", [])
    sample["dropped_periods"].extend(
        {
            "period": period,
            "reason": (
                "horizon_holdback"
                if "local_projection" in payload and estimated and period > estimated[-1]
                else "model_initialisation"
            ),
        }
        for period in common
        if period not in set(estimated)
    )
    crisis = payload.get("local_projection", {}).get("crisis")
    if crisis:
        excluded = {p for dates in crisis["excluded_anchors_by_horizon"].values() for p in dates}
        for item in sample["dropped_periods"]:
            if item["period"] in excluded:
                item["reason"] = "crisis_footprint"
        sample["crisis"] = copy.deepcopy(crisis)
    return sample


def run_analysis(
    config: dict[str, Any],
    bundle: dict[str, Any] | None = None,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Return checks even when a country is blocked; never estimate a blocked selection."""
    from macrolab.analysis.sensitivity import build_sensitivity
    from macrolab.checks.core import postfit_checks

    started = time.perf_counter()
    config = validated_config(config)
    bundle = _inputs(config, bundle)
    from macrolab.analysis.templates_v2 import IDS as V2_TEMPLATES

    if config["model"]["params"].get("template_id") in V2_TEMPLATES:
        from macrolab.analysis.templates_v2 import run_template as run_v2_template

        return run_v2_template(config, bundle, progress=progress, cancelled=cancelled)
    if config["model"]["id"] in {"panel.fe", "panel.lp"}:
        from macrolab.analysis.panel import run_panel

        return run_panel(config, bundle, progress=progress, cancelled=cancelled)
    if config["model"]["params"].get("template_id"):
        from macrolab.analysis.templates_v1 import run_template

        return run_template(config, bundle, progress=progress, cancelled=cancelled)
    if config["model"]["id"] == "cmp.common_shock":
        from macrolab.analysis.v1 import run_common

        return run_common(config, bundle, progress=progress, cancelled=cancelled)
    plugin = get_plugin(config["model"]["id"])
    if (
        plugin.id == "test.break"
        and config["model"]["params"].get("source_variant", "none") != "none"
    ):
        from macrolab.analysis.templates_v1 import variant_bundle

        bundle = variant_bundle(bundle, config["model"]["params"]["source_variant"])
    prepared = {country: _prepare(config, bundle, country) for country in config["countries"]}
    # Comparative statistics require the same dates in every eligible country.
    if plugin.inputs.get("cross_country") and len(prepared) > 1:
        eligible = [d for d, c in prepared.values() if not any(x["level"] == "block" for x in c)]
        if eligible:
            common = eligible[0].frame.index
            for data in eligible[1:]:
                common = common.intersection(data.frame.index, sort=False)
            for data in eligible:
                removed = data.frame.index.difference(common)
                data.sample.setdefault("dropped_periods", []).extend(
                    {"period": str(p), "reason": "cross_country_common_sample"} for p in removed
                )
                data.frame = data.frame.loc[common]
                if data.exog is not None:
                    data.exog = data.exog.loc[common]
                data.panels = {d.country: d.frame.loc[common] for d in eligible}
                data.sample.update(
                    {
                        "start": str(common[0]) if len(common) else None,
                        "end": str(common[-1]) if len(common) else None,
                        "nobs": len(common),
                        "common_nobs": len(common),
                        "periods": list(map(str, common)),
                    }
                )
                country_checks = prepared[data.country][1]
                if not len(common):
                    country_checks.append(
                        check(
                            "block",
                            "missing_coverage",
                            "Selected countries have no common observed sample.",
                            country=data.country,
                        )
                    )
                else:
                    from macrolab.checks.core import evaluate_checks

                    country_checks.extend(evaluate_checks(data, config, bundle))
                    country_checks.extend(plugin.check(data, config))
    results: list[dict[str, Any]] = []
    for country, (data, checks) in prepared.items():
        entry: dict[str, Any] = {
            "country": country,
            "model_id": plugin.id,
            "status": "blocked",
            "label": plugin.label,
            "checks": checks,
        }
        payload: dict[str, Any] = {}
        if not any(c["level"] == "block" for c in checks):
            try:
                if plugin.id in {"uni.arima", "fc.var", "fc.eval"}:
                    from macrolab.models.arima import run_arima
                    from macrolab.models.forecast_eval import run_evaluation
                    from macrolab.models.forecast_var import run_var_forecast

                    runner = {
                        "uni.arima": run_arima,
                        "fc.var": run_var_forecast,
                        "fc.eval": run_evaluation,
                    }[plugin.id]
                    payload = runner(data, config, progress=progress, cancelled=cancelled)
                    checks.extend(payload.pop("checks", []))
                elif plugin.id in {"test.coint", "vecm", "test.break"}:
                    from macrolab.models.break_tests import run_break_tests
                    from macrolab.models.cointegration import fit_vecm, test_cointegration

                    if plugin.id == "test.coint":
                        payload = test_cointegration(data, config)
                    else:
                        diagnostic_runner = fit_vecm if plugin.id == "vecm" else run_break_tests
                        payload = diagnostic_runner(
                            data, config, progress=progress, cancelled=cancelled
                        )
                    checks.extend(payload.pop("checks", []))
                elif plugin.id == "bvar.minn":
                    from macrolab.models.bvar import fit_bvar

                    payload = fit_bvar(data, config, progress=progress, cancelled=cancelled)
                    checks.extend(payload.pop("checks", []))
                else:
                    payload = run_configured_plugin(data, config)
                canonical_json(payload)
                checks.extend(postfit_checks(data, config, payload))
                if not any(c["level"] == "block" for c in checks):
                    entry.update(payload)
                    entry["status"] = "ok"
            except (
                ValueError,
                TypeError,
                KeyError,
                ZeroDivisionError,
                np.linalg.LinAlgError,
            ) as exc:
                checks.append(
                    check(
                        "block",
                        "model_fit_failed",
                        str(exc),
                        country=country,
                        phase="post_estimation",
                    )
                )
        entry["checks"] = _dedupe(checks, country)
        entry["actual_sample"] = actual_sample(data, payload if entry["status"] == "ok" else {})
        if entry["status"] == "ok":
            entry["sensitivity"] = (
                payload["sensitivity"]
                if plugin.id
                in {
                    "bvar.minn",
                    "uni.arima",
                    "fc.var",
                    "fc.eval",
                    "test.coint",
                    "vecm",
                    "test.break",
                }
                else build_sensitivity(data, config, payload, bundle=bundle)
            )
        else:
            entry["actual_sample"].update(
                {
                    "start": None,
                    "end": None,
                    "nobs": 0,
                    "periods": [],
                    "estimation_performed": False,
                }
            )
            entry["sensitivity"] = {
                "status": "blocked",
                "variants": [],
                "reason": "Resolve the blocking input or model checks first.",
            }
        results.append(entry)
    successful = sum(r["status"] == "ok" for r in results)
    result = {
        "schema_version": 1,
        "status": "ok" if successful == len(results) else "partial" if successful else "blocked",
        "config_hash": config_hash(config),
        "snapshot_id": config["snapshot_id"],
        "code_version": os.environ.get("MACROLAB_CODE_VERSION", __version__),
        "runtime_ms": (time.perf_counter() - started) * 1000,
        "label": next((r["label"] for r in results if r["status"] == "ok"), plugin.label),
        "config": config,
        "checks": [c for r in results for c in r["checks"]],
        "results": results,
        "actual_samples": {r["country"]: r["actual_sample"] for r in results},
    }
    canonical_json(result)
    return result


def compatibility(config: dict[str, Any], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """List all v0 choices, preserving the reasons for unavailable alternatives."""
    config = validated_config(config)
    bundle = _inputs(config, bundle)
    from macrolab.analysis.templates_v2 import IDS as V2_TEMPLATES
    from macrolab.analysis.templates_v2 import resolve_filter_endpoint

    if config["model"]["params"].get("template_id") in V2_TEMPLATES:
        # Compatibility prepares inputs; it must not run a costly forecast horse race.
        result = compatibility(resolve_filter_endpoint(config, bundle), bundle)
        result["config_hash"] = config_hash(config)
        return result
    if config["model"]["params"].get("template_id"):
        from macrolab.analysis.templates_v1 import base_run

        candidate = copy.deepcopy(config)
        candidate["model"]["params"]["displayed_band"] = "conditional"
        result = base_run(candidate, bundle)
        return {
            "schema_version": 1,
            "snapshot_id": config["snapshot_id"],
            "config_hash": config_hash(config),
            "models": [
                {
                    **m,
                    "available": result["status"] == "ok"
                    if m["id"] == config["model"]["id"]
                    else False,
                    "checks": result["checks"]
                    if m["id"] == config["model"]["id"]
                    else [
                        check(
                            "block",
                            "template_method",
                            "Select another template to change the method",
                        )
                    ],
                }
                for m in catalogue()
            ],
            "released_models": list(PLUGINS),
        }
    choices = []
    for metadata in catalogue():
        candidate = copy.deepcopy(config)
        candidate["model"] = {
            "id": metadata["id"],
            "params": (
                config["model"]["params"] if metadata["id"] == config["model"]["id"] else {}
            ),
        }
        if metadata["id"] not in ("var.ols", "ident.recursive"):
            candidate["identification"] = None
            candidate["outputs"].pop("irf", None)
        checks: list[dict[str, Any]] = []
        try:
            candidate = validated_config(candidate)
            if candidate["model"]["id"] in {"panel.fe", "panel.lp"}:
                from macrolab.analysis.panel import prepare_panel

                _, checks, _ = prepare_panel(candidate, bundle)
            else:
                for country in candidate["countries"]:
                    _, country_checks = _prepare(candidate, bundle, country)
                    checks.extend(country_checks)
        except ValueError as exc:
            checks.append(check("block", "model_configuration", str(exc)))
        choices.append(
            {
                **metadata,
                "available": not any(c["level"] == "block" for c in checks),
                "checks": checks,
            }
        )
    return {
        "schema_version": 1,
        "snapshot_id": config["snapshot_id"],
        "config_hash": config_hash(config),
        "models": choices,
        "released_models": list(PLUGINS),
    }
