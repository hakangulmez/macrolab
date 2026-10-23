"""Joint residual bootstrap of a block-triangular first/national-stage system."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import period_frequency
from macrolab.ident.external_series import attach, recover
from macrolab.models.base import AnalysisData, roles
from macrolab.models.lp import fit
from macrolab.models.var import _stable, moving_average


class CancelledError(ValueError):
    """A cooperative cancellation never returns a partial estimate as complete."""


def joint_bootstrap(
    first: AnalysisData,
    first_config: dict[str, Any],
    countries: dict[str, AnalysisData],
    configs: dict[str, dict[str, Any]],
    *,
    draws: int = 200,
    seed: int = 20261023,
    progress: Callable[[dict[str, Any]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not 20 <= draws <= 5000 or not countries or set(countries) != set(configs):
        raise ValueError("Joint bootstrap needs country configurations and 20–5000 draws")
    if first_config["model"]["params"].get("exclude_window"):
        raise ValueError("Joint bootstrap requires one continuous first-stage window")
    shock, fitted = recover(first, first_config)
    if not shock["stable"]:
        raise ValueError(
            "Joint simulation requires a stable first-stage VAR; residual shocks remain usable"
        )
    configs = deepcopy(configs)
    for config in configs.values():
        config["model"]["params"]["shock_size"] = shock["requested_structural_size"]
    dates = pd.PeriodIndex(first.frame.index, freq=period_frequency(first.frequency))
    source_dates = dates[fitted.k_ar :]
    national_dates = {
        key: pd.PeriodIndex(d.frame.index, freq=period_frequency(d.frequency))
        for key, d in countries.items()
    }
    common_dates = next(iter(national_dates.values()))
    if any(not idx.equals(common_dates) for idx in national_dates.values()):
        raise ValueError(
            "Joint bootstrap requires an explicit common-window alternative; "
            "country baseline samples differ"
        )
    if not common_dates.isin(source_dates).all():
        raise ValueError("First-stage shock must cover every joint-bootstrap country input date")
    q = max(max(1, int(c["model"]["params"].get("lags", 2))) for c in configs.values())
    if len(common_dates) - q < 20:
        raise ValueError("Joint bootstrap auxiliary system needs at least 20 residual observations")
    first_names = list(fitted.names)
    first_values = first.frame[first_names].to_numpy()
    ar = np.asarray(fitted.coefs)
    p = fitted.k_ar
    deterministic = (
        np.asarray(fitted.endog_lagged[:, : fitted.k_exog])
        @ np.asarray(fitted.params)[: fitted.k_exog]
    )
    impact = np.linalg.cholesky(np.asarray(fitted.sigma_u))
    first_residual = np.asarray(fitted.resid)
    first_residual = (first_residual - first_residual.mean(axis=0)) * np.sqrt(
        fitted.nobs / fitted.df_resid
    )
    country_positions = dates.get_indexer(common_dates)
    joint_dates = common_dates[q:]
    rows_first = source_dates.get_indexer(joint_dates)
    innovation_parts = [first_residual[rows_first]]
    systems: dict[str, Any] = {}
    start = len(first_names)
    for key, original in countries.items():
        config = configs[key]
        data = with_seasonal_controls(original, config)
        shared = config["model"]["params"].get("shared_controls", {})
        names = sorted(
            set(roles(config, "response", "dependent", "endogenous", "regressor")) - set(shared)
        )
        if not names:
            raise ValueError("The national bootstrap system needs at least one national variable")
        values = data.frame[names].to_numpy()
        exogenous = roles(config, "exogenous")
        fixed = pd.DataFrame({"const": np.ones(len(data.frame))}, index=data.frame.index)
        if exogenous:
            fixed = pd.concat([fixed, data.frame[exogenous]], axis=1)
        if data.exog is not None:
            fixed = pd.concat([fixed, data.exog], axis=1)
        active = [name for name in fixed if name == "const" or np.any(fixed[name].iloc[q:])]
        fixed_values = fixed[active].to_numpy()
        structural = np.asarray(shock["all_values"])[source_dates.get_indexer(common_dates)]
        pieces = [fixed_values[q:], structural[q:]]
        for lag in range(1, q + 1):
            pieces.append(values[q - lag : len(values) - lag])
            for national_name, first_name in sorted(shared.items()):
                first_j = first_names.index(first_name)
                pieces.append(
                    first_values[dates.get_indexer(common_dates[q:] - lag), first_j, None]
                )
                expected = first_values[dates.get_indexer(common_dates), first_j]
                if not np.allclose(data.frame[national_name], expected, atol=1e-12, rtol=0):
                    raise ValueError("Shared stage-1 control values do not agree exactly")
        x = np.column_stack(pieces)
        if np.linalg.matrix_rank(x) < x.shape[1] or len(x) <= x.shape[1]:
            raise ValueError(
                "Joint bootstrap auxiliary design is rank deficient or has no residual df"
            )
        b = np.linalg.lstsq(x, values[q:], rcond=1e-15)[0]
        residual = values[q:] - x @ b
        residual = (residual - residual.mean(axis=0)) * np.sqrt(len(x) / (len(x) - x.shape[1]))
        innovation_parts.append(residual)
        systems[key] = {
            "names": names,
            "values": values,
            "fixed": fixed_values,
            "shared": shared,
            "coefficients": b,
            "slice": slice(start, start + len(names)),
        }
        start += len(names)
    pool = np.column_stack(innovation_parts)
    base = {
        key: fit(attach(countries[key], shock), configs[key], point_only=True)["estimates"]
        for key in countries
    }
    generator = np.random.default_rng(seed)
    collected: dict[str, list[Any]] = {key: [] for key in countries}
    failures: list[str] = []
    max_attempts = draws + max(10, draws // 10)
    accepted = 0
    for attempt in range(max_attempts):
        if accepted == draws:
            break
        if cancelled and cancelled():
            raise CancelledError("Joint bootstrap cancelled; no complete band returned")
        joint = pool[generator.integers(0, len(pool), len(pool))]
        innovations = first_residual[
            generator.integers(0, len(first_residual), len(first_residual))
        ].copy()
        innovations[rows_first] = joint[:, : len(first_names)]
        first_sim = first_values.copy()
        for t in range(p, len(first_sim)):
            first_sim[t] = deterministic[t - p] + innovations[t - p]
            for lag in range(1, p + 1):
                first_sim[t] += ar[lag - 1] @ first_sim[t - lag]
        simulated_first = deepcopy(first)
        simulated_first.frame[first_names] = first_sim
        try:
            recovered, refitted = recover(simulated_first, first_config)
            if not _stable(np.asarray(refitted.coefs))[0]:
                raise ValueError("Unstable first-stage draw")
            # These are the bootstrap DGP's innovations, not the re-estimated shock.
            true_structural = np.linalg.solve(impact, innovations.T).T
            estimates = {}
            for key, system in systems.items():
                sim = system["values"].copy()
                for t in range(q, len(sim)):
                    absolute = int(country_positions[t])
                    pieces = [system["fixed"][t], true_structural[absolute - p]]
                    for lag in range(1, q + 1):
                        pieces.append(sim[t - lag])
                        for _, first_name in sorted(system["shared"].items()):
                            pieces.append(
                                np.array([first_sim[absolute - lag, first_names.index(first_name)]])
                            )
                    sim[t] = (
                        np.concatenate(pieces) @ system["coefficients"]
                        + joint[t - q, system["slice"]]
                    )
                country = deepcopy(countries[key])
                country.frame[system["names"]] = sim
                for national_name, first_name in system["shared"].items():
                    country.frame[national_name] = first_sim[
                        dates.get_indexer(common_dates), first_names.index(first_name)
                    ]
                draw_config = deepcopy(configs[key])
                draw_config["model"]["params"]["shock_size"] = recovered[
                    "requested_structural_size"
                ]
                estimates[key] = fit(attach(country, recovered), draw_config, point_only=True)[
                    "estimates"
                ]
            for key, values in estimates.items():
                collected[key].append(values)
            accepted += 1
        except (ValueError, np.linalg.LinAlgError) as exc:
            failures.append(str(exc))
        if progress:
            progress(
                {
                    "phase": "joint_bootstrap",
                    "completed": accepted,
                    "total": draws,
                    "attempts": attempt + 1,
                    "failed_draws": len(failures),
                }
            )
    if accepted < draws:
        raise ValueError(
            f"Joint bootstrap obtained {accepted}/{draws} valid draws; failures: {failures[:3]}"
        )
    # Center bootstrap estimation errors on the auxiliary DGP's known response,
    # not on the sample LP estimate (the two methods need not agree in-sample).
    auxiliary_response: dict[str, Any] = {}
    chosen_shock = first_names.index(shock["shock"])
    for key, system in systems.items():
        opts = configs[key]["model"]["params"]
        horizon = opts.get("horizon", 12)
        size = opts.get("shock_size", 1.0)
        first_irf = moving_average(ar, horizon) @ (impact[:, chosen_shock] * size)
        national_irf = np.zeros((horizon + 1, len(system["names"])))
        for h in range(horizon + 1):
            structural_impulse = np.zeros(len(first_names))
            if h == 0:
                structural_impulse[chosen_shock] = size
            pieces = [np.zeros(system["fixed"].shape[1]), structural_impulse]
            for lag in range(1, q + 1):
                pieces.append(national_irf[h - lag] if h >= lag else np.zeros(len(system["names"])))
                for _, first_name in sorted(system["shared"].items()):
                    pieces.append(
                        np.array(
                            [first_irf[h - lag, first_names.index(first_name)] if h >= lag else 0.0]
                        )
                    )
            national_irf[h] = np.concatenate(pieces) @ system["coefficients"]
        response_name = roles(configs[key], "response", "dependent")[0]
        implied = national_irf[:, system["names"].index(response_name)]
        mode = opts.get("response_mode", "level")
        if mode == "cumulative_log":
            implied = 100 * implied
        elif mode == "growth_log":
            implied = 100 * opts.get("growth_scale", 1) * np.diff(np.r_[0.0, implied])
        auxiliary_response[key] = implied.tolist()
    bands: dict[str, Any] = {}
    for key, simulations in collected.items():
        point = np.asarray(base[key])
        bands[key] = {}
        for level in (0.68, 0.90):
            tail = (1 - level) / 2
            low, high = np.quantile(
                np.asarray(simulations) - np.asarray(auxiliary_response[key]),
                [tail, 1 - tail],
                axis=0,
            )
            bands[key][str(level)] = {
                "lower": (point - high).tolist(),
                "upper": (point - low).tolist(),
            }
    return {
        "method": (
            "joint residual bootstrap; pointwise intervals centered on "
            "auxiliary-DGP estimation errors"
        ),
        "draws": draws,
        "seed": seed,
        "failed_draws": len(failures),
        "failure_reasons": failures,
        "attempts": accepted + len(failures),
        "bands": bands,
        "sample": {
            "start": str(common_dates[0]),
            "end": str(common_dates[-1]),
            "nobs": len(common_dates),
        },
        "auxiliary_lags": q,
        "resampling": "paired contemporaneous innovations of the triangular system",
        "assumptions": (
            "serially exchangeable innovations; fixed exogenous controls; "
            "correctly specified auxiliary dynamics"
        ),
        "point_estimates": base,
        "auxiliary_population_responses": auxiliary_response,
        "default_enabled": False,
    }
