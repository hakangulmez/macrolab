# filter.hp — Hodrick-Prescott filter

G2 validated, local only. Method: Separate a smooth trend from a cycle using an explicit smoothing penalty.

Label: **Descriptive**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- The smoothing penalty determines the trend-cycle split.
- This two-sided filter uses future observations and has endpoint bias; it is not a real-time forecast.

## Validation

Maximum absolute reference difference: **0**;
required tolerance **1e-08**. Fixture runtime:
**2.05 ms**. Detailed compared outputs:

- cycle: 0
- trend: 0

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

- Retrospective filter; the full selected sample influences the fitted trend. It is not a forecast or a real-time gap estimate.

## References

- [statsmodels HP filter](https://www.statsmodels.org/stable/generated/statsmodels.tsa.filters.hp_filter.hpfilter.html)
