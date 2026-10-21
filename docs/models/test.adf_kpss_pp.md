# test.adf_kpss_pp — Unit-root and stationarity tests

G2 validated, local only. Method: Compare ADF and Phillips-Perron unit-root tests with the KPSS stationarity test.

Label: **Descriptive**. The same pure Python implementation runs natively and
in the offline Pyodide worker. Native dependencies are pinned in `uv.lock`;
browser dependencies and checksums are in `web/runtime/assets.lock.json`.

## Assumptions

- The deterministic trend specification must match the series.
- ADF and PP have a unit-root null; KPSS has a stationarity null.
- Tests have limited power in short or structurally changing samples.

## Validation

Maximum absolute reference difference: **1.7763568e-15**;
required tolerance **1e-08**. Fixture runtime:
**2.20 ms**. Detailed compared outputs:

- ADF: 0
- KPSS: 0
- PP: 1.7763568e-15

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

- Unit-root tests have limited power and depend on trends and lag/bandwidth choices. Disagreement is retained.

## References

- [statsmodels stationarity tests](https://www.statsmodels.org/stable/tsa.html#statistical-tests)
- [ARCH Phillips-Perron](https://arch.readthedocs.io/en/latest/unitroot/generated/arch.unitroot.PhillipsPerron.html)
