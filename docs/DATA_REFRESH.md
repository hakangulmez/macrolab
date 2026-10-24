# Explicit data refresh

`make refresh` fetches only reviewed source flows and writes a new immutable
UTC `YYYYMMDD-HHMM` snapshot. It performs 3-country × 3-date checks for each of
36 concepts/factors (324 checks), coverage/staleness assessment, the extra
18 v1 variant checks, EIA's independent table audit, and every configured
template on old and new inputs. No background schedule or publication is involved.

```sh
make refresh                         # explicit live network operation
make refresh DRY_RUN=1               # offline accepted P2 + audited G5 additions
make refresh SNAPSHOT=20261021-1600  # choose an unused UTC identifier
# PREVIOUS is a local static data folder containing manifest.json and countries/.
make refresh PREVIOUS=runs/g5/public/data
```

The default comparison remains frozen P2. After approving another local baseline,
pass it explicitly with PREVIOUS. A dry-run always replays P2 source observations
plus G5 additions and uses P2's as-of date; it is not a new live data vintage.
No API key, Pink Sheet fetch or FRED retry is permitted. OECD/IMF observation
URLs must match reviewed versioned source prefixes before any download. A new
flow/version requires a separate metadata/licence check. EIA and the three
IMF indices fail closed if required source/audit responses are missing. All live source failures (non-200, empty/incomplete response or provider/parser
failure) stop the refresh. Expected country coverage gaps remain explicit.
All nine default templates must complete. A changed reuse clause stops release
preparation until a new decision is recorded.

Outputs are `data/processed/snapshots/<id>/` and `docs/REFRESH_<id>.md`. Detailed
results and arrays stay in ignored `runs/refresh/<id>/comparison.json`. The report
lists every changed concept/country, added/removed dates, revisions exceeding
max(1e-8 source units, 1e-6 × absolute old value), newly stale inputs, template
sample and numerical changes. Gaps/outliers are flagged, never filled or dropped.

A failed audit/required template leaves a failed marker and diagnostics. A reused
snapshot ID is rejected. Neither a successful nor a failed refresh changes
`data/processed/current`, a frozen candidate, a remote branch or the live site.
The old raw responses, processed snapshots and P2/P3.1 comparisons remain available.
A release uses a chosen audited snapshot only at a separately approved gate.

G5 rehearses the procedure without fetching the full panel. G9 and G16 are the authorised
gates for their respective full live refreshes. The data-bearing report and review screenshots
are omitted from sanitised source exports.

## G9 refresh and recovery

The authorised live refresh is `20261023-1634`, compared with the accepted G8
static snapshot. All 59 requests succeeded. Two post-collection comparison errors
were corrected: propagating the selected snapshot ID to the ECB first stage and
supplying variant start/end metadata. No provider failed and no data was fetched
again. For a failed comparison only, the offline recovery command is:

```sh
make refresh RESUME_COMPARISON=1 SNAPSHOT=<failed-id> PREVIOUS=<baseline-folder>
```

Recovery requires passed data validation and audit, matching immutable file
hashes, and only successful, complete archived source responses. It cannot
resume a source failure or reopen a successful refresh. The G9 preparation also
requires a licence review covering the selected snapshot date.

## G16 refresh

The new immutable snapshot is `20261024-2040`. G16 enables only the three audited
Eurostat PPI replacements in the ordinary price mapping. Each full history has
an additional first/middle/latest audit against an independent country query.
The other 32 stale flags remain. The new snapshot is compared with
`runs/g15/site/data`, using all nine registered defaults and sensitivity rows.
Elapsed runtime metadata is excluded from numerical comparisons. The HP
complete-quarter endpoint and paired failed-origin rules are unchanged.

Prepare with `make g16-build SNAPSHOT=20261024-2040` only after the refresh and
dated licence review pass. `make static-build` aliases this preparation. This
build uses cached, pinned runtime assets, with no new package or automatic fetch.
