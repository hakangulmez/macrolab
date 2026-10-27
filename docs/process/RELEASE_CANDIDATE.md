# Local release-candidate procedure

## Historical v1.1 procedure

For v1.1, `make g10-build` prepares a browser-only
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

## v2.0 / G16

`make g16-build SNAPSHOT=<id>` requires the passed immutable refresh marker and
`docs/process/G16_LICENCE_REVIEW.json` dated to that snapshot. It prepares all nine
unchanged templates, withheld narratives, the current model registry and local
validation-card pages. All runtime packages and notices come from the pinned
cache; no new runtime package is fetched.

P6 candidates are separate local repositories with no remotes. Source must be
one successor to public main `23969e8`; static files must be one successor to
public gh-pages `7db5514`. Never copy development ancestry. Inventory file sizes
and SHA-256 hashes, scan for secrets/private paths, retain the source diff, and
wait for exact-artifact approval before either ordinary fast-forward push.

## v2.1.0 / G19

`make static-build ACCEPTED_SITE=<accepted-p7-site>` builds the UI only.
The accepted P7 tree SHA-256 is
`908607a6eddbb76572b748c9c5b50a66e221d52786965263e21946ff8d7636e0`.
The build rejects another input and preserves its data, runtime, licences, schemas
and validation cards. The new presentation projection uses the same observations.
Only the approved JetBrains Mono UI font is added, with its OFL notice.
No data refresh or scientific-runtime rebuild is performed.

P8 candidates are separate local repositories without remotes: one successor to
public main `3d9970d`, and one successor to gh-pages `e1d520b`. Development history,
review screenshots and generated numerical evidence are excluded from source.
Record inventories, hashes, source diff, licence review, secret/path scan, exact
frozen results, export comparisons, both themes at 1440/375 px, and performance
against v2.0.1. Version text is the only new G19 PNG/LaTeX export difference.
Wait for written approval of the exact artifacts before pushing either public
branch or the private development backup.
