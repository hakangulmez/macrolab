# sing.ols — Linear regression

G2 validated, local only. Method: Estimate a conditional linear association with HAC or HC1 uncertainty.

Label: **Association, not causation**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- Regressors are exogenous for the conditional mean.
- HAC allows weak serial dependence and heteroskedasticity; HC1 does not correct serial dependence.
- Coefficient intervals use Student t reference quantiles and do not establish causation.

## Validation

Maximum absolute reference difference: **0**;
required tolerance **1e-08**. Fixture runtime:
**2.46 ms**. Detailed compared outputs:

- coefficients_se_bands_pvalues: 0
- Longley_coefficients_se_bands_pvalues: 0

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
  "mean_coefficient_error": -0.002976246742379655,
  "rmse": 0.06268532854189762,
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

- [statsmodels OLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html)
