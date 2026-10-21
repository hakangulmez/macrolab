# sing.ardl — Autoregressive distributed lag regression

G2 validated, local only. Method: Estimate lagged responses and show their equivalent error-correction parameterisation.

Label: **Association, not causation**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- Conditional errors are not correlated with included regressors and lagged outcomes.
- The error-correction form is algebraic; it does not by itself establish cointegration.
- Selected regressors include current values and every lag through the chosen order.

## Validation

Maximum absolute reference difference: **0**;
required tolerance **1e-08**. Fixture runtime:
**5.30 ms**. Detailed compared outputs:

- levels: 0
- error_correction: 0

Recovery evidence (fixed seeds, thresholds set before the run):

```json
{
  "passed": true,
  "coverage": 0.9416666666666667,
  "coverage_count": 113,
  "repetitions": 120,
  "nominal_coverage": 0.95,
  "acceptance_interval": [
    0.85,
    1.0
  ],
  "mean_coefficient_error": -0.007606215100631373,
  "rmse": 0.0609137630371018,
  "seed": 504019,
  "nobs": 250,
  "covariance": "HAC",
  "hac_lags": 4
}
```

Reproduce with `python scripts/g2_validate.py` and `python -m pytest tests/reference
tests/synthetic tests/analysis`. Numerical reference tests cover the primary
estimands, standard errors and intervals where supplied; descriptive and filter
models do not claim probabilistic coefficient recovery. VAR tests include FEVD
adding-up, variable renaming, identified-order dependence and independent normalized
asymptotic delta-method comparison. Rolling fits are checked against future leakage.
Filter reconstruction and reversible transformation identities are tested separately.

## Limits

- Association only; covariance corrections do not identify causal effects. HAC bandwidth and sample choices affect inference.

## References

- [statsmodels ARDL and UECM](https://www.statsmodels.org/stable/generated/statsmodels.tsa.ardl.ARDL.html)
