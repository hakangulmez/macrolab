# P2 OECD flow metadata review

**Result: all seven selected flows are OK to redistribute processed data with attribution under the owner-approved P2 criterion. No flow with an explicit additional reuse or third-party restriction was found.**

On 21 October 2026, each exact selected flow version was fetched from the official OECD SDMX dataflow endpoint with `references=all`. All seven returned HTTP 200. The review read the English/French flow descriptions, annotations and referenced structures, and checked all keyword hits for ownership, licensing, copyright, redistribution, permission and reuse. Matches were economic classification labels, not restrictions. No reference metadata set or rights-specific attribute was supplied in these responses.

This follows the owner’s explicit instruction to include a selected flow when no explicit restriction is found in its official metadata. It supersedes P1’s more conservative missing-owner-register criterion. It is not a claim that OECD owns every underlying input. New dataflows or versions require another check; they do not inherit this decision.

| Exact selected flow | Dataset name | Explicit restriction / extra reuse note | Decision |
|---|---|---|---|
| [`OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_INDICES,1.1`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.NAD/DSD_NAMAIN1@DF_QNA_EXPENDITURE_INDICES/1.1?references=all) | Quarterly GDP and components - expenditure approach -  volume and price indices | None found | Include with OECD attribution |
| [`OECD.SDD.STES,DSD_KEI@DF_KEI,4.0`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/DSD_KEI@DF_KEI/4.0?references=all) | Key short-term economic indicators | None found | Include with OECD attribution |
| [`OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.TPS/DSD_PRICES@DF_PRICES_ALL/1.0?references=all) | Consumer price indices (CPIs, HICPs), COICOP 1999 | None found | Include with OECD attribution |
| [`OECD.SDD.TPS,DSD_LFS@DF_IALFS_LF_WAP_Q,1.0`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.TPS/DSD_LFS@DF_IALFS_LF_WAP_Q/1.0?references=all) | Labour force participation rate | None found | Include with OECD attribution |
| [`OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/DSD_STES@DF_FINMARK/4.0?references=all) | Financial market | None found | Include with OECD attribution |
| [`OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.TPS/DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL/1.0?references=all) | Consumer price indices (CPIs,HICPs), COICOP 2018 | None found | Include with OECD attribution |
| [`OECD.SDD.STES,DSD_STES@DF_CLI,4.1`](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/DSD_STES@DF_CLI/4.1?references=all) | Composite leading indicators | None found | Include with OECD attribution |

The supplied flow metadata contains no specific dataset citation. Each retained series therefore receives the Terms’ fallback citation with its dataset name, OECD Data Explorer, exact flow URL, citation year 2026 and the original data-access date, 20 October 2026. The metadata-check date is recorded separately. Transformations and downstream acknowledgement obligations remain visible.

Linked metadata references are methodological guides, release calendars, classification-migration links or general OECD directorate pages; no separate restricted-use notice is identified in the selected flow metadata. The `NonProductionDataflow` display annotation is not treated as a copyright restriction.

**Explicitly restricted flows: none.** Exact request/final URLs, timestamps, byte counts, hashes, flow names and citations are in [P2_OECD_METADATA_REVIEW.json](P2_OECD_METADATA_REVIEW.json). Unmodified XML and keyword review evidence remain ignored under `runs/p2/oecd-metadata/` and `runs/p2/oecd-metadata-live.json`; no source observations were refreshed.

Applicable general terms: [OECD Terms and Conditions, section 3](https://www.oecd.org/en/about/terms-conditions.html). Publication, hosting and remote creation remain unapproved.
