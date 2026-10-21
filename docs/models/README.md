# G2 model validation cards

Twelve v0 plug-ins share a pure Python input/output contract and run in the native
engine and offline browser worker. Each `<model_id>.md` records its method,
assumptions, references, maximum numerical difference, recovery evidence and limits.
Cards are rebuilt from actual reference results by `scripts/g2_validate.py`.

The release registry contains only these validated v0 models. New models require
reference, relevant recovery/identity/property tests and native/browser parity
before being added. Later-tier model identifiers are rejected by the configuration
validator and are absent from the library. A failed validation is gate-blocking.

Forecast leakage and historical decomposition reconstruction are inapplicable to
v0 because no forecast or historical decomposition model is released. Rolling
windows are tested for future leakage; filters are explicitly retrospective.
G3 owns chart, accessibility and product-screen end-to-end checks. G2 uses a real
headless Chrome worker and local API for numerical parity, including all templates.
