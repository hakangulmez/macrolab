# test.granger — Granger predictive-content test

G2 validated, local only. Method: Test whether lagged values of one series help predict another, conditional on its own lags.

Label: **Descriptive**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- The bivariate lag regression is correctly specified and covariance-stationary.
- The classical SSR F test assumes homoskedastic uncorrelated errors.
- The test measures predictive content, not causation.

## Validation

Maximum absolute reference difference: **0**;
required tolerance **1e-08**. Fixture runtime:
**1.49 ms**. Detailed compared outputs:

- F_and_p_value: 0

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

- Predictive content conditional on selected lags; no causal interpretation.

## References

- [statsmodels Granger tests](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.grangercausalitytests.html)
