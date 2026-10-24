# Forecasting — G13 validation card

Only `uni.arima`, `fc.var` and `fc.eval` produce forecasting outputs. All use
final-vintage data. Their uncertainty and assumptions do not establish causality.
No new runtime dependency or data source is used; the snapshots remain unchanged.

## Preparation and inverses

The raw, complete-period frequency-converted sample is retained. Every training
prefix is transformed independently. No later observation, full-sample mean,
standard deviation or BVAR scale is passed to an estimator. HP and Hamilton
cycles are blocked: their lossy inverse would require an additional trend model.
An index base later than the origin is also unavailable at that origin. Internal
gaps require an explicit contiguous sample; there is no automatic selection of
an evaluation window using later gaps. Monthly and quarterly frequencies are
released; annual forecasting is not included.

Linear inverses (level, difference, year-on-year difference and index-to-base)
use the full joint horizon covariance analytically for Gaussian SARIMAX paths.
Log, log difference, year-on-year percentage growth and annualised quarterly
growth use 10,000 seeded joint Gaussian paths. Original-unit predictive means
and equal-tail 68/90% intervals include Jensen effects. Invalid growth paths
(≤ −100%) block with an explanation; none are clipped or discarded. VAR/BVAR
intervals use their seeded predictive paths. All original-unit values retain
full computation precision in CSV/JSON and reproduction scripts.

## SARIMAX

ADF (constant, AIC lag choice) and KPSS (constant, automatic bandwidth), both at
5%, determine d. ADF rejection plus KPSS non-rejection gives d=0; agreement on
nonstationarity gives d=1. Disagreement uses d=1 and exposes a separately searched
d=0 sensitivity. KPSS p-values are table-bounded. Manual orders override automatic
selection and are recorded. The exhaustive AICc grid is p,q=0,…,4. Monthly NSA
series additionally search P,Q=0,1 at period 12; seasonal differencing D=0. The
chosen order and runner-up are reported. Failed/nonconverged candidates are
ineligible and listed, with a warning. AICc uses effective likelihood observations
and all fitted parameters. Residual Ljung–Box degrees of freedom subtract p+q+P+Q.

SARIMAX supplies the likelihood, Kalman states, forecast means, covariance and
residual diagnostics. Training-only centering/scaling improves conditioning;
likelihoods and predictions are returned to the requested transformed scale.
The stationary state covariance uses the same discrete Lyapunov equation as
SARIMAX, solved directly in vectorized form for small systems and by doubling for
seasonal systems. This avoids a native/WASM discrepancy in complex derivatives
of the library's Schur initialization. Direct SARIMAX likelihood, prediction and
variance comparisons validate the equivalent initialization; central differences
validate the complete unconstrained complex-step score. Integrated models use
SARIMAX simple differencing, then restore the requested level and full joint
covariance. A small portable BFGS implementation controls native/WASM
line-search decisions: integer coordinates at 1e−10, inverse Hessian at ten
relative digits, per-observation objective at 1e−8, and gradient at 1e−9.
Training-standardized observations are rounded to 12 decimals. This is numerical
precision, not display rounding. Reported likelihoods and distributions are
re-evaluated without rounding at the final coordinates. There is no change to
any accepted estimator. SARIMAX predictive intervals condition on estimated
parameters; they do **not** include parameter uncertainty.

## VAR / BVAR

OLS uses a constant and fixed p (default 2). Each of 500 default residual-bootstrap
draws simulates a training history, re-estimates every coefficient and draws
future residual innovations. Linear inverses retain the exact iterated OLS point
forecast; the paths determine its intervals. Nonlinear predictive means use the
inverse paths. Initial p observations and historical deterministic
controls are held fixed. BVAR uses the accepted conjugate Minnesota prior with
λ=.2, lag variance decay 2, transform-derived own-lag means, and diffuse
deterministic priors. Univariate AR(p) residual scales are recomputed within each
training prefix. Predictive paths draw coefficients and covariance from the NIW
posterior, plus future Gaussian innovations, using separate seeded streams.
No explosive predictive paths are silently discarded; nonfinite paths block.

Selected exogenous variables require an explicit future assumption: held at the
last **transformed** value or zero in transformed units. This includes every
rolling evaluation origin, without reading future exogenous observations.
Defaults select no exogenous variables. Future COVID dummies are zero and
seasonal controls follow the known calendar, including NSA price controls.

## Evaluation and DM / HLN

The first origin has 40 raw quarters or 120 raw months; transformation holdback
is disclosed in each training sample. Every subsequent origin re-estimates all
models. Maximum prediction horizons remain fixed even near the end of the
sample; metrics use only subsequently observed targets. Q horizons are 1/4/8;
M horizons 1/6/12. Random walk (no change), AR(BIC), ARIMA and BVAR are always
included. The target is the first selected non-exogenous variable, explicitly
selectable in Builder. AR(BIC) searches p=1,…,min(12,floor((T−5)/3)) on a common
lag holdback, then refits the chosen order on all available rows. AR/ARIMA orders
are fixed at the first origin by default; optional re-selection uses each prefix.
BVAR lag count stays user-fixed. Metrics compare original-unit errors on common
successful origins and show counts. First-origin failure blocks; later failures
are listed and warned. Sensitivity excludes 2020–2021 **targets**, without
removing those observations from later training histories.

For paired squared-error differential d, γ(k)=Σ(d[t]−mean)(d[t−k]−mean)/N.
The long-run variance is γ(0)+2Σ(k=1,…,h−1)γ(k). A negative estimate triggers
Bartlett weights 1−k/h and a flag. Removed targets preserve calendar lag distances.
Zero/invalid variance or N≤h produces an unavailable test. The DM statistic is
multiplied by sqrt((N+1−2h+h(h−1)/N)/N), with two-sided t(N−1) p-values.
Several pairwise DM tests are not a joint test; nested-model comparisons also
need caution. The label is **pseudo-out-of-sample, final-vintage data; real-time
performance may be worse**. The EA HICP horse-race template remains for G15.

References: [statsmodels SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html),
[statsmodels VAR forecasting](https://www.statsmodels.org/stable/vector_ar.html#forecasting),
[Harvey, Leybourne and Newbold (1997)](https://doi.org/10.1016/S0169-2070(96)00719-4).

## Accepted G13 diagnostic and timing targets

The accepted warm median targets are 10 seconds for exhaustive ARIMA search and
40 seconds for approximately 60 evaluation origins with four models, both with
progress and cancellation. The original G13 measurements meet these revised
targets. Evaluation offers separate exclusions for 2020–2021 target dates and
2020–2021 origin dates; neither refits a model or removes observations from its
training prefix. Error plots show actual minus prediction by target date against
the random walk for the same origin and horizon. CSV retains origin, target,
horizon and the unrounded errors; PNG exports the selected error chart.

See USA unemployment loss attribution (local review record omitted from source export) for the
eight-quarter diagnostic and independent native statsmodels prefix checks.
