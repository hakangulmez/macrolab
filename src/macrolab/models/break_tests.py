"""Equation-attached structural-change diagnostics with explicit covariance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
from scipy.stats import chi2, f  # type: ignore[import-untyped]
from statsmodels.api import OLS, RecursiveLS  # type: ignore[import-untyped]

from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.models.base import AnalysisData, BasePlugin, check, roles
from macrolab.models.break_bootstrap import calibrate
from macrolab.models.break_calibration import ANDREWS_15, HANSEN_15
from macrolab.models.forecast_common import Cancelled, Progress, tick
from macrolab.models.linear import ARDLPlugin, choice, integer, regression_data, schema


def hansen_probability(wald: float, dimension: int) -> float:
    if not 1 <= dimension <= 40:
        raise ValueError("Hansen calibration supports 1–40 tested coefficients.")
    a, b, df = HANSEN_15[dimension - 1]
    return float(chi2.sf(max(0.0, a + b * wald), df))


def critical_values(dimension: int) -> tuple[dict[str, float], str]:
    if dimension <= 20:
        values = ANDREWS_15[dimension - 1]
        source = "Andrews (2003), corrected Table I, 15% trim"
    else:
        a, b, df = HANSEN_15[dimension - 1]
        values = ((chi2.isf([0.1, 0.05, 0.01], df) - a) / b).tolist()
        source = "Hansen (1997) response-surface approximation; beyond Andrews table dimension 20"
    return dict(
        zip(["90", "95", "99"], [float(v / dimension) for v in values], strict=True)
    ), source


def host_design(
    data: AnalysisData, config: dict[str, Any]
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], list[str], list[str]]:
    host = config["model"]["params"].get("host", "sing.ols")
    c = deepcopy(config)
    c["model"]["id"] = host
    if host == "ident.external_series":
        from macrolab.ident.external_series import recover

        shock, fitted = recover(deepcopy(data), c)
        j = shock["order"].index(shock["shock"])
        matrix = np.asarray(fitted.endog_lagged)
        # Reconstruct the equation's actual dependent observations on its fitted rows.
        values = matrix @ np.asarray(fitted.params)[:, j] + np.asarray(fitted.resid)[:, j]
        if hasattr(fitted, "exog_names"):
            names = list(fitted.exog_names)
        else:
            raise ValueError("Break diagnostics require the contiguous first-stage specification.")
        return values, matrix, names, shock["periods"]
    data = with_seasonal_controls(data, c)
    if host == "sing.ardl":
        x = ARDLPlugin().design(data, c)
        y = data.frame[roles(c, "dependent")[0]].loc[x.index]
    else:
        y, x = regression_data(data, c)
    return y.to_numpy(), x.to_numpy(), list(x.columns), list(map(str, x.index))


def split_test(
    y: np.ndarray[Any, Any],
    x: np.ndarray[Any, Any],
    split: int,
    tested: list[int],
    covariance: str,
    bandwidth: int,
) -> dict[str, float]:
    n, k = x.shape
    q = len(tested)
    # An invertible basis change within the tested block preserves the null and
    # fitted values. Orthogonal columns avoid platform-dependent cancellation
    # when persistent ARDL lags make the Wald covariance poorly conditioned.
    x = x.copy()
    x[:, tested] = np.linalg.qr(x[:, tested], mode="reduced")[0] * np.sqrt(n)
    changed = x[:, tested].copy()
    changed[:split] = 0
    augmented = np.column_stack([x, changed])
    if split <= q or n - split <= q or n <= k + q or np.linalg.matrix_rank(augmented) != k + q:
        raise ValueError("Too few independent observations on either side of this break date.")
    kwargs: dict[str, Any] = {}
    if covariance == "HAC":
        kwargs = dict(cov_type="HAC", cov_kwds={"maxlags": bandwidth}, use_t=False)
    elif covariance == "HC1":
        kwargs = dict(cov_type="HC1", use_t=False)
    fit = OLS(y, augmented).fit(**kwargs)
    delta = np.asarray(fit.params)[-q:]
    variance = np.asarray(fit.cov_params())[-q:, -q:]
    wald = float(delta @ np.linalg.solve(variance, delta))
    restricted = OLS(y, x).fit()
    sse, restricted_sse = float(fit.ssr), float(restricted.ssr)
    classical = max(0.0, (restricted_sse - sse) / q / (sse / (n - k - q)))
    return dict(
        f_statistic=wald / q,
        wald=wald,
        classical_chow_f=classical,
        classical_chow_p=float(f.sf(classical, q, n - k - q)),
        pointwise_wald_p=float(chi2.sf(wald, q)),
        residual_df=n - k - q,
    )


def run_break_tests(
    data: AnalysisData,
    config: dict[str, Any],
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    y, x, names, periods = host_design(data, config)
    options = config["model"]["params"]
    host_covariance = options.get("covariance", "HAC")
    inference = options.get("inference", "hac_bootstrap")
    covariance = "HAC" if inference.startswith("hac_") else "conventional"
    bandwidth = int(options.get("hac_lags", 4))
    # Calendar dummies are stable nuisance regressors, not unidentified split coefficients.
    tested = [
        i for i, name in enumerate(names) if not name.startswith(("covid_", "season_", "seasonal_"))
    ]
    q = len(tested)
    if not 1 <= q <= 40:
        raise ValueError("Break tests support 1–40 tested equation coefficients.")
    n = len(y)
    lower, upper = int(np.ceil(0.15 * n)), int(np.floor(0.85 * n))
    path: list[dict[str, Any]] = []
    omitted = []
    for i, split in enumerate(range(lower, upper + 1)):
        tick(progress, cancelled, "break_candidates", i, upper - lower + 1)
        try:
            row = split_test(y, x, split, tested, covariance, bandwidth)
            path.append(dict(date=periods[split], split=split, **row))
        except (ValueError, np.linalg.LinAlgError) as exc:
            omitted.append(dict(date=periods[split], reason=str(exc)))
    if not path:
        raise ValueError("No estimable break dates inside the 15%-trimmed window.")
    tick(progress, cancelled, "break_candidates", upper - lower + 1, upper - lower + 1)
    peak = max(path, key=lambda r: r["f_statistic"])
    asymptotic_critical, asymptotic_source = critical_values(q)
    bootstrap = calibrate(
        y,
        x,
        tested,
        bandwidth,
        499,
        int(config.get("seed", 42)),
        progress=progress,
        cancelled=cancelled,
    )
    labels = {
        "conventional_asymptotic": "Conventional asymptotic",
        "hac_asymptotic": f"HAC({bandwidth}) asymptotic",
        "hc_bootstrap": "HC fixed-regressor bootstrap (conventional Wald)",
        "hac_bootstrap": f"Fixed-regressor bootstrap, HAC({bandwidth}) Wald",
    }
    variants = []
    for variant, label in labels.items():
        cov = "HAC" if variant.startswith("hac_") else "conventional"
        rows = (
            path
            if cov == covariance
            else [
                dict(
                    date=periods[r["split"]],
                    split=r["split"],
                    **split_test(y, x, r["split"], tested, cov, bandwidth),
                )
                for r in path
            ]
        )
        top = max(rows, key=lambda r: r["f_statistic"])
        is_bootstrap = variant.endswith("bootstrap")
        cv = bootstrap[variant]["critical_values"] if is_bootstrap else asymptotic_critical
        p_value = (
            bootstrap[variant]["p_value"] if is_bootstrap else hansen_probability(top["wald"], q)
        )
        variants.append(
            dict(
                id=variant,
                label=label,
                selected=variant == inference,
                covariance=cov,
                date=top["date"],
                f_statistic=top["f_statistic"],
                wald=top["wald"],
                p_value=p_value,
                critical_values=cv,
                p_value_method="Fixed-regressor bootstrap"
                if is_bootstrap
                else "Hansen (1997) approximation",
                reject_5pct=bool(p_value <= 0.05)
                if is_bootstrap
                else bool(top["f_statistic"] > cv["95"]),
            )
        )
    selected = next(r for r in variants if r["id"] == inference)
    critical = selected["critical_values"]
    source = (
        "Hansen (2000) fixed-regressor bootstrap, 499 draws"
        if inference.endswith("bootstrap")
        else asymptotic_source
    )
    bootstrap.pop("observed_path")
    chow: dict[str, Any] = {"status": "not_requested"}
    date = options.get("break_date", "")
    if date:
        if date not in periods:
            raise ValueError("Choose a Chow date present in the host equation's effective sample.")
        chow = dict(
            status="ok",
            date=date,
            **split_test(y, x, periods.index(date), tested, host_covariance, bandwidth),
        )
    # Recursive residuals also depend only on the column span. A fixed QR
    # reparameterisation improves the diffuse filter's conditioning without
    # changing any prefix regression or estimating a new economic model.
    recursive_x = np.linalg.qr(x, mode="reduced")[0] * np.sqrt(n)
    recursive = RecursiveLS(y, recursive_x).fit()
    burn = int(max(recursive.nobs_diffuse, recursive.loglikelihood_burn))
    if n - burn < 5:
        raise ValueError("Too few recursive residuals after the initial design becomes identified.")
    points = np.arange(burn, n)
    cl, cu = recursive._cusum_significance_bounds(0.05, points=points)
    sl, su = recursive._cusum_squares_significance_bounds(0.05, points=points)
    recursive_rows = [
        dict(
            date=periods[t],
            cusum=float(recursive.cusum[j]),
            cusum_lower=float(cl[j]),
            cusum_upper=float(cu[j]),
            cusum_squares=float(recursive.cusum_squares[j]),
            squares_lower=float(sl[j]),
            squares_upper=float(su[j]),
        )
        for j, t in enumerate(points)
    ]
    checks = []
    minimum_segment = min(lower, n - upper)
    if minimum_segment / q < 5:
        checks.append(
            check(
                "warn",
                "break_segment_thin",
                f"The smallest trimmed segment has {minimum_segment} observations for "
                f"{q} tested coefficients ({minimum_segment / q:.2f} per coefficient), "
                "below five. Break inference in such short segments is unreliable.",
                phase="post_estimation",
            )
        )
    if omitted:
        checks.append(
            check(
                "warn",
                "break_candidates_omitted",
                f"{len(omitted)} break dates lack rank or residual degrees of freedom; "
                "inspect details.",
                phase="post_estimation",
            )
        )
    if min(peak["split"] - lower, upper - peak["split"]) <= 2:
        checks.append(
            check(
                "warn",
                "break_boundary_peak",
                "The sup-F peak is within two observations of the 15% trimming boundary; "
                "the estimated date is sensitive to the search window.",
                phase="post_estimation",
            )
        )
    checks.append(
        check(
            "warn",
            "break_calibration_limits",
            "The default HAC(4)-studentised bootstrap benchmark rejected 9.6%, 9.6% "
            "and 17.2% in the IID, "
            "heteroskedastic and AR(1) null checks at nominal 5% (500 replications). "
            "Inference remains oversized, especially with serial correlation. "
            "IID wild multipliers do not preserve serial correlation; "
            "compare all four calibration rows.",
            phase="post_estimation",
        )
    )
    if n - burn < 40:
        checks.append(
            check(
                "warn",
                "break_recursive_short",
                f"Only {n - burn} recursive residuals remain after {burn} initial rows. "
                "Sparse calendar dummies can delay recursive identification.",
                phase="post_estimation",
            )
        )
    return {
        "break_tests": dict(
            host=options.get("host", "sing.ols"),
            covariance=covariance,
            host_covariance=host_covariance,
            inference=inference,
            inference_label=labels[inference],
            tested_coefficients=q,
            minimum_segment_observations=minimum_segment,
            minimum_segment_observations_per_coefficient=minimum_segment / q,
            statistic_scale="Wald/q",
            asymptotic_critical_values=asymptotic_critical,
            asymptotic_critical_source=asymptotic_source,
            inference_variants=variants,
            bootstrap=bootstrap,
            hac_lags=bandwidth if covariance == "HAC" else None,
            tested_terms=[names[i] for i in tested],
            fixed_nuisance_terms=[name for i, name in enumerate(names) if i not in tested],
            trimming=0.15,
            candidate_path=path,
            omitted_candidates=omitted,
            supremum={
                **peak,
                "approximate_p_value": hansen_probability(peak["wald"], q),
                "p_value": selected["p_value"],
                "p_value_method": selected["p_value_method"],
            },
            critical_values=critical,
            critical_source=source,
            chow=chow,
            recursive=recursive_rows,
            recursive_burn=burn,
            notes=[
                "Statistics and critical values are displayed as Wald/q. Hansen (1997) receives "
                "the unscaled Wald statistic; q is the number of tested coefficients.",
                "The default calibration is chosen by the predeclared minimax size simulation, "
                "not by real-data significance. All four variants remain visible.",
                "HC bootstrap uses heteroskedastic Gaussian wild draws and conventional Wald "
                "as in Hansen (2000); HAC studentisation is a separately evaluated extension.",
                "Hansen (1997) p-values are approximate. Corrected Andrews (2003) "
                "critical values are tabulated separately; near a threshold the "
                "two calibrations can disagree.",
                "CUSUM and CUSUM-of-squares use OLS recursive residuals and 95% "
                "statsmodels bounds; they are not HAC-robust tests.",
                "The Chow SSE F test uses conventional homoskedastic covariance. "
                "The accompanying fixed-date Wald test uses the selected "
                "covariance.",
                "Calendar dummies remain stable nuisance coefficients. Omitted "
                "singular candidate dates are listed; the reference critical line "
                "retains the full nominal 15%-trimmed search.",
            ],
        ),
        "diagnostics": dict(estimated_indices=periods, nobs=n, tested_coefficients=q),
        "checks": checks,
        "sensitivity": {"status": "ok", "variants": []},
    }


class BreakTestsPlugin(BasePlugin):
    id, family, title = "test.break", "tests", "Structural-break diagnostics"
    summary = "Chow, 15%-trimmed sup-F, recursive CUSUM and CUSUM-of-squares for a host equation."
    label = "Parameter stability diagnostic; not causation"
    inputs = {"min_series": 2, "max_series": 12, "frequencies": ["M", "Q", "A"]}
    params = schema(
        host=choice("sing.ols", "sing.ols", "sing.ardl", "ident.external_series"),
        covariance=choice("HAC", "HAC", "HC1", "conventional"),
        inference=choice(
            "hac_bootstrap",
            "hac_bootstrap",
            "hc_bootstrap",
            "hac_asymptotic",
            "conventional_asymptotic",
        ),
        hac_lags=integer(4, 0, 24),
        trend=choice("c", "c", "n"),
        lags=integer(1, 1, 24),
        order=integer(1, 1, 24),
        break_date={"type": "string", "default": ""},
        source_variant=choice("none", "none", "dfr", "bis", "rate_3m"),
    )
    assumptions = [
        "HAC sup-Wald permits weak dependence under regularity conditions; "
        "the asymptotic calibration can be inaccurate in small samples."
    ]
    references = [
        {
            "title": "Hansen (2000), fixed-regressor bootstrap",
            "url": "https://users.ssc.wisc.edu/~bhansen/papers/joe_00.pdf",
        },
        {
            "title": "Hansen (1997), p-value approximation",
            "url": "https://users.ssc.wisc.edu/~behansen/progs/jbes_97.html",
        },
        {
            "title": "Andrews (2003), corrected critical values",
            "url": "https://doi.org/10.1111/1468-0262.00405",
        },
    ]

    def check(self, data: AnalysisData, config: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            y, x, names, periods = host_design(data, config)
            if len(y) < 25 or np.linalg.matrix_rank(x) != x.shape[1]:
                raise ValueError(
                    "Break tests require at least 25 observations and a full-rank host equation."
                )
            if config["model"]["params"].get("hac_lags", 4) >= len(y):
                raise ValueError("HAC bandwidth must be below the effective sample size.")
            date = config["model"]["params"].get("break_date")
            if date:
                if date not in periods:
                    raise ValueError(
                        "The Chow date must be in the host equation's effective sample."
                    )
                tested = [
                    i
                    for i, name in enumerate(names)
                    if not name.startswith(("covid_", "season_", "seasonal_"))
                ]
                split_test(y, x, periods.index(date), tested, "conventional", 0)
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            return [check("block", "break_sample", str(exc))]
        return []

    def run(self, data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
        return run_break_tests(data, config)
