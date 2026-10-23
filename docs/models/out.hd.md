# out.hd — historical decomposition (G6)

Fit a stable recursively identified VAR, including its selected deterministic,
seasonal, COVID and exogenous terms. The Cholesky factor maps unit structural
innovations into reduced-form residuals. Recursively propagate a separate
contribution for each shock, the initial p observed states, and the deterministic
path. At every date:

actual = deterministic + initial condition + sum of structural-shock contributions.

The output includes all four components, actual values, deviations from the
deterministic path, periods, variables and the reconstruction error. Initial
conditions are explicit, not attributed to historical shocks. The first p dates
are marked as initial conditions. Units are those of the transformed VAR inputs.
No contribution intervals are claimed.

Unstable VARs block this output. A missing/internal calendar period also blocks;
it is never compressed into the preceding date. No v0 VAR output is changed or
expanded automatically; this is a separate output plug-in.

Required label: **Model-based accounting of the past under the recursive
identification, not evidence of what caused each movement.**

Validation includes a hand-computed two-variable diagonal VAR(1), fitted VAR(2)
reconstruction at every date, shock/residual reconstruction, stability and
calendar rejection, browser/native parity, and offline Python reproduction.
Reconstruction must be within 1e-8. Final differences are in the G6 report.

Reference: [Lütkepohl (2005), New Introduction to Multiple Time Series Analysis](https://doi.org/10.1007/978-3-540-27752-1).
