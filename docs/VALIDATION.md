# How methods are validated

Validation checks whether a calculation implements its stated method. It does
not establish that a model is true, that identification is credible, or that an
interval has nominal coverage in every dataset. [Methods](METHODS.md) explains
the assumptions. The table below covers all **25 released methods**.

## Numerical cross-checks

We compare coefficients, standard errors, responses or test statistics with
statsmodels, linearmodels (native tests only), and separately written formulas.
The usual absolute tolerance is **1e−8**; the weak-prior BVAR-to-OLS limit uses
**1e−6**, and the published Andrews critical-value check allows **1%** relative
error. Cards specify the outputs and exceptions. Agreement with a library that
also supplies the estimator tests integration; it is not independent evidence
that the library itself is correct. Algebraic identities provide additional checks.

| Method                  | Checked against                                                     | Validation card                         |
| ----------------------- | ------------------------------------------------------------------- | --------------------------------------- |
| `desc.plot`             | pandas values and dates                                             | [Card](models/desc.plot.md)             |
| `desc.corr`             | NumPy / pandas correlations                                         | [Card](models/desc.corr.md)             |
| `desc.compare`          | pandas country means                                                | [Card](models/desc.compare.md)          |
| `test.adf_kpss_pp`      | statsmodels ADF/KPSS; ARCH PP                                       | [Card](models/test.adf_kpss_pp.md)      |
| `test.granger`          | statsmodels F statistic / p-value                                   | [Card](models/test.granger.md)          |
| `sing.ols`              | statsmodels OLS; Longley fixture                                    | [Card](models/sing.ols.md)              |
| `sing.ardl`             | statsmodels ARDL / UECM                                             | [Card](models/sing.ardl.md)             |
| `sing.rolling`          | statsmodels RollingOLS / window OLS                                 | [Card](models/sing.rolling.md)          |
| `filter.hp`             | statsmodels HP trend and cycle                                      | [Card](models/filter.hp.md)             |
| `filter.hamilton`       | Independent projection / QuantEcon                                  | [Card](models/filter.hamilton.md)       |
| `var.ols`               | statsmodels VAR, IRF and FEVD                                       | [Card](models/var.ols.md)               |
| `lp.ols`                | Independent statsmodels OLS/HAC/HC1                                 | [Card](models/lp.ols.md)                |
| `ident.recursive`       | statsmodels orthogonal IRF / FEVD                                   | [Card](models/ident.recursive.md)       |
| `ident.external_series` | No end-to-end reference; residual identities / two-stage simulation | [Card](models/ident.external_series.md) |
| `cmp.common_shock`      | No end-to-end reference; direct-LP identity / alignment checks      | [Card](models/cmp.common_shock.md)      |
| `out.hd`                | Hand-computed VAR / reconstruction identity                         | [Card](models/out.hd.md)                |
| `panel.fe`              | linearmodels PanelOLS coefficients / covariances                    | [Card](models/panel_fe.md)              |
| `panel.lp`              | PanelOLS per horizon; N=1 LP identity                               | [Card](models/panel_lp.md)              |
| `bvar.minn`             | Independent posterior moments / OLS limit                           | [Card](models/bvar_minn.md)             |
| `uni.arima`             | Native SARIMAX; closed-form AR(1)                                   | [Card](models/forecasting.md)           |
| `fc.var`                | Native VAR forecasts / predictive-path identities                   | [Card](models/forecasting.md)           |
| `fc.eval`               | Independent DM/HLN / post-origin perturbation                       | [Card](models/forecasting.md)           |
| `test.coint`            | Native statsmodels coint / Johansen                                 | [Card](models/cointegration.md)         |
| `vecm`                  | Native VECM / VAR-conversion identity                               | [Card](models/cointegration.md)         |
| `test.break`            | Andrews table / Hansen calibration / RecursiveLS                    | [Card](models/break-tests.md)           |

**No independent end-to-end cross-check:** `ident.external_series` and
`cmp.common_shock` combine tested components in MacroLab-specific workflows;
there is no separate implementation of those complete workflows in the suite.
Residual/shock reconstruction, direct-LP equivalence, calendar alignment,
simulation and reproducibility tests cover their contracts. They should not be
read as two additional independently benchmarked estimators.

## Simulation recovery and coverage

The [fixed protocol](process/G6_VALIDATION_PROTOCOL.md) uses **200 replications**
at each of **T=120 and 240**, horizons 0–12 and fixed seeds. LP recovery uses a
known two-variable VAR(2) and its observed structural shock. Two-stage recovery
estimates the first-stage VAR shock and feeds a national AR(2) outcome with
independent noise; joint inference uses **200 bootstrap draws** per replication
and refits both stages. Bias must satisfy **|mean bias| ≤ max(0.10, 3 Monte Carlo
standard errors)**. Coverage below **75%** at any horizon triggers investigation;
that diagnostic floor is not a claim of correctly calibrated 90% bands.

For the original HAC LP, observed 90% coverage spans **80.5–89.5%** across sample
sizes/horizons. Joint two-stage bands span **84.5–92.5%**, versus **79.5–90.5%**
for conditional bands. Lag-augmented HC1 reduced mean absolute coverage error
in this design (2.00/1.62 percentage points at T=120/240); this motivated the v1
template choice, not a universal guarantee. Other cards report method-specific
recovery, including the unreliable finite-sample ECB break-test calibration.

## Regression and export safeguards

**160,958 frozen numerical fields** are compared exactly within each runtime,
using their original snapshots: 4,042 v0 fields on `20261021-p2-eia-021530`;
the remaining accepted v1/v2 fields on `20261023-1634`. Browser/native comparisons
use absolute **1e−8**, including documented seeded simulations; seeds and draw
counts are fixed. Execution timing and previously approved version/copy changes
are explicitly separated. These are regression tests, not independent validation.

CSV and standalone Python exports are checked byte-for-byte; Python replays run
without networking. PNG pixels and LaTeX scientific content are compared, with
build-version text isolated. JSON comparisons exclude recorded execution timing.
Forecast tests perturb observations after each origin: earlier predictions must
stay unchanged. Current-data template checks supplement the frozen fixtures;
passing them does not remove revision, sample, identification or coverage limits.
