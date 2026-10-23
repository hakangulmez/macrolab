# cmp.common_shock — descriptive national responses (G6)

Estimate one first-stage shock, then reuse it in separate LPs for every selected
country and response. Each country retains its valid observed sample. The default
start is max(1999 Q1, euro adoption), with a partial adoption quarter excluded.
Every response has its actual sample and n per horizon; multi-response results
retain separate payloads and sample records. Missing/stale inputs obey the existing
blocking/warning rules. No panel pooling or silent imputation occurs.

The summary reports the signed largest-absolute response, its horizon, pointwise
interval, whether the interval excludes zero, and n. Selected-peak comparisons
and cross-country differences are **descriptive**. Overlapping intervals do not
support a ranking. No cross-country equality test is implemented or claimed.

A method-comparison helper returns each horizon's sign agreement and band overlap,
plus peaks. Same-estimand comparisons require matching samples, horizons and shock
normalisation. A national recursive VAR row must be labelled **different method
and different identification** and excluded from same-estimand agreement counts.

Progress events are emitted per country/response and bootstrap draw. Native calls
can cancel cooperatively; the browser terminates its worker and never presents a
partial result as complete. Bootstrap assumptions and common-window requirements
are documented in [ident.external_series](ident.external_series.md).

Validation: one-country comparison is exactly the direct LP result; separate
multi-response results; euro-adoption dates; blocked shock alignment; progress
and cancellation; native/browser comparisons with four synthetic countries;
standalone Python reproduction of both stages. Real ECB/Türkiye templates and
all required economic sensitivity rows belong to G7. New visual views belong to
G8; this card does not claim those later gates are complete.

## G8 country view

For each response, all selected countries share the same numeric axis range and
rounded ticks. The ranking uses signed largest-absolute peaks and each country's
pointwise interval at that peak. The displayed warning is “overlapping intervals
do not support a ranking”; selecting different peak horizons prevents treating
this as a same-horizon equality test. Each response retains its own country sample
table. At 375 px a selector displays one country alongside the complete ranking.
PNG panels retain all countries and responses with shared per-response scales.
