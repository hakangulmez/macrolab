"""Audited-data template orchestration; all v0 execution paths remain unchanged."""

from __future__ import annotations

import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from macrolab.analysis.config import config_hash, validated_config
from macrolab.analysis.data import prepare_country
from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.models.var import (
    _estimate,
    _normalized_response,
    _settings,
    _stable,
    residual_bootstrap,
)


def variant_bundle(bundle: dict[str, Any], measure: str) -> dict[str, Any]:
    out = deepcopy(bundle)
    ea = out["countries"]["EA"]["series"]
    for cid, name in [("policy_rate", measure), ("cpi", "hicp_sa")]:
        if name == "bis":
            continue
        if name == "rate_3m":
            item = deepcopy(ea["rate_3m"])
            item["metadata"]["concept_id"] = cid
        else:
            raw = out["variants"][name]
            meta = raw["metadata"]
            card = deepcopy(ea[cid]["metadata"])
            card.update(meta)
            card.update(
                concept_id=cid,
                frequency=meta["freq"],
                first_date=meta["start"],
                last_date=meta["end"],
                source_segments=[deepcopy(meta)],
                sources=[meta["source"]],
                flags=[],
                warnings=[],
                reason_codes=["definition_note"],
                stale=False,
                status="available_note",
            )
            item = {"metadata": card, "observations": deepcopy(raw["observations"])}
        ea[cid] = item
    for code, country in out["countries"].items():
        if code != "EA":
            country["series"]["policy_rate"] = deepcopy(ea["policy_rate"])
    return out


def merged_responses(run: dict[str, Any], band: str) -> None:
    """Expose all response columns to the existing renderer; preserve detailed blocks."""
    joint = run.get("joint_bootstrap", {})
    for row in run["results"]:
        if row["status"] != "ok":
            continue
        responses = row.get("response_results", {row["irf"]["variables"][0]: deepcopy(row)})
        names = list(responses)
        irfs = []
        for name, response in responses.items():
            irf = deepcopy(response["irf"])
            selected = joint.get("responses", {}).get(name, joint)
            if band == "joint":
                if selected.get("status") != "ok":
                    raise ValueError(
                        "Requested joint band unavailable: " + str(selected.get("reason", selected))
                    )
                bounds = selected["bands"][row["country"]]["0.68"]
                irf["lower"] = [[v] for v in bounds["lower"]]
                irf["upper"] = [[v] for v in bounds["upper"]]
                irf["band_method"] = "joint residual bootstrap (both stages)"
            irfs.append(irf)
        row["irf"] = {
            **irfs[0],
            "variables": names,
            **{
                key: [[irf[key][h][0] for irf in irfs] for h in range(len(irfs[0]["periods"]))]
                for key in ("values", "lower", "upper")
            },
        }
        shock = run["first_stage"]["results"][0]["identified_shock"]
        row["irf"].update(
            shock="policy_rate",
            shock_size=shock["requested_physical_size"],
            shock_normalization={
                "own_impact": shock["own_impact"],
                "structural_size": shock["requested_structural_size"],
            },
        )
        row["displayed_band"] = band
        row["notes"] = list(
            dict.fromkeys(
                [
                    *row.get("notes", []),
                    "Displayed band: " + row["irf"]["band_method"] + "; 68% pointwise intervals.",
                    (
                        "Conditional bands understate uncertainty by ignoring "
                        "first-stage estimation uncertainty."
                    )
                    if band == "conditional"
                    else (
                        "Joint bands re-estimate both stages; they remain pointwise and rely on "
                        "the auxiliary-model assumptions."
                    ),
                ]
            )
        )


def base_run(
    config: dict[str, Any], bundle: dict[str, Any], *, progress: Any = None, cancelled: Any = None
) -> dict[str, Any]:
    from macrolab.analysis.engine import run_analysis

    c = deepcopy(config)
    p = c["model"]["params"]
    template = p.pop("template_id")
    p["template_id"] = ""
    c["comparison"] = {"enabled": False}
    if template == "same_ecb_shock":
        b = variant_bundle(bundle, p["policy_measure"])
        first = p["first_stage"]
        first["sample"] = deepcopy(c["sample"])
        first["special_periods"] = deepcopy(c["special_periods"])
        # Resolve latest complete observations explicitly, retain the requested window.
        first_data, checks = prepare_country(first, b, "EA")
        if not len(first_data.frame):
            raise ValueError("First-stage data unavailable: " + str(checks))
        end = first_data.sample["end"]
        c["sample"]["end"] = end
        first["sample"]["end"] = end
        if p["country_window"] == "common":
            windows = []
            national_config = deepcopy(c)
            national_config["series"] = [
                s for s in c["series"] if s["concept_id"] != "identified_impulse"
            ]
            for code in c["countries"]:
                data, _ = prepare_country(national_config, b, code)
                if not len(data.frame):
                    raise ValueError("No national data for " + code)
                adoption = b["countries"][code]["metadata"].get("euro_adoption")
                start = data.sample["start"]
                if adoption:
                    start = max(start, str(pd.Period(adoption, freq="Q")).replace("Q", "-Q"))
                windows.append((start, data.sample["end"]))
            c["sample"] = {"start": max(w[0] for w in windows), "end": min(w[1] for w in windows)}
            # First-stage history remains the declared EA window; only national windows intersect.
        p["joint_bootstrap"] = p["displayed_band"] == "joint"
        run = run_analysis(c, b, progress=progress, cancelled=cancelled)
        if run["status"] == "ok":
            merged_responses(run, p["displayed_band"])
            stage_checks = [
                x for x in run["first_stage"]["checks"] if x["code"] == "first_stage_persistence"
            ]
            run["checks"].extend(stage_checks)
            for row in run["results"]:
                row["checks"].extend(deepcopy(stage_checks))
        run["requested_template_sample"] = deepcopy(config["sample"])
        run["resolved_template_sample"] = deepcopy(c["sample"])
        return run
    run = run_analysis(c, bundle, progress=progress, cancelled=cancelled)
    for row in run["results"]:
        if row["status"] == "ok":
            from macrolab.analysis.pass_through import response_ratio

            data, _ = prepare_country(c, bundle, row["country"])
            ratio_config = deepcopy(c)
            ratio_config["model"]["params"]["response_mode"] = "cumulative_log"
            row["pass_through"] = response_ratio(data, ratio_config)
            row["label"] = "Conditional cumulative pass-through ratio (depreciation-positive)"
            row["displayed_band"] = "conditional"
            row["notes"] = [
                *row.get("notes", []),
                "This is a conditional association, not an identified exchange-rate shock.",
                "Displayed band: " + row["irf"]["band_method"] + "; 68% pointwise intervals.",
                (
                    "The 2018 and 2021–2023 currency-crisis periods may affect this linear "
                    "average. Crisis-period options are deferred to v1.1."
                ),
            ]
    return run


def national_var(
    config: dict[str, Any], bundle: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Same anchor window, different identification; cumulate each bootstrap draw."""
    ecb = config["model"]["params"]["template_id"] == "same_ecb_shock"
    b = variant_bundle(bundle, config["model"]["params"]["policy_measure"]) if ecb else bundle
    from macrolab.analysis.engine import actual_sample

    output = []
    for target in baseline["results"]:
        if target["status"] != "ok":
            continue
        country = target["country"]
        if ecb:
            c = deepcopy(config["model"]["params"]["first_stage"])
            c["countries"] = [country]
            for s in c["series"]:
                if s["concept_id"] in ("gdp_real", "cpi"):
                    s["transform"] = "log_diff"
            size = baseline["first_stage"]["results"][0]["identified_shock"][
                "requested_physical_size"
            ]
            cumulative = ["gdp_real", "cpi"]
        else:
            c = deepcopy(config)
            c["series"] = [
                {
                    **s,
                    "role": "endogenous" if s["concept_id"] == "cpi" else s["role"],
                    "transform": "log_diff" if s["concept_id"] == "cpi" else s["transform"],
                }
                for s in c["series"]
            ]
            impulse = next(s["concept_id"] for s in c["series"] if s["role"] == "shock")
            c["identification"] = {"id": "recursive", "params": {"order": [impulse, "cpi"]}}
            size = config["model"]["params"]["shock_size"]
            cumulative = ["cpi"]
        c["model"] = {
            "id": "var.ols",
            "params": {
                "lags": config["model"]["params"]["lags"],
                "trend": "c",
                "lag_selection": "fixed",
                "maxlags": config["model"]["params"]["lags"],
            },
        }
        c["comparison"] = {"enabled": False}
        c["outputs"] = {
            "confidence": 0.95,
            "irf": {
                "horizon": config["model"]["params"]["horizon"],
                "bands": 0.68,
                "shock_size": size,
                "shock_mode": "fixed",
                "method": "bootstrap",
                "draws": 200,
            },
        }
        c["sample"] = deepcopy(config["sample"])
        c = validated_config(c)
        data, checks = prepare_country(c, b, country)
        data = with_seasonal_controls(data, c)
        p = c["model"]["params"]["lags"]
        freq = c["frequency"]
        anchors = target["actual_sample"]["periods"]
        left = pd.Period(anchors[0], freq=freq) - p
        right = pd.Period(anchors[-1], freq=freq)
        periods = pd.PeriodIndex(data.frame.index, freq=freq)
        keep = (periods >= left) & (periods <= right)
        data.frame = data.frame.loc[keep]
        if data.exog is not None:
            data.exog = data.exog.loc[data.frame.index]
        try:
            settings = _settings(c, recursive=True)
            fitted = _estimate(data, c, settings)
            if not _stable(np.asarray(fitted.coefs))[0]:
                raise ValueError("National VAR IRFs require stable dynamics")
            values = _normalized_response(
                np.asarray(fitted.coefs),
                np.asarray(fitted.sigma_u),
                settings["horizon"],
                settings["names"].index(settings["shock"]),
                size,
            )
            draws, meta = residual_bootstrap(
                fitted,
                horizon=settings["horizon"],
                shock=settings["names"].index(settings["shock"]),
                size=size,
                draws=200,
                seed=config["seed"],
            )
            for name in cumulative:
                j = settings["names"].index(name)
                mode = (
                    config["model"]["params"]
                    .get("response_modes", {})
                    .get(name, config["model"]["params"].get("response_mode", "cumulative_log"))
                )
                if mode == "growth_log":
                    scale = config["model"]["params"].get("growth_scale", 1)
                    values[:, j] *= scale
                    draws[:, :, j] *= scale
                else:
                    values[:, j] = values[:, j].cumsum()
                    draws[:, :, j] = draws[:, :, j].cumsum(axis=1)
            low, high = np.quantile(draws, [0.16, 0.84], axis=0)
            output.append(
                {
                    "country": country,
                    "status": "ok",
                    "irf": {
                        "variables": settings["names"],
                        "periods": list(range(settings["horizon"] + 1)),
                        "values": values.tolist(),
                        "lower": low.tolist(),
                        "upper": high.tolist(),
                        "shock": settings["shock"],
                        "shock_size": size,
                        "band_level": 0.68,
                        "band_method": "residual bootstrap, transformed within each draw",
                    },
                    "diagnostics": {
                        "stable": _stable(np.asarray(fitted.coefs))[0],
                        "estimated_indices": list(data.frame.index[p:]),
                        "bootstrap": meta,
                    },
                    "actual_sample": actual_sample(
                        data, {"diagnostics": {"estimated_indices": list(data.frame.index[p:])}}
                    ),
                    "checks": checks,
                }
            )
        except (ValueError, np.linalg.LinAlgError) as exc:
            output.append({"country": country, "status": "blocked", "reason": str(exc)})
    return {
        "status": "ok" if all(r["status"] == "ok" for r in output) else "partial",
        "results": output,
        "label": "different method and different identification",
        "same_estimand": False,
    }


def summary_rows(run: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in run["results"]:
        if entry["status"] != "ok":
            continue
        irf = entry["irf"]
        for j, name in enumerate(irf["variables"]):
            if name not in ("gdp_real", "cpi", "unemp"):
                continue
            values = np.asarray(irf["values"])[:, j]
            h = int(np.argmax(abs(values)))
            lo = irf["lower"][h][j]
            hi = irf["upper"][h][j]
            rows.append(
                {
                    "country": entry["country"],
                    "response": name,
                    "peak": float(values[h]),
                    "horizon": h,
                    "lower": lo,
                    "upper": hi,
                    "band_excludes_zero": lo > 0 or hi < 0,
                    "sample": entry["actual_sample"],
                    "periods": irf["periods"],
                    "values": values.tolist(),
                    "lowers": np.asarray(irf["lower"])[:, j].tolist(),
                    "uppers": np.asarray(irf["upper"])[:, j].tolist(),
                }
            )
    return rows


def run_template(
    config: dict[str, Any],
    bundle: dict[str, Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = base_run(config, bundle, progress=progress, cancelled=cancelled)
    template = config["model"]["params"]["template_id"]
    ecb = template == "same_ecb_shock"
    variants: list[dict[str, Any]] = []

    def publish() -> None:
        if progress and ecb and result["status"] == "ok":
            snapshot = finish_template(config, bundle, deepcopy(result), variants, started)
            snapshot["sensitivity_pending"] = bool(config["comparison"].get("enabled", True))
            progress({"phase": "template_result", "result": snapshot})

    publish()

    def add(key: str, candidate: dict[str, Any], note: str = "", same: bool = True) -> None:
        if cancelled and cancelled():
            from macrolab.ident.bootstrap import CancelledError

            raise CancelledError("Template cancelled")
        if progress:
            progress(
                {
                    "phase": "template_sensitivity",
                    "variant": key,
                    "completed": len(variants),
                    "total": 9 if ecb else 5,
                }
            )
        try:
            value = base_run(validated_config(candidate), bundle, cancelled=cancelled)
            variants.append(
                {
                    "variant_id": key,
                    "status": value["status"],
                    "label": note or key.replace("_", " "),
                    "same_estimand": same,
                    "include_in_agreement_counts": same,
                    "summary": summary_rows(value),
                    "checks": value["checks"],
                    "config": candidate,
                    "first_stage_largest_root": value.get("first_stage", {})
                    .get("results", [{}])[0]
                    .get("identified_shock", {})
                    .get("companion_spectral_radius"),
                    "pass_through": [
                        r.get("pass_through") for r in value["results"] if r.get("pass_through")
                    ],
                    "reason": "; ".join(
                        dict.fromkeys(
                            c["message"] for c in value["checks"] if c["level"] == "block"
                        )
                    ),
                }
            )
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            variants.append(
                {
                    "variant_id": key,
                    "status": "blocked",
                    "label": note or key,
                    "reason": str(exc),
                    "same_estimand": same,
                    "summary": [],
                }
            )

        publish()

    if result["status"] == "ok" and config["comparison"].get("enabled", True):
        if ecb:
            for measure in ("rate_3m", "bis"):
                c = deepcopy(config)
                c["model"]["params"].update(policy_measure=measure, displayed_band="conditional")
                add(
                    measure,
                    c,
                    "BIS switches MRO to DFR on 18 September 2024."
                    if measure == "bis"
                    else "EA 3-month money-market rate",
                    False,
                )
            c = deepcopy(config)
            c["sample"]["end"] = "2019-Q4"
            c["model"]["params"]["displayed_band"] = "conditional"
            add("end_2019", c)
            c = deepcopy(config)
            c["model"]["params"]["displayed_band"] = "conditional"
            c["model"]["params"]["first_stage"]["model"]["params"]["exclude_window"] = {
                "start": "2014-Q1",
                "end": "2022-Q4",
            }
            add(
                "exclude_2014_2022",
                c,
                "Exclude 2014–2022 in both stages; preserve calendar lags and horizon gaps",
            )
            c = deepcopy(config)
            c["model"]["params"].update(country_window="common", displayed_band="conditional")
            add("common_window", c)
            c = deepcopy(config)
            c["model"]["params"].update(lags=4, displayed_band="conditional")
            c["model"]["params"]["first_stage"]["model"]["params"]["lags"] = 4
            add("lags_4", c)
            c = deepcopy(config)
            c["model"]["params"].update(
                lag_augmented=False, covariance="HAC", displayed_band="conditional"
            )
            add("hac", c)
            c = deepcopy(config)
            c["model"]["params"]["displayed_band"] = "conditional"
            for s in c["series"]:
                if s["concept_id"] == "cpi":
                    s["transform"] = "yoy_pct"
            c["model"]["params"]["response_modes"]["cpi"] = "level"
            c["model"]["params"]["lag_difference_scales"].pop("cpi", None)
            for s in c["model"]["params"]["first_stage"]["series"]:
                if s["concept_id"] == "cpi":
                    s["transform"] = "yoy_pct"
            add("year_on_year_inflation", c, "Year-on-year inflation; different estimand", False)
        else:
            c = deepcopy(config)
            c["sample"]["start"] = "2003-01"
            add("sample_2003", c, "Pre-specified 2003 onward window; not an estimated break")
            c = deepcopy(config)
            c["model"]["params"]["lags"] = 6
            add("lags_6", c)
            c = deepcopy(config)
            c["model"]["params"]["shock_size"] = 1
            for s in c["series"]:
                if s["concept_id"] == "neer":
                    s["concept_id"] = "fx_usd"
            c["aggregation"].pop("neer", None)
            c["aggregation"]["fx_usd"] = "mean"
            add("usd", c, "TRY per USD: +1% depreciation", False)
            c = deepcopy(config)
            c["model"]["params"].update(lag_augmented=False, covariance="HAC")
            add("hac", c)
        if progress:
            progress(
                {
                    "phase": "template_sensitivity",
                    "variant": "national_var",
                    "completed": len(variants),
                    "total": 9 if ecb else 5,
                }
            )
        var = national_var(config, bundle, result)
        variants.append(
            {
                "variant_id": "national_var",
                "status": var["status"],
                "label": var["label"],
                "same_estimand": False,
                "include_in_agreement_counts": False,
                "summary": summary_rows(var),
                "results": var["results"],
            }
        )
        if ecb and config["model"]["params"]["displayed_band"] != "joint":
            variants.append(
                {
                    "variant_id": "joint_bootstrap",
                    "status": "on_demand",
                    "label": "Compute full uncertainty (joint bootstrap), on the common window",
                    "same_estimand": True,
                    "include_in_agreement_counts": False,
                    "summary": [],
                }
            )
    return finish_template(config, bundle, result, variants, started)


def finish_template(
    config: dict[str, Any],
    bundle: dict[str, Any],
    result: dict[str, Any],
    variants: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    """A complete baseline is usable while sensitivity rows are still pending."""
    ecb = config["model"]["params"]["template_id"] == "same_ecb_shock"
    if ecb and result["status"] == "ok" and "lag_criteria" not in result:
        from macrolab.ident.external_series import recover

        first = result["first_stage"]["config"]
        selected = variant_bundle(bundle, config["model"]["params"]["policy_measure"])
        data, _ = prepare_country(first, selected, "EA")
        _, fitted = recover(data, first)
        criteria = fitted.model.select_order(maxlags=4) if hasattr(fitted, "model") else None
        result["lag_criteria"] = {
            "selected_lags": {k: int(v) for k, v in criteria.selected_orders.items()}
            if criteria
            else {},
            "candidates": [
                {"lag": h, **{k: float(values[h]) for k, values in criteria.ics.items()}}
                for h in range(5)
            ]
            if criteria
            else [],
            "comparison_sample": {
                "start": str(data.frame.index[4]),
                "end": str(data.frame.index[-1]),
                "nobs": len(data.frame) - 4,
            }
            if criteria
            else {},
            "note": "Selection criteria are shown; the pre-specified two-lag default is retained.",
        }
    result["template_sensitivity"] = deepcopy(variants)
    result["template_summary"] = summary_rows(result)
    if ecb and result["status"] == "ok":
        shock = result["first_stage"]["results"][0]["identified_shock"]
        result["first_stage_largest_root"] = shock["companion_spectral_radius"]
        result["magnitude_note"] = (
            "The peak price responses are large relative to typical "
            "estimates for a shock of this size "
            "and should be read with the identification caveats."
        )
        result["scaled_peaks"] = [
            {
                "country": r["country"],
                "response": r["response"],
                "horizon": r["horizon"],
                "one_sd": r["peak"] / shock["requested_structural_size"],
                "plus_25bp": r["peak"] * 0.25 / shock["requested_physical_size"],
            }
            for r in result["template_summary"]
        ]
    for row in result["results"]:
        if row["status"] != "ok":
            continue
        notes = row.setdefault("notes", [])
        if ecb:
            notes.extend(
                [
                    (
                        "The 2014–2022 lower-bound/negative-rate period is included; no shadow "
                        "rate is available in v1."
                    ),
                    (
                        "Recursive identification assumes national/EA output and prices do not "
                        "respond within the quarter to the policy innovation; ordering cannot "
                        "remove omitted policy information."
                    ),
                    (
                        "Selected-peak country comparisons are descriptive; overlapping intervals"
                        " do not support a ranking."
                    ),
                ]
            )
            if any(
                s["peak"] > 0
                for s in result["template_summary"]
                if s["country"] == row["country"] and s["response"] in ("gdp_real", "cpi")
            ):
                notes.append(
                    "An output/price puzzle appears: policy reacts to omitted information, "
                    "recursive timing restrictions and lower-bound/sample choices can produce"
                    " positive responses. The estimate is retained, not forced to a textbook "
                    "sign."
                )
        row["sensitivity"] = {
            "status": "ok",
            "variants": [
                {
                    "variant_id": v["variant_id"],
                    "status": "available" if v["status"] == "ok" else v["status"],
                    "label": v["label"],
                    "same_estimand": v["same_estimand"],
                    "include_in_agreement_counts": v.get("include_in_agreement_counts", False),
                    "informative_point_comparison": v.get("include_in_agreement_counts", False)
                    and v["variant_id"] != "common_window",
                    "metrics": {
                        "responses": [
                            {
                                "variable": s["response"],
                                "peak": s["peak"],
                                "peak_response": s["peak"],
                                "peak_absolute_response": abs(s["peak"]),
                                "band_excludes_zero_at_peak": s["band_excludes_zero"],
                                "peak_horizon": s["horizon"],
                                "periods": s["periods"],
                                "values": s["values"],
                                "lower": s["lowers"],
                                "upper": s["uppers"],
                            }
                            for s in v["summary"]
                            if s["country"] == row["country"]
                        ]
                    },
                    "reason": v.get("reason"),
                    "first_stage_largest_root": v.get("first_stage_largest_root"),
                }
                for v in variants
            ],
        }
        from macrolab.analysis.sensitivity import _response_summary

        baseline_metrics = {
            "variant_id": "baseline",
            "status": "available",
            "metrics": {
                "responses": [
                    {
                        "variable": s["response"],
                        "peak_response": s["peak"],
                        "peak_absolute_response": abs(s["peak"]),
                        "peak_horizon": s["horizon"],
                        "band_excludes_zero_at_peak": s["band_excludes_zero"],
                    }
                    for s in result["template_summary"]
                    if s["country"] == row["country"]
                ]
            },
        }
        row["sensitivity"]["summary"] = _response_summary(
            [baseline_metrics, *row["sensitivity"]["variants"]]
        )
        row["sensitivity"]["comparison_rule"] = (
            "Same-estimand alternatives only; national VAR uses different method and "
            "different identification and is excluded from agreement counts."
        )
        if ecb:
            row["sensitivity"]["lag_criteria"] = result.get("lag_criteria", {})
    result.update(
        config=config,
        config_hash=config_hash(config),
        runtime_ms=(time.perf_counter() - started) * 1000,
    )
    return result
