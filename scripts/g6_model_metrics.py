"""Persist small independent-reference and consistency metrics for the G6 report."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from statsmodels.api import OLS
from statsmodels.tsa.api import VAR

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from g2_browser_fixture import difference  # noqa: E402

from macrolab.compare.common_shock import compare_countries  # noqa: E402
from macrolab.ident.external_series import attach, recover  # noqa: E402
from macrolab.models.lp import fit  # noqa: E402
from macrolab.outputs.hd import decompose  # noqa: E402
from tests.v1.fixtures import lp_case, two_stage  # noqa: E402


def main():
    lp_metrics = []
    for mode in ("common", "horizon_specific"):
        for augmented in (False, True):
            data, config = lp_case()
            config["model"]["params"].update(sample_mode=mode, lag_augmented=augmented)
            result = fit(data, config)
            p = 2 + int(augmented)
            coefficient_diff = se_diff = 0.0
            for h in range(13):
                stop = len(data.frame) - (12 if mode == "common" else h)
                anchors = np.arange(p, stop)
                x = np.column_stack(
                    [np.ones(len(anchors)), data.frame["shock"].iloc[anchors]]
                    + [
                        data.frame[name].iloc[anchors - lag]
                        for lag in range(1, p + 1)
                        for name in ["shock", "x", "y"]
                    ]
                )
                reference = OLS(data.frame["y"].iloc[anchors + h].to_numpy(), x).fit(
                    cov_type="HC1" if augmented else "HAC",
                    cov_kwds={} if augmented else {"maxlags": h + 1, "use_correction": False},
                    use_t=False,
                )
                row = result["local_projection"]["horizons"][h]
                coefficient_diff = max(coefficient_diff, abs(row["estimate"] - reference.params[1]))
                se_diff = max(se_diff, abs(row["std_error"] - reference.bse[1]))
            lp_metrics.append(
                {
                    "sample_mode": mode,
                    "covariance": "HC1 (lag augmented)" if augmented else "HAC",
                    "coefficient_maximum_absolute_difference": float(coefficient_diff),
                    "se_maximum_absolute_difference": float(se_diff),
                }
            )
    first, fc, country, config = two_stage()
    shock, fitted = recover(first, fc)
    reference = VAR(first.frame.to_numpy()).fit(2, trend="c")
    expected = np.linalg.solve(np.linalg.cholesky(reference.sigma_u), reference.resid.T).T
    shock_diff = float(np.max(np.abs(expected - np.asarray(shock["all_values"]))))
    hd = decompose(fitted, list(first.frame.index))
    fake = SimpleNamespace(
        coefs=np.array([np.diag([0.5, 0.25])]),
        endog=np.array([[2.0, 4.0], [3.0, 2.0], [2.5, -0.5]]),
        k_ar=1,
        neqs=2,
        sigma_u=np.eye(2),
        resid=np.array([[1.0, 2.0], [0.0, 0.0]]),
        endog_lagged=np.ones((2, 1)),
        k_exog=1,
        params=np.array([[1.0, -1.0]]),
        names=["a", "b"],
    )
    hand = decompose(fake, ["0", "1", "2"])
    direct = fit(attach(country, shock), config)
    comparison = compare_countries(shock, {"AAA": country}, {"AAA": config})
    cmp_diff = difference(direct, comparison["entries"][0]["result"])
    report = {
        "lp.ols": lp_metrics,
        "ident.external_series": {"reference_maximum_absolute_difference": shock_diff},
        "out.hd": {
            "hand_fixture_maximum_absolute_difference": hand["maximum_identity_error"],
            "fitted_identity_maximum_absolute_difference": hd["maximum_identity_error"],
        },
        "cmp.common_shock": {"direct_lp_maximum_absolute_difference": cmp_diff},
        "passed": max(
            shock_diff, hd["maximum_identity_error"], hand["maximum_identity_error"], cmp_diff
        )
        < 1e-8,
    }
    report["passed"] = report["passed"] and all(
        max(row["coefficient_maximum_absolute_difference"], row["se_maximum_absolute_difference"])
        < 1e-8
        for row in lp_metrics
    )
    (ROOT / "runs/g6/model-metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
