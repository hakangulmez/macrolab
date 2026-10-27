# G1.1 price source refresh

This bounded refresh adds separate candidates for `cpi`, `cpi_core`, and `ppi`.
It does not replace the prior snapshot, splice old and new classifications,
rebase observations, interpolate missing dates, or change other concepts.
Source observations remain in ignored local data. Nothing is published.

## Production interface and source order

`fetch_prices(client, countries)` in `src/macrolab/data/sources/g11_prices.py`
returns `rows`, `issues`, `requests`, and `source_details`. It accepts the shared
`SourceClient`/`SnapshotClient`; replay uses the same three request identifiers:
`g11_cpi2018_metadata`, `g11_cpi2018_data`, and `g11_ppi_domestic`.
The harmoniser retains responsibility for whole-series selection and fallback
logging. The adapter emits no IMF candidates and makes no IMF requests.

`configs/g11_prices.yaml` contains the exact official URLs and selectors, with
no raw observation values. The existing OECD PPI candidates remain available
through the original adapter, with their actual stale end dates. Eurostat PPI is
limited to runtime EU members plus `EA`, even though the response also contains
some non-EU countries. No non-EU PPI gap is filled by this increment.

## OECD CPI and core CPI

The verified current flow is
`OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0`.
Its [official metadata](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.TPS/DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL/1.0?references=all)
resolves the actual identifying dimensions and expenditure labels. At each run,
the parser checks their order and the selected labels before accepting values.

Headline selects `_T`. National core selects `_TXCP01_NRG`, excluding food and
energy. EU/EA core selects HICP `_TXNRG_01_02`, which additionally excludes
alcohol and tobacco; this definition difference is explicitly flagged. National
CPI is never substituted for required EU/EA HICP. The `EA` requirement survives
missing or false `eu_member` enrichment metadata.

All observations carry `classification_COICOP2018`; HICP observations also carry
`HICP`. SA and NSA, monthly and quarterly frequencies, and different aggregate
compositions remain separate series. The preferred native frequency is monthly.
The original index base and multiplier are retained; blank OECD multipliers carry
`unit_multiplier_not_reported` rather than being silently asserted as reported.

The current dataset resolves the main stale national CPI histories:

| Country | Latest headline/core month | Available monthly history in this response |
|---|---|---|
| Japan | 2026-08 | 1998-01 onward |
| Mexico | 2026-09 | 1998-01 onward |
| Chile | 2026-09 | Headline 1998-01; core 1998-12 onward |
| Costa Rica | 2026-09 | 1998-01 onward |
| Euro area | 2026-09 | 1998-01 onward, with actual source composition retained |

The query begins in 1998 for the requested 1999 Q1 analysis start and later
transformations. Actual sample boundaries remain a result-level responsibility.
Missing additional candidates for countries still served by the prior COICOP1999
flow are recorded as increment-level missingness, not as a claim that all existing
coverage is missing.

## OECD PPI discovery: bounded negative result

Two current official checks on 20 October 2026 establish why the discovered
industry dataset cannot replace the stale OECD KEI manufacturing PPI:

1. The [current STES agency flow inventory](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/all/latest?references=none)
   lists nine flows: KEI, BTS, CLI, CS, CSBAR, FINMARK, INDSERV, MONAGG, and STES
   revisions. It exposes no dedicated current producer-price flow.
2. The discovered [INDSERV 4.3 structure and constraints](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/DSD_STES@DF_INDSERV/4.3?references=all)
   describe production, sales, work started, and orders. Its actual measure
   constraint contains `TOCAPA`, `NODW`, `WSDW`, `TOVM`, and `PRVM`; its allowed
   constraint adds `SERVPRD` and `SL`. Neither permits producer-price measure `PP`.

The inventory SHA-256 is
`2c0117cdfd36607fa39413c2af0a3867926abf908d2bfb59b29bb50a4554096c`.
The INDSERV metadata SHA-256 is
`8bb82b9ebe76ee491c51360d4b01273f2a327fb8d7037d2f842ae2054ab67704`.
Both responses are archived under discovery snapshot
`g11-price-discovery-20261020-221928`. These are bounded findings for the
verified inventory and dataset; they are not proof that no possible future or
other OECD flow exists. No guessed industry dataset identifier is used.

The previously verified KEI `PP` history mostly ends in December 2022, with a few
series ending in late 2022 or early 2023. Those actual end dates remain visible.

A separate check of the [all-agency flow inventory](https://sdmx.oecd.org/public/rest/v1/dataflow/all/all/latest?references=none)
covered 1,550 flows. No title identified a producer-price dataset and no flow ID
contained PPI. Relevant descriptions pointed to KEI; regional ROPI references
concerned GDP/GVA deflation. This strengthens the bounded negative finding,
without asserting that OECD ceased PPI publication. The response was retrieved
at 2026-10-20 21:32:58 UTC; SHA-256
`0d9b5a8c9fd1b4158daeb093656d85c444f7fbb014bcee3721ea91ba5ad5f377`.

## Eurostat EU PPI fallback

[Eurostat `sts_inppd_m`](https://ec.europa.eu/eurostat/databrowser/view/sts_inppd_m/default/table?lang=en)
provides monthly manufacturing producer prices for the domestic market:
`indic_bt=PRC_PRR_DOM`, `nace_r2=C`, `s_adj=NSA`, and `unit=I21` (2021=100).
The parser requires those exact response dimensions before assigning metadata.
Domestic-market scope and unadjusted status are explicit in the definition and
flags. The latest official aggregate is `EA21`; older compositions are not merged
into it.

The retained response supplies 23 eligible runtime units: AUT, BEL, CZE, DEU,
DNK, EA, ESP, EST, FIN, FRA, GRC, HUN, IRL, ITA, LTU, LUX, LVA, NLD, POL, PRT,
SVK, SVN, and SWE. CZE, DNK, and LTU reach September 2026; the other 20 units
reach August 2026. Some histories begin after 1999; the actual first month is
retained and should produce the existing shorter-history warning where applicable.

## Verification and limits

The final scoped adapter was replayed without network access from discovery
snapshot `g11-price-discovery-20261020-221721`. Its three production requests had
HTTP 200 complete payloads. It returned **31,627 candidates**: 12,451 OECD
headline CPI, 11,789 OECD core CPI, and 7,387 Eurostat PPI observations. There were
no standardisation errors. These are candidate counts, including distinct
frequencies and adjustments, not selected-series coverage counts.

A separate raw-payload reader matched **42 of 42** beginning/middle/latest checks
across OECD CPI/core and Eurostat PPI for DEU, EA, JPN, MEX, CHL, and CRI where
those source/concept pairs exist. The ignored evidence files are
`runs/g11_price_adapter_readback.json` and `runs/g11_price_audit.json`.
Seven offline tests verify definition boundaries, unchanged values and full audit
selectors, mislabelled Eurostat responses, exclusion of non-EU PPI, and rejection
of incomplete responses even when HTTP status is 200. Ruff and strict mypy pass.

Some non-EU producer-price histories therefore remain stale or missing. Exploratory
IMF PPI responses remain only in ignored discovery archives and are excluded from
this production implementation. The root pipeline must still verify the combined
selected panel and its final snapshot before accepting G1.1.
