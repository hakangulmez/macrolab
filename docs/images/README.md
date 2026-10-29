# Screenshot provenance

## Featured interface (v2.6.4)

The README now leads with the single-screen analysis form, Canada's Phillips
workspace and a pooled ECB response with Spain selected. All six featured images
show the published **v2.6.4** interface, snapshot **20261024-2040**, captured on
**29 October 2026**. The source commit is
`a0ac8013046f13e2b16b1e664ec8e881e1a8c3e8`; the site commit is
`9edcc09f236b86f1285e8d23a9adb824c33be0c0`.

- `builder-light.webp` and `builder-dark.webp` include Simple/Advanced, the four
  form cards, collapsed sample settings and Run analysis. These use the genuine
  v2.6.4 browser captures prepared for the introduction document on the same day.
- `workspace-current-light.webp` and `workspace-current-dark.webp` are fresh
  published Phillips-template captures. All 17 browser tables match the accepted
  capture exactly: Canada, quarterly, 1999 Q1–2026 Q3, n = 111.
- `ecb-current-light.webp` and `ecb-current-dark.webp` are fresh published pooled
  ECB-template captures, using default HICP output with Spain selected through
  the overlay control. Chart controls, legend and the conditional-band caveat
  remain in the image.

Light and dark themes were captured separately through normal application
controls. Only cropping at panel boundaries and WebP encoding (quality 90) are
applied. No chart, number, UI label or annotation is composited or recoloured.
The manifest records original capture hashes, native crop rectangles, output
dimensions and per-file versions. Older images and their records are preserved;
the collapsed gallery explicitly identifies its earlier capture versions.

README image tags specify a width and leave height to the intrinsic image ratio.
This avoids the vertical stretching caused by GitHub constraining image width
while retaining an explicit height. The featured images are shown directly;
additional Data, forecasting and mobile captures are in a closed disclosure.

## Earlier capture history

The original screenshots show real states of MacroLab v2.2.0, snapshot **20261024-2040**, from published site commit `f2eb4636fec22ced92eadaee7e2019738392b4d5`, captured from https://hakangulmez.github.io/macrolab/ on 26 October 2026. Every served resource was checked byte-for-byte against that release.

Desktop viewports are 1440 CSS pixels wide; mobile viewports are 375 pixels wide. Those original captures use a 2× device scale and retain that resolution. Light and dark images are separate captures through the app's theme control. Germany's HICP cell is selected in the dataset explorer. Template captures use unchanged defaults, with computed results checked against the published build.

Only image encoding is optimised. No numbers, text, DOM styles, overlays, fake cursors or editor annotations are added or changed. The captures are browser viewports, not chart reconstructions. Images retain the app's source attributions and modelling caveats.

[manifest.json](manifest.json) records dimensions, file sizes, SHA-256 digests, source capture hashes and compression settings. Every image is at most 350,000 bytes; the complete image set is below 4,000,000 bytes. Screenshots do not broaden data rights: see [DATA.md](../../DATA.md).

The refreshed gallery includes the Phillips relationship scatter and a separate RMSE-by-horizon capture. These screenshots document the live v2.2.0 release; the local v2.2.1 axis rounding is verified separately. The original eighteen README images use lossless WebP encoding.

## v2.4.0 result-page refresh

On 27 October 2026, only result-page captures were refreshed from the final local
v2.4.0 build, snapshot 20261024-2040. These show the layered result page and its
existing charts through the normal controls. Home, Dataset explorer and mobile
Home captures retain their original published v2.2.0 files. Result comparisons
against the accepted v2.3.0 outputs are exact. The manifest records each refreshed
file's source tree, dimensions, capture hash and encoding; the whole image set
remains below 4 MB and each file below 350 KB. No figures or app text were edited.

## v2.5.0 entry-view refresh

On 27 October 2026, Home (desktop/mobile) and Dataset explorer captures were refreshed from the final local v2.5.0 build, snapshot 20261024-2040. They show the shared question picker and Data actions. Existing result captures remain byte-identical to v2.4.0. Each refreshed image has its source tree, capture hash, size and encoding recorded in the manifest. Scientific runtime version is 2.0.0; the application wheel/source hashes changed for the approved annual-frequency fix. Third-party runtime files and snapshot observations are unchanged. No app text, figures or cursors were added in an editor.

## v2.6.0 visible-results refresh

On 28 October 2026, pooled ECB (desktop/mobile), Türkiye, horse-race/error and RMSE, and Phillips result captures were refreshed from the final local v2.6.0 build. They are real 2x browser viewports scrolled to existing scientific charts, using app controls only. Home and Data images remain exact v2.5.0 captures. Per-file source tree, original capture hash, dimensions and encoding are in the manifest. No chart, number, cursor or annotation was edited. Scientific runtime 2.0.0, wheel, data and scientific outputs remain identical to accepted v2.5.0.

The G29 visual-flow correction refreshes the result captures again: per-point Chart data tables now start collapsed, while charts and scientific result tables stay visible. Capture hashes and the replacement build tree are recorded in the manifest. Version remains v2.6.0.

## Research workspace (v2.6.3)

`workspace-light.webp` and `workspace-dark.webp` are real local v2.6.3 Phillips-template captures at 1× device scale, encoded as lossy WebP (quality 85), 1440 × 1296 pixels, cropped at the boundary between the principal result and the model-check collection. Canada, quarterly, 1999 Q1–2026 Q3, n = 111; the same accepted snapshot and existing OLS/HAC estimates. The application was run before capture; no chart, estimate or label was composited. Other gallery images keep their earlier build labels.
