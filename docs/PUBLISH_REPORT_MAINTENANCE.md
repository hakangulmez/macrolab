# MacroLab v2.8.0-beta.2 — final maintenance package

18 November 2026. **Feature development is frozen; maintenance fixes only.** This package adds presentation, warnings, a real demo and an approved one-page case study. It preserves the previously published beta search engine, the econometric methods and the numerical snapshot. The failed general correction is excluded.

## Live destinations

- [MacroLab](https://hakangulmez.github.io/macrolab/)
- [Screen recording and transcript](https://hakangulmez.github.io/macrolab/demo/)
- [One-page Spain–Germany case study](https://hakangulmez.github.io/macrolab/case-study/)
- [Publication record, all three measurements and limitations](https://hakangulmez.github.io/macrolab/publication/)

The definition at the start of the site and README is: **“Resmî makro veriyle, doğrulanmış ekonometrik yöntemleri tarayıcıda çalıştıran açık kaynak araç.”** Report search is under **Deneysel / Experimental**. Its visible warning is **“Beta; yanlış öncüllü sorularda güvenilir değil.”** The same substantive limitations are in the README, the live report-search screen and the publication page.

## All three preserved measurements

| Local research-candidate measurement | Complete positive references | Safe negative abstentions | Complete comparisons | Unrejected false premises |
| ------------------------------------ | ---------------------------: | ------------------------: | -------------------: | ------------------------: |
| First 20 — initial measurement       |                         7/14 |                       5/6 |                  0/3 |                         1 |
| Same 20 — observed **retest**        |                        13/14 |                       6/6 |                  3/3 |                         0 |
| New 25 — first final measurement     |                        10/17 |                       4/8 |                  2/5 |                         4 |

**None of these rows measures the currently deployed public search binary.** The first 20 also used a different local candidate. The retest improved on observed development data; it is not fresh independent validation. The new 25 failed the ≥85% positive-reference and zero-false-premise-error gate. The correction was not deployed. No further correction round is planned. Source references were selected and audited by AI, not independently human-validated. [Immutable measurement hashes and implementation provenance](MAINTENANCE_EVALUATIONS.json).

## Demo and case-study scope

The actual browser recording is **106.16 seconds**, with English captions and a transcript. It opens the existing Same ECB shock template, chooses the common country window, runs the existing method and shows Spain/Germany GDP responses with their 68% pointwise conditional bands. No calculated values or charts were fabricated, and no new estimator was added.

Hakan reviewed the one-page case study and explicitly approved publication. Its shock is generated internally from the existing recursive EA VAR(2), ordered GDP → prices → unemployment → policy rate. It is not an external high-frequency surprise series. One positive identified SD implies a DFR impact of 0.19658045296347496 percentage points. Both countries use 92 LP origins, 2000 Q3–2023 Q2. At four quarters the responses are Germany −0.174% [−0.445%, +0.097%] and Spain −0.101% [−0.492%, +0.290%]; these intervals contain zero. The existing template has no Spain-minus-Germany interval or equality test. The case does not claim a statistically significant country difference. Its final paragraph states sample, identification, single-shock-measure and uncertainty limitations. Machine-readable estimates and the exact existing-template configuration accompany the page.

## Release-specific verification

| Check                                                              | Observed result                                                                                                |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Public-baseline release web suite                                  | 284/284 pass                                                                                                   |
| Private maintenance checkout web suite                             | 305/305 pass; includes unpublished research-candidate tests                                                    |
| TypeScript and production build                                    | Pass                                                                                                           |
| ESLint and formatting                                              | Pass                                                                                                           |
| Presentation browser audit                                         | 20 views: 1440/375 px, light/dark; no horizontal overflow or serious/critical axe findings                     |
| Real ECB analysis, previous public baseline vs maintenance package | Exact complete result except elapsed runtime fields                                                            |
| Existing share compatibility                                       | 13 exact configuration decodes; also one fresh full fixture analysis; not 13 numerical replays                 |
| Existing public report-search smoke parity                         | Exact status, primary, comparison and related quotations for the same question                                 |
| Preserved protected source files                                   | 231 byte-exact; package metadata changes only version and presentation-copy build step; dependencies unchanged |
| Preserved published payloads                                       | 117 byte-exact, including 19 report shards and the compiled live search worker                                 |
| Expensive numerical regression                                     | Earlier 160,958-field evidence retained with source/payload hash proof; **not rerun**                          |
| Demo                                                               | Real WebM, 106.16 seconds; playback, seeking, captions and source links checked                                |
| Clean rebuild                                                      | Must match the complete reviewed site artifact before the authorized push                                      |

The frozen question sets and earlier results were not edited or rerun as a new semantic test. This is a maintenance presentation release, not a claim that the failed correction has become reliable.

## Preserved attempts and browser-media handling

Two early automation attempts used an unsuitable field locator and were preserved. An initial recording encountered a missing caption asset in the unfinished preview; that attempt was preserved, the caption was added, and a clean recording completed with zero request/page errors. A new mobile table needed keyboard access to its horizontal scrolling region; it was corrected before release and the full 20-view audit passed.

The local preview server needed standard byte-range support for video seeking. Browsers intentionally cancel and replace media transfers when loading metadata or seeking; those `ERR_ABORTED` media transfers are logged separately and accepted only with successful playback/seeking and no video error. They are not discarded or reported as successful data requests. Application HTTP/request errors, external requests and page errors were zero in the final presentation audit. The initial over-broad page-definition assertion and premature media-seek assertions are preserved with the test corrections.

## Publication and preservation boundaries

Public source parent: `a6f5a90305e3abf757cb0025214889a83a4d3cfb`; Pages parent: `82a144fce00b7580f62926cdec7a9d38df847fc7`. The failed private correction remains private. Public ancestry, the existing AskReportPassages component, search/date/support/worker code, corpus, timeline, scientific code, template defaults, runtime 2.0.0 and snapshot 20261024-2040 are preserved. The only package-manifest differences are the UI version and a deterministic copy of presentation assets after the normal build.

Candidates must have exact parents, a clean reproducible site and fast-forward remote heads before publication. The source and Pages refs are pushed atomically, without force, tags or releases. The private backup remains private. Portfolio, `.DS_Store`, original reports, the swap file, embeddings and research archives are untouched. Deployment readback and final commit identifiers are recorded in the private maintenance release evidence and reported to Hakan after Pages succeeds.

From this point: maintenance only when something breaks.
