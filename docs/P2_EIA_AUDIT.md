# P2 EIA Brent input audit

The P2 candidate uses EIA's monthly **Europe Brent Spot Price FOB**, nominal US
dollars per barrel. The original G1.1 data and the P1 full-data comparison remain
unchanged. Only P2 `oil_brent` observations use this replacement; `commod_idx`
and its alternative commodity variant contain no observations.

## Official files and lineage

- [Monthly XLS workbook](https://www.eia.gov/dnav/pet/hist_xls/RBRTEm.xls):
  `Data 1`, source key `RBRTE`, column B; candidate identifier `PET.RBRTE.M`.
- [Independently readable monthly table](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RBRTE&f=M):
  year rows and January–December columns.
- Published release: **2026-10-15**. Retrieval: **2026-10-21 02:15 UTC**.
- Workbook: 55,296 bytes;
  SHA-256 `26468c66b2ebffa5cf9cbb49f2dd1875c7539b3a9309860d0e5981e26a8735ee`.
- HTML table: 20,117 bytes;
  SHA-256 `c98878a3315012c2dd0f15a01ca8f5cbdcf747dfcf04989ae117e9b916c448d5`.

The archive is `data/raw/EIA/p2-eia-20261021-021530/`, outside the publication
candidate. Fetch records preserve both URLs, HTTP status, retrieval time,
content type, size, digest and completeness. The XLS reader is locked locally
as `xlrd==2.0.2`; it is not a new browser runtime dependency.

## Independent value check

The XLS parser and the separate HTML parser agree exactly on all **473 monthly
observations**, spanning **1987-05–2026-09**. The following three dates are also
recorded individually in `runs/p2/eia/audit.json`:

| Month | XLS cell | Workbook USD/barrel | Official HTML USD/barrel | Difference |
|---|---|---:|---:|---:|
| 1999-01 | B144 | 11.11 | 11.11 | 0 |
| 2020-04 | B399 | 18.38 | 18.38 | 0 |
| 2026-09 | B476 | 114.16 | 114.16 | 0 |

Parsing rejects the wrong title or source key, duplicate months, nonfinite or
nonpositive prices, invalid dates and reordered table headers. The month is
derived from the workbook's dated cell; its full original date and both cell
coordinates remain in local audit metadata. No source price is interpolated,
rescaled or replaced by a synthetic observation.

## Candidate boundary and reproducibility

The candidate snapshot is `20261021-p2-eia-021530`, with parent
`20261021-0025`. All four template settings are unchanged; their snapshot
reference points to the new candidate. Source cards and the catalogue identify
EIA, the source series, publication/access dates and the reviewed reuse terms.

The existing monetary template takes complete three-month arithmetic means,
then logs Brent as an exogenous factor. EIA's first quarter, 1987 Q2, has only
May and June and is therefore recorded as incomplete. It lies before the
requested 1999 start and does not change the fitted common sample. This
historical bookkeeping difference is retained visibly in the conversion
metadata.

`python scripts/p2_eia.py` replays and audits the archived files. Live retrieval
requires the explicit `--fetch` flag; static preparation never fetches data.
`make p2-build` reads the checksum-verified EIA marker and the accepted parent,
then writes only the separate P2 candidate. Complete model comparisons are
saved under `runs/p2/validation.json` and `runs/p2/differences/`; the final P2
stop report gives their observed numerical outcomes.

The source policy and redistribution conditions are recorded in
[DATA.md](../DATA.md). Nothing in this local audit constitutes publication or
deployment approval.
