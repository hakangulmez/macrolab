# Model validation cards

## Original G2 validation record

Twelve v0 plug-ins share a pure Python input/output contract and run in the native
engine and offline browser worker. Each `<model_id>.md` records its method,
assumptions, references, maximum numerical difference, recovery evidence and limits.
Cards are rebuilt from actual reference results by `scripts/g2_validate.py`.

At G2 the release registry contained only these validated v0 models. New models require
reference, relevant recovery/identity/property tests and native/browser parity
before being added. Later-tier model identifiers are rejected by the configuration
validator and are absent from the library. A failed validation is gate-blocking.

Forecast leakage and historical decomposition reconstruction are inapplicable to
v0 because no forecast or historical decomposition model is released. Rolling
windows are tested for future leakage; filters are explicitly retrospective.
G3 owns chart, accessibility and product-screen end-to-end checks. G2 uses a real
headless Chrome worker and local API for numerical parity, including all templates.

## G6 model extensions

The engine registry adds four v1 capabilities, alongside the unchanged twelve
v0 models: [LP](lp.ols.md), [historical decomposition](out.hd.md),
[reusable shocks and joint bootstrap](ident.external_series.md), and
[common-shock comparison](cmp.common_shock.md). These cards and the G6 stop report
record their separate validation. The fixed experimental protocol is
[here](../G6_VALIDATION_PROTOCOL.md). New templates are G7; new product views are G8.

## v2.0 available methods

The v2.0 registry includes [Panel FE](panel_fe.md), [panel LP](panel_lp.md),
[BVAR](bvar_minn.md), [SARIMAX, VAR/BVAR forecasting and evaluation](forecasting.md),
[Engle–Granger, Johansen and VECM](cointegration.md), and
[structural-break diagnostics](break-tests.md). Each linked card records native
reference checks, browser/offline parity, recovery and finite-sample limits.
The three product templates are the pooled euro-area Phillips curve, pooled
responses to the same ECB shock and the EA inflation forecast horse race.
These are release-candidate capabilities awaiting exact-artifact P6 approval.
Sign restrictions, proxy SVAR/LP-IV, state dependence and TVP-VAR remain planned
for v3. Published observations are not real-time vintages.
