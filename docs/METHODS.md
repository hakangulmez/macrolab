# Methods

MacroLab provides **25 methods in 8 families**. These are the released methods,
not a menu of identification guarantees. Every result records its actual sample,
transformations, shock units and inference choices. See [Validation](VALIDATION.md)
for what has been tested and [the cards](models/README.md) for implementation details.

HAC allows weak serial correlation and heteroskedasticity; HC1 addresses
heteroskedasticity only. Driscoll–Kraay addresses temporal and cross-country
dependence under its large-time-dimension assumptions. Bootstrap validity depends
on the resampling model. A pointwise band concerns one horizon; it is not a
simultaneous band for a whole path. Bayesian credible bands have a different
interpretation from repeated-sample confidence intervals.

## Explore & test

### Time-series plots · `desc.plot`

Compare transformed series over their recorded observed dates.

- **Key assumptions:** Units and transformations must be comparable; missing periods are not filled.
- **Inference:** Descriptive; no confidence intervals.
- **Reference:** [pandas DataFrame](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html). [Validation card](models/desc.plot.md).

### Correlation · `desc.corr`

Measure contemporaneous and trailing-window co-movement.

- **Key assumptions:** Common complete samples; correlation is not causation.
- **Inference:** Descriptive correlations; no causal or simultaneous inference.
- **Reference:** [NumPy correlation](https://numpy.org/doc/stable/reference/generated/numpy.corrcoef.html). [Validation card](models/desc.corr.md).

### Country comparison · `desc.compare`

Compare means or latest observations across economies.

- **Key assumptions:** Comparable definitions and units; unequal samples can alter rankings.
- **Inference:** Descriptive ranks; no equality test.
- **Reference:** [pandas aggregation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.mean.html). [Validation card](models/desc.compare.md).

### Stationarity tests · `test.adf_kpss_pp`

Compare ADF/Phillips–Perron unit-root tests with KPSS stationarity tests.

- **Key assumptions:** Appropriate trend and lag/bandwidth choices; short samples and breaks reduce reliability.
- **Inference:** Test-specific nonstandard p-values and critical values; KPSS is table-bounded.
- **Reference:** [statsmodels stationarity tests](https://www.statsmodels.org/stable/tsa.html#statistical-tests). [Validation card](models/test.adf_kpss_pp.md).

### Granger predictive-content test · `test.granger`

Test whether lagged values add predictive information in a bivariate regression.

- **Key assumptions:** Correct lag specification and covariance stationarity; the classical test assumes uncorrelated homoskedastic errors.
- **Inference:** Classical SSR F test; predictive content does not establish causality.
- **Reference:** [statsmodels Granger tests](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html). [Validation card](models/test.granger.md).

## Regression

### Linear regression · `sing.ols`

Estimate a conditional linear association.

- **Key assumptions:** Regressors must be exogenous for the conditional mean.
- **Inference:** HAC or HC1 standard errors and residual-df Student t intervals; HC1 does not address serial correlation.
- **Reference:** [Newey–West (1987)](#covariance-and-prior-references) for HAC; [statsmodels OLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html). [Validation card](models/sing.ols.md).

### Autoregressive distributed lags · `sing.ardl`

Relate an outcome to its own lags and current/lagged regressors.

- **Key assumptions:** Valid conditional error assumptions; the algebraic error-correction form does not establish cointegration.
- **Inference:** HAC/HC1 regression uncertainty, conditional on the selected lags.
- **Reference:** [statsmodels ARDL / UECM](https://www.statsmodels.org/stable/generated/statsmodels.tsa.ardl.ARDL.html). [Validation card](models/sing.ardl.md).

### Rolling and recursive regression · `sing.rolling`

Refit a regression over trailing or expanding windows.

- **Key assumptions:** Each window uses only observations through its endpoint; regression assumptions must hold within it.
- **Inference:** HAC/HC1 Student t intervals, pointwise across windows.
- **Reference:** [statsmodels RollingOLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.rolling.RollingOLS.html). [Validation card](models/sing.rolling.md).

## Trends & gaps

### Hodrick–Prescott gap · `filter.hp`

Separate a smooth trend and cycle using a chosen penalty.

- **Key assumptions:** The penalty defines the split; this two-sided filter uses future observations and has endpoint sensitivity.
- **Inference:** Descriptive decomposition; no probabilistic bands.
- **Reference:** [statsmodels HP filter](https://www.statsmodels.org/stable/generated/statsmodels.tsa.filters.hp_filter.hpfilter.html). [Validation card](models/filter.hp.md).

### Hamilton gap · `filter.hamilton`

Define the cycle as the residual of a long-horizon projection on lags.

- **Key assumptions:** Horizon/lags define the gap; full-sample coefficients use later information.
- **Inference:** Descriptive fitted gap, not a real-time estimate; no bands.
- **Reference:** [Hamilton (2018)](https://doi.org/10.1162/rest_a_00706). [Validation card](models/filter.hamilton.md).

## VAR & local projections

### OLS VAR · `var.ols`

Estimate joint dynamics, impulse responses and variance shares.

- **Key assumptions:** Adequate lag specification; exogenous controls fixed; residual bootstrap assumes exchangeable innovations.
- **Inference:** Coefficient uncertainty and seeded residual-bootstrap pointwise response bands; identification is separate.
- **Reference:** [Lütkepohl (2005)](https://doi.org/10.1007/978-3-540-27752-1). [Validation card](models/var.ols.md).

### Local projections · `lp.ols`

Estimate a separate outcome regression at each horizon.

- **Key assumptions:** Valid impulse and controls; lag/target windows use the recorded calendar. A raw impulse gives a conditional association.
- **Inference:** Generic default: HAC, bandwidth h+1. Lag augmentation uses HC1. Response bands are normal 68/90%, pointwise; generated-shock uncertainty is conditional unless joint inference is selected.
- **Reference:** [Jordà (2005)](https://doi.org/10.1257/0002828053828518). [Validation card](models/lp.ols.md).

## Identify & compare

### Recursive identification · `ident.recursive`

Convert VAR innovations to ordered shocks using Cholesky restrictions.

- **Key assumptions:** Earlier variables cannot respond within the period to shocks ordered later; ordering is an assumption.
- **Inference:** Inherited VAR response bands and explicit physical shock scaling.
- **Reference:** [Lütkepohl (2005)](https://doi.org/10.1007/978-3-540-27752-1). [Validation card](models/ident.recursive.md).

### Reusable estimated shock · `ident.external_series`

Extract a recursive first-stage VAR shock for another model.

- **Key assumptions:** Aligned dates and a defensible ordering; this is an internally estimated shock, not an imported external instrument.
- **Inference:** Conditional second-stage bands omit first-stage uncertainty. Optional joint residual bootstrap refits both stages on a common window; assumes a suitable auxiliary system and exchangeable innovations.
- **Reference:** [Lütkepohl (2005)](https://doi.org/10.1007/978-3-540-27752-1). [Validation card](models/ident.external_series.md).

### Common-shock comparison · `cmp.common_shock`

Reuse one estimated shock in separate national local projections.

- **Key assumptions:** The same dated impulse and units; samples may differ unless a common window is selected.
- **Inference:** Inherited conditional LP or optional joint bands. Peaks/rankings are descriptive; no cross-country equality test.
- **Reference:** [Jordà (2005)](https://doi.org/10.1257/0002828053828518). [Validation card](models/cmp.common_shock.md).

### Historical decomposition · `out.hd`

Account for past movements using shocks, initial conditions and deterministic terms.

- **Key assumptions:** Stable recursively identified VAR and a regular calendar; model-based accounting does not establish historical causation.
- **Inference:** No contribution intervals; reconstruction is an accounting identity.
- **Reference:** [Lütkepohl (2005)](https://doi.org/10.1007/978-3-540-27752-1). [Validation card](models/out.hd.md).

## Panel models

### Panel fixed effects · `panel.fe`

Estimate a common slope with country effects, optionally time effects.

- **Key assumptions:** Conditional exogeneity; pooled slopes need not describe every country. Lagged outcomes can create Nickell bias.
- **Inference:** Driscoll–Kraay default; clustered and conventional alternatives; Student t intervals. Country OLS uses HAC(4) by default.
- **Reference:** [Driscoll–Kraay (1998)](#covariance-and-prior-references) for panel covariance; [linearmodels 7.0 PanelOLS reference implementation](https://pypi.org/project/linearmodels/7.0/). [Validation card](models/panel_fe.md).

### Panel local projections · `panel.lp`

Pool horizon regressions with fixed effects and country-response overlays.

- **Key assumptions:** A common slope restriction; common shocks exclude time effects. Matched overlays use identical dates.
- **Inference:** Driscoll–Kraay default, clustered sensitivity; normal 68/90% pointwise bands. Country LP: HC1 with augmentation, otherwise HAC. Pooled bands omit first-stage uncertainty.
- **Reference:** [Jordà (2005)](https://doi.org/10.1257/0002828053828518). [Validation card](models/panel_lp.md).

## Bayesian & forecasting

### Minnesota BVAR · `bvar.minn`

Shrink a VAR through a conjugate normal–inverse-Wishart dummy-observation prior.

- **Key assumptions:** Prior/lag/order choices matter; own and cross-variable lags receive symmetric conjugate treatment. Default λ=0.2; AR(p) residuals set scales.
- **Inference:** Seeded posterior draws; 68/90% pointwise credible response bands. Explosive draws are disclosed and retained unless explicitly filtered.
- **Reference:** [Litterman (1986)](#covariance-and-prior-references) for the Minnesota prior; [Bańbura, Giannone and Reichlin, Large Bayesian VARs](https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp966.pdf). [Validation card](models/bvar_minn.md).

### ARIMA / SARIMAX · `uni.arima`

Fit a univariate model with automatic or fixed orders and predict in original units.

- **Key assumptions:** ADF/KPSS guide differencing; AICc chooses orders. Seasonal terms are restricted to monthly NSA inputs.
- **Inference:** 68/90% predictive intervals condition on fitted parameters; linear inverses analytic, nonlinear inverses use seeded joint simulation.
- **Reference:** [statsmodels SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html). [Validation card](models/forecasting.md).

### VAR / BVAR forecasts · `fc.var`

Iterate a multivariate model to generate predictive paths.

- **Key assumptions:** Stable-enough fitted dynamics; any exogenous future path must be chosen explicitly, not read from later data.
- **Inference:** OLS: re-estimated residual bootstrap (500 default draws). BVAR: posterior predictive coefficients and shocks; original-unit 68/90% intervals.
- **Reference:** [statsmodels VAR forecasting](https://www.statsmodels.org/stable/vector_ar.html#forecasting). [Validation card](models/forecasting.md).

### Forecast evaluation · `fc.eval`

Compare expanding-window forecasts with random-walk and AR benchmarks.

- **Key assumptions:** Every transformation/fit uses its training prefix; final-vintage data are not a real-time evaluation.
- **Inference:** RMSE/MAE and paired DM tests with HLN correction and h−1 autocovariances; flagged Bartlett fallback for negative variance. Multiple pairwise tests are not a joint test.
- **Reference:** [Harvey, Leybourne and Newbold (1997)](<https://doi.org/10.1016/S0169-2070(96)00719-4>). [Validation card](models/forecasting.md).

## Long run & breaks

### Cointegration tests · `test.coint`

Run Engle–Granger in both two-variable normalisations and Johansen rank tests.

- **Key assumptions:** I(1) level/log-level inputs, suitable deterministic terms and lag order; no growth inputs.
- **Inference:** MacKinnon p-values; Johansen asymptotic critical values and sequential 95% trace-rank suggestion.
- **Reference:** [statsmodels Johansen test](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.vector_ar.vecm.coint_johansen.html). [Validation card](models/cointegration.md).

### Vector error correction · `vecm`

Fit long-run relations and adjustment dynamics at a user-chosen rank.

- **Key assumptions:** Cointegration assumptions; rank and deterministic specification are conditioned on. Responses may be permanent.
- **Inference:** Asymptotic coefficient SEs; 200-draw seeded residual-bootstrap 68/90% pointwise recursive-response bands, with rank fixed.
- **Reference:** [statsmodels VECM](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.vector_ar.vecm.VECM.html). [Validation card](models/cointegration.md).

### Structural-break diagnostics · `test.break`

Test a chosen split, search a trimmed break window, and show recursive-residual diagnostics.

- **Key assumptions:** Adequate segment lengths; q tested coefficients and Wald/q scaling are explicit. Calibration can be poor with persistence or many parameters.
- **Inference:** HAC-studentised fixed-regressor bootstrap default (499 draws); conventional/HAC asymptotic and HC-bootstrap alternatives; RecursiveLS CUSUM bounds. ECB size remains unreliable.
- **Reference:** [Hansen (2000), Testing for structural change in conditional models](https://users.ssc.wisc.edu/~bhansen/papers/joe_00.pdf). [Validation card](models/break-tests.md).

## Scope and planned work

Shock identification is currently recursive. The reusable-shock interface does
not supply a high-frequency or external-instrument shock dataset. New series
such as EA-MPD require separate data-source approval. Double/debiased machine
learning for shock identification is planned, not implemented. References above
come from the existing validation cards or checked publisher records; software
documentation is retained where it specifies the implemented procedure.

## Covariance and prior references

- Newey, Whitney K., and Kenneth D. West (1987). “A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix.” *Econometrica*, 55(3), 703–708. [doi:10.2307/1913610](https://doi.org/10.2307/1913610).
- Driscoll, John C., and Aart C. Kraay (1998). “Consistent Covariance Matrix Estimation with Spatially Dependent Panel Data.” *The Review of Economics and Statistics*, 80(4), 549–560. [doi:10.1162/003465398557825](https://doi.org/10.1162/003465398557825).
- Litterman, Robert B. (1986). “Forecasting With Bayesian Vector Autoregressions—Five Years of Experience.” *Journal of Business & Economic Statistics*, 4(1), 25–38. [doi:10.1080/07350015.1986.10509491](https://doi.org/10.1080/07350015.1986.10509491).

These references describe covariance estimators and prior motivation. They do not
validate a particular economic interpretation or replace the implementation
choices and limitations in MacroLab's validation cards.
