# Self-contained PNG exports

v1.1 adds an individual Export PNG action to every chart, including country
rankings and HD. Each export identifies the snapshot. HD uses signed stacked
shock contributions with initial/deterministic accounting and an actual line.

Results offers Selected chart or All response charts. The chart selector chooses
the selected PNG on desktop; at 375 px it also selects the one visible chart.
Panel export includes every response even when mobile hides the other charts.
The active sensitivity comparison is exported with its human-readable name.

Each PNG includes the analysis/template title, country, actual estimation sample
and n, human-readable labels, axis units, estimate and interval-level legend,
comparison legend when present, source credit and the model-scenario/not-forecast
footer. The plot is drawn from the exact same result points without estimation,
normalisation or smoothing. Coefficients use dots with interval whiskers; no
coefficient bars. Missing points or bands break segments rather than bridge gaps.
Bundled fonts are awaited before rasterisation. No external asset is requested.

CSV/Python numerical exports retain their accepted contracts. v1 exports include
LP, matched VAR/LP and common-shock panels. Türkiye shows the ratio first, CPI
and NEER cumulative responses second. The NEER 68% pointwise band uses the
same-fit marginal standard error; the 2003-window comparison legend and initial-
depreciation subtitle belong only to the CPI panel. The title includes Türkiye
once. PNGs and review screenshots containing results remain outside the public
source export. Footer versions come from the build.
