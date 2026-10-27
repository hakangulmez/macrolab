# Local build and reproduction

The published application is a static site. Analyses run in the browser; no analysis server or data-provider request is needed.

## Source checks

Use Python 3.11, a supported Node version (`web/package.json`), and `uv` on PATH. Run `make setup`, `make quick`, `make test typecheck` and `make lint`. Dependencies are pinned. No API key is required. The two preserved UI-preparation helpers currently carry formatting/lint debt; this does not change runtime calculations.

## Reproduce a result

Download **Python script** from the result's export controls. Follow its embedded environment instructions. The script includes the configuration, necessary observations and provenance; once the stated packages are installed, calculation can run without networking. Data terms in [DATA.md](../DATA.md) still apply to embedded observations and derived outputs.

## Build a runnable static copy

`npm run build` in `web/` compiles the interface only. A runnable static copy also needs the audited data snapshot, schemas, validation cards and pinned scientific runtime. These binaries and data are intentionally absent from the source repository.

The presentation builder accepts the previously published v2.0.1 static archive as read-only input. It verifies the archive's SHA-256 inventory, preserves its data/runtime bytes and prepares the current interface. Supply that archive yourself; this command does not fetch it:

```sh
make static-build ACCEPTED_SITE=relative/path/to/published-v2.0.1-site
```

The builder reports its output directory. Serve it under `/macrolab/` using a static HTTP server. Opening the HTML as a `file:` URL is insufficient for the worker and data fetches. The published v2.1.0 payload is also available on the repository's `gh-pages` branch.

A new data refresh is separate from the presentation build. See [refresh instructions](DATA_REFRESH.md) and the [release procedure](process/RELEASE_CANDIDATE.md). Refreshing locally does not alter the published site or previous snapshots; failures or changed licence clauses require review.
