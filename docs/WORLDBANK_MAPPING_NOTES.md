# World Bank and country metadata mapping — G1

Status: local implementation and source evidence. Country narratives remain **DRAFT** for owner review. No publication or redistribution permission is implied.

## Current Pink Sheet resolution

The adapter first retrieves the [official commodity markets page](https://www.worldbank.org/en/research/commodity-markets), reads download links only, and requires exactly one distinct link whose path ends in `CMO-Historical-Data-Monthly.xlsx`. Duplicate navigation links are deduplicated. A missing, ambiguous or non-World-Bank link produces an explicit issue; there is no fallback to the stale G0 URL. Every page and workbook response is archived by `SourceClient` with its request, retrieval time and checksum. Observations are read from the XLSX, never scraped from HTML.

On the client reference date `2026-10-20`, this resolved to the [current monthly workbook](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx). Its checksum is `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`. The workbook reports an update on `2026-10-02`. All selected series run from `1960-01` through `2026-09`; the old G0 download ended in `2024-12`. These findings come from the archived discovery and adapter smoke snapshots, not the URL's document year alone.

| Concept / variant | Worksheet and observed header | Unit | Primary use |
|---|---|---|---|
| `oil_brent` | Monthly Prices / Crude oil, Brent | Nominal USD per barrel | Primary global series |
| `commod_idx`, `non_energy` | Monthly Indices / Non-energy ** | Nominal USD index, 2010=100 | Primary commodity index |
| `commod_idx`, `energy` | Monthly Indices / Energy | Nominal USD index, 2010=100 | Preserved in `variant_rows` side table |

Non-energy is the explicit initial commodity-index choice, avoiding duplication of the separately selected oil factor. Energy remains available as a distinct variant; it must not overwrite the primary key or be averaged with non-energy. The double asterisks are retained in the audit header. Unknown seasonal-adjustment metadata is `UNKNOWN`, with `seasonal_adjustment_not_reported` flagged. Units and index base headers are checked before observations are accepted. Missing cells stay missing; no interpolation occurs.

Staleness is calculated separately for every selected column: `(as_of_year - latest_year) × 12 + as_of_month - latest_month`. More than three months produces `stale_source` on its rows and a `stale_pink_sheet` warning. The verified latest period is one month behind the reference date and does not trigger that warning. Absence of a current file produces `current_pink_sheet_unavailable`. Each accepted row retains worksheet, one-based row/column, original column label and source period for independent cell readback.

The workbook also contains an ancillary “Mismatch Details” worksheet. It is not an observation source; only the named monthly sheets and verified columns are parsed.

## WDI structural profiles

The official [WDI API](https://api.worldbank.org/v2/country/DEU;TUR;EMU/indicator/SP.POP.TOTL;NY.GDP.PCAP.PP.KD;NE.TRD.GNFS.ZS;GB.XPD.RSDV.GD.ZS;SP.POP.DPND?source=2&date=1999:2026&format=json&per_page=20000) supplies annual profiles from the configured start year through the client reference year. The adapter pages explicitly and retains underlying indicator titles, update dates, provider codes and JSON pointers. `EMU` maps to the internal `EA` aggregate with a World Bank composition flag.

| Profile | WDI series | Unit / interpretation |
|---|---|---|
| Population | `SP.POP.TOTL` | Persons |
| GDP per capita PPP | `NY.GDP.PCAP.PP.KD` | Constant international dollars; base year parsed from provider title |
| Trade openness | `NE.TRD.GNFS.ZS` | Exports plus imports, % of GDP |
| R&D | `GB.XPD.RSDV.GD.ZS` | Research and development expenditure, % of GDP |
| Age dependency | `SP.POP.DPND` | Dependents relative to working-age population, % |

Profiles remain separate from model series. A fully missing country/profile pair becomes an issue; missing annual observations are not filled. The bounded Germany/Türkiye/euro-area smoke returned 399 finite profile observations, 1,602 primary commodity observations and 801 energy-variant observations, with no adapter issues. This is a smoke result, not a claim of full OECD coverage. Evidence is in ignored `runs/worldbank_adapter_smoke.json` and raw snapshot `g1-worldbank-adapter-smoke`.

## Country metadata and DRAFT notes

The roster comes from the live OECD membership adapter. Enrichment never adds countries. The [WDI rich country metadata endpoint](https://api.worldbank.org/v2/sources/2/country/USA/metadata?format=json) provides ISO2 codes, currency descriptions and World Bank region labels. OECD region grouping is retained separately; a World Bank grouping is not relabelled as OECD. Currency descriptions are not invented ISO currency codes. WDI's historical “New Turkish lira” wording is retained as provider metadata and explicitly overridden by the OECD's “Turkish lira” / TRY wording.

The [ECB country overview](https://www.ecb.europa.eu/euro/changeover/html/index.en.html) establishes current EU/euro membership. Its [EMU history](https://www.ecb.europa.eu/ecb/history-arts-culture/history/emu/html/index.en.html) supplies exact adoption dates, including Bulgaria in 2026. These dated configuration entries are intersected with the fetched OECD roster. Adoption limits the default rate-shock sample; actual model samples still depend on non-missing observations and are reported downstream. The internal `EA` ISO2-like code is explicitly marked as an aggregate identifier.

The Denmark note cites the [ECB ERM II announcement](https://www.ecb.europa.eu/press/pr/date/1998/html/pr981231_3.en.html). The Türkiye note cites [OECD Economic Surveys: Türkiye 2025, section 1.1.3](https://www.oecd.org/en/publications/oecd-economic-surveys-turkiye-2025_d01c660f-en/full-report/staying-the-course-on-macroeconomic-stabilisation_91899ae0.html). It describes a historical policy change after the May 2023 elections without inventing a daily structural-break date or automatically changing model samples. That official OECD page was readable through official web retrieval, while the direct snapshot client returned HTTP 403; the archival limitation is recorded in the configuration.

All narratives carry `DRAFT` and `review_required: true`. Source terms remain unresolved for redistribution; raw files, profiles and processed observations remain git-ignored.

## Verification

Eight offline tests pass. They cover current-link ambiguity and host rejection, missing cells, independently reread XLSX coordinates, separate variants, the exact staleness boundary, changed units, duplicate dates, null WDI values, profile provenance, runtime roster preservation, adoption sample limits and unavailable-current-file reporting. Ruff and strict mypy pass for the adapter and country metadata modules. No browser or model claims are made by these checks.
