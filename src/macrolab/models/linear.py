"""Browser-compatible descriptive, single-equation, unit-root and filter plugins.

ARCH and QuantEcon are used only by the independent native reference tests.
No estimator silently removes observations or replaces a failed fit.
"""

from __future__ import annotations

import math
import warnings
from itertools import combinations
from typing import Any, cast

import numpy as np
import pandas as pd
from statsmodels.api import OLS, add_constant  # type: ignore[import-untyped]
from statsmodels.tsa.adfvalues import mackinnoncrit, mackinnonp  # type: ignore[import-untyped]
from statsmodels.tsa.ardl import ARDL, UECM  # type: ignore[import-untyped]
from statsmodels.tsa.filters.hp_filter import hpfilter  # type: ignore[import-untyped]
from statsmodels.tsa.stattools import (  # type: ignore[import-untyped]
    adfuller,
    grangercausalitytests,
    kpss,
)

from macrolab.models.base import (
    AnalysisConfig,
    AnalysisData,
    BasePlugin,
    check,
    parameters,
    roles,
    sample_size_check,
)


def schema(**properties: Any) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "additionalProperties": False}


def integer(default: int, minimum: int = 1, maximum: int = 120) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def choice(default: str, *values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values), "default": default}


ROBUST = {
    "covariance": choice("HAC", "HAC", "HC1"),
    "hac_lags": integer(4, 0),
    "confidence": {"type": "number", "default": 0.95, "minimum": 0.5, "maximum": 0.999},
}
INPUTS: dict[str, Any] = {
    "min_series": 1,
    "max_series": 6,
    "frequencies": ["M", "Q", "A"],
    "cross_country": False,
}
SINGLE_INPUTS = {**INPUTS, "min_series": 2, "required_roles": {"dependent": 1}, "min_regressors": 1}


def selected(data: AnalysisData, config: AnalysisConfig) -> list[str]:
    return [str(s["concept_id"]) for s in config.get("series", [])] or list(data.frame.columns)


def validate_frame(frame: pd.DataFrame, columns: list[str]) -> None:
    if frame.empty or not columns:
        raise ValueError("Choose at least one series with observations.")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("The sample index must be unique and increasing.")
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise ValueError("The estimation sample must contain finite observations without gaps.")


def sample_diagnostics(frame: pd.DataFrame, **extra: Any) -> dict[str, Any]:
    return {"estimated_indices": [str(i) for i in frame.index], "nobs": len(frame), **extra}


def covariance(params: dict[str, Any], nobs: int) -> dict[str, Any]:
    kind = str(params.get("covariance", "HAC"))
    if kind not in {"HAC", "HC1"}:
        raise ValueError("Covariance must be HAC or HC1.")
    bandwidth = int(params.get("hac_lags", 4))
    if kind == "HAC" and (bandwidth < 0 or bandwidth >= nobs):
        raise ValueError("HAC lags must be nonnegative and smaller than the estimation sample.")
    return {
        "cov_type": kind,
        "cov_kwds": {"maxlags": bandwidth} if kind == "HAC" else {},
        "use_t": True,
    }


def coefficients(fit: Any, names: list[str], confidence: float = 0.95) -> list[dict[str, Any]]:
    if not 0.0 < confidence < 1.0:
        raise ValueError("Confidence must lie strictly between zero and one.")
    bands = np.asarray(fit.conf_int(alpha=1 - confidence))
    matrix = np.column_stack((fit.params, fit.bse, bands, fit.pvalues))
    if not np.isfinite(matrix).all():
        raise ValueError("The fitted coefficient inference is not finite; inspect sample and rank.")
    return [
        {
            "term": name,
            **dict(
                zip(
                    ("estimate", "std_error", "lower", "upper", "p_value"),
                    map(float, row),
                    strict=True,
                )
            ),
        }
        for name, row in zip(names, matrix, strict=True)
    ]


def regression_data(
    data: AnalysisData, config: AnalysisConfig
) -> tuple[pd.Series[Any], pd.DataFrame]:
    dependent, regressors = roles(config, "dependent"), roles(config, "regressor")
    if len(dependent) != 1 or not regressors:
        raise ValueError("Choose one dependent series and at least one regressor.")
    validate_frame(data.frame, dependent + regressors)
    x = data.frame[regressors].copy()
    if data.exog is not None and not data.exog.empty:
        if not data.exog.index.equals(data.frame.index):
            raise ValueError("Fixed regressors must have exactly the estimation sample index.")
        if set(x.columns) & set(data.exog.columns):
            raise ValueError("Fixed and selected regressors must have distinct names.")
        validate_frame(data.exog, list(data.exog.columns))
        x = pd.concat([x, data.exog], axis=1)
    if parameters(config).get("trend", "c") == "c":
        x = add_constant(x, has_constant="add")
    return data.frame[dependent[0]], x


def fit_checks(nobs: int, count: int, condition: float | None = None) -> list[dict[str, Any]]:
    checks = []
    sample = sample_size_check(nobs, count)
    if sample is not None:
        checks.append(sample)
    if condition is not None and condition > 1e8:
        checks.append(
            check(
                "warn",
                "collinearity",
                "Regressors are highly collinear.",
                condition_number=condition,
            )
        )
    return checks


class LinearPlugin(BasePlugin):
    inputs = INPUTS

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        try:
            validate_frame(data.frame, selected(data, config))
        except (ValueError, KeyError) as exc:
            return [check("block", "missing_coverage", str(exc))]
        return []


class PlotPlugin(LinearPlugin):
    id, family, title = "desc.plot", "descriptive", "Time-series plots"
    summary = "Compare selected series over their actual observed sample."
    assumptions = ["Series units and transformations must be comparable before sharing an axis."]
    inputs = {**INPUTS, "cross_country": True}
    params = schema()
    references = [
        {
            "title": "pandas DataFrame",
            "url": "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html",
        }
    ]

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns = selected(data, config)
        rows: list[dict[str, Any]] = []
        samples = {}
        for country, frame in sorted((data.panels or {data.country: data.frame}).items()):
            validate_frame(frame, columns)
            samples[country] = sample_diagnostics(frame)
            for column in columns:
                rows.extend(
                    {
                        "date": str(index),
                        "country": country,
                        "series": column,
                        "value": float(value),
                    }
                    for index, value in frame[column].items()
                )
        return {
            "filtered_series": rows,
            "diagnostics": sample_diagnostics(data.frame, country_samples=samples),
            "notes": ["Values retain the selected transformation and units."],
        }


class CorrelationPlugin(LinearPlugin):
    id, family, title = "desc.corr", "descriptive", "Correlation and rolling correlation"
    summary = "Describe contemporaneous co-movement and its change across trailing windows."
    assumptions = [
        "Correlation describes association; it does not identify a causal effect.",
        "All pairs use the same complete sample.",
    ]
    inputs = {**INPUTS, "min_series": 2}
    params = schema(window=integer(20, 3))
    references = [
        {
            "title": "NumPy correlation coefficient",
            "url": "https://numpy.org/doc/stable/reference/generated/numpy.corrcoef.html",
        }
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        checks = super().check(data, config)
        if len(data.frame) < int(parameters(config).get("window", 20)):
            checks.append(check("block", "small_sample", "The rolling window exceeds the sample."))
        if any(data.frame[c].nunique() < 2 for c in selected(data, config) if c in data.frame):
            checks.append(
                check("block", "constant_series", "Correlation is undefined for a constant series.")
            )
        return checks

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns = selected(data, config)
        validate_frame(data.frame, columns)
        if len(columns) < 2:
            raise ValueError("Correlation requires at least two series.")
        window = int(parameters(config).get("window", 20))
        if window < 3 or window > len(data.frame):
            raise ValueError("Choose a rolling window between three and the sample size.")
        tests, rolling = [], []
        for a, b in combinations(columns, 2):
            value = float(data.frame[a].corr(data.frame[b]))
            if not math.isfinite(value):
                raise ValueError("Correlation is undefined for a constant series.")
            tests.append(
                {"series_a": a, "series_b": b, "statistic": value, "test": "Pearson correlation"}
            )
            values = data.frame[a].rolling(window).corr(data.frame[b]).iloc[window - 1 :]
            for index, value in values.items():
                rolling.append(
                    {
                        "date": str(index),
                        "series_a": a,
                        "series_b": b,
                        "value": float(value) if math.isfinite(value) else None,
                        "window": window,
                    }
                )
        return {
            "test_results": tests,
            "filtered_series": rolling,
            "diagnostics": sample_diagnostics(data.frame),
            "notes": [
                "Undefined correlation in a constant trailing window is shown as missing.",
                "No causal interpretation or confidence bands are attached to correlations.",
            ],
        }


class ComparisonPlugin(LinearPlugin):
    id, family, title = "desc.compare", "descriptive", "Country comparison and ranking"
    summary = "Rank country averages or latest observations over explicitly recorded samples."
    assumptions = [
        "Cross-country series must have comparable definitions and units.",
        "Unequal country samples can change rankings.",
    ]
    inputs = {**INPUTS, "cross_country": True}
    params = schema(statistic=choice("mean", "mean", "last"))
    references = [
        {
            "title": "pandas aggregation",
            "url": "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.mean.html",
        }
    ]

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns = selected(data, config)
        method = parameters(config).get("statistic", "mean")
        if method not in {"mean", "last"}:
            raise ValueError("Comparison statistic must be mean or last.")
        panels = data.panels or {data.country: data.frame}
        rows, samples = [], {}
        for country, frame in sorted(panels.items()):
            validate_frame(frame, columns)
            samples[country] = sample_diagnostics(frame)
            for column in columns:
                value = frame[column].mean() if method == "mean" else frame[column].iloc[-1]
                rows.append(
                    {
                        "country": country,
                        "series": column,
                        "statistic": float(value),
                        "method": method,
                        "sample_start": str(frame.index[0]),
                        "sample_end": str(frame.index[-1]),
                        "nobs": len(frame),
                    }
                )
        for row in rows:
            row["rank"] = 1 + sum(
                other["statistic"] > row["statistic"]
                for other in rows
                if other["series"] == row["series"]
            )
        return {
            "test_results": rows,
            "diagnostics": sample_diagnostics(data.frame, country_samples=samples),
            "notes": [
                "Ranks are descending with equal values receiving equal ranks; "
                "samples are shown for each country."
            ],
        }


def phillips_perron(values: Any, lags: int | None = None, trend: str = "c") -> dict[str, Any]:
    """Phillips-Perron Z-tau with Bartlett long-run variance and MacKinnon inference.

    The residual covariance has denominator T (no demeaning); the OLS variance
    uses T-k. These finite-sample conventions match ARCH's documented PP test.
    """
    y = np.asarray(values, dtype=float)
    if y.ndim != 1 or len(y) < 5 or not np.isfinite(y).all() or np.ptp(y) == 0:
        raise ValueError(
            "Phillips-Perron requires a finite, nonconstant series with at least five observations."
        )
    if trend not in {"n", "c", "ct"}:
        raise ValueError("Phillips-Perron trend must be n, c or ct.")
    n = len(y) - 1
    bandwidth = int(math.ceil(12 * (len(y) / 100) ** 0.25)) if lags is None else lags
    if bandwidth < 0 or bandwidth > n:
        raise ValueError("Phillips-Perron bandwidth must be between zero and residual sample size.")
    regressors = [y[:-1]]
    if trend != "n":
        regressors.append(np.ones(n))
    if trend == "ct":
        regressors.append(np.arange(1, n + 1, dtype=float))
    x = np.column_stack(regressors)
    fit = OLS(y[1:], x).fit()
    residuals = np.asarray(fit.resid)
    gamma0 = float(residuals @ residuals / n)
    long_variance = gamma0 + sum(
        2 * (1 - lag / (bandwidth + 1)) * float(residuals[lag:] @ residuals[:-lag]) / n
        for lag in range(1, bandwidth + 1)
    )
    sigma = float(fit.bse[0])
    s = math.sqrt(float(residuals @ residuals) / (n - x.shape[1]))
    if sigma <= 0 or long_variance <= 0 or s <= 0:
        raise ValueError("Phillips-Perron residual and long-run variances must be positive.")
    statistic = (
        math.sqrt(gamma0 / long_variance) * (float(fit.params[0]) - 1) / sigma
        - 0.5 * ((long_variance - gamma0) / math.sqrt(long_variance)) * n * sigma / s
    )
    critical = mackinnoncrit(N=1, regression=trend, nobs=n)
    return {
        "statistic": float(statistic),
        "p_value": float(mackinnonp(statistic, regression=trend, N=1)),
        "lags": bandwidth,
        "nobs": n,
        "critical_values": dict(zip(("1%", "5%", "10%"), map(float, critical), strict=True)),
    }


class UnitRootPlugin(LinearPlugin):
    id, family, title = "test.adf_kpss_pp", "descriptive", "Unit-root and stationarity tests"
    summary = "Compare ADF and Phillips-Perron unit-root tests with the KPSS stationarity test."
    assumptions = [
        "The deterministic trend specification must match the series.",
        "ADF and PP have a unit-root null; KPSS has a stationarity null.",
        "Tests have limited power in short or structurally changing samples.",
    ]
    params = schema(
        trend=choice("c", "c", "ct"),
        adf_lags=integer(4, 0),
        kpss_lags=integer(4, 0),
        pp_lags=integer(4, 0),
    )
    references = [
        {
            "title": "statsmodels stationarity tests",
            "url": "https://www.statsmodels.org/stable/tsa.html#statistical-tests",
        },
        {
            "title": "ARCH Phillips-Perron",
            "url": "https://arch.readthedocs.io/en/latest/unitroot/generated/arch.unitroot.PhillipsPerron.html",
        },
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        checks = super().check(data, config)
        p = parameters(config)
        lags = int(p.get("adf_lags", 4))
        trend_count = 2 if p.get("trend", "c") == "ct" else 1
        if lags > len(data.frame) // 2 - trend_count - 1:
            checks.append(
                check(
                    "block",
                    "small_sample",
                    "The sample is too short for the chosen ADF lags and trend.",
                )
            )
        if any(int(p.get(key, 4)) >= len(data.frame) for key in ("kpss_lags", "pp_lags")):
            checks.append(
                check("block", "small_sample", "Test bandwidth must be smaller than the sample.")
            )
        if any(data.frame[c].nunique() < 2 for c in selected(data, config) if c in data.frame):
            checks.append(
                check("block", "constant_series", "Unit-root tests require a nonconstant series.")
            )
        return checks

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns, p = selected(data, config), parameters(config)
        validate_frame(data.frame, columns)
        trend = str(p.get("trend", "c"))
        results: list[dict[str, Any]] = []
        notes: list[str] = []
        for column in columns:
            y = data.frame[column]
            if y.nunique() < 2:
                raise ValueError("Unit-root tests require nonconstant series.")
            adf = adfuller(y, maxlag=int(p.get("adf_lags", 4)), regression=trend, autolag=None)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                kp = kpss(y, regression=trend, nlags=int(p.get("kpss_lags", 4)))
            notes.extend(f"{column}: {warning.message}" for warning in caught)
            pp = phillips_perron(y, int(p.get("pp_lags", 4)), trend)
            for name, result in (
                (
                    "ADF",
                    {
                        "statistic": float(adf[0]),
                        "p_value": float(adf[1]),
                        "lags": int(adf[2]),
                        "nobs": int(adf[3]),
                        "critical_values": {key: float(v) for key, v in adf[4].items()},
                    },
                ),
                (
                    "KPSS",
                    {
                        "statistic": float(kp[0]),
                        "p_value": float(kp[1]),
                        "lags": int(kp[2]),
                        "nobs": len(y),
                        "critical_values": {key: float(v) for key, v in kp[3].items()},
                        "p_value_censored": bool(caught),
                    },
                ),
                ("PP", pp),
            ):
                results.append(
                    {
                        "series": column,
                        "test": name,
                        "null": "stationarity" if name == "KPSS" else "unit root",
                        "trend": trend,
                        "sample": sample_diagnostics(data.frame.iloc[-cast(int, result["nobs"]) :]),
                        **result,
                    }
                )
        return {
            "test_results": results,
            "diagnostics": sample_diagnostics(data.frame),
            "notes": notes,
        }


class OLSPlugin(LinearPlugin):
    id, family, title = "sing.ols", "single_eq", "Linear regression"
    label = "Association, not causation"
    summary = "Estimate a conditional linear association with HAC or HC1 uncertainty."
    assumptions = [
        "Regressors are exogenous for the conditional mean.",
        "HAC allows weak serial dependence and heteroskedasticity; "
        "HC1 does not correct serial dependence.",
        "Coefficient intervals use Student t reference quantiles and do not establish causation.",
    ]
    inputs = SINGLE_INPUTS
    params = schema(**ROBUST, trend=choice("c", "c", "n"))
    references = [
        {
            "title": "statsmodels OLS",
            "url": "https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html",
        }
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        try:
            y, x = regression_data(data, config)
        except (ValueError, KeyError) as exc:
            return [check("block", "invalid_regression", str(exc))]
        checks = fit_checks(len(y), x.shape[1], float(np.linalg.cond(x)))
        if y.nunique() < 2:
            checks.append(check("block", "constant_series", "The dependent series is constant."))
        if np.linalg.matrix_rank(x) < x.shape[1]:
            checks.append(check("block", "collinearity", "Regressors are exactly collinear."))
        return checks

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        y, x = regression_data(data, config)
        p = parameters(config)
        if y.nunique() < 2:
            raise ValueError("The dependent series is constant; regression inference is undefined.")
        if np.linalg.matrix_rank(x) != x.shape[1] or len(y) <= x.shape[1]:
            raise ValueError(
                "OLS requires a full-rank design and positive residual degrees of freedom."
            )
        fit = OLS(y, x).fit(**covariance(p, len(y)))
        return {
            "coefficients_table": coefficients(
                fit, list(x.columns), float(p.get("confidence", 0.95))
            ),
            "filtered_series": [
                {
                    "date": str(index),
                    "series": str(y.name),
                    "value": float(value),
                    "fitted": float(fitted),
                    "residual": float(residual),
                }
                for index, value, fitted, residual in zip(
                    y.index, y, fit.fittedvalues, fit.resid, strict=True
                )
            ],
            "diagnostics": sample_diagnostics(
                data.frame,
                r_squared=float(fit.rsquared),
                condition_number=float(fit.condition_number),
                covariance=p.get("covariance", "HAC"),
                hac_lags=p.get("hac_lags", 4),
                residual_df=float(fit.df_resid),
                confidence=float(p.get("confidence", 0.95)),
            ),
            "notes": [
                "Intervals describe coefficient uncertainty; "
                "this regression alone does not identify causation."
            ],
        }


class ARDLPlugin(OLSPlugin):
    id, title = "sing.ardl", "Autoregressive distributed lag regression"
    summary = (
        "Estimate lagged responses and show their equivalent error-correction parameterisation."
    )
    assumptions = [
        "Conditional errors are not correlated with included regressors and lagged outcomes.",
        "The error-correction form is algebraic; it does not by itself establish cointegration.",
        "Selected regressors include current values and every lag through the chosen order.",
    ]
    params = schema(
        **ROBUST, trend=choice("c", "c", "n"), lags=integer(1, 1, 24), order=integer(1, 1, 24)
    )
    references = [
        {
            "title": "statsmodels ARDL and UECM",
            "url": "https://www.statsmodels.org/stable/generated/statsmodels.tsa.ardl.ARDL.html",
        }
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        try:
            regression_data(data, config)
        except (KeyError, ValueError) as exc:
            return [check("block", "invalid_regression", str(exc))]
        p = parameters(config)
        lags, order = int(p.get("lags", 1)), int(p.get("order", 1))
        if min(lags, order) < 1 or max(lags, order) >= len(data.frame):
            return [
                check(
                    "block",
                    "small_sample",
                    "ARDL lags must be positive and smaller than the sample.",
                )
            ]
        design = self.design(data, config)
        checks = fit_checks(len(design), design.shape[1], float(np.linalg.cond(design)))
        if np.linalg.matrix_rank(design) != design.shape[1]:
            checks.append(check("block", "collinearity", "The ARDL lag design is rank deficient."))
        return checks

    def design(self, data: AnalysisData, config: AnalysisConfig) -> pd.DataFrame:
        """Build the visible lag design for rank and sample checks before fitting."""
        p = parameters(config)
        lags, order = int(p.get("lags", 1)), int(p.get("order", 1))
        dependent = roles(config, "dependent")[0]
        columns = {
            f"{dependent}.L{lag}": data.frame[dependent].shift(lag) for lag in range(1, lags + 1)
        }
        columns.update(
            {
                f"{name}.L{lag}": data.frame[name].shift(lag)
                for name in roles(config, "regressor")
                for lag in range(order + 1)
            }
        )
        design = pd.DataFrame(columns, index=data.frame.index)
        if data.exog is not None:
            design = pd.concat([design, data.exog], axis=1)
        if p.get("trend", "c") == "c":
            design = add_constant(design, has_constant="add")
        return design.iloc[max(lags, order) :]

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        p = parameters(config)
        dependent, regressors = roles(config, "dependent"), roles(config, "regressor")
        regression_data(data, config)  # Validate roles, complete observations and fixed regressors.
        lags, order = int(p.get("lags", 1)), int(p.get("order", 1))
        if lags < 1 or order < 1:
            raise ValueError("ARDL error-correction form requires lags and order of at least one.")
        design = self.design(data, config)
        if (
            design.empty
            or len(design) <= design.shape[1]
            or np.linalg.matrix_rank(design) != design.shape[1]
        ):
            raise ValueError(
                "ARDL requires a full-rank lag design and positive residual degrees of freedom."
            )
        model = ARDL(
            data.frame[dependent[0]],
            lags,
            data.frame[regressors],
            order,
            trend=p.get("trend", "c"),
            fixed=data.exog,
            missing="raise",
        )
        effective = data.frame.iloc[max(lags, order) :]
        fit = model.fit(**covariance(p, len(effective)))
        ecm = UECM.from_ardl(model).fit(**covariance(p, len(effective)))
        confidence = float(p.get("confidence", 0.95))
        return {
            "coefficients_table": coefficients(fit, list(fit.model.exog_names), confidence),
            "error_correction_table": coefficients(ecm, list(ecm.model.exog_names), confidence),
            "filtered_series": [
                {
                    "date": str(index),
                    "series": dependent[0],
                    "fitted": float(fitted),
                    "residual": float(residual),
                }
                for index, fitted, residual in zip(
                    effective.index, fit.fittedvalues, fit.resid, strict=True
                )
            ],
            "diagnostics": sample_diagnostics(
                effective,
                lags=lags,
                order=order,
                covariance=p.get("covariance", "HAC"),
                hac_lags=p.get("hac_lags", 4),
                confidence=confidence,
                error_correction_nobs=int(ecm.nobs),
            ),
            "notes": [
                "The error-correction table is a reparameterisation of the same ARDL fit. "
                "It is not a bounds test or evidence of cointegration."
            ],
        }


class RollingPlugin(OLSPlugin):
    id, title = "sing.rolling", "Rolling and recursive regression"
    summary = "Track coefficient estimates in trailing windows or an expanding historical sample."
    assumptions = OLSPlugin.assumptions + [
        "Each window uses only observations available through its endpoint.",
        "Pointwise bands do not adjust for comparisons across many windows.",
    ]
    params = schema(
        **ROBUST,
        trend=choice("c", "c", "n"),
        window=integer(40, 6, 1000),
        mode=choice("rolling", "rolling", "recursive"),
    )
    references = [
        {
            "title": "statsmodels RollingOLS",
            "url": "https://www.statsmodels.org/stable/generated/statsmodels.regression.rolling.RollingOLS.html",
        }
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        checks = super().check(data, config)
        p = parameters(config)
        window = int(p.get("window", 40))
        count = (
            len(roles(config, "regressor"))
            + (0 if data.exog is None else data.exog.shape[1])
            + int(p.get("trend", "c") == "c")
        )
        if window > len(data.frame):
            checks.append(
                check("block", "small_sample", "The regression window exceeds the sample.")
            )
        return checks + fit_checks(window, count)

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        y, x = regression_data(data, config)
        p = parameters(config)
        window, mode = int(p.get("window", 40)), p.get("mode", "rolling")
        if window <= x.shape[1] or window > len(y) or mode not in {"rolling", "recursive"}:
            raise ValueError(
                "Choose a valid regression window with positive residual degrees of freedom."
            )
        rows: list[dict[str, Any]] = []
        for stop in range(window, len(y) + 1):
            start = 0 if mode == "recursive" else stop - window
            window_x = x.iloc[start:stop]
            if np.linalg.matrix_rank(window_x) != x.shape[1]:
                raise ValueError(
                    f"The regression window ending {y.index[stop - 1]} is rank deficient."
                )
            fit = OLS(y.iloc[start:stop], window_x).fit(**covariance(p, stop - start))
            rows.extend(
                {
                    **row,
                    "date": str(y.index[stop - 1]),
                    "window_start": str(y.index[start]),
                    "nobs": stop - start,
                }
                for row in coefficients(fit, list(x.columns), float(p.get("confidence", 0.95)))
            )
        return {
            "filtered_series": rows,
            "coefficients_table": [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"date", "window_start", "nobs"}
                }
                for row in rows[-x.shape[1] :]
            ],
            "diagnostics": sample_diagnostics(
                data.frame,
                window=window,
                mode=mode,
                output_indices=[str(i) for i in y.index[window - 1 :]],
                coefficient_sample=sample_diagnostics(
                    data.frame if mode == "recursive" else data.frame.iloc[-window:]
                ),
                covariance=p.get("covariance", "HAC"),
            ),
            "notes": [
                "Bands are pointwise coefficient intervals, not simultaneous bands. "
                "The coefficient table shows the last window."
            ],
        }


class GrangerPlugin(LinearPlugin):
    id, family, title = "test.granger", "descriptive", "Granger predictive-content test"
    summary = (
        "Test whether lagged values of one series help predict another, "
        "conditional on its own lags."
    )
    assumptions = [
        "The bivariate lag regression is correctly specified and covariance-stationary.",
        "The classical SSR F test assumes homoskedastic uncorrelated errors.",
        "The test measures predictive content, not causation.",
    ]
    inputs = {**SINGLE_INPUTS, "max_series": 2}
    params = schema(lags=integer(4, 1, 24))
    references = [
        {
            "title": "statsmodels Granger tests",
            "url": "https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html",
        }
    ]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        lags = int(parameters(config).get("lags", 4))
        checks = (
            super().check(data, config)
            + fit_checks(len(data.frame) - lags, 2 * lags + 1)
            + [
                check(
                    "info",
                    "granger_language",
                    "Granger causality means predictive content, not causation.",
                )
            ]
        )
        if data.exog is not None and not data.exog.empty:
            checks.append(
                check(
                    "block",
                    "unsupported_fixed_regressors",
                    "The bivariate Granger test cannot include fixed regressors; "
                    "choose COVID include or exclude.",
                )
            )
        if any(data.frame[c].nunique() < 2 for c in selected(data, config) if c in data.frame):
            checks.append(
                check("block", "constant_series", "Granger tests require nonconstant series.")
            )
        return checks

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        dependent, regressors = roles(config, "dependent"), roles(config, "regressor")
        if len(dependent) != 1 or len(regressors) != 1:
            raise ValueError("Choose one dependent series and one predictive regressor.")
        validate_frame(data.frame, dependent + regressors)
        if data.exog is not None and not data.exog.empty:
            raise ValueError(
                "The bivariate Granger reference test does not support fixed regressors."
            )
        lags = int(parameters(config).get("lags", 4))
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="verbose is deprecated", category=FutureWarning
            )
            result = grangercausalitytests(
                data.frame[dependent + regressors], maxlag=[lags], verbose=False
            )[lags][0]["ssr_ftest"]
        return {
            "test_results": [
                {
                    "test": "Granger SSR F",
                    "dependent": dependent[0],
                    "regressor": regressors[0],
                    "lags": lags,
                    "statistic": float(result[0]),
                    "p_value": float(result[1]),
                    "df_denominator": float(result[2]),
                    "df_numerator": float(result[3]),
                    "null": "Lagged regressor coefficients are jointly zero.",
                }
            ],
            "diagnostics": sample_diagnostics(data.frame.iloc[lags:]),
            "notes": [
                "Granger causality means predictive content, not causation. "
                "The reported F test uses classical, non-HAC covariance."
            ],
        }


class HPPlugin(LinearPlugin):
    id, family, title = "filter.hp", "filter", "Hodrick-Prescott filter"
    summary = "Separate a smooth trend from a cycle using an explicit smoothing penalty."
    assumptions = [
        "The smoothing penalty determines the trend-cycle split.",
        "This two-sided filter uses future observations and has endpoint bias; "
        "it is not a real-time forecast.",
    ]
    params = schema(**{"lambda": {"type": "number", "minimum": 0.01, "maximum": 1e9}})
    references = [
        {
            "title": "statsmodels HP filter",
            "url": "https://www.statsmodels.org/stable/generated/statsmodels.tsa.filters.hp_filter.hpfilter.html",
        }
    ]

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns = selected(data, config)
        validate_frame(data.frame, columns)
        penalty = float(
            parameters(config).get(
                "lambda", {"M": 129600.0, "Q": 1600.0, "A": 6.25}[data.frequency]
            )
        )
        if penalty <= 0 or len(data.frame) < 3:
            raise ValueError(
                "HP filtering requires a positive penalty and at least three observations."
            )
        rows: list[dict[str, Any]] = []
        for column in columns:
            cycle, trend = hpfilter(data.frame[column], lamb=penalty)
            rows.extend(
                {
                    "date": str(index),
                    "series": column,
                    "value": float(value),
                    "trend": float(trend_value),
                    "cycle": float(cycle_value),
                }
                for index, value, trend_value, cycle_value in zip(
                    data.frame.index, data.frame[column], trend, cycle, strict=True
                )
            )
        return {
            "filtered_series": rows,
            "diagnostics": sample_diagnostics(data.frame, smoothing_lambda=penalty),
            "notes": [
                "This decomposition is descriptive and has no confidence bands. "
                "The full sample, including future observations, determines the trend."
            ],
        }


class HamiltonPlugin(LinearPlugin):
    id, family, title = "filter.hamilton", "filter", "Hamilton regression filter"
    summary = "Define the cycle as the error in a long-horizon projection on past observations."
    assumptions = [
        "The specified projection horizon and lag count define the cycle.",
        "Full-sample coefficients use future information; "
        "this is a descriptive filter, not a real-time forecast.",
    ]
    params = schema(horizon=integer(8, 1, 120), lags=integer(4, 1, 48))
    references = [
        {
            "title": "Hamilton (2018), Why You Should Never Use the Hodrick-Prescott Filter",
            "url": "https://doi.org/10.1162/rest_a_00706",
        },
        {
            "title": "QuantEcon Hamilton reference",
            "url": "https://quanteconpy.readthedocs.io/en/latest/tools/filter.html",
        },
    ]

    def dimensions(self, data: AnalysisData, config: AnalysisConfig) -> tuple[int, int]:
        defaults = {"M": (24, 12), "Q": (8, 4), "A": (2, 1)}[data.frequency]
        p = parameters(config)
        return int(p.get("horizon", defaults[0])), int(p.get("lags", defaults[1]))

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        horizon, lags = self.dimensions(data, config)
        return super().check(data, config) + fit_checks(
            len(data.frame) - horizon - lags + 1, lags + 1
        )

    def run(self, data: AnalysisData, config: AnalysisConfig) -> dict[str, Any]:
        columns = selected(data, config)
        validate_frame(data.frame, columns)
        horizon, lags = self.dimensions(data, config)
        offset = horizon + lags - 1
        if horizon < 1 or lags < 1 or len(data.frame) - offset <= lags + 1:
            raise ValueError(
                "Hamilton filtering requires positive horizon/lags and a longer sample."
            )
        rows: list[dict[str, Any]] = []
        for column in columns:
            y = data.frame[column].to_numpy(dtype=float)
            x = np.column_stack(
                [np.ones(len(y) - offset)]
                + [y[lags - 1 - lag : len(y) - horizon - lag] for lag in range(lags)]
            )
            if np.linalg.matrix_rank(x) != x.shape[1]:
                raise ValueError("Hamilton filter projection is rank deficient.")
            beta = np.linalg.lstsq(x, y[offset:], rcond=None)[0]
            trend = x @ beta
            rows.extend(
                {
                    "date": str(index),
                    "series": column,
                    "value": float(value),
                    "trend": float(trend_value),
                    "cycle": float(value - trend_value),
                }
                for index, value, trend_value in zip(
                    data.frame.index[offset:], y[offset:], trend, strict=True
                )
            )
        return {
            "filtered_series": rows,
            "diagnostics": sample_diagnostics(
                data.frame.iloc[offset:],
                horizon=horizon,
                lags=lags,
                conditioning_indices=[str(i) for i in data.frame.index[:offset]],
            ),
            "notes": [
                "Initial observations needed to form the projection are omitted; "
                "the actual filtered sample is recorded. "
                "No confidence bands are attached to the descriptive decomposition."
            ],
        }


PLUGINS: list[BasePlugin] = [
    PlotPlugin(),
    CorrelationPlugin(),
    ComparisonPlugin(),
    UnitRootPlugin(),
    OLSPlugin(),
    ARDLPlugin(),
    RollingPlugin(),
    GrangerPlugin(),
    HPPlugin(),
    HamiltonPlugin(),
]
