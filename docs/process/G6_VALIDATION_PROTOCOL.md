# G6 validation protocol (fixed before recovery runs)

No v0 numerical default changes. Exact within-runtime comparisons retain 4,042
accepted numeric fields; browser/native tolerance is 1e-8. LP coefficients and
SEs must match independent statsmodels OLS/HAC or HC1 fits within 1e-8. HAC uses
Bartlett weights, bandwidth h+1, no finite-sample correction, normal quantiles;
HC1 uses n/(n-k). Lag augmentation adds one full lag and uses HC1.

LP recovery: 200 replications each at T=120 and T=240, H=12, burn-in=300,
seed 20261022. Recursive VAR(2): A1=[[.45,.10],[.05,.35]],
A2=[[-.10,0],[.02,-.08]], impact=[[1,0],[.35,.8]]. Response is variable 2 to
structural shock 1; true shock is observed. Two lags of both variables and the
shock; constant; common sample. Report mean bias, Monte Carlo SE and empirical
90% pointwise coverage for every horizon. Recovery check: absolute mean bias
<= max(.10, 3*Monte Carlo SE). Coverage is reported, including departures from
90%; a floor of 75% at any horizon flags a validation failure for investigation,
not a reason to tune the DGP or bands. Monte Carlo binomial SE at 90% is 2.12 pp.

Two-stage recovery: same 200 replications per T and stage-1 DGP, policy shock 2;
national outcome y[t]=.5*y[t-1]-.1*y[t-2]+.6*epsilon2[t]+eta[t], eta SD=.7.
True response follows this AR(2) recursion. Conditional LP and optional joint
bootstrap are both evaluated, H=12, two lags, 200 bootstrap draws per replication,
seed 20261023. Same bias/coverage reporting and diagnostic thresholds as above.

Joint residual bootstrap: fit a block-triangular auxiliary system. Stage 1 is the
specified recursive VAR; each national vector is an ARX conditional on current
structural shocks, selected lagged variables and fixed exogenous/deterministic
controls. Resample complete contemporaneous innovation vectors together and
simulate stage 1 and national outcomes recursively. Re-estimate stage 1, recover
a new shock, and refit all second-stage LPs in every draw. This preserves within-
date cross-equation dependence; innovations must be serially exchangeable and
exogenous controls are conditioned on. Center each bootstrap estimation error on the analytically computed response
of the fitted auxiliary DGP, then invert those error quantiles around the sample
LP estimate. The auxiliary VAR/ARX population response need not equal the sample
LP estimate; treating them as interchangeable would miscenter the bands. These
are pointwise intervals, not simultaneous bands. An unbalanced system requires an explicit common-window
alternative; it must not silently change a country's baseline sample. Failed or
unstable first-stage bootstrap draws are counted and cause a visible failure if
there are insufficient valid draws; never silently discard an arbitrary tail.

Additional gates: H=0 OLS identity, control permutation/renaming invariance,
cumulative log-level and growth-display identities, per-horizon sample accounting,
seasonal controls in each stage, strict shock dates/coverage and stable first-stage
requirements, historical-decomposition identity and a hand-computed fixture,
one-country comparison identical to direct LP, progress/cancel, offline exported
Python reproduction, native/browser parity and warm performance. No network is
needed for this validation; the pinned scientific runtime is already cached.

Reference-test finding before Monte Carlo execution: known VAR shocks plus a
full augmented lag can make nuisance regressors algebraically redundant. Keep
all specified columns and report their effective rank/redundant dimension;
Moore–Penrose OLS and HC1 use effective rank, as statsmodels does. Block when the
impulse itself lies in the nuisance span. This is not automatic variable selection
or a change to the DGP. Sample-size notes use the effective estimable rank.
