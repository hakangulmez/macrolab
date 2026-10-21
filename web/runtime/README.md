# Local browser runtime validation

MacroLab uses a real Google Chrome Web Worker running Pyodide WebAssembly. The worker imports
the same portable Python analysis, checks and model sources used by the local FastAPI
service. It does not simulate Python in JavaScript. G2 introduced the validation
harness; G3 uses the same worker through the lazy frontend transport.

`assets.lock.json` pins the official npm Pyodide 314.0.7 runtime and its nine scientific
dependency artifacts. The user approved one download of those exact nine CDN files,
subject to a 100 MiB total limit. Their SHA-256 digests come from the official runtime
lock. All nine were verified before use and occupy 30,299,063 bytes; the five runtime
files occupy another 13,531,207 bytes. Binary files remain in the ignored local cache.
Ordinary build and test commands never download runtime files.

From the project directory:

```sh
make runtime-build
make runtime-check
```

The build verifies cached artifacts and creates a deterministic `py3-none-any` model
wheel under `runs/g2`. This wheel includes only `analysis`, `checks`, `models`, `export`
and the package version file. The existing data-ingestion package remains a native
Python installation. The tested native and browser dependency versions are recorded
separately: they are not assumed identical.

The check generates a portable JSON fixture for all twelve v0 models, an additional
seeded VAR bootstrap case, and the four canonical templates using the accepted local
data snapshot. It compares each browser result with `POST /run` on a loopback FastAPI
server, including coefficients, standard errors, intervals, diagnostics, checks,
sensitivity results and actual samples. Only measured `runtime_ms` fields are ignored.
Numeric comparison uses absolute tolerance `1e-8`; structure and text must agree.
The compatibility endpoint is also compared.

The harness uses the installed Chrome executable, an ephemeral `127.0.0.1` port and
project-local temporary files. Browser request routing and the worker's fetch guard
reject nonlocal origins. The browser and server are terminated on completion or failure.
No browser binary is downloaded. Cancelling a worker terminates it; no unfinished result
is returned. The `/run`, `/compatibility` and `/export/python` production API routes can
also be started independently with `make serve`, which binds only to `127.0.0.1`.

Evidence is written to ignored local outputs:

- `runs/g2/runtime_assets.json`: URLs, versions, byte counts and verified checksums.
- `runs/g2/runtime_wheel.json`: exact Python source hashes and portable wheel hash.
- `runs/g2/browser_fixture.json`: complete configurations and unchanged input bundles.
- `runs/g2/runtime_parity.json`: real-browser identity, versions, differences per case,
  actual samples, observed network requests and success/failure.
- `runs/g2/export_parity.json`: API and standalone Python reproduction differences.

Standalone exports embed configuration, selected observations and exact Python source;
they need no repository and download nothing. They record dependency versions, source
and input hashes, snapshot, code version and actual samples, then enforce these on
execution. Reproduction tests launch isolated Python processes, assert that imports
come from the embedded source and forbid network connections. Generated exports stay
local: producing an export does not approve publication or raw-data redistribution.

## G3 static preparation and frontend verification

`python scripts/g3_prepare.py` verifies the accepted snapshot and cached runtime,
then prepares ignored `web/public` files: a compact manifest, independently hashed
country bundles, schemas, templates and the local runtime. Country observations load
only when needed. No data service, CDN or external request is required by the browser.

With the caller-owned Vite preview running locally, use
`G3_BASE_URL=http://127.0.0.1:5173/ node scripts/g3_runtime_smoke.mjs`.
The check exercises the actual typed frontend transport: all four template results,
configuration encode/decode, browser-generated Python downloads, cancellation and a
fresh worker after cancellation. It executes each downloaded script outside the
checkout import path with networking forbidden and compares the complete result.
Evidence and the exact downloaded files are kept under `runs/g3/runtime`.

Browser downloads target the native dependency versions recorded by the preparation
step; metadata separately records the Python and dependency versions that generated
the download. This makes the supported reproduction environment explicit despite
the current native/Pyodide version differences. Dates, counts and source/configuration
hashes must agree exactly. Floating transformation metadata and result comparisons
use absolute tolerance `1e-8`, including HP trends that can differ by rounding across
runtimes. The exported script embeds all inputs and sources and downloads nothing.
