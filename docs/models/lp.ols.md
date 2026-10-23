# lp.ols — local projections (G6)

For each horizon h, regress the explicit response target on an impulse, a
constant, p lags of the response/impulse/other endogenous controls, and current
exogenous controls. The default uses one common anchor sample across all horizons;
horizon-specific windows are optional. Report anchor dates, n, dropped dates,
frequency conversion and transformations, including the final horizon holdback.
Missing calendar periods are never treated as adjacent or interpolated.

Response modes:

- level: transformed Y[t+h];
- change: Y[t+h] − Y[t−1], in the input units;
- cumulative_log: 100 × (log Y[t+h] − log Y[t−1]), labelled
  **cumulative % change in the level**, without annualisation;
- growth_log: 100 × (log Y[t+h] − log Y[t+h−1]), optionally multiplied by an
  explicitly reported frequency scale for the alternative growth display.

The log modes require source log levels, not previously computed growth rates.
Default inference is Bartlett/Newey–West HAC, bandwidth h+1, no small-sample
covariance correction, normal quantiles, 68% and 90% **pointwise** intervals.
Lag augmentation adds one complete lag and uses HC1, n/(n−rank). Nuisance-column
redundancy is retained and its effective rank reported; the impulse coefficient
must be separately identified. No band is called simultaneous.

At the longest horizon, n<40 warns and n<20 blocks. General observations-per-
parameter, stale/missing data, lower-bound and COVID checks also apply. NSA inputs
receive calendar controls (Q2–Q4 or February–December, reference season 1); no
observations are seasonally adjusted in the app. The y/y-price sensitivity changes
the estimand and is excluded from same-estimand agreement counts.

A raw impulse is labelled a conditional association, controlling for lags. An
identified impulse is conditional on the stated first-stage identification;
default HAC/HC1 bands ignore its estimation uncertainty. The joint alternative
is described in [ident.external_series](ident.external_series.md).

Validation: independent statsmodels OLS/HAC/HC1 comparisons, H=0 OLS identity,
control permutation/renaming, cumulative/growth target identities, calendars,
seasonality and full-engine y/y sensitivity. Fixed-seed VAR(2) recovery uses 200
replications at each of T=120 and T=240; empirical 90% coverage is 80.5–88.0% and
83.5–89.5%, respectively. This finite-sample undercoverage is disclosed, not tuned
away. Coefficient reference maximum difference is 0; HAC SE maximum is 1.45e-14.
The G6 report records browser parity, runtime and coverage at every horizon.

References: [Jordà (2005)](https://doi.org/10.1257/0002828053828518);
[Montiel Olea and Plagborg-Møller (2021)](https://doi.org/10.3982/ECTA18756).

## G7 template inference

The generic plug-in retains its G6 defaults. The two new templates select
lag-augmented HC1: the fixed 200-replication G6 protocol gives mean absolute
90%-coverage errors of 2.00 and 1.62 percentage points at T=120/240, versus
5.85 and 2.96 for HAC. This is a DGP-specific improvement, not a coverage
promise. HAC remains a sensitivity option and removes the augmentation lag.

`lag_difference_scales` lets original log levels define the response target
while their lag controls enter as growth: 400 times the quarterly log difference
for ECB output/prices, 100 times the monthly log difference for Türkiye prices.
The response remains exactly 100×(log Y[t+h]−log Y[t−1]). One additional initial
period is recorded when a lagged difference requires it. Independent OLS/HC1
and the bootstrap fast fit are checked against this same design.

## G7.1 cumulative pass-through ratio

The Türkiye headline is R(h) = -CPI(h)/NEER(h), where both responses are
cumulative 100 × log-level changes from t−1 to t+h following the same initial
−1% NEER impulse. NEER rises with appreciation, so the minus sign makes
depreciation-positive pass-through explicit. TRY/USD uses +CPI(h)/FX(h). This
is a conditional association; normalization does not identify an exogenous shock.
See [Forbes, Hjortsoe and Nenova (2017)](https://www.bankofengland.co.uk/external-mpc-discussion-paper/2017/explaining-differences-in-exchange-rate-pass-through)
and the explicit NEER sign convention in [World Bank WPS8780, section 3.2](https://documents.worldbank.org/curated/en/880231552490402888/pdf/WPS8780.pdf).

The CPI LP design, original controls, seasonal dummies and anchor sample stay
unchanged. A second dependent target cumulates observed NEER log changes over
t..t+h on exactly those rows. The two response coefficients have a joint HC1
sandwich covariance, including the cross-equation score product. Delta-method
variance is gradient(R)' covariance gradient(R); the HAC alternative instead
uses the same horizon h+1 Bartlett covariance as its price LP. Both 68% and 90%
pointwise normal intervals are exported. A denominator below 1e−10 in absolute
value yields an undefined ratio, not infinity; a 90% denominator interval
crossing zero flags weak identification of the ratio. Delta intervals may be
unreliable near zero and are not Fieller confidence sets.

The secondary CPI response is explicitly labelled “response to an initial 1%
depreciation, followed by the exchange rate’s own subsequent path”. A growth-rate
display does not change the cumulative definition of the headline ratio.

## G8 matched method view

The on-demand comparison is a separate result. Common LP anchor dates determine
an auxiliary VAR estimation window, including its lag initialization. Fit that VAR
once, then evaluate its residuals over the observed calendar with those fixed
coefficients and covariance. Its orthogonalised residual is the same dated impulse
used in LP; future observations supply targets, not extra VAR estimation rows.
The VAR and LP estimation date lists must match exactly or comparison blocks.
The baseline physical normalization is retained, although the shorter VAR window
is refitted. Required NSA calendar controls enter both paired methods; obtain the
baseline one-SD physical size before adding those controls. For a raw-impulse LP,
this recursive identification is a different
estimand from the baseline and is labelled accordingly.

The pair reports conditional lag-augmented HC1 LP bands and 200-draw residual
bootstrap VAR bands, each pointwise at 68%. Log-response VARs use growth dynamics
and cumulate each draw before quantiles. Level targets retain level units.
Agreement/overlap is reported at every horizon and only within the pair; none of
its rows is included in the baseline's sensitivity counts. Exact dates, dropped
periods, conversions, order, physical size and innovations are exported in JSON;
CSV retains sample and conversion metadata. Python reproduces both baseline and
pair offline. Shock fingerprints cover full-precision outputs within one runtime;
compare browser/native numbers at 1e-8, not their byte-level shock fingerprints.
Fixed positive lags and a constant are supported; irregular windows, unsupported
response definitions and unstable paired VARs block the comparison visibly.
Independent statsmodels tests cover response units, residual recovery, HC1
coefficients/intervals, exact anchor identity and non-mutation of baseline inputs.
