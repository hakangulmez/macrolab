# MacroLab

Explore, model and stress-test macroeconomic relationships across countries.
MacroLab provides 33 national indicators, two included P2 global factors, twelve v0 methods,
four template configurations, visible data checks, sensitivity comparisons and
reproducible exports. Models include single-equation regressions, VARs, recursive
identification, filters, stationarity tests and descriptive comparisons.
The commodity index remains visibly excluded; Brent uses EIA and the US policy
factor uses BIS.

This is a **source-only local export** with a new Git history. It contains no
full input datasets, review screenshots, generated result arrays, compiled site,
runtime binaries, dependency cache or country narratives. Synthetic test fixtures
and three public-domain EIA audit observations remain documented. No push,
deployment or publication is performed by this export.

## Install and check

Use an existing Python 3.11 and a Node version satisfying `web/package.json`, plus
`uv` on PATH. Dependencies are pinned by `uv.lock` and `web/package-lock.json`.

```sh
make setup
make quick
make test lint typecheck
# Compile the interface source; this does not prepare a data-bearing site:
cd web && npm run build
```

Setup retrieves dependencies from PyPI/npm; Python auto-downloads and npm lifecycle
scripts are disabled. `make quick` uses seeded synthetic data without network.
Tests use local fixtures/mocks; checks that require an accepted private snapshot
are skipped when it is absent. No data is fetched by these checking commands.

## Data and a runnable local site

Real-data operation additionally needs an independently obtained, verified snapshot
and the exact scientific runtime assets listed in `web/runtime/assets.lock.json`.
Those assets and full input datasets are deliberately absent here. Review [data terms and
publication policy](DATA.md) before preparing any data-bearing artifact. Source
retrieval is an explicit operation; `make data` fetches from the configured official
providers. Local preparation commands do not silently retrieve missing runtime files.

The original gate-specific seeding/report commands refer to private review evidence
that this source export omits. They are retained as development utilities, not as a
claim that the original local review can be reconstructed from code alone. Public
country metadata retains adoption/currency/source fields while narrative notes are
empty; candidate preparation also withholds generated narratives.

## Documentation

- [Model methods](docs/models/README.md)
- [Source mappings and transformations](docs/SOURCES.md)
- [Data attribution and redistribution policy](DATA.md)
- [Software notices](docs/P1_SOFTWARE_NOTICES.md)
- [Pinned runtime notices and source availability](third_party/runtime/SOURCE_AVAILABILITY.md)
- [Explicit export omissions and modifications](EXPORT_SCOPE.md)

## Licence

MacroLab's original code is licensed under the [MIT License](LICENSE).
**Data and data-derived outputs are not covered by the MIT licence**; see
[DATA.md](DATA.md) for source-specific terms, attribution and restrictions.
Third-party software, fonts and runtime components retain their own licences
and notices. A shared configuration does not grant data reuse rights.
