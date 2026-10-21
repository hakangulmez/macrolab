# OECD mapping notes — G1

Mapping metadata was verified against official OECD SDMX responses on 20 October 2026.
`configs/oecd_mappings.yaml` records exact dataflow versions, dimension order,
selectors, English codelist labels and metadata checksums. No observation values
are stored in that configuration or this note.

## Membership and country metadata

`fetch_countries(client)` reads the latest [OECD CL_AREA codelist](https://sdmx.oecd.org/public/rest/v1/codelist/OECD/CL_AREA/latest?references=none).
It parses the `OECD00` evolving-composition group's `COMP_RULE` annotation. It
never treats every geographic code in the codelist as an OECD member and never
uses a hard-coded country list. Missing composition metadata is an error.
The retained response currently has codelist version `1.12`. OECD regional groups
come from the `OECDA`, `OECDE`, and `OECDSO` composition annotations.

The euro-area unit has ISO-like project code `EA`, with its current composition
code and member list preserved separately. The latest returned numbered
composition is `EA21`. Several OECD datasets still publish `EA20` or `EA19`.
Those observations retain their actual `source_geo`, different series IDs and
`aggregate_composition_differs_from_current_euro_area` flags. They are candidates,
not silently interchangeable current-euro-area observations.

National currencies are unresolved in this codelist except where current euro
membership establishes EUR. The country-enrichment layer must supply other
currency metadata from official evidence.

## Concept decisions

- National accounts use quarterly calendar- and seasonally-adjusted indices:
  `LR` is chain-linked volume (rebased), `DR` is a rebased deflator. The original
  `REF_YEAR_PRICE` is retained. Private consumption includes households and NPISH
  (`S1M`); government consumption uses `S13`.
- Industrial production uses ISIC B–E; retail trade uses G47. PPI uses
  manufacturing, ISIC C. These sector definitions remain visible.
- Quarterly employment is in persons with the reported multiplier. Labour-force
  participation uses both sexes aged 15–64 and percentage of the same working-age
  subgroup. The `age_15_64` flag is retained.
- Broad money is the source's M3 index. Country-specific aggregate definitions
  require attention; national euro-area member values are not replaced by the
  euro-area aggregate.
- Headline and core CPI require HICP for current EU members and EA; otherwise
  national CPI is used. OECD's index dataset currently has headline HICP but no
  food-and-energy-excluded HICP index. EU core coverage therefore requires the
  separately implemented Eurostat source. National CPI is not silently used to
  fill that gap. Verified HICP rows carry `methodology=HICP` and the `HICP` flag.
- Harmonised amplitude-adjusted OECD confidence indices are preferred to the
  older percentage-balance candidates. Both their units and source identities
  are kept. The leading-indicator dataset currently publishes CLI only for a
  subset of OECD members; this is a documented coverage gap.
- Official source quarterly series remain quarterly where monthly series do not
  exist. Such candidates carry `native_frequency_differs_from_catalogue` and a
  lower selection preference. No quarterly-to-monthly disaggregation occurs.
- SA and NSA are different whole-series candidates. The adapter never splices
  them by date. `Y`/`S` map to SA, `N`/`W` to NSA; source `AA` remains NA with an
  amplitude-adjustment flag, rather than claiming a separate seasonal adjustment.

The [OECD short-rate definition](https://www.oecd.org/en/data/indicators/short-term-interest-rates.html)
uses three-month money-market rates where available and can include treasury-bill
instruments. `IR3TIB` must therefore not be described as a universally verified
interbank rate: every candidate carries an instrument-comparability caveat. The
[OECD long-rate definition](https://www.oecd.org/en/data/indicators/long-term-interest-rates.html)
explicitly refers to ten-year government bonds. The short-rate page returned
HTTP 403 to the source client but its official page was readable through the web
reader; the long-rate page was also archived by the client. These pages supply
method definitions only; observations come from SDMX.

## Audit and missingness

Values remain source numeric values, with `unit_mult` retained separately. Blank
multipliers, present in the CPI index response, are represented as zero without
rescaling and explicitly flagged `unit_multiplier_not_reported`; the original
empty field is retained as `source_unit_mult`.

Every row includes `raw_path`, the exact source URL and a deterministic series ID.
Its `audit` object records `parser=csv`, `time_column=TIME_PERIOD`,
`value_column=OBS_VALUE`, `source_period`, and a selector containing `DATAFLOW`
and every dimension from the source structure. This supports independent
re-reading of raw values. Invalid numeric values and dates are counted in issues
and not published; raw bodies are preserved. Missing verified series produce
explicit country/concept issues. No interpolation, numerical transformation or
cross-adjustment/composition splicing is performed here.

## Bounded adapter readback

The development readback combines already archived, live-verified source responses;
it is not a substitute for the final full-snapshot audit. Its machine-readable
summary is ignored at `runs/oecd_adapter_updated_check.json`. Full-snapshot
coverage and acceptance are determined by the main pipeline.

The readback parsed **245,638 candidate observations** for **39 units** and **25 concepts**, with **83 missing-coverage issues** and no dataset parsing/request failures. These are candidate coverage counts and include explicitly flagged older euro-area compositions.

| Concept | Units with candidates | Units with no matching OECD candidate |
|---|---:|---|
| `ca_gdp` | 39 | None in this OECD candidate readback |
| `cli` | 12 | AUT, BEL, CHE, CHL, COL, CRI, CZE, DNK, EA, EST, FIN, GRC, HUN, IRL, ISL, ISR, LTU, LUX, LVA, NLD, NOR, NZL, POL, PRT, SVK, SVN, SWE |
| `conf_bus` | 38 | ISL |
| `conf_cons` | 37 | ISL, NOR |
| `cons_gov` | 39 | None in this OECD candidate readback |
| `cons_priv` | 39 | None in this OECD candidate readback |
| `cpi` | 39 | None in this OECD candidate readback |
| `cpi_core` | 16 | AUT, BEL, CZE, DEU, DNK, EA, ESP, EST, FIN, FRA, GRC, HUN, IRL, ITA, LTU, LUX, LVA, NLD, POL, PRT, SVK, SVN, SWE |
| `employment` | 39 | None in this OECD candidate readback |
| `equity_idx` | 39 | None in this OECD candidate readback |
| `exports_real` | 39 | None in this OECD candidate readback |
| `fx_usd` | 38 | USA |
| `gdp_defl` | 39 | None in this OECD candidate readback |
| `gdp_real` | 39 | None in this OECD candidate readback |
| `gfcf` | 39 | None in this OECD candidate readback |
| `imports_real` | 39 | None in this OECD candidate readback |
| `ind_prod` | 38 | CRI |
| `lfpr` | 39 | None in this OECD candidate readback |
| `money_broad` | 22 | AUT, BEL, DEU, ESP, EST, FIN, FRA, GRC, IRL, ITA, LTU, LUX, LVA, NLD, PRT, SVK, SVN |
| `ppi` | 35 | ISR, JPN, KOR, MEX |
| `rate_10y` | 38 | TUR |
| `rate_3m` | 39 | None in this OECD candidate readback |
| `retail_vol` | 37 | CHL, CRI |
| `ulc` | 35 | CHL, COL, ISL, MEX |
| `unemp` | 39 | None in this OECD candidate readback |


## Validation and operational scope

Offline tests cover dynamic membership, nonmember exclusion, missing membership
metadata, exact codelist version resolution, unchanged values and multipliers,
raw audit selectors, HICP methodology enforcement, invalid observations and dates,
separate euro-area compositions, and explicit special-adjustment/multiplier flags.

The adapter uses only the shared `SourceClient`. Its largest verified request is
below the existing response cap because KEI monthly and quarterly histories are
requested separately. Data histories begin in 1998 to support transformations for
the requested 1999 Q1 analysis start. This adapter starts no jobs, obtains no keys,
and publishes nothing.

## Archived freshness limits in snapshot 20261020-2149

A read-only inspection of the retained official CPI and KEI payloads found no
newer equivalents excluded by a reference-year selector. Neither the configured
selector nor the adapter filters `BASE_PER`; the CPI, PPI and M3 records in these
payloads all report 2015. This conclusion concerns the archived responses, not
all possible OECD dataflows.

- Manufacturing PPI ends in December 2022 for 29 units; the other available
  series end in late 2022 or early 2023. No current counterpart is present in the
  retained KEI responses. These histories must be displayed as stale.
- National M3 ends in December 2018 for CHE, CHL, DNK, MEX, NZL, POL, SWE and TUR.
  The corresponding quarterly candidates also end in 2018 Q4. Quarterly selection
  therefore cannot repair these stale histories.
- National headline CPI in the retained response ends in June 2021 for JPN,
  January 2022 for ISL, December 2023 for CHL, and July 2024 for MEX. These are
  source-response limits, not failed parsing or filtered new base years.
- CAN headline CPI has an NSA candidate through August 2026 while the SA series
  ends in May 2025. USA core CPI has an NSA candidate through August 2026 while
  the SA series ends in December 2024. These candidates remain separate, and the
  harmonisation layer may choose a fresh eligible whole series with its adjustment
  caveat and a recorded selection reason.
- Many OECD headline HICP series end in December 2025. A more current national
  CPI, such as DEU through September 2026, cannot fulfil the EU-HICP requirement.
  The separately retained Eurostat HICP is the eligible current fallback.

Evidence is in the snapshot's `oecd_cpi_data_0`, `oecd_cpi_data_1`,
`oecd_kei_data_0` and `oecd_kei_data_1` raw responses and their manifest hashes.
Exact official request URLs are in `configs/oecd_mappings.yaml` and the raw
manifest. No replacement series or additional requests were introduced by this
freshness review.
