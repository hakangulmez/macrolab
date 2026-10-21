# desc.plot — Time-series plots

G2 validated, local only. Method: Compare selected series over their actual observed sample.

Label: **Descriptive**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- Series units and transformations must be comparable before sharing an axis.

## Validation

Maximum absolute reference difference: **0**;
required tolerance **1e-08**. Fixture runtime:
**0.95 ms**. Detailed compared outputs:

- plot_values: 0

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

- Interpret only the selected, transformed common sample; no omitted-country imputation or sample extrapolation.

## References

- [pandas DataFrame](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html)
