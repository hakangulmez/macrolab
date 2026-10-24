"""G15 preregistered compositions of accepted estimators (DECISIONS, 82ff653).

No estimator defaults or legacy template paths are changed here. Each alternative
retains its complete configuration, checks, country windows and fitted results.
"""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from macrolab.analysis.config import config_hash, required_countries, validated_config
from macrolab.models.forecast_common import tick
from macrolab.models.forecast_eval import score_predictions
from macrolab.models.panel import PanelLPPlugin

FOUNDERS = ["AUT", "BEL", "FIN", "FRA", "DEU", "IRL", "ITA", "LUX", "NLD", "PRT", "ESP"]
IDS = {"ea_phillips_pooled", "same_ecb_shock_pooled", "ea_inflation_horse_race"}


def catalogue(existing: list[dict[str, Any]], snapshot: str) -> list[dict[str, Any]]:
    """Pure configuration construction; does not read observations or estimate."""
    fe: dict[str, Any] = dict(
        schema_version=1,
        snapshot_id=snapshot,
        countries=FOUNDERS,
        frequency="Q",
        series=[
            dict(concept_id="cpi", role="dependent", transform="yoy_pct"),
            dict(
                concept_id="unemp",
                role="regressor",
                transform="hp_cycle",
                transform_params=dict(lamb=1600, log=False),
            ),
            dict(concept_id="oil_brent", role="exogenous", transform="yoy_pct"),
        ],
        aggregation=dict(cpi="mean", unemp="mean", oil_brent="mean"),
        sample=dict(start="1999-Q1", end="latest"),
        special_periods=dict(covid="include"),
        model=dict(id="panel.fe", params=dict(template_id="ea_phillips_pooled")),
        outputs=dict(confidence=0.95),
        comparison=dict(enabled=False),
        seed=20261021,
    )
    lp = deepcopy(next(t["config"] for t in existing if t["id"] == "same_ecb_shock"))
    lp["countries"] = ["DEU", "FRA", "ITA", "ESP"]
    p = {
        k: v
        for k, v in lp["model"]["params"].items()
        if k in PanelLPPlugin.params["properties"] and k != "template_id"
    }
    p.update(
        template_id="same_ecb_shock_pooled",
        first_stage_source="ecb_dfr",
        covariance="Driscoll-Kraay",
        response_mode="cumulative_log",
        horizon=20,
        lags=2,
        lag_augmented=True,
        country_window="common",
        sample_mode="common",
        lag_difference_scales=dict(cpi=400, gdp_real=400),
        effects="country",
    )
    lp["model"] = dict(id="panel.lp", params=p)
    lp["comparison"] = dict(enabled=False)
    for s in lp["series"]:
        if s["concept_id"] in {"cpi", "gdp_real"}:
            s.update(role="response" if s["concept_id"] == "cpi" else "endogenous", transform="log")
        elif s["role"] == "response":
            s["role"] = "endogenous"
    fc = deepcopy(fe)
    fc.update(
        countries=["EA"],
        series=[
            dict(concept_id="cpi", role="endogenous", transform="yoy_pct"),
            dict(concept_id="unemp", role="endogenous", transform="level"),
            dict(concept_id="rate_3m", role="endogenous", transform="level"),
            dict(concept_id="gdp_real", role="endogenous", transform="qoq_saar"),
        ],
    )
    fc["aggregation"] = {s["concept_id"]: "mean" for s in fc["series"]}
    fc["model"] = dict(
        id="fc.eval",
        params=dict(
            template_id="ea_inflation_horse_race",
            evaluation_scale="transformed",
            lags=2,
            draws=500,
            **{"lambda": 0.2},
            reselect=False,
        ),
    )
    return [
        dict(id=key, title=title, description=description, config=validated_config(config))
        for key, title, description, config in [
            (
                "ea_phillips_pooled",
                "Euro-area Phillips curve · pooled",
                "Eleven founding members: inflation, the unemployment gap and oil growth. "
                "Country fixed effects, Driscoll–Kraay intervals; a two-sided HP gap.",
                fe,
            ),
            (
                "same_ecb_shock_pooled",
                "Same ECB shock · pooled",
                "Pool price and GDP responses across Germany, France, Italy and Spain. "
                "Country LP overlays use identical dates; bands condition on the EA shock.",
                lp,
            ),
            (
                "ea_inflation_horse_race",
                "Euro-area inflation forecast horse race",
                "Random walk, AR, ARIMA and BVAR predict year-on-year HICP inflation. "
                "Expanding windows, final-vintage data and visible crisis sensitivities.",
                fc,
            ),
        ]
    ]


def base_config(config: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(config)
    out["model"]["params"].pop("template_id", None)
    out["comparison"] = dict(enabled=False)
    return out


def resolve_filter_endpoint(config: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Bound only the new template's retrospective filter to observed endpoints.

    Do not relax internal-gap validation or truncate the filter's prehistory.
    The requested configuration stays in the result alongside this effective one.
    """
    from macrolab.analysis.data import prepare_country

    c = base_config(config)
    filtered = [s for s in c["series"] if s["transform"] in {"hp_cycle", "hamilton_cycle"}]
    if c["sample"]["end"] != "latest" or not filtered:
        return c
    ends = []
    raw = deepcopy(c)
    raw["series"] = [
        dict(concept_id=s["concept_id"], role="regressor", transform="level") for s in filtered
    ]
    for country in c["countries"]:
        data, _ = prepare_country(raw, bundle, country)
        if len(data.frame):
            ends.append(str(data.frame.index[-1]))
    if len(ends) == len(c["countries"]):
        c["sample"]["end"] = min(ends)
    return c


def alternatives(config: dict[str, Any]) -> list[dict[str, Any]]:
    """The preregistered rows; callable without fitting the baseline."""
    template = config["model"]["params"]["template_id"]
    result = []
    ids = (
        ["rate", "hamilton", "end_2019", "lagged_inflation", "two_way", "clustered", "conventional"]
        if template == "ea_phillips_pooled"
        else ["founders", "end_2019", "horizon_12", "clustered"]
    )
    labels = {
        "rate": "Unemployment rate instead of the gap",
        "hamilton": "Hamilton unemployment gap (h = 8, p = 4)",
        "end_2019": "Sample ending 2019 Q4",
        "lagged_inflation": "Add one lag of inflation",
        "two_way": "Two-way fixed effects · common oil term absorbed",
        "clustered": "Country-clustered standard errors",
        "conventional": "Conventional standard errors",
        "founders": "Eleven founding members · common window",
        "horizon_12": "Horizon 12 · common horizon window",
    }
    for key in ids:
        c = base_config(config)
        p = c["model"]["params"]
        if key in {"rate", "hamilton"}:
            s = next(s for s in c["series"] if s["concept_id"] == "unemp")
            s.update(
                transform="level" if key == "rate" else "hamilton_cycle",
                transform_params={} if key == "rate" else dict(h=8, p=4, log=False),
            )
        elif key == "end_2019":
            c["sample"]["end"] = "2019-Q4"
            if "first_stage" in p:
                p["first_stage"]["sample"]["end"] = "2019-Q4"
        elif key == "lagged_inflation":
            p["dependent_lags"] = 1
        elif key == "two_way":
            p["effects"] = "two_way"
            c["series"] = [s for s in c["series"] if s["concept_id"] != "oil_brent"]
            c["aggregation"].pop("oil_brent")
        elif key in {"clustered", "conventional"}:
            p["covariance"] = "country-clustered" if key == "clustered" else "conventional"
        elif key == "founders":
            c["countries"] = FOUNDERS.copy()
        elif key == "horizon_12":
            p["horizon"] = 12
        result.append(dict(id=key, label=labels[key], config=validated_config(c)))
    return result


def _fit(
    config: dict[str, Any], bundle: dict[str, Any], progress: Any, cancelled: Any
) -> dict[str, Any]:
    from macrolab.analysis.engine import run_analysis

    c = resolve_filter_endpoint(config, bundle)
    # Sensitivity bundles contain eleven countries; each fit only needs its own
    # selected countries plus the first stage. Selected bytes stay unchanged.
    needed = set(required_countries(c))
    bundle = {**bundle, "countries": {k: v for k, v in bundle["countries"].items() if k in needed}}
    result = run_analysis(c, bundle, progress=progress, cancelled=cancelled)
    result["effective_config"] = c
    if c["model"]["id"] != "panel.lp":
        return result
    result["results"][0]["outcome"] = "cpi"
    other = deepcopy(c)
    for s in other["series"]:
        if s["concept_id"] in {"cpi", "gdp_real"}:
            s["role"] = "response" if s["concept_id"] == "gdp_real" else "endogenous"
    gdp = run_analysis(other, bundle, progress=progress, cancelled=cancelled)
    gdp["results"][0]["outcome"] = "gdp_real"
    result["results"].extend(gdp["results"])
    result["checks"].extend(gdp["checks"])
    result["actual_samples"] = {"cpi": result["actual_samples"], "gdp_real": gdp["actual_samples"]}
    result["response_configs"] = {"cpi": c, "gdp_real": other}
    result["status"] = "ok" if result["status"] == gdp["status"] == "ok" else "partial"
    return result


def materially_changed(baseline: float, alternative: float) -> bool:
    """Descriptive threshold only; never a significance or same-estimand test."""
    return bool(baseline * alternative < 0 or abs(alternative - baseline) > 0.5 * abs(baseline))


def comparison_rows(base: Any, variant: Any) -> list[dict[str, Any]]:
    rows = []
    for b, v in zip(base["results"], variant["results"], strict=True):
        if b["status"] != "ok" or v["status"] != "ok":
            continue
        if b["model_id"] == "panel.fe":
            for r in v["coefficients_table"]:
                old = next((x for x in b["coefficients_table"] if x["term"] == r["term"]), None)
                if old:
                    rows.append(
                        dict(
                            term=r["term"],
                            baseline=old["estimate"],
                            estimate=r["estimate"],
                            lower=r["lower"],
                            upper=r["upper"],
                            material=materially_changed(old["estimate"], r["estimate"]),
                        )
                    )
        else:
            for h, value in enumerate(v["irf"]["values"]):
                old = b["irf"]["values"][h][0]
                rows.append(
                    dict(
                        outcome=v["outcome"],
                        horizon=h,
                        baseline=old,
                        estimate=value[0],
                        lower=v["irf"]["lower"][h][0],
                        upper=v["irf"]["upper"][h][0],
                        material=materially_changed(old, value[0]),
                    )
                )
    return rows


def run_template(
    config: dict[str, Any], bundle: dict[str, Any], *, progress: Any = None, cancelled: Any = None
) -> dict[str, Any]:
    started = time.perf_counter()
    template = config["model"]["params"]["template_id"]
    result = _fit(config, bundle, progress, cancelled)
    result.update(config=config, config_hash=config_hash(config))
    result["template_notes"] = {
        "ea_phillips_pooled": [
            "The HP unemployment gap is two-sided (λ = 1600): future observations influence "
            "historical gaps. This is an association, not a real-time or causal Phillips curve.",
            "HICP inflation and Brent growth are year-on-year percentage changes. "
            "Country OLS uses HAC(4); pooled 95% intervals use Driscoll–Kraay.",
        ],
        "same_ecb_shock_pooled": [
            "Displayed bands: 68% pointwise Driscoll–Kraay, conditional on the estimated EA "
            "DFR shock. They ignore first-stage estimation uncertainty. 90% bands are in details.",
            "Country LPs use identical dates and controls with lag-augmented HC1 inference. "
            "The pooled common-slope restriction is different; this is not an agreement count.",
            "Prices and GDP are cumulative % changes in the level. They need not return to "
            "zero at horizon 20; a persistent estimated level effect is not proof of permanence.",
            "Time effects are disabled because they would absorb the common shock.",
        ],
        "ea_inflation_horse_race": [
            "The target is year-on-year HICP inflation itself. Errors are percentage points "
            "of inflation, not HICP-index points. All models start with 40 usable quarters.",
            "No exogenous regressors. Fixed first-origin orders; λ = 0.2, two BVAR lags. "
            "Final-vintage pseudo-out-of-sample results may overstate real-time performance.",
        ],
    }[template]
    if template == "ea_phillips_pooled" and config["sample"]["end"] == "latest":
        result["template_notes"].append(
            "Latest is resolved to the complete filtered-series endpoint "
            + result["effective_config"]["sample"]["end"]
            + ". Incomplete trailing quarters are excluded before filtering; internal gaps "
            "remain blocking. Requested and effective specifications are retained in exports."
        )
    result["template_sensitivity"] = []
    result["sensitivity_pending"] = True
    baseline_ms = (time.perf_counter() - started) * 1000
    if progress:
        progress(dict(phase="template_result", result=deepcopy(result)))
    if template == "ea_inflation_horse_race":
        if result["status"] == "ok":
            r = result["results"][0]
            predictions = r["evaluation"]["predictions"]
            retained = [p for p in predictions if not "2021-Q3" <= p["target"] <= "2023-Q4"]
            metrics, tests = score_predictions(retained, config["frequency"])
            r["sensitivity"]["variants"].append(
                dict(
                    id="exclude_inflation_surge_targets",
                    label="Exclude 2021 Q3–2023 Q4 targets",
                    status="ok",
                    metrics=metrics,
                    dm_tests=tests,
                    removed_predictions=len(predictions) - len(retained),
                )
            )
    else:
        variants = alternatives(config)
        for i, row in enumerate(variants):
            tick(None, cancelled, "template_sensitivity", i, len(variants))
            if progress:
                progress(
                    dict(
                        phase="template_sensitivity",
                        completed=i,
                        total=len(variants),
                        variant=row["id"],
                    )
                )
            fitted = _fit(row["config"], bundle, progress, cancelled)
            result["template_sensitivity"].append(
                dict(
                    **row,
                    status=fitted["status"],
                    results=fitted["results"],
                    effective_config=fitted["effective_config"],
                    actual_samples=fitted["actual_samples"],
                    checks=fitted["checks"],
                    comparison=comparison_rows(result, fitted),
                )
            )
        if progress:
            progress(
                dict(
                    phase="template_sensitivity",
                    completed=len(variants) - 1,
                    total=len(variants),
                    variant="complete",
                )
            )
    result["template_timing"] = dict(
        baseline_ms=baseline_ms, total_ms=(time.perf_counter() - started) * 1000
    )
    result["runtime_ms"] = result["template_timing"]["total_ms"]
    result["sensitivity_pending"] = False
    return result
