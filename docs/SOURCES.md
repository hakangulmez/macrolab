# G0 official-source probe evidence

Evidence set: `probe-20261020-211231-420155`. Retrieval times are UTC.
Combined G0 evidence: original probes plus bounded Eurostat follow-up; each fetch retains its own snapshot ID.

These are bounded access and parsing probes, not validated G1 concept mappings. A successful status requires finite observations and source response metadata; HTTP success alone is insufficient. Candidate IDs remain unverified where the probe failed.

Raw response bodies and observation values are stored only in ignored `data/` and `runs/`. The tracked `docs/probe_evidence.json` contains metadata, checksums and counts without observation values.

| Provider / probe | Status | Parsed observations | Details |
|---|---|---:|---|
| OECD / `oecd_finmark` | verified_observations | 875 | Response parsed; concept mapping deferred to G1. |
| BIS / `bis_policy` | verified_observations | 3 | Response parsed; concept mapping deferred to G1. |
| IMF / `imf_cpi` | verified_observations | 168 | Response parsed; concept mapping deferred to G1. |
| ECB / `ecb_exchange` | verified_observations | 3 | Response parsed; concept mapping deferred to G1. |
| Eurostat / `eurostat_unemployment` | verified_observations | 9 | Response parsed; concept mapping deferred to G1. |
| WorldBank / `worldbank_wdi` | verified_observations | 2 | Response parsed; concept mapping deferred to G1. |
| WorldBank / `worldbank_pink` | verified_observations | 780 | Response parsed; concept mapping deferred to G1. |
| FRED / `fred_csv` | unavailable | — | TimeoutError: The read operation timed out |

## OECD — oecd_finmark

- Base URL: `https://sdmx.oecd.org/`
- Example query: <https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,/.?lastNObservations=1>
- Final URL: https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,/.?lastNObservations=1
- Dataset candidate: `OECD.SDD.STES,DSD_STES@DF_FINMARK`
- Series candidate: `latest observations (metadata-discovery probe)`
- Retrieval: `2026-10-20T21:09:03.914233+00:00`; HTTP: `200`; MIME: `text/csv; charset=utf-8`.
- SHA-256: `84844b65741ac18f6478c3c163620fbb9e4410d0d8daba7a2bb6f9b987960278`; complete body: `True`.
- Observed period range: `2006` to `2026-Q3`.

## BIS — bis_policy

- Base URL: `https://stats.bis.org/`
- Example query: <https://stats.bis.org/api/v1/data/WS_CBPOL/M.US?startPeriod=2024-01&endPeriod=2024-03>
- Final URL: https://stats.bis.org/api/v1/data/WS_CBPOL/M.US?startPeriod=2024-01&endPeriod=2024-03
- Dataset candidate: `WS_CBPOL`
- Series candidate: `M.US`
- Retrieval: `2026-10-20T21:09:06.045933+00:00`; HTTP: `200`; MIME: `text/csv;charset=UTF-8`.
- SHA-256: `e7692697015194ed8da2bf365ad39550bc5b398d96018cbcb22e4e92ce489c7d`; complete body: `True`.
- Observed period range: `2024-01` to `2024-03`.

## IMF — imf_cpi

- Base URL: `https://api.imf.org/`
- Example query: <https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI,5.0.0/USA...?startPeriod=2024-01&endPeriod=2024-03>
- Final URL: https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI,5.0.0/USA...?startPeriod=2024-01&endPeriod=2024-03
- Dataset candidate: `IMF.STA,CPI,5.0.0`
- Series candidate: `USA... (unverified discovery candidate)`
- Retrieval: `2026-10-20T21:09:07.193015+00:00`; HTTP: `200`; MIME: `text/csv`.
- SHA-256: `a579be4c47b5826d7691a2cd42ff5f4601dfc2f159f5dc2fb39b0f533e8f8e32`; complete body: `True`.
- Observed period range: `2024-M01` to `2024-Q1`.

## ECB — ecb_exchange

- Base URL: `https://data-api.ecb.europa.eu/`
- Example query: <https://data-api.ecb.europa.eu/service/data/EXR/M.USD.EUR.SP00.A?startPeriod=2024-01&endPeriod=2024-03&format=csvdata>
- Final URL: https://data-api.ecb.europa.eu/service/data/EXR/M.USD.EUR.SP00.A?startPeriod=2024-01&endPeriod=2024-03&format=csvdata
- Dataset candidate: `EXR`
- Series candidate: `M.USD.EUR.SP00.A`
- Retrieval: `2026-10-20T21:09:10.309464+00:00`; HTTP: `200`; MIME: `text/csv`.
- SHA-256: `6ca199a1728f7fba60327d21d8d6f068d52c3ea615deec4569fb08e520385278`; complete body: `True`.
- Observed period range: `2024-01` to `2024-03`.

## Eurostat — eurostat_unemployment

- Base URL: `https://ec.europa.eu/`
- Example query: <https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?lang=EN&geo=DE&sex=T&unit=PC_ACT&s_adj=SA&sinceTimePeriod=2024-01&untilTimePeriod=2024-03>
- Final URL: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?lang=EN&geo=DE&sex=T&unit=PC_ACT&s_adj=SA&sinceTimePeriod=2024-01&untilTimePeriod=2024-03
- Dataset candidate: `une_rt_m`
- Series candidate: `DE;T;all returned age categories;PC_ACT;SA`
- Retrieval: `2026-10-20T21:12:31.420534+00:00`; HTTP: `200`; MIME: `application/json`.
- SHA-256: `2e58fc942f72cb91f892f7b428cfc8d5e196f0d3aa31482aa63a95c999a81a90`; complete body: `True`.
- Observed period range: `2024-01` to `2024-03`.

## WorldBank — worldbank_wdi

- Base URL: `https://api.worldbank.org/`
- Example query: <https://api.worldbank.org/v2/country/USA/indicator/SP.POP.TOTL?date=2023:2024&format=json>
- Final URL: https://api.worldbank.org/v2/country/USA/indicator/SP.POP.TOTL?date=2023:2024&format=json
- Dataset candidate: `WDI`
- Series candidate: `USA/SP.POP.TOTL`
- Retrieval: `2026-10-20T21:09:14.115978+00:00`; HTTP: `200`; MIME: `application/json;charset=utf-8`.
- SHA-256: `65adecf14390294e1eb4d81160d8eb39732fb7a5906c61cd64ac08e9c08ba05a`; complete body: `True`.
- Observed period range: `2023` to `2024`.

## WorldBank — worldbank_pink

- Base URL: `https://thedocs.worldbank.org/`
- Example query: <https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx>
- Final URL: https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx
- Dataset candidate: `Pink Sheet monthly historical workbook`
- Series candidate: `Crude oil, Brent`
- Retrieval: `2026-10-20T21:09:15.510269+00:00`; HTTP: `200`; MIME: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- SHA-256: `bd89b83eeceadaecb803018c104f76b316d2df3fae28ef7afde48021100c7e11`; complete body: `True`.
- Observed period range: `1960M01` to `2024M12`.

## FRED — fred_csv

- Base URL: `https://fred.stlouisfed.org/`
- Example query: <https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS&cosd=2024-01-01&coed=2024-03-31>
- Final URL: No response
- Dataset candidate: `fredgraph CSV`
- Series candidate: `FEDFUNDS (access diagnostic only; not adopted)`
- Retrieval: `2026-10-20T21:09:38.115900+00:00`; HTTP: `None`; MIME: `None`.
- SHA-256: `None`; complete body: `False`.

## Operational boundary

The stdlib client disables environment proxies and supplies no cookies, authentication, API keys or credentials. HTTPS hosts and every redirect are checked against an explicit allowlist. Requests use a project-named User-Agent, bounded timeout, one retry for transient errors, a response-size cap, and a pause between probes. Truncated responses are not retained as complete snapshots.

Use `python -m macrolab.data.sources.probe` from this repository after setup. Use `--skip-terms` for data-only diagnostics. The command is explicitly live-network; `make quick` and `make test` do not call it. Probe snapshots are diagnostic runs with unique IDs, not complete G1 data snapshots. Previous raw files are never overwritten.

FRED is an access diagnostic only. FEDFUNDS is not adopted as a data mapping: the original publisher/source priority and series-specific rights still govern G1.

Licence review is in `DATA.md`. Availability, licensing and suitability are separate checks.

## G1 current-source addendum — 20 October 2026

The G0 observations above remain historical feasibility evidence. In particular,
the G0 Pink Sheet download is not the current G1 data URL. Full-snapshot coverage,
selected fallbacks and independent audit results are reported separately at the
G1 gate; the bounded readbacks below do not establish that gate's acceptance.

### Pink Sheet current-link resolution and freshness

The G1 adapter retrieves the [official Commodity Markets page](https://www.worldbank.org/en/research/commodity-markets)
and resolves its actual monthly historical XLSX download link. It examines links
only, not HTML observations. The resolver requires one distinct official World
Bank link ending in `CMO-Historical-Data-Monthly.xlsx`; repeated navigation links
are deduplicated. Missing or ambiguous links and failed downloads produce an
explicit issue. The obsolete G0 URL is never used as a silent fallback.

The discovery and bounded adapter readback resolved the
[current monthly workbook](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx).
Its SHA-256 is
`ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`.
The workbook reports an update on `2026-10-02`; Brent, energy and non-energy
monthly observations each end in `2026-09`. Freshness is therefore established
from parsed observation periods against the client reference date `2026-10-20`,
not inferred from the download path or HTTP status. The G0 URL's last period was
`2024-12`.

More than three elapsed calendar months after a selected column's latest period
triggers `stale_source` and `stale_pink_sheet`. The latter is a visible warning;
it does not alter or interpolate observations. If no current file is reachable,
`current_pink_sheet_unavailable` records the limitation and no old file is
silently substituted. Country series cards retain freshness warnings. Energy
and non-energy indices stay separate: `commod_idx` initially selects non-energy,
while energy is preserved as a named variant.

The ignored raw snapshots `g1-worldbank-discovery` and
`g1-worldbank-adapter-smoke` retain the page and workbook responses, timestamps,
URLs and checksums. Per-row provenance retains worksheet, original header,
source period and one-based cell coordinates. Detailed mapping and offline-test
evidence is in [World Bank mapping notes](WORLDBANK_MAPPING_NOTES.md).

### G1 mapping and definition references

- [OECD mapping notes](OECD_MAPPING_NOTES.md) document live membership discovery,
  exact versioned SDMX dimensions, concept selectors, units, adjustments, source
  definitions and explicit older euro-area compositions. The mapping
  configuration is [OECD mappings](../configs/oecd_mappings.yaml).
- [Supplementary mapping notes](SUPPLEMENTAL_MAPPING_NOTES.md) document BIS,
  ECB, Eurostat and IMF datasets and verified definitions. This includes BIS
  policy-rate end-of-period observations, actual-only IMF fiscal data, the
  current HICP table and aggregate-composition caveats. Exact queries/selectors
  are in [supplementary mappings](../configs/supplemental_mappings.yaml).
- [World Bank mapping notes](WORLDBANK_MAPPING_NOTES.md) document current Pink
  Sheet resolution, WDI structural profiles, official country/currency metadata,
  ECB adoption dates and the source limits of DRAFT country notes.

FRED remains unavailable and is disabled in the G1 collection and replay path;
no repeated FRED request is part of `make quick`. BIS supplies
`us_policy_rate`. IMF and World Bank data retain the exact operational rights
status **unresolved – no redistribution of raw data**. That status permits the
authorised local G1 work to continue, without establishing publication rights.
See [DATA.md](../DATA.md) for the retained G0 legal evidence and G1 handling rules.

## G1.1 bounded corrections

The [price source review](G1_1_PRICE_SOURCES.md) verifies current OECD COICOP2018
CPI/core and Eurostat domestic manufacturing PPI for EU members and EA. It also
records the bounded negative search for a replacement OECD PPI flow. The
[CLI review](G1_1_CLI_SOURCES.md) verifies the current 4.1 flow, all available
geographies and its stated G20-plus-Spain coverage. Five official responses
support this correction; original G1 responses remain referenced through the
accepted parent snapshot. IMF was not needed for CPI/core. M3, Türkiye's short
rate, FRED and the Pink Sheet resolver are unchanged.

## P2 publication candidate — 21 October 2026

The earlier sections record their respective historical gates. Current
candidate-specific rights decisions are in [DATA.md](../DATA.md), including the
seven exact OECD dataflow versions, non-commercial IMF use, and the continued
Pink Sheet exclusion. Those decisions do not rewrite the accepted G1.1 data or
the frozen P1 full-data comparison.

P2 replaces `oil_brent` only with the keyless official EIA monthly Europe Brent
spot-price workbook. The [EIA audit](P2_EIA_AUDIT.md) records both official
formats, raw checksums, 473 exact workbook/table matches and three cell-level
spot checks. Source values remain nominal USD per barrel at monthly frequency;
frequency conversion and log transformations occur only in the requested
analysis. The browser carries no XLS parser or live data API requirement.

The independent P2 snapshot records its accepted parent and EIA input digest.
It retains 33 national concepts and two included global factors: EIA Brent and
the existing BIS US policy rate. Broad commodity-index observations and their
variant are excluded; their catalogue metadata explains the absence. Country
narratives remain withheld. All non-Brent series values, other than the
explicitly removed commodity index, and all reviewed WDI profile values are
checked against the frozen P1 full-data input.
