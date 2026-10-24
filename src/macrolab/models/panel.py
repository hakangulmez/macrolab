"""Portable within estimators; linearmodels is an independent native test only."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm, t  # type: ignore[import-untyped]

from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import label, period_frequency
from macrolab.ident.bootstrap import CancelledError
from macrolab.models.base import (
    AnalysisData,
    BasePlugin,
    check,
    parameters,
    roles,
    sample_size_check,
)
from macrolab.models.linear import choice, integer, schema
from macrolab.models.lp import _active, design

COVARIANCES = ("Driscoll-Kraay", "country-clustered", "conventional")


def demean(a: Any, groups: Any) -> Any:
    sums = np.zeros((int(groups.max()) + 1, a.shape[1]))
    np.add.at(sums, groups, a)
    return a - (sums / np.bincount(groups)[:, None])[groups]


def within_fit(
    y: Any,
    x: Any,
    entities: Any,
    dates: Any,
    *,
    two_way: bool = False,
    allow_redundant: bool = False,
    impulse_index: int | None = None,
) -> dict[str, Any]:
    """FWL within projection; unbalanced two-way effects use alternating projections."""
    _, entities = np.unique(entities, return_inverse=True)
    dates, time = np.unique(dates, return_inverse=True)
    n, k = x.shape
    nentity, ntime = int(entities.max()) + 1, len(dates)
    raw = np.column_stack([y, x])
    z = demean(raw, entities)
    effect_rank = nentity
    if two_way:
        # Connected components determine effect rank in disconnected unbalanced panels.
        parent = list(range(nentity + ntime))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for e, tt in zip(entities, time, strict=True):
            parent[find(int(e))] = find(nentity + int(tt))
        components = len({find(i) for i in range(len(parent))})
        effect_rank = nentity + ntime - components
        for _ in range(10000):
            old = z.copy()
            z = demean(demean(z, time), entities)
            if np.max(np.abs(z - old)) < 1e-13:
                break
        else:
            raise ValueError("Two-way within projection did not converge")
    yy, xx = z[:, 0], z[:, 1:]
    rank = int(np.linalg.matrix_rank(xx))
    if rank < k and not allow_redundant:
        raise ValueError(
            "A regressor is absorbed by fixed effects or collinear; remove it explicitly"
        )
    if impulse_index is not None and rank == np.linalg.matrix_rank(
        np.delete(xx, impulse_index, axis=1)
    ):
        raise ValueError("Panel impulse is absorbed by fixed effects or collinear with controls")
    k = rank
    df = n - k - effect_rank
    if df <= 0:
        raise ValueError("Panel needs positive residual degrees of freedom after fixed effects")
    beta = np.linalg.lstsq(xx, yy, rcond=None)[0]
    residual = yy - xx @ beta
    pinv = np.linalg.pinv(xx, rcond=1e-15)
    bread = pinv @ pinv.T
    scores = xx * residual[:, None]
    covariances = {}
    covariances["conventional"] = bread * float(residual @ residual) / df
    clusters = np.zeros((nentity, x.shape[1]))
    np.add.at(clusters, entities, scores)
    # PanelOLS auto_df=True: one-way country effects are nested in country clusters.
    cluster_df = n - k - (effect_rank if two_way else 0)
    covariances["country-clustered"] = bread @ (clusters.T @ clusters) @ bread * n / cluster_df
    bandwidth = int(np.floor(4 * (ntime / 100) ** (2 / 9)))
    # Preserve calendar distance; absent whole periods contribute zero scores.
    time_scores = np.zeros((int(dates[-1] - dates[0]) + 1, x.shape[1]))
    np.add.at(time_scores, dates[time] - dates[0], scores)
    meat = time_scores.T @ time_scores
    for lag in range(1, min(bandwidth, len(time_scores) - 1) + 1):
        cross = time_scores[lag:].T @ time_scores[:-lag]
        meat += (1 - lag / (bandwidth + 1)) * (cross + cross.T)
    covariances["Driscoll-Kraay"] = bread @ meat @ bread * n / df
    for name, cov in covariances.items():
        covariances[name] = (cov + cov.T) / 2
    wy, wx = demean(raw, entities)[:, 0], demean(raw, entities)[:, 1:]
    rss = float((wy - wx @ beta) @ (wy - wx @ beta))
    tss = float(wy @ wy)
    effects = y - x @ beta - residual
    return {
        "beta": beta,
        "covariances": covariances,
        "residual": residual,
        "effects": effects,
        "effect_rank": effect_rank,
        "df_resid": df,
        "nobs": n,
        "parameters": k,
        "bandwidth": bandwidth,
        "within_r_squared": 1 - rss / tss if tss else None,
        "entities": entities,
        "time": time,
        "dates": dates,
    }


def coefficient_rows(
    names: list[str], beta: Any, cov: Any, covariance: str, df: int, confidence: float = 0.95
) -> list[dict[str, Any]]:
    critical = float(t.ppf((1 + confidence) / 2, df))
    rows = []
    for i, name in enumerate(names):
        se = float(np.sqrt(max(0, cov[i, i])))
        b = float(beta[i])
        rows.append(
            {
                "term": name,
                "estimate": b,
                "std_error": se,
                "lower": b - critical * se,
                "upper": b + critical * se,
                "confidence_level": confidence,
                "covariance": covariance,
            }
        )
    return rows


def fe_design(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    p = parameters(config)
    dependent = roles(config, "dependent")
    if len(dependent) != 1 or not roles(config, "regressor", "exogenous"):
        raise ValueError("Panel FE needs one dependent variable and at least one regressor")
    if any(s["role"] not in {"dependent", "regressor", "exogenous"} for s in config["series"]):
        raise ValueError("Panel FE uses dependent, regressor or exogenous roles")
    data = with_seasonal_controls(data, config)
    calendar = pd.PeriodIndex(data.frame.index, freq=period_frequency(data.frequency))
    grid = pd.period_range(calendar[0], calendar[-1], freq=period_frequency(data.frequency))
    frame = data.frame.set_axis(calendar).reindex(grid)
    x = frame[sorted(roles(config, "regressor", "exogenous"))].copy()
    for lag in range(1, int(p.get("dependent_lags", 0)) + 1):
        x[f"L{lag}.{dependent[0]}"] = frame[dependent[0]].shift(lag)
    if data.exog is not None:
        x = pd.concat([x, data.exog.set_axis(calendar).reindex(grid)], axis=1)
    y = frame[dependent[0]]
    mask = np.isfinite(x).all(axis=1) & np.isfinite(y)
    return {"x": x, "y": y, "mask": mask, "data": data}


def lp_config(config: dict[str, Any]) -> dict[str, Any]:
    from macrolab.models.lp import LPPlugin

    c = deepcopy(config)
    p = {k: v for k, v in parameters(c).items() if k in LPPlugin.params["properties"]}
    p["covariance"] = p.get("country_covariance", "HC1") if p.get("lag_augmented", True) else "HAC"
    p.setdefault("lag_augmented", True)
    c["model"] = {"id": "lp.ols", "params": p}
    c["comparison"] = {"enabled": False}
    return c


def stack_design(designs: dict[str, Any], horizon: int | None, two_way: bool) -> dict[str, Any]:
    parts = []
    samples = {}
    for country, d in designs.items():
        mask = d["mask"] if horizon is None else d["masks"][horizon]
        x = d["x"].loc[mask].drop(columns=["const"], errors="ignore")
        y = d["y"].loc[mask] if horizon is None else d["y"].loc[mask, horizon]
        if len(x) < (3 if horizon is None else 20):
            raise ValueError(f"{country}: insufficient observations on the panel estimation sample")
        periods = [label(p) for p in x.index]
        samples[country] = {
            "periods": periods,
            "nobs": len(x),
            "start": periods[0],
            "end": periods[-1],
            "dropped_periods": [label(p) for p in d["x"].index[~mask]],
        }
        parts.append((country, x, y))
    names = list(dict.fromkeys(str(c) for _, x, _ in parts for c in x))
    # Calendar indicators are nuisance controls; time FE span them exactly.
    omitted = [c for c in names if two_way and c.startswith(("season_", "covid_"))]
    names = [c for c in names if c not in omitted]
    xx = np.concatenate([x.reindex(columns=names, fill_value=0).to_numpy() for _, x, _ in parts])
    zeros = [
        i
        for i in range(len(names))
        if not np.any(xx[:, i]) and names[i].startswith(("season_", "covid_"))
    ]
    omitted.extend(names[i] for i in zeros)
    xx = np.delete(xx, zeros, axis=1)
    names = [c for i, c in enumerate(names) if i not in zeros]
    return {
        "x": xx,
        "y": np.concatenate([y.to_numpy() for _, _, y in parts]),
        "entities": np.concatenate([np.full(len(x), i) for i, (_, x, _) in enumerate(parts)]),
        "dates": np.concatenate([x.index.asi8 for _, x, _ in parts]),
        "names": names,
        "samples": samples,
        "omitted": omitted,
    }


def panel_checks(samples: dict[str, Any], *, lagged: bool, covariance: str) -> list[dict[str, Any]]:
    checks = []
    if covariance == "country-clustered" and len(samples) < 10:
        checks.append(
            check(
                "warn",
                "few_clusters",
                "Fewer than ten country clusters; cluster-robust inference is unreliable.",
                clusters=len(samples),
            )
        )
    tmin = min(s["nobs"] for s in samples.values())
    if lagged and tmin < 40:
        checks.append(
            check(
                "warn",
                "nickell_bias",
                (
                    "A lagged dependent variable with fewer than 40 periods "
                    "per country can cause Nickell bias."
                ),
                T_min=tmin,
            )
        )
    return checks


def fit_panel(
    data: dict[str, AnalysisData],
    config: dict[str, Any],
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    p = parameters(config)
    is_lp = config["model"]["id"] == "panel.lp"
    two_way = p.get("effects", "country") == "two_way"
    cov = p.get("covariance", "Driscoll-Kraay")
    if is_lp and p.get("shock_type", "common") == "common" and two_way:
        raise ValueError(
            "Time effects are disabled with a common shock because they absorb the shock"
        )
    if cov in {"HC1", "HAC"} and (not is_lp or len(data) != 1):
        raise ValueError(
            "Matched HC1/HAC inference is available only for the N=1 LP identity check"
        )
    c = lp_config(config) if is_lp else config
    designs = {country: design(d, c) if is_lp else fe_design(d, c) for country, d in data.items()}
    if is_lp and p.get("country_window", "own") == "common":
        for shared_h in range(int(p.get("horizon", 20)) + 1):
            common = None
            for d in designs.values():
                idx = d["x"].index[d["masks"][shared_h]]
                common = idx if common is None else common.intersection(idx)
            for d in designs.values():
                d["masks"][shared_h] &= d["x"].index.isin(common)
    if is_lp and p.get("shock_type", "common") == "common":
        impulses = pd.concat([d["x"]["impulse"].rename(k) for k, d in designs.items()], axis=1)
        for _, row in impulses.iterrows():
            values = row.dropna().to_numpy()
            if len(values) and np.any(values != values[0]):
                raise ValueError(
                    "Selected common-shock observations differ across "
                    "countries; choose country-specific shock"
                )
    horizons = range(int(p.get("horizon", 20)) + 1) if is_lp else [None]
    rows = []
    checks: list[dict[str, Any]] = []
    fit0 = None
    stacked0 = None
    country_rows: dict[str, list[Any]] = {k: [] for k in data}
    country_conventional: dict[str, list[Any]] = {}
    sensitivity: dict[str, list[Any]] = {name: [] for name in COVARIANCES if name != cov}
    if is_lp:
        sensitivity.pop("conventional", None)
    for h in horizons:
        if cancelled and cancelled():
            raise CancelledError("Panel estimation cancelled")
        stacked = stack_design(designs, h, two_way)
        fitted = within_fit(
            stacked["y"],
            stacked["x"],
            stacked["entities"],
            stacked["dates"],
            two_way=two_way,
            allow_redundant=is_lp,
            impulse_index=stacked["names"].index("impulse") if is_lp else None,
        )
        if fit0 is None:
            fit0, stacked0 = fitted, stacked
        checks.extend(
            {**item, **({"horizon": h} if h is not None else {})}
            for item in panel_checks(
                stacked["samples"], lagged=is_lp or p.get("dependent_lags", 0) > 0, covariance=cov
            )
        )
        size_check = sample_size_check(
            fitted["nobs"], fitted["parameters"] + fitted["effect_rank"], horizon=h
        )
        if size_check:
            checks.append(size_check)
        if is_lp:
            assert h is not None
            size = float(p.get("shock_size", 1))
            j = stacked["names"].index("impulse")
            estimate = float(fitted["beta"][j] * size)
            se = float(
                np.sqrt(
                    max(
                        0,
                        fitted["covariances"].get(cov, fitted["covariances"]["Driscoll-Kraay"])[
                            j, j
                        ],
                    )
                )
                * abs(size)
            )
            # The exact existing per-country LP fit is used on the same masks.
            for country, d in designs.items():
                mask = d["masks"][h]
                x, _ = _active(d["x"].loc[mask])
                a = x.to_numpy()
                y = d["y"].loc[mask, h].to_numpy()
                rank = int(np.linalg.matrix_rank(a))
                if len(a) <= rank or rank == np.linalg.matrix_rank(np.delete(a, 1, axis=1)):
                    raise ValueError(
                        f"{country}: matched country LP lacks residual degrees of freedom "
                        "or an identified impulse"
                    )
                pinv = np.linalg.pinv(a, rcond=1e-15)
                beta = pinv @ y
                score = pinv[1] * (y - a @ beta)
                variance = float(score @ score)
                local_cov = "HC1" if p.get("lag_augmented", True) else "HAC"
                if local_cov == "HC1":
                    variance *= len(a) / (len(a) - int(np.linalg.matrix_rank(a)))
                else:
                    for lag in range(1, int(h) + 2):
                        variance += 2 * (1 - lag / (int(h) + 2)) * float(score[lag:] @ score[:-lag])
                local_b = float(beta[1] * size)
                local_se = float(np.sqrt(max(0, variance)) * abs(size))
                country_rows[country].append(
                    {
                        "horizon": h,
                        "estimate": local_b,
                        "std_error": local_se,
                        "covariance": local_cov,
                        **stacked["samples"][country],
                    }
                )
                if len(data) == 1:
                    estimate = local_b
                    if cov in {"HC1", "HAC"}:
                        if cov != local_cov:
                            raise ValueError(
                                "Match lag augmentation and covariance to lp.ols for N=1 inference"
                            )
                        se = local_se
            rows.append(
                {
                    "horizon": h,
                    "estimate": estimate,
                    "std_error": se,
                    "bands": {
                        str(level): {
                            "lower": estimate - float(norm.ppf((1 + level) / 2)) * se,
                            "upper": estimate + float(norm.ppf((1 + level) / 2)) * se,
                        }
                        for level in (0.68, 0.90)
                    },
                    "samples": stacked["samples"],
                    "nobs": fitted["nobs"],
                    "dk_bandwidth": fitted["bandwidth"],
                }
            )
            for method in sensitivity:
                alt_se = float(np.sqrt(max(0, fitted["covariances"][method][j, j])) * abs(size))
                sensitivity[method].append(
                    {"horizon": h, "estimate": estimate, "std_error": alt_se}
                )
        else:
            confidence = float(config.get("outputs", {}).get("confidence", 0.95))
            rows = coefficient_rows(
                stacked["names"],
                fitted["beta"],
                fitted["covariances"][cov],
                cov,
                fitted["df_resid"],
                confidence,
            )
            for method in sensitivity:
                sensitivity[method] = coefficient_rows(
                    stacked["names"],
                    fitted["beta"],
                    fitted["covariances"][method],
                    method,
                    fitted["df_resid"],
                    confidence,
                )
            for country, d in designs.items():
                mask = d["mask"]
                x, _ = _active(d["x"].loc[mask])
                a = np.column_stack([np.ones(len(x)), x.to_numpy()])
                y = d["y"].loc[mask].to_numpy()
                pinv = np.linalg.pinv(a, rcond=1e-15)
                beta = pinv @ y
                residual = y - a @ beta
                df = len(a) - int(np.linalg.matrix_rank(a))
                if df <= 0:
                    raise ValueError(f"{country}: country OLS has no residual degrees of freedom")
                country_conventional[country] = coefficient_rows(
                    ["const", *map(str, x.columns)],
                    beta,
                    (pinv @ pinv.T) * float(residual @ residual) / df,
                    "conventional",
                    df,
                    confidence,
                )
                # Match v0 OLS HAC(4): Bartlett weights, no finite-sample
                # multiplier, residual-df t intervals. Preserve calendar gaps.
                dates = pd.PeriodIndex(x.index, freq=period_frequency(data[country].frequency))
                ordinals = dates.astype("int64").to_numpy()
                ordinal = ordinals - ordinals[0]
                scores = np.zeros((int(ordinal[-1]) + 1, a.shape[1]))
                scores[ordinal] = (pinv * residual).T
                hac = scores.T @ scores
                for lag in range(1, min(4, len(scores) - 1) + 1):
                    cross = scores[lag:].T @ scores[:-lag]
                    hac += (1 - lag / 5) * (cross + cross.T)
                country_rows[country] = coefficient_rows(
                    ["const", *map(str, x.columns)], beta, hac, "HAC(4)", df, confidence
                )
        if progress:
            progress(
                {
                    "phase": "panel_horizon",
                    "completed": int(h) + 1 if h is not None else 1,
                    "total": len(horizons),
                }
            )
    assert fit0 is not None and stacked0 is not None
    counts = [s["nobs"] for s in stacked0["samples"].values()]
    panel = {
        "N": len(data),
        "seasonal_controls": {
            country: d["data"].sample.get("seasonal_controls", {}) for country, d in designs.items()
        },
        "T_min": min(counts),
        "T_max": max(counts),
        "total_observations": sum(counts),
        "effects": "two_way" if two_way else "country",
        "effect_rank": fit0["effect_rank"],
        "df_resid": fit0["df_resid"],
        "covariance": cov,
        "dk_bandwidth": fit0["bandwidth"],
        "within_r_squared": fit0["within_r_squared"],
        "coefficient_terms": stacked0["names"],
        "covariance_matrix": fit0["covariances"]
        .get(cov, fit0["covariances"]["Driscoll-Kraay"])
        .tolist(),
        "country_samples": stacked0["samples"],
        "country_estimates": country_rows,
        "omitted_indicators": stacked0["omitted"],
        "fixed_effect_summary": [
            {
                "country": country,
                "mean_effect": float(np.mean(fit0["effects"][stacked0["entities"] == i])),
            }
            for i, country in enumerate(data)
        ],
    }
    if not is_lp:
        panel["country_estimates_conventional"] = country_conventional
    variants = [
        {
            "variant_id": method,
            "label": method,
            "status": "ok",
            "same_estimand": True,
            "rows": values,
            "checks": panel_checks(
                stacked0["samples"],
                lagged=is_lp or p.get("dependent_lags", 0) > 0,
                covariance=method,
            ),
        }
        for method, values in sensitivity.items()
    ]
    result: dict[str, Any] = {
        "label": "Conditional pooled association; fixed effects do not establish causality",
        "panel": panel,
        "checks": checks,
        "sensitivity": {
            "status": "ok",
            "enabled": True,
            "variants": variants,
            "summary": [],
            "note": (
                "Covariance alternatives keep point estimates unchanged; "
                "country slopes need not equal the pooled slope."
            ),
        },
        "diagnostics": {
            "nobs": sum(counts),
            "covariance": cov,
            "confidence": config.get("outputs", {}).get("confidence", 0.95),
        },
        "notes": [
            (
                "Driscoll–Kraay uses calendar-lagged aggregate scores and "
                "Bartlett weights; inference is asymptotic."
            ),
            (
                "Country OLS/LP curves use the same country-specific "
                "estimation dates as the pooled fit."
            ),
        ],
    }
    if is_lp:
        response = roles(config, "response", "dependent")[0]
        result["local_projection"] = {
            "horizons": rows,
            "response_mode": p.get("response_mode", "change"),
            "growth_scale": p.get("growth_scale", 1),
            "response_definition": {
                "cumulative_log": "cumulative % change in the level",
                "change": "change from the pre-impulse level",
                "level": "level",
                "growth_log": "log growth rate (%)",
            }[p.get("response_mode", "change")],
            "covariance": cov,
            "sample_mode": p.get("sample_mode", "common"),
        }
        result["irf"] = {
            "periods": [r["horizon"] for r in rows],
            "variables": [response],
            "values": [[r["estimate"]] for r in rows],
            "lower": [[r["bands"]["0.68"]["lower"]] for r in rows],
            "upper": [[r["bands"]["0.68"]["upper"]] for r in rows],
            "shock": roles(config, "shock")[0],
            "shock_size": p.get("shock_size", 1),
            "band_level": 0.68,
            "band_method": cov,
            "band_interpretation": "pointwise, not simultaneous",
        }
    else:
        result["coefficients_table"] = rows
    return result


class PanelFEPlugin(BasePlugin):
    id, family, title = "panel.fe", "panel", "Panel fixed effects"
    summary = "Pooled within-country associations beside country OLS, with robust panel inference."
    label = "Conditional pooled association"
    inputs = {
        "min_series": 2,
        "max_series": 20,
        "required_roles": {"dependent": 1},
        "frequencies": ["M", "Q", "A"],
        "cross_country": True,
    }
    params = schema(
        template_id={"type": "string", "enum": ["ea_phillips_pooled"]},
        effects=choice("country", "country", "two_way"),
        covariance=choice("Driscoll-Kraay", *COVARIANCES),
        dependent_lags=integer(0, 0, 12),
        seasonal={"type": "boolean", "default": False},
    )
    assumptions = [
        "Regressors must be exogenous conditional on fixed effects.",
        (
            "Driscoll–Kraay needs a sufficiently long time dimension; "
            "clustered inference needs enough countries."
        ),
    ]
    references = [
        {
            "title": "linearmodels PanelOLS 7.0 (native validation reference)",
            "url": "https://pypi.org/project/linearmodels/7.0/",
        }
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            fe_design(data, config)
        except (ValueError, KeyError, IndexError) as exc:
            return [check("block", "panel_inputs", str(exc))]
        return []


class PanelLPPlugin(PanelFEPlugin):
    id, title = "panel.lp", "Panel local projections"
    summary = "Pool lag-augmented responses to a common or country-specific impulse."
    inputs = {
        "min_series": 2,
        "max_series": 20,
        "required_roles": {"shock": 1},
        "frequencies": ["M", "Q", "A"],
        "cross_country": True,
    }
    params = schema(
        template_id={"type": "string", "enum": ["same_ecb_shock_pooled"]},
        effects=choice("country", "country", "two_way"),
        covariance=choice("Driscoll-Kraay", *COVARIANCES, "HC1", "HAC"),
        shock_type=choice("common", "common", "country_specific"),
        first_stage={"type": "object"},
        first_stage_source=choice("selected", "selected", "ecb_dfr"),
        lags=integer(2, 0, 24),
        horizon=integer(20, 0, 60),
        lag_augmented={"type": "boolean", "default": True},
        response_mode=choice("change", "change", "level", "cumulative_log", "growth_log"),
        sample_mode=choice("common", "common", "horizon_specific"),
        country_window=choice("own", "own", "common"),
        shock_size={"type": "number", "default": 1},
        growth_scale={"type": "number", "default": 1},
        lag_difference_scales={"type": "object", "default": {}},
        seasonal={"type": "boolean", "default": False},
    )

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        p = parameters(config)
        if p.get("shock_type", "common") == "common" and p.get("effects") == "two_way":
            return [
                check(
                    "block",
                    "common_shock_time_effects",
                    "Time effects are disabled with a common shock because they absorb the shock.",
                )
            ]
        try:
            design(data, lp_config(config))
        except (ValueError, KeyError, IndexError) as exc:
            return [check("block", "panel_inputs", str(exc))]
        return []
