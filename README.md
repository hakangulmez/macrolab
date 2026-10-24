# MacroLab

MacroLab is a non-commercial research and teaching tool for exploring official
macro data and testing how results depend on modelling assumptions. **v1.1**
provides 33 national indicators and three global factors across 38 OECD economies
and the euro area. Six templates cover monetary policy, Taylor and Phillips
relationships, Okun's law, a common ECB shock and Türkiye exchange-rate pass-through.

The app runs entirely in the browser, including estimation in a pinned Pyodide
worker. A published build contains a fixed, audited data snapshot; visiting the
app does not fetch new observations from providers. Results record the actual
sample, transformations, dropped periods, source notes and sensitivity variants.
They are **not forecasts**. Conditional associations and recursively identified
scenarios carry their respective limitations; inference is pointwise.

v1 adds matched VAR/LP comparisons, country-response panels with shared axes,
peak intervals and the cumulative pass-through ratio. v1.1 adds historical
decomposition, optional Türkiye crisis sensitivities and per-chart PNG exports.
Country narratives remain withheld. The October 23 snapshot is unchanged.
Forecasting, BVAR, panel methods and other v2/v3 features are planned.

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
exact cached runtime files listed in `web/runtime/assets.lock.json`. Preparation
never silently downloads runtime files. Original review evidence is private and
absent from the public source export; code alone cannot recreate that evidence.

```sh
# Explicit live data operation; PREVIOUS is an existing audited static data folder:
make refresh PREVIOUS=runs/g8/public/data
# Technical v1.1: provide the accepted v1.0.1 site at runs/v101/site first.
# Preparation copies its cleared data bytes and builds only current source/UI:
make g10-build
# Serve runs/g10/site under /macrolab/ with a static server (no local API).
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
