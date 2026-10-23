# Local release-candidate procedure

`make static-build SNAPSHOT=<id>` prepares a browser-only candidate under
`runs/g9/site/`, with the `/macrolab/` base path. It requires a passed refresh
marker, verified processed files, reviewed source policy and cached scientific
runtime assets. The build performs no source download, API request or deployment.
The local G9 licence evidence must be reviewed for the selected vintage.

Country narratives are withheld from both static data and sanitised source.
Only the reviewed OECD flows, BIS, non-commercial IMF indices/statistics, ECB,
selected Eurostat/WDI data and EIA are eligible. Pink Sheet and unreviewed data
fail closed. Source cards and exports retain attribution and modifications.

Before publication, verify all six templates in the browser, offline Python
exports, desktop/mobile accessibility and zero external requests. Compare the
new snapshot with the accepted one while retaining exact v0 regression on the
old inputs. The permitted release-version change is recorded separately from
numerical comparison. Record every candidate file's size and SHA-256.

A sanitised update must descend from the accepted public `main` commit, never
from private development history. Exclude private data, generated result reports,
review screenshots, caches and environments. Use the public author identity.
Prepare the site branch from only candidate files plus `.nojekyll`, preserving
public branch history. Local preparation is not approval to push or deploy.

P4 requires separate approval of the exact source commit, site commit and file
inventory. Never force-push. No country narrative can be published without its
own text approval. Archived old snapshots and public release artifacts are not
overwritten by this procedure.

`python scripts/g9_export.py` creates the local source/site commits only after
the development changes are committed. It validates the pinned public parents,
refuses existing output folders, removes local-clone remotes and records exact
readback inventories plus `runs/g9/source.patch`. It performs no network calls.
