"""G14 published-table audit, reference differences, recovery and null-size evidence."""

import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macrolab.models.break_calibration import ANDREWS_15, HANSEN_15  # noqa: E402
from macrolab.models.break_tests import critical_values, run_break_tests  # noqa: E402
from macrolab.models.cointegration import fit_vecm, impulse_responses, test_cointegration  # noqa: E402
from tests.v2.test_cointegration_breaks import break_fixture, coint_fixture  # noqa: E402

OUT = ROOT / "runs/g14"


def main():
    text = (OUT / "references/andrews-table.txt").read_text().replace("\x04", ".")
    # Each table row starts with trimming fraction and the transformed window length.
    rows = [
        list(map(float, re.findall(r"(?:\d+)?\.\d+", line)))[2:]
        for line in text.splitlines()
        if line.startswith(".15")
    ]
    reference = np.array(rows).reshape(20, 3)
    np.testing.assert_array_equal(reference, ANDREWS_15)
    displayed = (
        np.array([list(critical_values(k)[0].values()) for k in range(1, 21)])
        * np.arange(1, 21)[:, None]
    )
    relative = np.abs(displayed / reference - 1)
    raw_hansen = np.array(
        [(chi2.isf([0.1, 0.05, 0.01], df) - a) / b for a, b, df in HANSEN_15[:20]]
    )
    data, config = coint_fixture()
    r = test_cointegration(data, config)
    ref = coint_johansen(data.frame.to_numpy(), 0, 1)
    v = fit_vecm(data, config)["vecm"]
    native = VECM(data.frame.to_numpy(), k_ar_diff=1, coint_rank=1, deterministic="co").fit()
    size = {}
    for covariance in ["conventional", "HAC"]:
        rejected = 0
        for seed in range(200):
            raw, c = break_fixture(False, seed=20261024 + seed)
            c["model"]["params"].update(covariance=covariance, break_date="")
            b = run_break_tests(raw, c)["break_tests"]
            rejected += b["supremum"]["f_statistic"] > b["critical_values"]["95"]
        size[covariance] = dict(
            replications=200,
            sample=110,
            rejected=int(rejected),
            nominal=0.05,
            rejection_rate=rejected / 200,
        )
    broken, c = break_fixture()
    b = run_break_tests(broken, c)["break_tests"]
    report = dict(
        corrected_andrews_table=dict(
            dimensions=list(range(1, 21)),
            quantiles=[0.9, 0.95, 0.99],
            max_relative_difference=float(relative.max()),
            passed=bool(relative.max() < 0.01),
            source="references/Andrews2003.pdf, Table I, 15% trim; "
            "visually verified and independently extracted",
        ),
        original_hansen_vs_corrected_andrews_max_relative_difference=float(
            np.max(np.abs(raw_hansen / reference - 1))
        ),
        reference=dict(
            johansen_trace=float(
                np.max(np.abs([x["trace"] for x in r["cointegration"]["johansen"]] - ref.lr1))
            ),
            vecm_beta=float(np.max(np.abs(v["beta"] - native.beta))),
            vecm_alpha=float(np.max(np.abs(v["alpha"] - native.alpha))),
            var_irf_identity=float(
                np.max(
                    np.abs(
                        impulse_responses(native.var_rep, native.sigma_u, 20)
                        - native.irf(20).orth_irfs
                    )
                )
            ),
        ),
        recovery=dict(
            suggested_rank=r["cointegration"]["suggested_rank"],
            true_rank=1,
            beta=v["beta"],
            true_beta=[1, -0.5, 0],
        ),
        break_recovery=dict(
            true_index=55,
            estimated_index=b["supremum"]["split"],
            approximate_p=b["supremum"]["approximate_p_value"],
        ),
        no_break_size=size,
    )
    (OUT / "reference-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
