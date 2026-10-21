# Local DRAFT template configurations — G3.1 defaults

Countries remain USA (monetary policy), GBR (Taylor rule), CAN (Phillips curve),
and ESP (Okun's law). All use accepted snapshot `20261021-0025`, quarterly
frequency, seed 20261021, complete-period aggregation, and no gap filling.
Every result and sensitivity includes actual common/estimation samples,
dropped periods, conversions, transformations, checks and source provenance.

- Monetary: four endogenous variables in a VAR(2), constant; recursive order
  GDP growth, CPI inflation, unemployment, policy rate. GDP/CPI use
  quarter-on-quarter annualised growth. Brent oil remains an exogenous log
  level after complete-quarter means. Three intervention dummies cover exactly
  2020Q1, Q2 and Q3. Requested sample: 1999Q1–latest. Responses span 12 quarters
  with 200 seeded residual bootstrap draws and 68% pointwise bands. The
  higher-precision UI option requests 1,000 draws using the same estimator.
  The default remains +1 fitted structural SD, defined below. Extended VAR
  adds log REER and private nonfinancial credit in levels; COVID-included,
  end-2019, order, fixed-lag and lag-criteria comparisons remain explicit.
- Taylor: policy rate on year-on-year CPI inflation and retrospective HP log
  output gap (lambda 1600), OLS HAC(4), 95% intervals. Default 1999Q1–2008Q4
  limits lower-bound-era distortions. Full-sample and recent-half-of-full-sample
  alternatives expose dependence on the period. Full-sample HP values use their
  own endpoint; the recent half retains those values. This is an association,
  not a real-time output gap or an identified central-bank reaction function.
- Phillips: year-on-year CPI inflation on unemployment, OLS HAC(4), 95%
  intervals, 1999Q1–latest; includes a 40-quarter rolling alternative.
- Okun: year-on-year unemployment-rate change on year-on-year GDP growth,
  OLS HAC(4), 95% intervals, 1999Q1–latest. The quarterly alternative matches
  quarterly unemployment changes with 100×quarterly log GDP growth, without
  annualisation. Its different horizon is not pooled in same-estimand summaries.

## Compatible orchestration options

`outputs.irf.shock_mode` is `fixed` (legacy default) or `one_sd`. With `fixed`,
`shock_size` is a physical transformed-unit size: policy-rate options include
`0.25` (+25bp) and `1.0` (+1pp, explicitly labelled a large illustration).
With `one_sd`, `shock_size` must be `1.0`: exactly +1 structural SD.
The engine fits the existing estimator on the actual sample and computes
`L[k,k]`, where `L L' = SSE / residual degrees of freedom` in the recursive
ordering and k is the policy variable. This covariance-corrected Cholesky
impact is not the empirical ddof=1 SD of recovered physical shocks.

The resolved physical size, formula, residual degrees of freedom and fitted
sample are stored in `irf.shock_normalization`; policy-rate units also have
`resolved_percentage_points`. `resolved_config.outputs.irf` records the
execution request. Bands condition on that resolved physical shock. The
portable config hash identifies the original symbolic request, not a derived
floating-point size. Each sample/COVID scenario resolves its own +1 SD;
order/lag alternatives hold the baseline physical size fixed for comparability.

`special_periods.covid_window` is an optional `{start,end}` in the analysis
frequency. Absent, the legacy 2020Q1–2021Q2 window remains. The monetary
template explicitly narrows this to 2020Q1–Q3. Existing `covid` values
`include`, `dummy`, and `exclude` retain their meaning.

`comparison.scenarios` is an optional unique list of `covid_include`,
`end_2019`, `full_sample`, `recent_half_full_sample`, `quarterly_okun`,
`extended_var`, and `lag_criteria`.
Scenarios reprepare original source inputs, never reuse a truncated source
bundle as full history. Unavailable/blocked scenarios remain visible.
Recent-half estimates require at least 40 observations. In the Taylor template,
the explicit full-history recent half replaces the generic recent half of
the short baseline. Other automatic covariance/sample/order/lag comparisons
remain. Unsupported method or scenario requests never silently change roles.

Result notes are deterministic and based on actual results. Positive output
or inflation responses are retained with an explanation of recursive ordering,
omitted policy information, sample/control dependence and uncertainty.

Run locally: `.venv/bin/python -m macrolab run configs/templates/taylor_rule.json`.
G2.1 comparison: `.venv/bin/python scripts/g21_validate.py` (writes `runs/g21`
and `docs/G2_1_RESULTS.md`; preserves accepted G2 results).

## G3.1 monetary evidence

`extended_var` requires the four-variable GDP/CPI/unemployment/policy system.
It adds REER (log) and credit (level) before policy in the recursive order,
keeps baseline lags, and holds the baseline physical shock size fixed. It
reprepares the actual common sample; missing extra source inputs block this
alternative visibly. Bundle loaders include those two inputs only when the
scenario is explicitly enabled; they do not enter the smaller baseline.

`lag_criteria` exposes AIC, BIC and HQIC for candidates 0–4 (or a smaller
configured maximum). Candidate scores share the maximum-lag holdback, using
the unchanged statsmodels/v0 selection rule. Selected models use their own
estimation sample. A criterion selecting an already fitted lag/order/sample
is marked duplicate, with its equivalent variant, sample, checks and parameter
counts, and incurs no additional bootstrap fit. The fixed default stays at
lag two regardless of the criteria. The evidence is returned under
`sensitivity.lag_criteria`; the candidate table and actual comparison sample
are explicit. Default selection is never silently overwritten.

`sensitivity.summary.peak_response_range` contains the minimum and maximum
signed response at each specification's own absolute-peak horizon, including
the baseline. `peak_absolute_response_range` remains a separate magnitude
summary. Both retain full numerical precision. Duplicate/blocked/failed
alternatives are excluded from agreement denominators.

The first accepted-vintage run is stable, but the observations-per-parameter
warning remains: 105 estimation observations / 13 parameters per equation =
8.0769, below the unchanged ten-to-one warning guideline. This target is not
claimed met. Extended-model instability also remains visible. No warning
threshold, control or source observation was changed to suppress a warning.

Rebuild local evidence with `.venv/bin/python scripts/g31_validate.py`.
It freezes the accepted G3 configuration from commit
`3b12b1ece8b4d86ee7371af9eb466895421a231d`, verifies unchanged model sources,
runs both configurations on the same snapshot, verifies twelve reference
methods, and writes `runs/g31/validation.json` and `runs/g31/REPORT.md`.
Historical G2/G2.1/G3 gate reports are not overwritten.
