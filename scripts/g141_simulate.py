"""Execute the predeclared G14.1 size and asymptotic-scale protocol."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import binom
from statsmodels.stats.proportion import proportion_confint

from macrolab.models.break_bootstrap import calibrate
from macrolab.models.break_tests import critical_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g14_1"


def size():
    variants = ["conventional_asymptotic", "hac_asymptotic", "hc_bootstrap", "hac_bootstrap"]
    rows = []
    for j, null in enumerate(["IID", "Heteroskedastic", "AR(1), rho=0.5"]):
        for rep in range(500):
            rng = np.random.default_rng(202614100 + j * 10000 + rep)
            x = rng.normal(size=110)
            e = rng.normal(size=110)
            if j == 1:
                e *= np.sqrt(1 + 4 * x * x)
            if j == 2:
                for t in range(1, 110):
                    e[t] = 0.5 * e[t - 1] + np.sqrt(0.75) * e[t]
            y = 1 + 0.6 * x + e
            b = calibrate(y, np.column_stack([np.ones(110), x]), [0, 1], seed=202614200 + rep)
            cv = critical_values(2)[0]["95"]
            rejected = [
                b["hc_bootstrap"]["statistic"] > cv,
                b["hac_bootstrap"]["statistic"] > cv,
                b["hc_bootstrap"]["p_value"] <= 0.05,
                b["hac_bootstrap"]["p_value"] <= 0.05,
            ]
            rows.append(
                dict(
                    null=null,
                    replication=rep,
                    rejected=dict(zip(variants, map(bool, rejected), strict=True)),
                )
            )
            if (rep + 1) % 50 == 0:
                print(null, rep + 1, flush=True)
        (OUT / "size-replications.json").write_text(json.dumps(rows))
    table = []
    for variant in variants:
        rates = []
        for null in ["IID", "Heteroskedastic", "AR(1), rho=0.5"]:
            count = sum(r["rejected"][variant] for r in rows if r["null"] == null)
            rates.append(count / 500)
            table.append(
                dict(
                    variant=variant,
                    null=null,
                    rejected=count,
                    replications=500,
                    rate=count / 500,
                    wilson95=list(proportion_confint(count, 500, method="wilson")),
                )
            )
    errors = {v: max(abs(r["rate"] - 0.05) for r in table if r["variant"] == v) for v in variants}
    preference = ["hac_bootstrap", "hc_bootstrap", "hac_asymptotic", "conventional_asymptotic"]
    chosen = min(preference, key=lambda v: errors[v])
    report = dict(
        protocol_sha256=hashlib.sha256((ROOT / "docs/G14_1_PROTOCOL.md").read_bytes()).hexdigest(),
        table=table,
        maximum_absolute_size_error=errors,
        selected_default=chosen,
    )
    (OUT / "size-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


def scale():
    rows = []
    for q in [1, 11]:
        rng = np.random.default_rng(202614300 + q)
        n = 4000
        r = np.arange(1, n + 1) / n
        sel = (r >= 0.15) & (r <= 0.85)
        maxima = []
        coarse = []
        for _ in range(200):
            w = np.cumsum(rng.normal(size=(100, n, q)), axis=1) / np.sqrt(n)
            bridge = w - r[None, :, None] * w[:, -1:, :]
            process = np.sum(bridge[:, sel, :] ** 2, axis=2) / (r[sel] * (1 - r[sel]))
            maxima.extend(np.max(process, axis=1).tolist())
            coarse.extend(np.max(process[:, ::2], axis=1).tolist())
        values = np.sort(maxima)
        lo, hi = binom.ppf([0.005, 0.995], len(values), 0.95).astype(int)
        interval = [float(values[lo - 1]), float(values[hi])]
        tab = critical_values(q)[0]["95"] * q
        discretisation = float(np.quantile(maxima, 0.95) - np.quantile(coarse, 0.95))
        row = dict(
            q=q,
            replications=20000,
            grid_intervals=n,
            scale="Wald",
            simulated95=float(np.quantile(values, 0.95)),
            tabulated95=tab,
            mc99=interval,
            coarse_grid_difference=discretisation,
            passed=bool(interval[0] <= tab <= interval[1] + discretisation),
            displayed95=tab / q,
        )
        rows.append(row)
        print(row, flush=True)
    (OUT / "scale-validation.json").write_text(json.dumps(rows, indent=2) + "\n")
    assert all(row["passed"] for row in rows), rows


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scale", action="store_true")
    args = p.parse_args()
    scale() if args.scale else size()
