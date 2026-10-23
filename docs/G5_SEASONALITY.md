# G5 seasonality review — 21 October 2026

| Input | Official SA result | v1 default / controls |
|---|---|---|
| EA HICP | Current ECB `HICP.M.U2.Y.000000.4F0.INX`, working-day and seasonally adjusted, 2025=100, Jan 1997–Sep 2026 | Use the official variant in the ECB first stage; quarterly mean, then the requested q/q annualised transform. |
| Germany HICP | Only NSA national total index in current ECB HICP flow; Eurostat metadata says unadjusted | Preserve NSA; quarterly seasonal dummies in every model using q/q prices, including LP and national VAR comparison. |
| France HICP | Same result | Same rule. |
| Italy HICP | Same result | Same rule. |
| Spain HICP | Same result | Same rule. |
| Türkiye CPI | Current OECD COICOP2018 flow returns only adjustment N for the requested monthly total CPI index | Preserve NSA; monthly seasonal dummies in all monthly pass-through models, including sensitivity. |
| Brent, IMF commodity indices, BIS NEER / IMF FX | Market price and exchange-rate histories, not a newly seasonally adjusted official variant | For their short-period changes in v1, retain original values and use the model's monthly/quarterly seasonal controls; never adjust in the app. |

The obsolete ECB ICP SA series (2015=100) ends December 2025. It is **not** adopted.
The replacement HICP flow supplies a complete rebased history through September
2026. There is no splicing of the old and new base years. Three dates match the
independent SDMX publication exactly; the ECB licence record is in DATA.md.

Discovery covered ECB current HICP and legacy ICP, Eurostat current and legacy
HICP dimensions plus its official metadata, and the current OECD total-price
flow for Türkiye. No claim is made that an SA series is absent from every
possible national publication. The approved official feeds do not provide a
current national SA alternative for these defaults.

## Official evidence

- [ECB current HICP SA keys, all five required units plus Türkiye](https://data-api.ecb.europa.eu/service/data/HICP/M.U2+DE+FR+IT+ES+TR.S+Y.000000..INX?detail=serieskeysonly&format=csvdata): only EA/4F0/Y returned.
- [ECB all adjustments](https://data-api.ecb.europa.eu/service/data/HICP/M.U2+DE+FR+IT+ES+TR..000000..INX?detail=serieskeysonly&format=csvdata): national DE/FR/IT/ES returned as N/4D0.
- [Eurostat HICP metadata, §18.6](https://ec.europa.eu/eurostat/cache/metadata/en/prc_hicp_esms.htm): the official series are not seasonally adjusted. Current `prc_hicp_minr` dimensions are freq, unit, coicop18, geo, time; there is no SA selector.
- [OECD Türkiye adjustment discovery](https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/TUR.M..CPI.IX._T.._Z?startPeriod=2025-01): adjustment N only.

Raw responses and metadata are retained in `data/raw/*/g5-discovery-*`, with
retrieval times and SHA-256 hashes in the raw manifest.

## G6/G7 implementation contract

`configs/v1_data.json` records the default selection and control policy. Include
quarterly dummies Q2–Q4 (Q1 reference) or monthly dummies February–December
(January reference), with the intercept. Apply the rule to every relevant
regression and both stages, including sensitivity and the optional joint
bootstrap. A stage using official SA HICP still receives seasonal controls if
another NSA short-period input requires them. A year-on-year inflation row is
required in sensitivity. The SA first-stage series does not justify leaving
national NSA prices untreated in stage two. These model/template changes belong
to G6/G7; G5 adds the audited inputs and this explicit contract. All v0 numerical
defaults remain frozen.
