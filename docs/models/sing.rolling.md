# sing.rolling — Rolling and recursive regression

G2 validated, local only. Method: Track coefficient estimates in trailing windows or an expanding historical sample.

Label: **Association, not causation**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- Regressors are exogenous for the conditional mean.
- HAC allows weak serial dependence and heteroskedasticity; HC1 does not correct serial dependence.
- Coefficient intervals use Student t reference quantiles and do not establish causation.
- Each window uses only observations available through its endpoint.
- Pointwise bands do not adjust for comparisons across many windows.

## Validation

Maximum absolute reference difference: **5.7731597e-15**;
required tolerance **1e-08**. Fixture runtime:
**77.09 ms**. Detailed compared outputs:

- rolling_coefficients: 5.7731597e-15
- last_window_se_bands: 0

Recovery evidence (fixed seeds, thresholds set before the run):

```json
{
  "status": "not_applicable"
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

- [statsmodels RollingOLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.rolling.RollingOLS.html)
