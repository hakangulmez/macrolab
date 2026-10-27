# G1.1 OECD CLI coverage verification

Verified at 2026-10-20 22:12–22:13 UTC. The host date is preserved; this was
21 October in Europe/Berlin. Data and full response bodies remain in ignored paths.

The current OECD metadata endpoint resolves `OECD.SDD.STES,DSD_STES@DF_CLI,4.1`.
Its description states: “CLIs are calculated for G20 countries plus Spain and 5 zone
aggregates.” [Official current dataflow metadata](https://sdmx.oecd.org/public/rest/v1/dataflow/OECD.SDD.STES/DSD_STES@DF_CLI/latest?references=all).

Two successful data requests removed every CLI filter except monthly frequency
and measure `LI`: one since 2025, followed by the full available history. The
[full-history query](https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/.M.LI......)
returned 56,308 observations across 22 source geographies, from 1955-01 through
2026-09. Every observation uses methodology `H`, whose referenced codelist label
is “OECD harmonised”. No national-methodology CLI was hidden by the G1 `H` filter
in this response. The presence of `N` in a shared codelist or a flow-wide
constraint does not establish an `N` CLI observation for any country.

Observed adjustment/transformation pairs are `AA/IX`, `NOR/IX`, `TR/IX` and `TR/GY`.
The adapter retains the official headline amplitude-adjusted index (`AA/IX`)
with `UNIT_MEASURE=IX`, `ACTIVITY=_Z`, `TIME_HORIZ=_Z`, and `METHODOLOGY=H`.
It preserves the raw value, multiplier, source period and full dimension selector.
Amplitude adjustment is recorded explicitly; it is not relabelled seasonal adjustment.
Normalised, trend-restored and growth-rate variants are counted in evidence, not
substituted into the headline concept.

Intersecting the source response with the dynamically fetched G1 country universe
produces 8,362 headline observations for 12 OECD members:
AUS, CAN, DEU, ESP, FRA, GBR, ITA, JPN, KOR, MEX, TUR, USA.

The same 27 country/concept cells remain missing: AUT, BEL, CHE, CHL, COL, CRI,
CZE, DNK, EST, FIN, GRC, HUN, IRL, ISL, ISR, LTU, LUX, LVA, NLD, NOR, NZL,
POL, PRT, SVK, SVN, SWE, and EA. Each receives the issue code
`cli_not_observed_in_current_oecd_flow` with the broad query, metadata URL and
archived raw path. The current flow description and actual response support this
bounded finding. They do not prove when historical publication began or ceased,
or that no other historical OECD archive ever contained a series.

The source includes groups such as `G4E`, `G7`, `G20` and `NAFTA`; none is silently
renamed as the euro-area aggregate. Business and consumer confidence remain
separate concepts and are neither queried nor changed by this adapter.

The flow also contains `NonProductionDataflow=true`. This annotation is retained
as source metadata without interpreting it as cessation of publication: the
current-version lookup and live data requests succeed and return observations
through September 2026.

| Evidence | SHA-256 |
|---|---|
| Current metadata, HTTP 200, 1,924,357 bytes | `1fe30ad75cdaf4fd83101b3839e77c3cc97dcdfb9c040f22ad3e2d64a8cb02f9` |
| Broad recent CLI query, HTTP 200, 144,521 bytes | `4b6b489b15e940875d09932b34031ac552a7c8c7b4e11d3295ccf7190aba6e94` |
| Broad full-history CLI query, HTTP 200, 4,858,013 bytes | `429f6a0d198130787889a8b06114468521c887bbc7bc20b02d7ee2a996377293` |

The source archive is `data/raw/OECD/g11-cli-discovery-20261020-221220/`;
request URLs, retrieval times, MIME types and hashes are in the ignored raw
manifest. The ignored adapter result is
`runs/g11-cli-discovery-20261020-221220/result.json`.

`fetch_cli(client, countries)` returns `rows`, `issues`, `mapping_evidence`, and
`requests`. It checks the current dataflow version and dimension labels before
using the verified mapping. Unavailable requests produce per-country
`cli_verification_unavailable` issues, never assertions about non-publication.
If other LI variants appear without the headline form, the distinct issue is
`cli_headline_definition_not_observed` so absence and definition mismatch are
not confused. No country universe is hard-coded in the adapter.

Integration replaces only existing `cli` candidates when adopting these freshly
verified rows; it must not combine overlapping vintages blindly. Confidence
indicators and their existing mappings are unchanged. This investigation
recovers zero additional countries; it establishes why the 27 gaps remain.

Validation: nine offline synthetic tests pass. Independent source auditing
re-read first, middle and last observations for USA, Germany and Japan from the
archived broad CSV: all nine matched exactly. All three successful discovery
responses also passed raw-manifest checksum verification. Ruff, formatting and
strict mypy pass for the new adapter and tests.
