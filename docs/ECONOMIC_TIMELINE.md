# Economic timeline

[Open the chronology](https://hakangulmez.github.io/macrolab/#timeline). Select a country or region, publication year and economic topic, or search the note text and quotations. Six highlights provide an overview; Show all opens the selected notes in publication order. View source passage exposes the original quotation and official source link.

## Coverage

The v2.7.0 collection contains 801 selected notes for all 39 MacroLab economies, reviewed through 17 November 2026. It covers 2009–2026, with one explicit gap: no date-verified Costa Rica note is included for 2012. The collection is a selected report chronology, not a complete archive of economic events, national policy decisions or every report issued during the period.

The United States, euro area and Türkiye retain 154 notes from Fed, ECB, CBRT and OECD sources. The other 36 economies add 622 notes from OECD country sections and 25 early-period IMF country releases. The new OECD selection uses one Economic Outlook edition per publication year; the newest selected edition is June 2026. The review cutoff does not mean that every later publication is included.

## Reading and attribution

Summaries were prepared with AI assistance and checked against their source passages. This is not a claim of human validation. Forecasts, risks, recommendations and decisions retain their original meaning. An OECD or IMF recommendation is an assessment by that institution, not an announcement by a national central bank. Conditional scenarios remain conditional.

Dates follow the publisher's stated publication date, rather than the report's reference period or an earlier meeting date. Original historical web vintages have not been independently reconstructed. OECD links use physical PDF page numbers, which may differ from printed page labels. Full third-party reports, embeddings and the research archive are not redistributed here; short attributed extracts link back to their publishers. These extracts remain subject to the original publishers' terms; the software's MIT licence does not relicense third-party text.

## Relationship to an analysis

Historical context below a successful result uses the selected economy, relevant economic topics and actual sample boundaries. For a forecast, later publications are excluded at the forecast origin's period end. Rolling forecast evaluations do not display a single pooled historical timeline because their origins differ. Explore chronology explicitly opens the full archive beyond those analysis boundaries.

The notes are never passed to an econometric model. They do not establish causality or explain, validate or improve the numerical estimates. Browsing them does not refit a model or request new provider data. The standalone chronology works without starting the numerical engine and does not use a paid API.

## Source files and reproducibility

The four `web/src/data/report-timeline-*.json` files contain the note records and coverage metadata. `web/src/reportTimeline.ts` handles country/topic/date filtering, and `web/src/components/ReportTimeline.tsx` renders the notes and original evidence. Their tests check country separation, date cutoffs, source links, chronological order and preservation of the original notes.

The standard build enables the timeline. Set `MACROLAB_TIMELINE_ENABLED=0` to omit it from a custom build. The separate experimental Ask the reports backend remains disabled in the published site.
