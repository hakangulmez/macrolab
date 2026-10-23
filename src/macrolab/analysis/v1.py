"""v1 orchestration. Existing v0 execution paths and defaults remain intact."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pandas as pd

from macrolab import __version__
from macrolab.analysis.config import config_hash, validated_config
from macrolab.analysis.data import input_fingerprint, prepare_country
from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.ident.bootstrap import CancelledError, joint_bootstrap
from macrolab.ident.external_series import attach
from macrolab.models.base import check
from macrolab.models.lp import fit


def lp_sensitivity(
    data: Any, config: dict[str, Any], baseline: dict[str, Any], bundle: Any
) -> dict[str, Any]:
    from macrolab.analysis.engine import run_analysis

    variants: list[dict[str, Any]] = [
        {"variant_id": "baseline", "status": "ok", "result": baseline}
    ]
    candidates = []
    for key, value in (
        ("lag_augmented", not config["model"]["params"].get("lag_augmented", False)),
        ("lags", min(24, config["model"]["params"].get("lags", 2) + 1)),
    ):
        candidate = deepcopy(config)
        candidate["model"]["params"][key] = value
        candidates.append((key, candidate))
    for name, candidate in candidates:
        try:
            from macrolab.models.lp import LPPlugin

            checks = LPPlugin().check(data, candidate)
            if any(c["level"] == "block" for c in checks):
                variants.append({"variant_id": name, "status": "blocked", "checks": checks})
            else:
                variants.append(
                    {
                        "variant_id": name,
                        "status": "ok",
                        "result": fit(data, candidate),
                        "checks": checks,
                    }
                )
        except ValueError as exc:
            variants.append({"variant_id": name, "status": "blocked", "reason": str(exc)})
    # This changes the estimand and is explicitly excluded from agreement counts.
    prices = [
        s
        for s in config["series"]
        if s["concept_id"] in {"cpi", "cpi_core"}
        and s["transform"] in {"log", "qoq_saar", "log_diff", "diff"}
    ]
    if prices and bundle is not None:
        candidate = deepcopy(config)
        for spec in candidate["series"]:
            if spec["concept_id"] in {s["concept_id"] for s in prices}:
                spec["transform"] = "yoy_pct"
        if any(s["role"] in {"response", "dependent"} for s in prices):
            candidate["model"]["params"]["response_mode"] = "level"
        candidate["comparison"] = {"enabled": False}
        candidate["countries"] = [data.country]
        result = run_analysis(candidate, bundle)
        variants.append(
            {
                "variant_id": "year_on_year_inflation",
                "status": result["status"],
                "result": result,
                "same_estimand": False,
                "include_in_agreement_counts": False,
                "label": "Year-on-year inflation; different response horizon",
            }
        )
    return {
        "status": "ok",
        "variants": variants,
        "enabled": True,
        "note": "Specifications are shown separately, never averaged.",
    }


def run_common(
    config: dict[str, Any],
    bundle: dict[str, Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    _first_stage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from macrolab.analysis.engine import actual_sample, run_analysis

    started = time.perf_counter()
    params = config["model"]["params"]
    responses = [
        s["concept_id"] for s in config["series"] if s["role"] in {"response", "dependent"}
    ]
    if len(responses) > 1:
        runs = {}
        for response in responses:
            candidate = deepcopy(config)
            for spec in candidate["series"]:
                if spec["concept_id"] in responses:
                    spec["role"] = "response" if spec["concept_id"] == response else "endogenous"
            candidate["model"]["params"]["response_mode"] = params.get("response_modes", {}).get(
                response, params.get("response_mode", "level")
            )
            candidate = validated_config(candidate)

            def response_progress(detail: dict[str, Any], response: str = response) -> None:
                if progress:
                    progress({**detail, "response": response})

            runs[response] = run_common(
                candidate,
                bundle,
                progress=response_progress,
                cancelled=cancelled,
                _first_stage=_first_stage,
            )
            _first_stage = runs[response]["first_stage"]
        combined = deepcopy(runs[responses[0]])
        combined.update(
            config=config,
            config_hash=config_hash(config),
            runtime_ms=(time.perf_counter() - started) * 1000,
        )
        combined["status"] = (
            "ok"
            if all(r["status"] == "ok" for r in runs.values())
            else "blocked"
            if all(r["status"] == "blocked" for r in runs.values())
            else "partial"
        )
        combined["checks"] = [c for r in runs.values() for c in r["checks"]]
        for entry in combined["results"]:
            country = entry["country"]
            entry["response_results"] = {
                response: next(r for r in run["results"] if r["country"] == country)
                for response, run in runs.items()
            }
            entry["actual_sample"]["responses"] = {
                response: row["actual_sample"]
                for response, row in entry["response_results"].items()
            }
        combined["actual_samples"] = {r["country"]: r["actual_sample"] for r in combined["results"]}
        combined["common_shock"]["summary"] = [
            {**row, "response": response}
            for response, run in runs.items()
            for row in run["common_shock"]["summary"]
        ]
        combined["joint_bootstrap"] = {
            "enabled": params.get("joint_bootstrap", False),
            "responses": {response: run["joint_bootstrap"] for response, run in runs.items()},
            "status": "ok"
            if all(run["joint_bootstrap"]["status"] == "ok" for run in runs.values())
            else "disabled"
            if not params.get("joint_bootstrap")
            else "blocked",
        }
        return combined
    first_config = deepcopy(params["first_stage"])
    first_config["model"]["id"] = "ident.external_series"
    first_config["comparison"] = {"enabled": False}
    first_config = validated_config(first_config)
    if cancelled and cancelled():
        raise CancelledError("Common-shock analysis cancelled")
    if progress:
        progress({"phase": "first_stage", "completed": 0, "total": 1})
    stage1 = _first_stage if _first_stage is not None else run_analysis(first_config, bundle)
    if stage1["status"] != "ok":
        blocked = deepcopy(stage1)
        blocked.update(config=config, config_hash=config_hash(config), first_stage=stage1)
        blocked["results"] = [
            {
                "country": country,
                "model_id": "cmp.common_shock",
                "status": "blocked",
                "label": "Common shock unavailable",
                "checks": stage1["checks"],
                "actual_sample": {
                    "start": None,
                    "end": None,
                    "nobs": 0,
                    "common_nobs": 0,
                    "periods": [],
                    "dropped_periods": [],
                    "frequency_conversion": {},
                    "transforms": {},
                },
                "sensitivity": {"status": "blocked", "variants": []},
            }
            for country in config["countries"]
        ]
        blocked["common_shock"] = {"summary": []}
        blocked["joint_bootstrap"] = {
            "status": "blocked",
            "enabled": params.get("joint_bootstrap", False),
            "reason": "First-stage checks block estimation",
        }
        blocked["actual_samples"] = {r["country"]: r["actual_sample"] for r in blocked["results"]}
        return blocked
    shock = stage1["results"][0]["identified_shock"]
    enriched = deepcopy(bundle)
    for country in config["countries"]:
        if country not in enriched["countries"]:
            continue
        enriched["countries"][country]["series"]["identified_impulse"] = {
            "metadata": {
                "concept_id": "identified_impulse",
                "frequency": config["frequency"],
                "status": "available_note",
                "identified_shock": True,
                "source": "EA recursive VAR",
                "first_date": shock["periods"][0],
                "last_date": shock["periods"][-1],
                "warnings": [],
                "flags": [],
            },
            "observations": list(zip(shock["periods"], shock["values"], strict=True)),
        }
    results, national, lp_configs = [], {}, {}
    for i, country in enumerate(config["countries"]):
        if cancelled and cancelled():
            raise CancelledError("Country comparison cancelled")
        lp_config = deepcopy(config)
        lp_config["model"] = {
            "id": "lp.ols",
            "params": {
                k: v
                for k, v in params.items()
                if k not in {"first_stage", "joint_bootstrap", "bootstrap_draws", "response_modes"}
            },
        }
        lp_config["model"]["params"]["shock_size"] = shock["requested_structural_size"]
        lp_config["countries"] = [country]
        adoption = enriched["countries"].get(country, {}).get("metadata", {}).get("euro_adoption")
        if (
            adoption
            and config["sample"]["start"]
            == {"Q": "1999-Q1", "M": "1999-01", "A": "1999"}[config["frequency"]]
        ):
            adopted = pd.Period(adoption, freq=config["frequency"])
            if pd.Timestamp(adoption) > adopted.start_time:
                adopted += 1
            requested = pd.Period(config["sample"]["start"], freq=config["frequency"])
            lp_config["sample"]["start"] = str(max(adopted, requested)).replace("Q", "-Q")
        lp_config = validated_config(lp_config)
        coverage_failure = None
        national_data = None
        if country in bundle["countries"]:
            original_config = deepcopy(lp_config)
            original_config["series"] = [
                spec
                for spec in original_config["series"]
                if spec["concept_id"] != "identified_impulse"
            ]
            national_data, _ = prepare_country(original_config, bundle, country)
            # The first-stage lag holdback is a known model-initialisation loss.
            # All other national input dates must be covered: do not silently
            # trim a late/early national sample to the generated shock window.
            initial = set(shock["first_stage_sample"].get("periods", [])) - set(shock["periods"])
            national_data.frame = national_data.frame.loc[~national_data.frame.index.isin(initial)]
            if national_data.exog is not None:
                national_data.exog = national_data.exog.loc[national_data.frame.index]
            if len(national_data.frame):
                try:
                    attach(national_data, shock)
                except ValueError as exc:
                    coverage_failure = str(exc)
        if coverage_failure and national_data is not None:
            sample = actual_sample(national_data, {})
            sample.update(start=None, end=None, nobs=0, periods=[], estimation_performed=False)
            entry = {
                "country": country,
                "model_id": "cmp.common_shock",
                "status": "blocked",
                "label": "Common shock does not cover the selected national sample",
                "checks": [check("block", "shock_alignment", coverage_failure, country=country)],
                "actual_sample": sample,
                "sensitivity": {"status": "blocked", "variants": []},
            }
        else:
            run = run_analysis(lp_config, enriched)
            entry = run["results"][0]

        # A generated regressor is a model output, not a new raw data source.
        # Fingerprint the original national inputs and the first-stage inputs /
        # configuration; keep the unrounded shocks in the first-stage result.
        def source_provenance(value: Any, country: str = country) -> None:
            if isinstance(value, dict):
                if "source_data_sha256" in value and "preparation_config" in value:
                    selected = value["preparation_config"]["series"]
                    original = bundle["countries"][country]
                    value["source_data_sha256"] = input_fingerprint(
                        {
                            "snapshot_id": config["snapshot_id"],
                            "country": country,
                            "metadata": original["metadata"],
                            "national_original_series": {
                                spec["concept_id"]: original["series"].get(spec["concept_id"])
                                for spec in selected
                                if spec["concept_id"] != "identified_impulse"
                            },
                            "generated_impulse": {
                                "first_stage_input_sha256": stage1["actual_samples"][
                                    first_config["countries"][0]
                                ]["source_data_sha256"],
                                "first_stage_config": first_config,
                                "definition": "inverse Cholesky times first-stage residual",
                            },
                        }
                    )
                    value["source_data_hash_basis"] = (
                        "Original national inputs plus first-stage input "
                        "fingerprint/configuration; "
                        "unrounded generated shocks are model outputs, not source observations."
                    )
                for child in value.values():
                    source_provenance(child)
            elif isinstance(value, list):
                for child in value:
                    source_provenance(child)

        source_provenance(entry)
        entry["model_id"] = "cmp.common_shock"
        if adoption and lp_config["sample"]["start"] != config["sample"]["start"]:
            entry["checks"].append(
                check(
                    "info",
                    "euro_sample_start",
                    "Sample starts at euro adoption.",
                    country=country,
                    adoption=adoption,
                )
            )
        results.append(entry)
        if progress:
            progress(
                {
                    "phase": "country_comparison",
                    "country": country,
                    "completed": i + 1,
                    "total": len(config["countries"]),
                }
            )
        if entry["status"] == "ok":
            national[country] = prepare_country(lp_config, enriched, country)[0]
            lp_configs[country] = lp_config
    summary = []
    for entry in results:
        if entry["status"] != "ok":
            continue
        row = max(entry["local_projection"]["horizons"], key=lambda r: abs(r["estimate"]))
        band = row["bands"]["0.68"]
        summary.append(
            {
                "country": entry["country"],
                "peak": row["estimate"],
                "horizon": row["horizon"],
                **band,
                "band_level": 0.68,
                "nobs": row["nobs"],
                "band_excludes_zero": band["lower"] > 0 or band["upper"] < 0,
                "sample": entry["actual_sample"],
            }
        )
    bootstrap = {"status": "disabled", "enabled": False}
    if params.get("joint_bootstrap"):
        try:
            if len(national) != len(config["countries"]):
                raise ValueError("Resolve blocked country inputs before joint bootstrap")
            first_data = with_seasonal_controls(
                prepare_country(first_config, bundle, first_config["countries"][0])[0], first_config
            )
            bootstrap = {
                "status": "ok",
                "enabled": True,
                **joint_bootstrap(
                    first_data,
                    first_config,
                    national,
                    lp_configs,
                    draws=params["bootstrap_draws"],
                    seed=config["seed"],
                    progress=progress,
                    cancelled=cancelled,
                ),
            }
        except CancelledError:
            raise
        except ValueError as exc:
            bootstrap = {"status": "blocked", "enabled": True, "reason": str(exc)}
            for entry in results:
                entry["checks"].append(
                    check(
                        "warn",
                        "joint_bootstrap_unavailable",
                        str(exc),
                        phase="post_estimation",
                        country=entry["country"],
                    )
                )
    successful = sum(r["status"] == "ok" for r in results)
    return {
        "schema_version": 1,
        "config": config,
        "config_hash": config_hash(config),
        "snapshot_id": config["snapshot_id"],
        "code_version": os.environ.get("MACROLAB_CODE_VERSION", __version__),
        "runtime_ms": (time.perf_counter() - started) * 1000,
        "status": "ok" if successful == len(results) else "partial" if successful else "blocked",
        "label": "Descriptive cross-country comparison under the same identified shock",
        "checks": [c for r in results for c in r["checks"]],
        "results": results,
        "actual_samples": {r["country"]: r["actual_sample"] for r in results},
        "first_stage": stage1,
        "common_shock": {
            "summary": summary,
            "ranking_note": (
                "Selected-peak comparisons are descriptive. Overlapping intervals do not "
                "support a ranking; no equality test is performed."
            ),
        },
        "joint_bootstrap": bootstrap,
    }
