# filter.hamilton — Hamilton regression filter

G2 validated, local only. Method: Define the cycle as the error in a long-horizon projection on past observations.

Label: **Descriptive**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- The specified projection horizon and lag count define the cycle.
- Full-sample coefficients use future information; this is a descriptive filter, not a real-time forecast.

## Validation

Maximum absolute reference difference: **7.1054274e-15**;
required tolerance **1e-08**. Fixture runtime:
**2.25 ms**. Detailed compared outputs:

- cycle: 7.1054274e-15
- trend: 6.8833828e-15

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

- [Hamilton (2018), Why You Should Never Use the Hodrick-Prescott Filter](https://doi.org/10.1162/rest_a_00706)
- [QuantEcon Hamilton reference](https://quanteconpy.readthedocs.io/en/latest/tools/filter.html)
