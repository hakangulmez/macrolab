# ident.external_series — reusable shock and joint inference (G6)

Fit the specified first-stage recursive VAR and expose its dated structural
innovations: epsilon = inverse(Cholesky(SSE/residual df)) × residual. Retain the
ordering, frequency, own-impact factor, physical-unit shock and first-stage
sample. A one-SD request uses one structural unit; a fixed physical size uses
size / own impact. Never identify a different national shock and call it the
same common impulse.

The first-stage VAR must use a complete regular calendar. Stability is not required
for its orthogonalised residuals. G7.1 reports a warning at a largest companion
root of 0.98 or above (near unit root), including roots at or above one
(unstable). This threshold is a disclosure rule, not a change to identification.
IRF, FEVD and historical decomposition from an unstable VAR remain blocked;
joint simulation also requires a stable auxiliary first stage. The
attachment helper blocks duplicate/misaligned dates, missing shock coverage or
frequency mismatch. Engine preparation records the common observed window and
stage/LP initialisation and horizon holdbacks. No shock values are filled.
The common-shock engine also checks the national input window before intersection:
only the recorded first-stage lag-initialisation dates are exempt. Other missing
shock coverage blocks and requires an explicit sample restriction.

Conditional LP bands ignore first-stage estimation uncertainty and say so.
The optional **joint residual bootstrap** is off by default (200 draws when
selected). It fits a block-triangular auxiliary system: the first-stage VAR and
national multivariate ARX equations driven by contemporaneous structural shocks,
selected lags, shared first-stage controls and fixed exogenous/deterministic terms.
Resample complete innovation vectors together, simulate both stages recursively,
refit the first stage and recover its new shock, then refit every national LP.
This retains contemporaneous dependence rather than holding observed national
outcomes fixed while changing the shock.

The bootstrap assumes serially exchangeable innovations and an adequate auxiliary
DGP; exogenous inputs are conditioned on. For each horizon, center the simulated
estimation errors on the known response of that fitted auxiliary DGP. Invert
those error quantiles around the sample LP estimate. The auxiliary population
response is reported separately and is never substituted for the LP point
estimate. Intervals are pointwise, not simultaneous. Failed/unstable draws are
counted; attempts are capped at draws + max(10, draws/10). Insufficient valid
draws block the requested band with an explanation.

Joint inference requires an explicit common-window alternative when country input
calendars differ. Default conditional comparisons retain each country's own sample.
G7 must show both conditional and joint bands on that same restricted alternative
sample, so sample changes are not mistaken for uncertainty changes. Different
responses are bootstrapped using identical seeds and the same auxiliary system;
they are retained separately, never averaged.

Validation was fixed before recovery runs: 200 replications per T=120/240, each
with 200 draws, a known national AR(2) response and known stage-1 VAR(2). Joint
90% coverage ranges from 85.5–92.5% at T=120 and 84.5–91.5% at T=240, with no
failed draws. Conditional bands cover 80.0–88.5% and 79.5–90.5%. Full horizon
coverage, bias, browser/native parity, seeded reproducibility, cancellation and
standalone two-stage export checks are in the G6 report. These are DGP-specific
finite-sample results, not a universal coverage guarantee.

Generated shocks remain unrounded numerical model outputs. Second-stage source
fingerprints identify original national data, the first-stage original-data
fingerprint and its configuration, rather than reclassifying floating-point
shock estimates as raw source observations. This preserves source provenance
across the native/browser tolerance without rounding model inputs or results.

## G7 exclusion sensitivity

The explicitly requested 2014–2022 exclusion fits first-stage OLS on calendar
rows whose dependent value and all VAR lags lie outside the omitted interval.
It never concatenates the two retained regimes. The second-stage calendar is
also kept intact: lags and horizon targets that touch missing shock periods are
omitted. Excluded dates are an explicit user-declared holdback, additional to
initialisation. Joint inference currently requires one continuous first-stage
window and blocks this exclusion variant. This restriction is not applied to
the default common-window bootstrap.

G7.1 compatibility exception: the accepted v0 monetary extended-VAR sensitivity
has root 1.0002933194541737 and retains its existing instability warning and
outputs. The v1 dynamic-output guard does not rewrite this frozen v0 result.
