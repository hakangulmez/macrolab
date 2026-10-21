# Supplementary source mappings and evidence

These adapters consume the runtime OECD-country metadata. They do not define membership, change euro-adoption dates, splice policy regimes, interpolate values, or apply model transformations. The main pipeline owns harmonisation and source priority.

## Verification

The scoped pilot used USA, DEU, FRA, ITA and the EA aggregate. Its immutable raw responses are in ignored `data/raw/<source>/g1-supplemental-discovery-pilot-20261020-214128/`; parsed diagnostic files are in ignored `runs/g1-supplemental-discovery-pilot-20261020-214128/`. The raw manifest preserves exact URLs, hashes, timestamps, response MIME types and statuses.

| Source | Parsed observations | Issues | Concepts |
|---|---:|---:|---|
| BIS | 10103 | 0 | credit_pnfs: 1164, house_real: 1188, neer: 1960, policy_rate: 2964, reer: 1960, us_policy_rate: 867 |
| ECB | 560 | 0 | money_broad: 560 |
| Eurostat | 9108 | 9 | cons_gov: 576, cons_priv: 576, cpi: 1706, cpi_core: 1382, exports_real: 576, gdp_real: 576, gfcf: 576, gov_balance: 122, gov_debt: 123, imports_real: 576, unemp: 2319 |
| IMF | 2721 | 3 | fx_usd: 2433, gov_balance: 144, gov_debt: 144 |

The issues are explicit source-coverage omissions, not failed HTTP requests. Pilot counts are feasibility evidence and are not the full-country G1 coverage totals.

## BIS

Policy rates use the source monthly end-of-period observations. They are not monthly averages, and the ingestion step does not reconstruct them from daily data. National pre-euro series and the XM euro-area series are returned separately for the pipeline adoption splice. The US common factor is an exact copy of the BIS US policy series with country `GLOBAL`.

Private non-financial credit uses all lenders, market valuation, percentage-of-GDP units and the break-adjusted series. Property prices select the real level index with unit code `628`; the separately published year-on-year growth series (`771`) is excluded. Broad real and nominal EERs use unit code `882`, the source index based on 2020. Structure-specific XML group attributes are joined to matching series so the unit is not lost.

BIS response payloads do not explicitly state seasonal adjustment for these series. They retain `sa_flag=UNKNOWN` and `seasonal_adjustment_unknown`; no false SA claim is introduced. Source series titles, compilation notes and original unit codes remain in metadata.

## IMF

The migrated API exposes WEO flow `IMF.RES,WEO,9.0.0`. General-government gross debt and net lending/borrowing use the source percentage-of-GDP series. Their original annual observations are retained only through each series' `LATEST_ACTUAL_ANNUAL_DATA`. Later WEO estimates/projections are excluded, and a missing actual boundary omits the series with an explicit issue. Source national fiscal-definition differences remain visible.

The FX fallback uses `IMF.STA,ER,4.0.1`, national-currency units per US dollar, period-average monthly rates. The source monthly date spelling is retained in the audit record while the tidy date is normalised. No reciprocal exchange rate or euro-adoption conversion is silently applied. IMF legal terms remain unverified; working access is not publication permission.

## Eurostat

The official compact catalogue identifies `prc_hicp_minr` as the current ECOICOP2 HICP table. The former `prc_hicp_midx` table is explicitly historical and stops at 2025. Current mappings use `coicop18=TOTAL` and `TOT_X_NRG_FOOD`, with `unit=I25`. The core series excludes energy, food, alcohol and tobacco; that definition is stated in flags. Indices remain NSA levels, with transformations deferred to analysis.

Quarterly national-account fallbacks select chain-linked volume amounts in millions of 2010 euros, seasonally and calendar adjusted. Components are household/NPISH consumption, government consumption, gross fixed capital formation, exports and imports. Chain-linked components are not additive. Fiscal fallbacks use annual EDP general-government consolidated gross debt and net lending/borrowing, each as a percentage of GDP. No quarterly-to-annual conversion is invented.

JSON-stat sparse observations are decoded using the declared dimension order and sizes. Each row retains its raw flat index and source dimension selectors, so an independent audit can read the exact official observation. Missing array entries remain missing. Euro-area variants are never silently combined: the adapter selects an available aggregate, records its source geography and flags any composition mismatch.

## ECB and remaining boundaries

ECB M3 supplies the euro-area broad-money aggregate, working-day and seasonally adjusted, as an end-of-period stock in millions of euros. The changing-composition source is labelled explicitly and is not assigned to individual member countries. BIS already supplies the aggregate policy rate, so no alternative ECB instrument is substituted.

No FRED calls, external instruments, model estimates, synthetic replacements, API keys or paid services are used. Missing source-country series remain coverage gaps. All numerical data and raw legal pages stay ignored; `configs/supplemental_mappings.yaml` contains mapping metadata only.
