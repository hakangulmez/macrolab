# Local release-candidate procedure

For v1.1, `make static-build` (or `make g10-build`) prepares a browser-only
candidate under `runs/g10/site/`, with the `/macrolab/` base path. It requires the
accepted v1.0.1 site at `runs/v101/site/`. It copies the cleared October 23 data
and pinned runtime dependencies, and rebuilds MacroLab's own runtime and UI.
Only software/candidate fields change in the data manifest. The build performs
no source download, API request, refresh or deployment. G9 licence evidence and
the accepted source policy still apply. Review evidence is not public source.

Country narratives are withheld from both static data and sanitised source.
Only the reviewed OECD flows, BIS, non-commercial IMF indices/statistics, ECB,
selected Eurostat/WDI data and EIA are eligible. Pink Sheet and unreviewed data
fail closed. Source cards and exports retain attribution and modifications.

Before publication, verify all six templates in the browser, offline Python
exports, desktop/mobile accessibility and zero external requests. Compare the
same snapshot with v1.0.1 while retaining exact v0 regression on its original
P2/EIA inputs. A data refresh is deferred to G16. The release-version change is recorded separately from
numerical comparison. Record every candidate file's size and SHA-256.

A sanitised update must descend from the accepted public `main` commit, never
from private development history. Exclude private data, generated result reports,
review screenshots, caches and environments. Use the public author identity.
Prepare the site branch from only candidate files plus `.nojekyll`, preserving
public branch history. Local preparation is not approval to push or deploy.

P5 requires separate approval of the exact source commit, site commit and file
inventory. Never force-push. No country narrative can be published without its
own text approval. Archived old snapshots and public release artifacts are not
overwritten by this procedure.

`python scripts/g10_export.py` creates the local source/site commits only after
the development changes are committed. It validates the pinned public parents,
refuses existing output folders, removes local-clone remotes and records exact
readback inventories plus `runs/g10/source.patch`. Its parents are public main
`d5ce053` and gh-pages `fc5a603`. It performs no network calls. The older G9
procedure remains in `scripts/g9_prepare.py` and `scripts/g9_export.py` for
historical reproducibility; it must not overwrite accepted artifacts.
