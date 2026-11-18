# Ask the reports — v2.8.0 beta

An extractive source search, not a generative chatbot. BM25 runs in a browser worker over checksum-verified static files. No account, embedding service, paid model or analysis server is required. Questions and searches stay in the browser.

## Output and boundaries

Every result is an original quotation with official link, country, institution, prominent meeting date and separate publication date. Unsupported premises return **Not found in these reports**; nearby material is labelled **Related, but not an answer**. Missing evidence does not prove an event did not occur.

First, last, highest, lowest and count questions return chronological source lists without a verdict. A selected archive is not a complete decision history. Relative references use the reviewed corpus cutoff, not the browser clock. The June2014 negative-deposit-rate passage now appears in external Q2's list. Its old direct-answer verifier still rejects it: that verifier was not relaxed. Chronological-list scoring was explicitly authorized by the user.

## Coverage

- 801 unchanged timeline notes across 39 economies, with 809 quotation records.
- 483 date-verified Fed documents: 150 statements, 142 minutes, 143 Beige Books and 48 SLOOS reports. 8,581 passages after 83 fragments were quarantined.
- 9,390 records in 19 gzip shards,3,072,104 compressed bytes. Selected coverage: 2009–2026, reviewed through 17 November 2026.
- International material consists of existing short extracts, not full OECD reports. Raw archives, embeddings and model weights are not redistributed. Fed press conferences and unverified-publication documents are excluded.
- Release dates are publisher-recorded;471 of 483 Fed reports lack independent historical-vintage verification. This is not a vintage-safe forecasting dataset.

See [data terms](../DATA.md), [timeline provenance](ECONOMIC_TIMELINE.md) and [source audit](../web/evaluation/report-source-audit.json).

## Beta gate measured 18 November 2026

| Set | Complete expected evidence under requested format | Negative abstentions | Period errors | False-premise errors |
| --- | ---: | ---: | ---: | ---: |
| Observed development | 39/40 | 22/22 | 0 | 0 |
| Previously held out, now regression | 12/14 (85.71%) | 6/6 | 0 | 0 |
| Claude-selected, Hakan-reviewed external set, now retested | 7/7 | 3/3 | 0 | 0 |

External total: 10/10, including Q2's chronological-list acceptance. The other six positive questions retain exact-ID top-five scoring. Earlier failed results remain preserved. These are observed regression tests after targeted fixes, not a new blind test. Internal source references were selected by Codex; this is not independent human validation.

Three positive misses remain: C01 lacks one strict gold reference despite a relevant alternate; FH03's risk-only quote does not pass its decision guard; FH11's purchase wording does not pass its decision guard. Those guards were not loosened to improve the score.

All 92 questions were checked cold and warm in normal Chrome: zero failed requests/page errors, period errors, false-premise answers and quote/metadata integrity failures. Cold maximum 309.2ms; warm maximum 80.8ms. Navigation is excluded; cold queries include worker startup, shard loading, checksums, decompression, indexing and rendering. These are loopback timings, not public-network guarantees. 284 web tests, TypeScript, ESLint and formatting pass. 24 layout/theme states show zero overflow or serious/critical accessibility findings.

The former three request failures affected a font, favicon and numerical-data manifest before submit, not the report index. Controlled unchanged-site tests reproduced 262 resets with the local server's queue 5, versus zero in matched queue 128 rounds. The verified queue 128 server also passed 12 standalone navigations / 240 exact-body requests. Original server logs were absent: this establishes a reproducible mechanism, not proof of the exact historical trigger. No application retry or timeout was changed to hide failures.

## Reproduce

From `web`, run `npm ci`, `npm test`, `npm run typecheck` and `npm run lint`. With supported Node:

```sh
node --experimental-strip-types scripts/evaluate-report-search.mjs evaluation/ask-reports-beta.gold.json /tmp/macrolab-beta-evaluation all
```

Use a fresh output directory. The [question set](../web/evaluation/ask-reports-beta.gold.json) retains exact source references. The [per-question results](../web/evaluation/ask-reports-beta.results.json) distinguish comparison lists from primary top-five evidence. Original r5/r6 files remain unchanged. Reconstructing shards requires the raw archive, which is not redistributed; running search does not.

The optional model adapter is development-only and disabled in the published build. It can select only a fixed navigation sentence, never an economic explanation. Scientific calculations, runtime/data and model defaults are unchanged. Prior 160,958-field numerical evidence is retained with hashes, not rerun for this source-search release.
