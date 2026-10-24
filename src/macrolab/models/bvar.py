"""Conjugate Minnesota BVAR, explicit dummy observations and seeded NIW draws.

No extra runtime dependency. See docs/models/bvar_minn.md for parameterization.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import multigammaln  # type: ignore[import-untyped]
from scipy.stats import t  # type: ignore[import-untyped]

from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.analysis.transforms import period_frequency
from macrolab.ident.bootstrap import CancelledError
from macrolab.models.base import AnalysisData, BasePlugin, check, parameters, sample_size_check
from macrolab.models.linear import choice, integer, schema
from macrolab.models.var import (
    _estimate,
    _inputs,
    _normalized_response,
    _omit_inactive_covid,
    _settings,
    _stable,
)

GRID = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0]
DIFFUSE_VARIANCE = 1e8


def design(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    """Same contiguous estimation rows, ordering and deterministic design as OLS VAR."""
    p = parameters(config)
    if any(
        s["role"] not in {"shock", "response", "endogenous", "exogenous"} for s in config["series"]
    ):
        raise ValueError("BVAR uses shock, response, endogenous or exogenous roles")
    execution = deepcopy(config)
    execution["outputs"]["irf"]["method"] = "asymptotic"
    s = _settings(execution, recursive=True)
    s.update(lags=int(p.get("lags", 4)), criterion=None, trend="c")
    if not 1 <= s["lags"] <= 12:
        raise ValueError("BVAR needs 1–12 fixed lags")
    data = with_seasonal_controls(deepcopy(data), config)
    frame, exog = _inputs(data, config, s)
    calendar = pd.PeriodIndex(frame.index, freq=period_frequency(data.frequency))
    if not calendar.equals(pd.period_range(calendar[0], calendar[-1], freq=calendar.freq)):
        raise ValueError("BVAR requires a contiguous observed sample; gaps are not compressed")
    exog, omitted = _omit_inactive_covid(data, exog, s["lags"])
    ar, n = s["lags"], len(s["names"])
    if len(frame) - ar <= ar + 1:
        raise ValueError("Too few observations for positive AR(p) residual degrees of freedom")
    xx = pd.DataFrame({"const": 1.0}, index=frame.index)
    if exog is not None:
        xx = pd.concat([xx, exog], axis=1)
    deterministic = xx.shape[1]
    for lag in range(1, ar + 1):
        for name in s["names"]:
            xx[f"L{lag}.{name}"] = frame[name].shift(lag)
    x, y = xx.iloc[ar:].to_numpy(), frame.iloc[ar:].to_numpy()
    sigmas = []
    for j in range(n):
        a = np.column_stack(
            [
                np.ones(len(y)),
                *[frame.iloc[ar - len_ : len(frame) - len_, j] for len_ in range(1, ar + 1)],
            ]
        )
        rank = int(np.linalg.matrix_rank(a))
        resid = y[:, j] - a @ np.linalg.lstsq(a, y[:, j], rcond=None)[0]
        sigma = float(np.sqrt(resid @ resid / (len(y) - rank)))
        if not np.isfinite(sigma) or sigma <= np.finfo(float).eps * max(1, np.max(np.abs(y[:, j]))):
            raise ValueError(f"{s['names'][j]} has no positive AR(p) residual scale")
        sigmas.append(sigma)
    transforms = {v["concept_id"]: v["transform"] for v in config["series"]}
    means = np.array(
        [1.0 if transforms[v] in {"level", "log", "index_to_base"} else 0.0 for v in s["names"]]
    )
    return dict(
        x=x,
        y=y,
        sigmas=np.array(sigmas),
        own_means=means,
        n=n,
        p=ar,
        deterministic=deterministic,
        terms=list(xx),
        settings=s,
        data=data,
        initial_mean=frame.iloc[:ar].mean().to_numpy(),
        omitted=omitted,
    )


def dummy_prior(d: dict[str, Any], tightness: float, params: dict[str, Any]) -> dict[str, Any]:
    n, k, q, ar = d["n"], d["x"].shape[1], d["deterministic"], d["p"]
    if not np.isfinite(tightness) or tightness <= 0:
        raise ValueError("Minnesota tightness must be finite and positive")
    decay = float(params.get("lag_decay", 2))
    precision = np.r_[
        np.full(q, 1 / DIFFUSE_VARIANCE),
        np.concatenate([d["sigmas"] ** 2 * lag**decay / tightness**2 for lag in range(1, ar + 1)]),
    ]
    mean = np.zeros((k, n))
    mean[q : q + n] = np.diag(d["own_means"])
    xd = np.vstack([np.diag(np.sqrt(precision)), np.zeros((n + 2, k))])
    yd = np.vstack([np.diag(np.sqrt(precision)) @ mean, np.diag(d["sigmas"]), np.zeros((2, n))])
    # m* - k = n+2: proper IW prior with E[Sigma] = diag(sigma_i^2).
    blocks = {"Minnesota and diffuse deterministic": k, "covariance": n + 2}
    initial = d["initial_mean"]
    if params.get("sum_of_coefficients", False):
        target = np.diag(initial) / float(params.get("sum_tightness", 1))
        xd = np.vstack([xd, np.column_stack([np.zeros((n, q)), *[target] * ar])])
        yd = np.vstack([yd, target])
        blocks["sum_of_coefficients"] = n
    if params.get("co_persistence", False):
        strength = float(params.get("co_persistence_tightness", 1))
        row = np.r_[1.0, np.zeros(q - 1), np.tile(initial, ar)][None, :] / strength
        xd = np.vstack([xd, row])
        yd = np.vstack([yd, initial[None, :] / strength])
        blocks["co_persistence"] = 1
    prior_mean = np.linalg.lstsq(xd, yd, rcond=None)[0]
    residual = yd - xd @ prior_mean
    return dict(
        x=xd,
        y=yd,
        mean=prior_mean,
        precision=xd.T @ xd,
        scale=residual.T @ residual,
        df=len(xd) - k,
        blocks=blocks,
    )


def posterior(d: dict[str, Any], tightness: float, params: dict[str, Any]) -> dict[str, Any]:
    prior = dummy_prior(d, tightness, params)
    x, y = d["x"], d["y"]
    augmented_x = np.vstack([prior["x"], x])
    augmented_y = np.vstack([prior["y"], y])
    mean = np.linalg.lstsq(augmented_x, augmented_y, rcond=None)[0]
    precision = augmented_x.T @ augmented_x
    variance = np.linalg.solve(precision, np.eye(precision.shape[0]))
    variance = (variance + variance.T) / 2
    errors = augmented_y - augmented_x @ mean
    scale = errors.T @ errors
    df = prior["df"] + len(y)
    for matrix in (variance, scale, prior["scale"]):
        np.linalg.cholesky(matrix)
    n, count = d["n"], len(y)

    def logdet(a: Any) -> float:
        return float(np.linalg.slogdet(a)[1])

    ml = (
        -count * n / 2 * np.log(np.pi)
        + n / 2 * (logdet(prior["precision"]) - logdet(precision))
        + prior["df"] / 2 * logdet(prior["scale"])
        - df / 2 * logdet(scale)
        + multigammaln(df / 2, n)
        - multigammaln(prior["df"] / 2, n)
    )
    return dict(
        mean=mean,
        variance=variance,
        scale=scale,
        df=df,
        covariance_mean=scale / (df - n - 1),
        prior=prior,
        log_marginal_likelihood=float(ml),
    )


def select_prior(
    d: dict[str, Any], params: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    grid = (
        params.get("lambda_grid", GRID)
        if params.get("lambda_selection") == "grid"
        else [float(params.get("lambda", 0.2))]
    )
    if (
        not isinstance(grid, list)
        or not 1 <= len(grid) <= 30
        or any(
            type(v) not in (int, float) or not np.isfinite(v) or not 0.001 <= v <= 1e8 for v in grid
        )
    ):
        raise ValueError("Lambda grid needs 1–30 finite positive values between .001 and 1e8")
    if len(set(grid)) != len(grid):
        raise ValueError("Lambda grid entries must be unique")
    fits = [posterior(d, float(value), params) for value in grid]
    best = int(np.argmax([p["log_marginal_likelihood"] for p in fits]))
    rows = [
        {
            "lambda": float(value),
            "log_marginal_likelihood": p["log_marginal_likelihood"],
            "selected": i == best,
        }
        for i, (value, p) in enumerate(zip(grid, fits, strict=True))
    ]
    return fits[best], rows, float(grid[best])


def draw_parameters(posterior_: dict[str, Any], draws: int, seed: int) -> tuple[Any, Any]:
    """Bartlett IW + matrix-normal, PCG64 with a fixed documented draw order."""
    rng = np.random.default_rng(seed)
    n = len(posterior_["scale"])
    bartlett = np.zeros((draws, n, n))
    for i in range(n):
        bartlett[:, i, i] = np.sqrt(rng.chisquare(posterior_["df"] - i, draws))
        for j in range(i):
            bartlett[:, i, j] = rng.standard_normal(draws)
    factor = np.linalg.cholesky(posterior_["scale"]) @ np.linalg.inv(bartlett.transpose(0, 2, 1))
    covariance = factor @ factor.transpose(0, 2, 1)
    z = rng.standard_normal((draws, *posterior_["mean"].shape))
    beta = posterior_["mean"] + np.linalg.cholesky(posterior_["variance"]) @ z @ factor.transpose(
        0, 2, 1
    )
    return beta, covariance


def posterior_responses(
    d: dict[str, Any],
    post: dict[str, Any],
    config: dict[str, Any],
    *,
    progress: Callable[..., Any] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    p = parameters(config)
    count, seed = int(p.get("draws", 1000)), int(config["seed"])
    beta, covariances = draw_parameters(post, count, seed)
    n, ar, q = d["n"], d["p"], d["deterministic"]
    horizon, names = d["settings"]["horizon"], d["settings"]["names"]
    shock = names.index(d["settings"]["shock"])
    requested = config["outputs"]["irf"]
    size = (
        float(np.linalg.cholesky(post["covariance_mean"])[shock, shock])
        if requested.get("shock_mode") == "one_sd"
        else float(requested.get("shock_size", 1))
    )
    coefs = beta[:, q:].reshape(count, ar, n, n).transpose(0, 1, 3, 2)
    radii, all_responses, all_fevd = [], [], []
    for start in range(0, count, 100):
        if cancelled and cancelled():
            raise CancelledError("BVAR posterior cancelled")
        a, sigma = coefs[start : start + 100], covariances[start : start + 100]
        batch = len(a)
        companion = np.zeros((batch, n * ar, n * ar))
        companion[:, :n] = a.transpose(0, 2, 1, 3).reshape(batch, n, n * ar)
        companion[:, n:, :-n] = np.eye(n * (ar - 1))
        radii.extend(np.max(np.abs(np.linalg.eigvals(companion)), axis=1))
        ma = np.zeros((batch, horizon + 1, n, n))
        ma[:, 0] = np.eye(n)
        for h in range(1, horizon + 1):
            for lag in range(1, min(ar, h) + 1):
                ma[:, h] += ma[:, h - lag] @ a[:, lag - 1]
        impact = np.linalg.cholesky(sigma)
        orthogonal = ma @ impact[:, None]
        response = orthogonal[:, :, :, shock] * (size / impact[:, shock, shock])[:, None, None]
        variance = np.cumsum(orthogonal[:, :-1] ** 2, axis=1)
        all_responses.append(response)
        all_fevd.append(variance / variance.sum(axis=3, keepdims=True))
        if progress:
            progress(dict(phase="bvar_draws", completed=min(start + 100, count), total=count))
    roots = np.asarray(radii)
    unstable = roots >= 1
    keep = ~unstable if p.get("drop_explosive", False) else np.ones(count, dtype=bool)
    if keep.sum() < 20:
        raise ValueError(
            f"Only {keep.sum()} of {count} draws remain; posterior bands need at least 20. "
            "Disable explosive-draw filtering or revise the model explicitly."
        )
    responses, fevds = np.concatenate(all_responses)[keep], np.concatenate(all_fevd)[keep]
    if not np.isfinite(responses).all() or not np.isfinite(fevds).all():
        raise ValueError(
            "Non-finite posterior dynamics; no numerical failures were silently discarded"
        )
    bands = {}
    for level in (0.68, 0.90):
        lo, hi = np.quantile(responses, [(1 - level) / 2, (1 + level) / 2], axis=0)
        bands[str(level)] = dict(lower=lo.tolist(), upper=hi.tolist())
    return dict(
        values=np.median(responses, axis=0).tolist(),
        bands=bands,
        fevd=np.mean(fevds, axis=0).tolist(),
        size=size,
        draws=dict(
            requested=count,
            retained=int(keep.sum()),
            dropped=int((~keep).sum()),
            explosive=int(unstable.sum()),
            explosive_share=float(unstable.mean()),
            largest_roots=roots.tolist(),
            seed=seed,
            distribution="NIW posterior; PCG64 Bartlett inverse-Wishart then matrix-normal",
            filtering="largest root < 1" if p.get("drop_explosive", False) else "none",
        ),
    )


def matched_ols(d: dict[str, Any], config: dict[str, Any], size: float) -> dict[str, Any]:
    """OLS uses the identical actual rows, controls, order and physical impulse."""
    c = deepcopy(config)
    c["model"] = dict(id="var.ols", params=dict(lags=d["p"], trend="c"))
    c["outputs"]["irf"].update(method="asymptotic", shock_size=size, shock_mode="fixed")
    try:
        fit = _estimate(d["data"], c, _settings(c))
        if not np.array_equal(fit.endog_lagged, d["x"]):
            raise ValueError("OLS and BVAR designs differ; matched comparison refused")
        stable, radius = _stable(fit.coefs)
        if not stable:
            return dict(
                status="blocked",
                reason="Matched OLS VAR is unstable; its IRF/FEVD are blocked",
                largest_root=radius,
            )
        s = d["settings"]
        values = _normalized_response(
            fit.coefs, np.asarray(fit.sigma_u), s["horizon"], s["names"].index(s["shock"]), size
        )
        return dict(
            status="ok",
            values=values.tolist(),
            largest_root=radius,
            coefficient_mean=fit.params.to_numpy().tolist(),
            periods=list(map(str, d["data"].frame.index[d["p"] :])),
            identification_order=s["names"],
            shock_size=size,
            note=(
                "OLS VAR point estimate; same sample, controls, ordering and physical "
                "shock. Different priors, not an independent identification check."
            ),
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        return dict(status="blocked", reason=str(exc))


def fit_bvar(
    data: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Callable[..., Any] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    d = design(data, config)
    params = parameters(config)
    post, grid, selected = select_prior(d, params)
    sample = list(map(str, d["data"].frame.index[d["p"] :]))
    paths = posterior_responses(d, post, config, progress=progress, cancelled=cancelled)
    names, n, q = d["settings"]["names"], d["n"], d["deterministic"]
    band_level = float(config["outputs"]["irf"].get("bands", 0.68))
    if band_level not in (0.68, 0.9):
        raise ValueError("BVAR supports 68% and 90% posterior bands")
    rows = []
    df = post["df"] - n + 1
    for k, term in enumerate(d["terms"]):
        for j, name in enumerate(names):
            sd = float(np.sqrt(post["variance"][k, k] * post["covariance_mean"][j, j]))
            half = float(
                t.ppf(0.975, df) * np.sqrt(post["variance"][k, k] * post["scale"][j, j] / df)
            )
            b = float(post["mean"][k, j])
            rows.append(
                dict(
                    term=term,
                    equation=name,
                    estimate=b,
                    std_error=sd,
                    lower=b - half,
                    upper=b + half,
                    confidence_level=0.95,
                    covariance="posterior NIW (credible interval)",
                )
            )
    central_coefs = post["mean"][q:].reshape(d["p"], n, n).transpose(0, 2, 1)
    stable, radius = _stable(central_coefs)
    residual = d["y"] - d["x"] @ post["mean"]
    impact = np.linalg.cholesky(post["covariance_mean"])
    j = names.index(d["settings"]["shock"])
    physical = np.linalg.solve(impact, residual.T).T[:, j] * impact[j, j]
    ols = matched_ols(d, config, paths["size"])
    checks = []
    if paths["draws"]["explosive_share"] > 0.1:
        checks.append(
            check(
                "warn",
                "bvar_explosive_draws",
                (
                    "More than 10% of posterior draws have a largest root of at least one; "
                    "long-horizon responses may be explosive."
                ),
                **{
                    k: v
                    for k, v in paths["draws"].items()
                    if k not in {"largest_roots", "distribution"}
                },
            )
        )
    if paths["draws"]["dropped"]:
        checks.append(
            check(
                "info",
                "bvar_draw_filter",
                "Explosive draws were explicitly excluded; displayed bands condition on stability.",
                dropped=paths["draws"]["dropped"],
                retained=paths["draws"]["retained"],
            )
        )
    if params.get("sum_of_coefficients") or params.get("co_persistence"):
        checks.append(
            check(
                "info",
                "bvar_unit_root_priors",
                (
                    "Optional sum/co-persistence dummies favor no-change behavior even for "
                    "transformed growth series. These are substantive prior restrictions."
                ),
            )
        )
    irf = dict(
        periods=list(range(d["settings"]["horizon"] + 1)),
        variables=names,
        values=paths["values"],
        **paths["bands"][str(band_level)],
        shock=d["settings"]["shock"],
        shock_size=paths["size"],
        band_level=band_level,
        band_method="posterior credible",
        band_interpretation="pointwise posterior credible bands; not confidence intervals",
        shock_normalization=dict(
            mode=config["outputs"]["irf"].get("shock_mode", "fixed"),
            basis="posterior_mean_covariance_cholesky; fixed across draws and OLS",
            resolved_size=paths["size"],
            shock=d["settings"]["shock"],
            unit="transformed units",
        ),
    )
    variant = dict(
        variant_id="matched_ols",
        label="Matched OLS VAR",
        model_id="var.ols",
        status=ols["status"],
        same_estimand=True,
        changes=["Prior shrinkage removed; identical sample and recursive ordering"],
        actual_sample=dict(start=sample[0], end=sample[-1], nobs=len(sample), periods=sample),
        reason=ols.get("reason"),
        checks=[],
        metrics={},
    )
    if ols["status"] == "ok":
        variant["metrics"] = {
            "responses": [
                dict(
                    variable=name,
                    periods=irf["periods"],
                    values=np.asarray(ols["values"])[:, i].tolist(),
                    peak=float(
                        np.asarray(ols["values"])[
                            np.argmax(np.abs(np.asarray(ols["values"])[:, i])), i
                        ]
                    ),
                )
                for i, name in enumerate(names)
            ]
        }
    return dict(
        label="Model-based scenario, not a forecast",
        coefficients_table=rows,
        irf=irf,
        fevd=dict(
            periods=list(range(1, d["settings"]["horizon"] + 1)),
            variables=names,
            shocks=names,
            values=paths["fevd"],
            units="posterior mean share of forecast-error variance",
            uncertainty="Posterior mean across retained draws; no FEVD band shown",
        ),
        diagnostics=dict(
            nobs=len(sample),
            estimated_indices=sample,
            selected_lags=d["p"],
            parameter_count_per_equation=d["x"].shape[1],
            stable=stable,
            companion_spectral_radius=radius,
            residual_covariance=post["covariance_mean"].tolist(),
            coefficients=central_coefs.tolist(),
            residual_shock_quantiles=dict(
                q05=float(np.quantile(physical, 0.05)),
                q95=float(np.quantile(physical, 0.95)),
                shock=irf["shock"],
            ),
        ),
        bvar=dict(
            prior=dict(
                lambda_=selected,
                lag_decay=params.get("lag_decay", 2),
                own_first_lag_mean=dict(zip(names, d["own_means"].tolist(), strict=True)),
                ar_residual_scales=dict(zip(names, d["sigmas"].tolist(), strict=True)),
                sigma_definition="Univariate AR(p) with constant; SSE / (nobs - design rank)",
                prior_df=post["prior"]["df"],
                dummy_blocks=post["prior"]["blocks"],
                constant_variance=DIFFUSE_VARIANCE,
                symmetric_own_cross=True,
                sum_of_coefficients=params.get("sum_of_coefficients", False),
                co_persistence=params.get("co_persistence", False),
            ),
            grid=grid,
            lambda_selection=params.get("lambda_selection", "fixed"),
            posterior_mean=post["mean"].tolist(),
            posterior_row_covariance=post["variance"].tolist(),
            posterior_scale=post["scale"].tolist(),
            posterior_df=post["df"],
            bands=paths["bands"],
            draws=paths["draws"],
            matched_ols=ols,
            seasonal_controls=d["data"].sample.get("seasonal_controls", {}),
        ),
        checks=[{**c, "phase": "post_estimation"} for c in checks],
        sensitivity=dict(
            status="ok",
            enabled=True,
            variants=[variant],
            comparison_rule=(
                "Matched OLS versus BVAR: same sample, ordering and physical impulse; "
                "descriptive method comparison only."
            ),
            limitations=[
                (
                    "Prior and recursive restrictions remain substantive; agreement is not "
                    "proof of causality."
                )
            ],
        ),
        notes=[
            (
                "The conjugate prior treats own and cross-variable lags symmetrically; "
                "no independent cross-lag tightness."
            ),
            (
                "IRF center is the retained-draw posterior median; 68%/90% bands are "
                "pointwise posterior credible intervals."
            ),
            (
                "One-SD impulses use the posterior-mean covariance Cholesky impact, "
                "held fixed across draws and the OLS comparison."
            ),
            (
                "Fixed or grid-selected hyperparameters are conditioned on; grid "
                "selection is not full hierarchical integration."
            ),
            (
                "Explosive draws remain unless the explicit filter is enabled. No "
                "numerical failures are silently retried or dropped."
            ),
        ],
    )


class BVARPlugin(BasePlugin):
    id, family, title = "bvar.minn", "multivariate", "Bayesian VAR · Minnesota prior"
    summary = "Conjugate shrinkage with seeded posterior bands and a matched OLS comparison."
    label = "Model-based scenario, not a forecast"
    inputs = dict(
        min_series=2,
        max_series=8,
        required_roles={"shock": 1},
        frequencies=["M", "Q", "A"],
        cross_country=False,
    )
    params = schema(
        lags=integer(4, 1, 12),
        **{"lambda": dict(type="number", default=0.2, minimum=0.001, maximum=1e8)},
        lag_decay=dict(type="number", default=2, minimum=0, maximum=4),
        lambda_selection=choice("fixed", "fixed", "grid"),
        lambda_grid=dict(type="array", default=GRID),
        draws=dict(type="integer", default=1000, enum=[1000, 5000]),
        sum_of_coefficients=dict(type="boolean", default=False),
        co_persistence=dict(type="boolean", default=False),
        sum_tightness=dict(type="number", default=1, minimum=0.01, maximum=100),
        co_persistence_tightness=dict(type="number", default=1, minimum=0.01, maximum=100),
        drop_explosive=dict(type="boolean", default=False),
    )
    assumptions = [
        "Recursive ordering imposes contemporaneous zero restrictions.",
        "The conjugate prior treats own and cross-variable lags symmetrically.",
        "Posterior bands condition on prior choices, fixed exogenous paths and the snapshot.",
    ]
    references = [
        dict(
            title="Bańbura, Giannone and Reichlin (2010), Large Bayesian VARs",
            url="https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp966.pdf",
        ),
        dict(
            title="Giannone, Lenza and Primiceri (2015), Prior selection for VARs (grid version)",
            url="https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1494.pdf",
        ),
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            d = design(data, config)
            if len(d["y"]) < 8:
                return [
                    check(
                        "block",
                        "bvar_sample",
                        "BVAR requires at least eight observed estimation periods",
                    )
                ]
            finding = sample_size_check(len(d["y"]), d["x"].shape[1])
            if finding and finding["level"] == "block":
                finding.update(
                    level="warn",
                    message=(
                        "More parameters than observations; BVAR identification relies on "
                        "the proper prior. Matched OLS may be unavailable."
                    ),
                )
            return [finding] if finding else []
        except (ValueError, KeyError, TypeError, IndexError, np.linalg.LinAlgError) as exc:
            return [check("block", "bvar_inputs", str(exc))]

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return fit_bvar(data, config)
