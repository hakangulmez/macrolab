# Data rights — v1.1 technical candidate, 24 October 2026

The v1.1 candidate retains snapshot `20261023-1634` and the accepted source
policy below. Country observations, global variants, profile data, source cards
and rights metadata are byte-identical to v1.0.1. The manifest changes only
software and candidate metadata. `make static-build` prepares `runs/g10/site/`;
P5 requires approval of the exact source and site artifacts. Country narratives
and World Bank Pink Sheet remain withheld. No new runtime dependency is added.

The inactive G16 PPI proposals use the already-cleared Eurostat STS dataset;
their observations do not enter v1.1. G10 did not refresh the release data or
repeat the legal review; the accepted dated evidence follows.

## Accepted G9 source-policy review

The local v1.0 candidate uses audited snapshot `20261023-1634` (23 October 2026).
All seven current provider reuse clauses quoted below remain present on their
[official terms pages](docs/G9_LICENCE_REVIEW.json). No changed reuse clause or
new dataset restriction was found. All seven selected OECD flow versions retain
identical non-availability metadata and reuse-related text versus the P2 review;
only response headers and availability constraints changed. All five WDI indicator
pages still identify CC BY 4.0. PCPS selected-index rows still identify PUBLIC_OPEN,
the reviewed IMF licence and empty additional sharing notes. The evidence record
contains official URLs, metadata hashes and the scope of the comparison.

The current catalogue includes **33 indicators + 3 global factors**: EIA Brent,
BIS US policy and IMF PCPS non-fuel. It includes the reviewed PCPS all/energy
variants, ECB DFR/MRO and official SA euro-area HICP documented below. Attribution
uses the 23 October access date. National NSA prices retain seasonal controls;
MacroLab does not seasonally adjust observations. Country narratives and Pink
Sheet remain excluded. IMF use remains non-commercial. The G9 build and its
subsequent P4 publication were separately approved; that approval does not cover
the new v1.1 candidate.

## Historical P2 scope and continuing source conditions

**Source inclusion is authorised for the local P2 candidate; publication is not authorised.** MacroLab is a non-commercial research and teaching tool. The source policy below implements the owner’s P2 decisions of 21 October 2026. The accepted G1.1 snapshot remains `20261021-0025`, manifest SHA-256 `50919e1e009aa43704c7feb185b013e13c131f9fe5f0dcde84c6ae1a62660035`; a separately archived EIA monthly Brent overlay is the only observation change. No permission request was sent.

The classifications drive [`configs/publication_sources.json`](configs/publication_sources.json). `allowed` means **OK to redistribute processed data with attribution**, within the stated scope and conditions. IMF inclusion is specifically non-commercial. Pink Sheet remains **unclear** and excluded by the owner. No source is classified **not allowed**. All country narratives remain withheld. The source policy does not authorise any remote, push or deployment.

**Data and data-derived outputs are not covered by the MIT licence.** The MIT licence applies to MacroLab code; the source-specific attribution, reuse and redistribution terms are recorded in this `DATA.md`. Third-party software and fonts retain their own licences.

## Licence table

| Source | Classification for this snapshot | Official terms and short exact clause | Required attribution and restrictions |
|---|---|---|---|
| OECD | **OK to redistribute processed data with attribution**, seven reviewed flows only | [Terms, §3 Data](https://www.oecd.org/en/about/terms-conditions.html): “distribute, share and embed Data for any purpose” | Use the supplied citation, otherwise: `OECD (year), (dataset name),(data source) DOI or URL (accessed on (date)).` P2 checked all seven exact flow versions and found no explicit extra reuse/third-party restriction. Preserve acknowledgement downstream and identify transformations. Future flows/versions require review. |
| BIS | **OK to redistribute processed data with attribution** | [Terms of permitted use of BIS statistics](https://data.bis.org/help/legal): “The use of the statistics is unrestricted, provided that:” | Cite BIS as the statistics source; MacroLab adds dataset, series and URL, and labels calculations. No misleading endorsement. Translations must be marked unofficial. A commercial product cannot impose an additional charge for including BIS statistics. The statistics are not investment advice. |
| IMF | **OK to redistribute processed data with attribution**, non-commercial use only | [Copyright and Usage, Special Terms for Statistical Data](https://www.imf.org/en/about/copyright-and-terms): “create derivative works, publish, distribute, and use Data” | `Source: International Monetary Fund, Database Name, link`. P2 credits World Economic Outlook (WEO) or Exchange Rates (ER) explicitly, preserves accuracy and terms, and identifies transformations. Potential commercial reuse requires permission and is outside this inclusion decision. |
| ECB | **OK to redistribute processed data with attribution** | [Disclaimer & copyright](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html): “When such information is distributed or reproduced, it must appear accurately and the ECB must be cited as the source.” | Cite ECB; identify transformations, including seasonal adjustment or growth calculations. If data are included in sold documents, disclose free availability before payment and on access. Authored papers have separate permission requirements. This row covers statistics, not logos or papers. |
| Eurostat | **OK to redistribute processed data with attribution** | [Copyright notice](https://ec.europa.eu/eurostat/web/main/help/copyright-notice): “for commercial or non-commercial purposes is authorised provided the source is acknowledged.” | For customised datasets: `Source: [Eurostat dataset datacode link], [access date]`. Identify changes and include a Eurostat non-responsibility disclaimer. Third-party material and specified country/trade exceptions apply. All selected observations here cover EU members or the euro area. |
| World Bank WDI | **OK to redistribute processed data with attribution**, for the five reviewed profile indicators | [Summary Terms of Use](https://data.worldbank.org/summary-terms-of-use): “copy, distribute, adapt, display or include the data”; [WDI catalogue](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators) identifies CC BY 4.0. | Required general credit: `The World Bank: Dataset name: Data source (if known).` Follow indicator metadata; retain licence/terms links and downstream acknowledgement, identify modifications, and avoid endorsement. CC BY 4.0 includes commercial reuse; World Bank additional dispute-resolution terms also apply. Third-party exceptions must be checked per indicator. |
| World Bank Pink Sheet | **unclear — excluded by owner** | [Commodity Prices catalogue](https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections): “This dataset is licensed under Creative Commons Attribution 4.0”. [World Bank data terms](https://data.worldbank.org/summary-terms-of-use) also apply. | Third-party interests in monthly workbook columns remain unresolved. P2 ships no Pink Sheet observations; EIA replaces Brent and both energy/non-energy commodity-index variants are withheld. |
| EIA | **OK to redistribute processed data with attribution**, selected Europe Brent monthly series | [Copyrights and reuse](https://www.eia.gov/about/copyrights_reuse.php): “U.S. government publications are in the public domain” | `Source: U.S. Energy Information Administration (October 2026)`, plus Europe Brent Spot Price FOB, monthly USD/bbl, official file URL and access date. Preserve the publication date; identify transformations and avoid implied endorsement. |

## Evidence and unresolved cases

**OECD.** The owner approved inclusion after a flow-level metadata check. The [dated P2 review](docs/P2_OECD_METADATA_REVIEW.md) records live HTTP 200 responses for all seven exact selected flows, their hashes and dataset names. No explicit additional reuse or third-party restriction was found in the flow descriptions, annotations or referenced structures. All seven are included with concrete dataset citations; unmatched flows fail closed. The earlier P1 “unclear” classification is superseded for these reviewed flows only.

**BIS.** The [general website terms](https://www.bis.org/about/terms-conditions) expressly route Data Portal statistics to the statistical terms above. Consequently the broader website's non-commercial clause is not the applicable blanket restriction for these statistical series. This corrects the preliminary G0 inventory.

**IMF.** Inclusion follows the owner’s non-commercial research/teaching decision. The special statistical-data terms cover redistribution and derivative results with attribution, accuracy, transformation disclosure and downstream terms; commercial reuse is outside this decision. The retained databases are [World Economic Outlook](https://data.imf.org/en/datasets/IMF.RES:WEO) and [Exchange Rates](https://data.imf.org/en/datasets/IMF.STA:ER), with their actual database names and links in each citation. Only the accepted actual-observation panel is used; no new IMF data collection or permission request occurred.

**P1 provenance correction:** its text incorrectly described the selected IMF observations as a BIS-hosted proxy. The accepted rows and successful archived response manifests show both request and final URLs on `api.imf.org` for WEO 9.0.0 and ER 4.0.1. P2 preserves those observed official URLs; it does not alter the observations to make this correction.

**Eurostat.** The selected Eurostat rows are producer prices, government balance and government debt for EU countries/the euro area. There are no selected non-European-country observations or the detailed trade categories named in its exceptions. The candidate carries this modification notice: `Data transformations are by MacroLab; Eurostat is not responsible for these modifications or results.` Future source/country additions need another scope check.

**WDI.** Each exact indicator page below explicitly displays CC BY-4.0 beside its provider metadata; no contrary indicator-specific restriction was displayed. The build restricts WDI to these five reviewed series and preserves the providers in its profile credits. This updates the prior unresolved WDI status for processed profile data only; raw archives remain private and excluded.

| Indicator | Official indicator/licence evidence | Provider credits retained |
|---|---|---|
| Population | [SP.POP.TOTL](https://data.worldbank.org/indicator/SP.POP.TOTL) | UN Population Division, national statistical offices, Eurostat, UN Statistics Division |
| GDP per capita, PPP | [NY.GDP.PCAP.PP.KD](https://data.worldbank.org/indicator/NY.GDP.PCAP.PP.KD) | International Comparison Program, Eurostat/OECD PPP programmes, World Bank staff, OECD national accounts, IMF WEO |
| Trade openness | [NE.TRD.GNFS.ZS](https://data.worldbank.org/indicator/NE.TRD.GNFS.ZS) | National statistical organisations/central banks, OECD national accounts, World Bank staff |
| R&D / GDP | [GB.XPD.RSDV.GD.ZS](https://data.worldbank.org/indicator/GB.XPD.RSDV.GD.ZS) | UNESCO Institute for Statistics |
| Age dependency | [SP.POP.DPND](https://data.worldbank.org/indicator/SP.POP.DPND) | UN Population Division and World Bank staff |

The [CC BY 4.0 licence](https://creativecommons.org/licenses/by/4.0/) and World Bank terms links accompany retained profiles. The former generic dataset-terms URL redirects to [general website terms](https://www.worldbank.org/ext/en/legal/terms-conditions), which separately recognises dataset-specific terms. Its general-content restrictions are not substituted for the explicit WDI licence.

**Pink Sheet.** The owner chose continued exclusion. No Pink Sheet Brent or energy/non-energy commodity-index observations enter the P2 candidate. The old accepted snapshot and full local comparison remain intact solely to measure the source-swap effect.

**EIA.** P2 uses the keyless official [monthly Europe Brent spot-price workbook](https://www.eia.gov/dnav/pet/hist_xls/RBRTEm.xls), series `PET.RBRTE.M`, in USD per barrel. Its raw response is archived with URL, timestamp and SHA-256; three dates are checked against the independent official monthly history table. See [the EIA audit](docs/P2_EIA_AUDIT.md) and [source details](docs/SOURCES.md). The public-domain statement and attribution come from EIA’s own reuse page, not an inferred third-party licence. The published catalogue contains 33 national indicators and two included global factors; `commod_idx` remains visibly “not included”.

## Build and publication boundary

- The accepted P2 candidate in `runs/p2/site/` uses browser-only estimation and same-origin runtime assets. It includes the reviewed OECD flows, non-commercial IMF data, BIS, Eurostat, the five WDI profile indicators and EIA Brent. ECB is permitted but contributes no selected observations to that frozen snapshot. G5 added the reviewed data below in `runs/g5/site/`. During G6, `make static-build` uses the same accepted inputs in `runs/g6/site/`, with the new local model runtime; it does not rebuild P2 or G5.
- No Pink Sheet values, commodity-index variants or country narratives enter P2. Missing/excluded inputs carry visible notes. Other accepted values, model defaults and estimators are preserved; Brent’s source is the sole monetary-template input change.
- Attribution, dataset/series URLs, terms and transformation records travel with retained series, profiles and exports. New or ambiguous provenance fails closed. Raw workbooks, processed archives, caches and runtime binaries remain ignored.
- The P1 full-data folder remains a **local comparison only**, with uncleared Pink Sheet inputs. It is not the P2 publication candidate.
- The accepted sanitised source export has fresh history, the owner-specified identity, and no review screenshots or historical verification arrays. P2/P3.1 were subsequently published with explicit approval. The new G5 development candidate remains local and is not covered by that approval.
- FRED remains unavailable and unused. Any new remote push or deployment requires the owner’s separate approval of the exact artifact.


## G5 additions — 21 October 2026 (local review only)

The accepted P2/P3.1 licence decisions above remain in force. The v1 policy is
`configs/publication_sources_v1.json`; the frozen P2 policy is unchanged.

| Addition | Classification | Official terms / exact clause | Scope and attribution |
|---|---|---|---|
| IMF PCPS indices | **OK to redistribute processed data with attribution**, non-commercial only | [IMF statistical-data terms](https://www.imf.org/en/about/copyright-and-terms), the reuse clause quoted in the IMF row above. For material not attributed to IMF, the terms require “permission directly from the respective third-party copyright holder”. | Only PALLFNF (all), PNRG (energy), PNFUEL (non-fuel), INDEX, monthly, 2016=100. `Source: International Monetary Fund, Primary Commodity Prices, https://data.imf.org/en/datasets/IMF.RES:PCPS.` Identify transformations and communicate terms downstream. |
| ECB DFR/MRO | **OK to redistribute processed data with attribution** | [ECB disclaimer and copyright](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html), exact reuse clause in the ECB row above. | Cite ECB, dataset FM and the original daily series. MacroLab selects published calendar month-end values; no filling. MRO uses fixed/minimum-bid tender regimes in their published periods. |
| ECB official SA HICP | **OK to redistribute processed data with attribution** | Same ECB statistical-data terms. | Cite ECB, `HICP.M.U2.Y.000000.4F0.INX`, 2025=100, working-day and seasonally adjusted by ECB. MacroLab growth and frequency calculations are separately identified. No in-app seasonal adjustment. |

The [PCPS dataset page](https://data.imf.org/en/datasets/IMF.RES:PCPS) and official
SDMX flow/series metadata were checked on 21 October 2026. They distinguish
indices from individual commodity market prices. The selected index records
identify IMF as author/publisher, access PUBLIC_OPEN and an empty additional
sharing-notes field. No explicit extra restriction on these three indices was
found; individual third-party commodity price series are **not included**.
The special statistical-data terms explicitly cover Primary Commodity Prices.
This applies the accepted non-commercial decision, not a new commercial licence.

Direct IMF HTML requests returned 403; the official dataset and terms pages were
read through the browsing tool instead. The API metadata and data responses were
archived in full with hashes. No login, key or access-control bypass was used.
ECB terms were retrieved directly (HTTP 200). Source metadata, audit URLs and
hashes are recorded in [G5 source review](docs/G5_DATA_SOURCES.md) and
G5 data evidence (local review record omitted from source export).

Pink Sheet stays excluded. Existing EIA Brent and BIS US-policy-rate data remain
unchanged. All country narratives remain withheld. Nothing in G5 authorises
publication or a remote push.
