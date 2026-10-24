# MacroLab

MacroLab is a non-commercial research and teaching tool for exploring official
macro data and testing how results depend on modelling assumptions. The **v2.0
release candidate** provides 33 national indicators and three global factors
across 38 OECD economies and the euro area, with nine templates.

Estimation runs entirely in the browser in a pinned Pyodide worker. A published
build bundles a fixed, audited snapshot; browsing never fetches new observations
from providers. Every result records its actual sample, transformations, dropped
periods, source notes and sensitivity. Country narratives remain withheld.

The six established templates cover monetary policy, Taylor and Phillips
relationships, Okun's law, a common ECB shock and Türkiye exchange-rate
pass-through. v2.0 adds a pooled euro-area Phillips curve, pooled responses to
the same ECB shock, and an EA inflation forecast horse race. Panel FE and LP,
Minnesota BVAR, SARIMAX, VAR/BVAR forecasts, expanding-window evaluation,
cointegration, VECM and structural-break diagnostics have linked validation cards.
Historical decomposition and optional crisis analysis remain available.

Only forecasting outputs are forecasts. Other outputs are conditional
associations or identified scenarios, not forecasts. Evaluation uses final-vintage
data and is pseudo-out-of-sample; real-time performance may be worse. Two-sided
HP gaps use later observations. Pooled shock bands omit first-stage uncertainty;
ECB break-test size remains unreliable. Sensitivities are descriptive and do not
remove identification or model uncertainty. Further v3 methods remain planned.

The local candidate requires separate approval of its exact source and site
artifacts at P6. No preparation command publishes or deploys the application.

## Install and check

Use Python 3.11, a Node version satisfying `web/package.json`, and `uv` on PATH.
Dependencies are pinned in `uv.lock` and `web/package-lock.json`.

```sh
make setup
make quick
make test lint typecheck
# Compile the interface source without preparing data or runtime assets:
cd web && npm run build
```

Setup retrieves dependencies from PyPI/npm. Automatic Python downloads and npm
lifecycle scripts are disabled. `make quick` uses seeded synthetic data without
network. Tests use fixtures/mocks; private-snapshot checks skip when inputs are
absent. No raw data, generated results, environments or scientific runtime
binaries are included in the public source repository.

## Data and a runnable static site

Sources are OECD, BIS, IMF WEO/ER/PCPS, ECB, Eurostat, World Bank WDI and EIA.
Global factors are EIA Brent, BIS US policy and the IMF non-fuel commodity index;
all/energy commodity variants are also available. Pink Sheet remains excluded.
Country narratives are withheld. Data rights and attribution are in [DATA.md](DATA.md).

Preparing a full local app additionally requires an audited snapshot and the
exact cached runtime files listed in `web/runtime/assets.lock.json`, their pinned
notices, and the accepted native reference-validation summary at
`runs/g4/model-validation.json`. Preparation
never silently downloads runtime files. Original review evidence is private and
absent from the public source export; code alone cannot recreate that evidence.

```sh
# Explicit live data operation; PREVIOUS is an existing audited static data folder:
make refresh PREVIOUS=runs/g15/site/data
# Use a passed refresh plus its completed dated licence review:
make g16-build SNAPSHOT=<audited-snapshot-id>
# Serve runs/g16/site under /macrolab/ with a static server (no local API).
```

Follow [refresh instructions](docs/DATA_REFRESH.md) and the
[release-candidate procedure](docs/RELEASE_CANDIDATE.md). A refresh never changes
the published site or the accepted old snapshot. Source failures and changed
licence clauses stop the release. No push or deployment is part of these commands.

The first browser run prepares the cached scientific runtime, taking about 8–9 s
on the review machine. ECB baseline results appear before background sensitivity;
joint uncertainty is available on demand. Finite-sample coverage limits,
identification caveats and data warnings remain visible.

## Documentation and licences

- [Model methods](docs/models/README.md)
- [Source mappings](docs/SOURCES.md)
- [Data rights and attribution](DATA.md)
- [Software notices](docs/P1_SOFTWARE_NOTICES.md)
- [Pinned runtime notices](third_party/runtime/SOURCE_AVAILABILITY.md)
- [Changelog](CHANGELOG.md)

MacroLab code is MIT licensed. **Data and data-derived outputs are not covered by
the MIT licence; see [DATA.md](DATA.md).** Third-party software and fonts retain
their own terms. A shared configuration is not a data licence or publication approval.
