# Model validation cards

These cards document the **25 released methods in 8 families**: assumptions,
implementation choices, numerical cross-checks, simulation evidence and limits.
Start with [How methods are validated](../VALIDATION.md) for the evidence types
and [Methods](../METHODS.md) for the economist-facing guide.

Dates and gate references inside a card identify its original validation record.
Later accepted addenda take precedence; a historical “local only” label does not
mean that the current released method is unavailable. Public observations are
final-vintage data, not a real-time dataset.

| Family                  | Method                  | Card                                   |
| ----------------------- | ----------------------- | -------------------------------------- |
| Explore & test          | `desc.plot`             | [Validation](desc.plot.md)             |
| Explore & test          | `desc.corr`             | [Validation](desc.corr.md)             |
| Explore & test          | `desc.compare`          | [Validation](desc.compare.md)          |
| Explore & test          | `test.adf_kpss_pp`      | [Validation](test.adf_kpss_pp.md)      |
| Explore & test          | `test.granger`          | [Validation](test.granger.md)          |
| Regression              | `sing.ols`              | [Validation](sing.ols.md)              |
| Regression              | `sing.ardl`             | [Validation](sing.ardl.md)             |
| Regression              | `sing.rolling`          | [Validation](sing.rolling.md)          |
| Trends & gaps           | `filter.hp`             | [Validation](filter.hp.md)             |
| Trends & gaps           | `filter.hamilton`       | [Validation](filter.hamilton.md)       |
| VAR & local projections | `var.ols`               | [Validation](var.ols.md)               |
| VAR & local projections | `lp.ols`                | [Validation](lp.ols.md)                |
| Identify & compare      | `ident.recursive`       | [Validation](ident.recursive.md)       |
| Identify & compare      | `ident.external_series` | [Validation](ident.external_series.md) |
| Identify & compare      | `cmp.common_shock`      | [Validation](cmp.common_shock.md)      |
| Identify & compare      | `out.hd`                | [Validation](out.hd.md)                |
| Panel models            | `panel.fe`              | [Validation](panel_fe.md)              |
| Panel models            | `panel.lp`              | [Validation](panel_lp.md)              |
| Bayesian & forecasting  | `bvar.minn`             | [Validation](bvar_minn.md)             |
| Bayesian & forecasting  | `uni.arima`             | [Validation](forecasting.md)           |
| Bayesian & forecasting  | `fc.var`                | [Validation](forecasting.md)           |
| Bayesian & forecasting  | `fc.eval`               | [Validation](forecasting.md)           |
| Long run & breaks       | `test.coint`            | [Validation](cointegration.md)         |
| Long run & breaks       | `vecm`                  | [Validation](cointegration.md)         |
| Long run & breaks       | `test.break`            | [Validation](break-tests.md)           |

The two orchestration methods, `ident.external_series` and `cmp.common_shock`,
have no independent end-to-end reference implementation in the suite. Their
cards describe component, identity, simulation and reproducibility checks.
Passing validation does not establish causal identification or guarantee nominal
interval coverage in an empirical application.
