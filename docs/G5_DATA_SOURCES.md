# G5 source review — 21 October 2026

This is a local addition to the frozen P2/P3.1 comparison, not a replacement
vintage for v0 templates. Complete response hashes and the 18 exact audit checks
are in G5_DATA_EVIDENCE.json (local review record omitted from source export). Raw files stay ignored.

| Variant | Official identifier | Base / unit | Coverage | Observations |
|---|---|---|---|---:|
| all | IMF.RES:PCPS(9.0.0).G001.PALLFNF.INDEX.M | 2016=100 | 1992-01–2026-09 | 417 |
| energy | IMF.RES:PCPS(9.0.0).G001.PNRG.INDEX.M | 2016=100 | 1992-01–2026-09 | 417 |
| nonfuel (default) | IMF.RES:PCPS(9.0.0).G001.PNFUEL.INDEX.M | 2016=100 | 1992-01–2026-09 | 417 |
| dfr | FM.D.U2.EUR.4F.KR.DFR.LEV | percent p.a. | 1999-01–2026-09 | 333 month-ends |
| mro | FM.D.U2.EUR.4F.KR.MRR_FR.LEV / MRR_MBR.LEV | percent p.a. | 1999-01–2026-09 | 333 month-ends |
| hicp_sa (EA only) | HICP.M.U2.Y.000000.4F0.INX | 2025=100; SA/WDA | 1997-01–2026-09 | 357 |

IMF flow 9.0.0 references DSD_PCPS 10.0.0. Exact dimension order: COUNTRY,
INDICATOR, DATA_TRANSFORMATION, FREQUENCY. The broad index weights use world
commodity imports during 2014–2016, from UN ComTrade. Only INDEX is selected;
INDEX_PCH and INDEX_PCHY are not substituted for index levels. Non-fuel avoids
mechanically duplicating the separately included EIA Brent factor. Default
growth is year-on-year percentage change; quarterly aggregation is the mean.
The default non-fuel history is shared by all 39 units, classified available_note
(shared global factor), with no stale history or internal gaps.

The current IMF endpoint is
<https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS,9.0.0/G001.PALLFNF+PNFUEL+PNRG.INDEX.M?startPeriod=1980>.
Flow metadata: <https://api.imf.org/external/sdmx/2.1/dataflow/IMF.RES/PCPS/latest?references=all>.
Licence review and exact reuse/restriction excerpts: [DATA.md](../DATA.md).

## ECB policy definitions and audit

[Official daily FM data](https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR+MRR_FR+MRR_MBR.LEV?startPeriod=1999-01-01&format=csvdata)
provide every calendar date. The adapter selects the actual last calendar day
of each completed month. It neither interpolates nor carries event values
forward. October 2026 is incomplete on the retrieval date and is omitted.
The B-frequency event-only series and an unavailable M-frequency query were
rejected during discovery. DFR and MRO are explicit EA variants, usable as
shared policy measures after euro adoption; they do not overwrite BIS.
MRO uses minimum-bid tenders from 28 June 2000 to 14 October 2008 and fixed-rate
tenders outside that interval. Duplicate overlapping regimes fail the adapter.

[Official BIS metadata](https://stats.bis.org/api/v1/data/WS_CBPOL/M.XM?startPeriod=2026-07)
identifies the selected euro-area policy measure as:

- 5 January 1999–27 June 2000: MRO fixed rate.
- 28 June 2000–14 October 2008: MRO minimum bid rate.
- 15 October 2008–17 September 2024: MRO fixed rate.
- From 18 September 2024: DFR, the official steering rate.

This switch matters for interpreting the accepted BIS default. The BIS series
and its historical values remain intact. DFR provides a continuous named
alternative across the negative-rate period. No shadow-rate series is added.
The accepted EA `rate_3m` remains OECD KEI `EA20.M.IR3TIB.PA._Z._Z._Z`,
1998-01–2026-09 (345 monthly observations), with its aggregate/instrument note.

## Auditing

Each of six variants is checked at 1999-01, 2020-04 and 2026-09: 18/18 match,
maximum absolute difference 0. Production parsing uses CSV; reference checks
use separately retrieved official SDMX XML and the independent SourceAudit
parser. These are two publication formats of the same provider, not independent
measurements. For DFR/MRO, reference dates are the published final calendar day
of each audit month. The MRO tender-regime boundary and duplicate handling also
have automated tests. Per-observation provenance remains in ignored artifacts.
