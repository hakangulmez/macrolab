# P2 static candidate: local review

MacroLab is a non-commercial research and teaching tool. P2 remains a local,
unapproved candidate. These steps do not create a remote, publish a repository,
upload files or deploy a site.

## Prepare and open

Use the existing locked Python and Node environments, accepted parent snapshot,
verified local runtime assets, and the separately recorded EIA monthly Brent
input. Candidate preparation reads those local inputs; it does not fetch data.

From the project root:

```sh
make p2-build
.venv/bin/python scripts/p1_serve.py --candidate p2 --port 5176 --base-path /macrolab/
```

Open **http://127.0.0.1:5176/macrolab/**. Stop the foreground server with Ctrl-C.
The output is `runs/p2/site/`; this is the only static-site folder. Do not serve
the project root or copy raw data, caches, historical run archives or the full
Git repository. A separate sanitised source export has its own review process.

The server serves files only. Models, uncertainty, sensitivity, sharing and
exports run in the browser worker. There is no estimation API, CDN fallback or
external runtime request. The build and server must use the same base path. For
another local project path, set `P1_BASE_PATH` when building and pass the same
path to the server; the variable name is retained for compatibility with P1.

## Included data and visible exclusions

The candidate records its own snapshot identity and its accepted parent. The
four template defaults retain their countries, transformations and model
settings; only their snapshot reference changes.

The reviewed source policy admits the explicitly checked OECD flows and IMF
data under the recorded non-commercial conditions. Source cards preserve the
dataset citations, original source links and reuse restrictions. The existing
BIS, ECB, Eurostat and reviewed World Bank WDI profile permissions remain
source-specific.

EIA monthly Brent replaces the excluded Pink Sheet Brent observations in this
candidate. The broad commodity index is **not included**: its catalogue metadata
explains the exclusion, but its observations are absent and it cannot be added
in the Builder. The interface therefore reports **33 indicators + 2 included
global factors**. Country narratives remain withheld pending review.

The full source decisions and evidence are in [DATA.md](../../DATA.md). P1 remains
historical evidence; its full-data comparison is local-only and must not be
confused with P2.

## Browser verification

With the local server running:

```sh
P2_BASE_URL=http://127.0.0.1:5176/macrolab/ node web/scripts/p2-static-e2e.mjs
```

The harness uses installed Chrome through the loopback-only wrapper. It blocks
API calls, external requests and paths outside `/macrolab/`, runs the four actual
template defaults, checks their charts and sensitivity, downloads their PNG,
CSV and Python exports, and reproduces their estimates through static share
links. It also checks attribution, exclusions, withheld narratives, and all six
screens at desktop and 375 px.

In CSV exports, `config_hash` identifies the overall analysis. Each
`sensitivity_variant` row also carries `variant_config_hash`, which identifies
that row's own configuration; it can differ from the baseline analysis hash.

Evidence is saved only under ignored `runs/p2/`: `e2e.json`, template browser
results, `downloads/`, and `screenshots/`. These data-bearing review artifacts
must not enter the sanitised source export. The browser report records actual
samples, checks, requests, accessibility findings and screenshot hashes. Refer
to the final P2 stop report for the observed result of the run.
