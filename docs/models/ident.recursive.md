# ident.recursive — Recursive identification

G2 validated, local only. Method: Identify ordered shocks with Cholesky restrictions and explicit shock units.

Label: **Model-based scenario, not a forecast**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- The chosen lag structure and deterministic terms describe the joint dynamics.
- Innovations are serially uncorrelated; the bootstrap assumes exchangeable innovations.
- Exogenous regressors are treated as fixed and contemporaneously exogenous.
- Earlier variables do not respond contemporaneously to later shocks in the stated ordering.

## Validation

Maximum absolute reference difference: **2.220446e-16**;
required tolerance **1e-08**. Fixture runtime:
**261.01 ms**. Detailed compared outputs:

- coefficients: 0
- standard_errors: 0
- coefficient_intervals: 0
- normalized_irf: 3.469447e-18
- fevd: 2.220446e-16

Recovery evidence (fixed seeds, thresholds set before the run):

```json
{
  "passed": true,
  "nominal_coverage": 0.68,
  "coverage": 0.653125,
  "coefficient_coverage": 0.675,
  "coverage_by_horizon_variable": [
    [
      0.725,
      0.575
    ],
    [
      0.725,
      0.55
    ],
    [
      0.75,
      0.575
    ],
    [
      0.7,
      0.625
    ]
  ],
  "replications": 40,
  "observations_per_replication": 180,
  "bootstrap_draws": 199,
  "dgp_seed_start": 43000,
  "bootstrap_seed_start": 74000,
  "coverage_diagnostic_envelope": [
    0.45873093302497076,
    0.9012690669750294
  ],
  "large_sample_coefficient_max_abs_error": 0.017111964257324197,
  "large_sample_observations": 4000,
  "interpretation": "Pointwise coverage at horizons 1\u20134; fixed impact restrictions excluded. The envelope is a finite-Monte-Carlo diagnostic, not a proof of calibrated coverage for arbitrary empirical data. Seeds, DGP and thresholds were not tuned."
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

- Residual bootstrap conditions on the selected lag and initial observations.
- Pointwise bands are not simultaneous; exogenous paths are held fixed.
- Recursive ordering is an identifying assumption, not an established causal fact.
- Interpret only the selected, transformed common sample; no omitted-country imputation or sample extrapolation.

## References

- [Lütkepohl (2005), New Introduction to Multiple Time Series Analysis](https://doi.org/10.1007/978-3-540-27752-1)
- [statsmodels VAR reference](https://www.statsmodels.org/stable/vector_ar.html)
