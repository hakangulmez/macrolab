"""G12 workloads, posterior validation and bounded carry-over comparison."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
from g11_panel_fixture import fixtures
from statsmodels.api import OLS
from statsmodels.tsa.api import VAR

from macrolab.analysis.config import encode_config, validated_config
from macrolab.analysis.data import prepare_country
from macrolab.analysis.engine import run_analysis
from macrolab.models.bvar import design, fit_bvar, posterior
from macrolab.models.panel import fe_design

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.v2.test_bvar import fixture  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g12"


def numbers(a, b, path=""):
    diffs = []
    if isinstance(a, dict):
        assert set(a) == set(b), (path, set(a) ^ set(b))
        for k in a:
            if k not in {"runtime_ms", "code_version"}:
                diffs += numbers(a[k], b[k], path + "/" + k)
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            diffs += numbers(x, y, path + "/" + str(i))
    elif isinstance(a, (int, float)) and not isinstance(a, bool):
        assert isinstance(b, (int, float)), path
        diffs.append(abs(a - b))
    else:
        assert a == b, (path, a, b)
    return diffs


def main():
    OUT.mkdir(exist_ok=True)
    cases, bundle = fixtures()
    carry = []
    for name, c in cases.items():
        r = run_analysis(c, bundle)
        assert r["status"] == "ok", r["checks"]
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        before = json.loads((ROOT / "runs/g11_1" / f"{name}.json").read_text())
        restored = deepcopy(r)
        if name == "panel_fe_11":
            panel = restored["results"][0]["panel"]
            for code, rows in panel["country_estimates"].items():
                old = before["results"][0]["panel"]["country_estimates"][code]
                assert panel["country_estimates_conventional"][code] == old
                for a, b in zip(old, rows, strict=True):
                    assert a["estimate"] == b["estimate"]
                    carry.append(
                        dict(
                            country=code,
                            term=a["term"],
                            estimate=a["estimate"],
                            before_se=a["std_error"],
                            after_se=b["std_error"],
                            before_lower=a["lower"],
                            after_lower=b["lower"],
                            before_upper=a["upper"],
                            after_upper=b["upper"],
                        )
                    )
                # Independent statsmodels Newey-West check for the real contiguous sample.
                d = fe_design(prepare_country(c, bundle, code)[0], c)
                mask = d["mask"]
                x = d["x"].loc[mask]
                y = d["y"].loc[mask]
                x = x.loc[:, (x != 0).any()]
                ref = OLS(y, np.column_stack([np.ones(len(x)), x])).fit(
                    cov_type="HAC", cov_kwds={"maxlags": 4}, use_t=True
                )
                np.testing.assert_allclose(
                    [v["std_error"] for v in rows], ref.bse, atol=1e-10, rtol=0
                )
            panel["country_estimates"] = panel.pop("country_estimates_conventional")
        delta = numbers(before, restored)
        assert max(delta) == 0, (name, max(delta))
        print(name, "unchanged fields exact", len(delta), flush=True)
    (OUT / "panel-carryover.json").write_text(
        json.dumps(
            dict(
                changes=carry,
                allowed_fields=[
                    "country_estimates: std_error, lower, upper, covariance",
                    "country_estimates_conventional: new copy of accepted conventional results",
                ],
                unchanged_numeric_max=0,
            ),
            indent=2,
        )
        + "\n"
    )
    (OUT / "panel-fixture.json").write_text(
        json.dumps(
            dict(cases=cases, tokens={k: encode_config(c) for k, c in cases.items()}, bundle=bundle)
        )
        + "\n"
    )
    m = json.loads((ROOT / "runs/g10_1/site/data/manifest.json").read_text())
    c = deepcopy(next(t["config"] for t in m["templates"] if t["id"] == "monetary_policy"))
    c["model"] = dict(id="bvar.minn", params=dict(lags=4))
    c = validated_config(c)
    grid = deepcopy(c)
    grid["model"]["params"]["lambda_selection"] = "grid"
    optional = deepcopy(c)
    optional["model"]["params"].update(
        draws=5000, sum_of_coefficients=True, co_persistence=True, drop_explosive=True
    )
    cases = {
        "bvar_fixed": c,
        "bvar_grid": validated_config(grid),
        "bvar_optional": validated_config(optional),
    }
    (OUT / "bvar-fixture.json").write_text(
        json.dumps(
            dict(cases=cases, tokens={k: encode_config(c) for k, c in cases.items()}, bundle=bundle)
        )
        + "\n"
    )
    for name, c in cases.items():
        r = run_analysis(c, bundle)
        assert r["status"] == "ok", r["checks"]
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        print(name, r["runtime_ms"], r["results"][0]["bvar"]["matched_ols"]["status"], flush=True)
    # Numerical evidence independent posterior formula across four prior settings.
    data, c = fixture()
    d = design(data, c)
    rows = []
    for opts in (
        {},
        {"sum_of_coefficients": True},
        {"co_persistence": True},
        {"sum_of_coefficients": True, "co_persistence": True},
    ):
        p = posterior(d, 0.2, opts)
        pr = p["prior"]
        v = np.linalg.inv(pr["precision"] + d["x"].T @ d["x"])
        mean = v @ (pr["precision"] @ pr["mean"] + d["x"].T @ d["y"])
        scale = (
            pr["scale"]
            + d["y"].T @ d["y"]
            + pr["mean"].T @ pr["precision"] @ pr["mean"]
            - mean.T @ np.linalg.solve(v, mean)
        )
        rows.append(
            dict(
                options=opts,
                mean_max=float(np.max(abs(p["mean"] - mean))),
                row_covariance_max=float(np.max(abs(p["variance"] - v))),
                scale_max=float(np.max(abs(p["scale"] - scale))),
                covariance_mean_max=float(
                    np.max(abs(p["covariance_mean"] - scale / (p["df"] - d["n"] - 1)))
                ),
            )
        )
    ols = VAR(data.frame).fit(2)
    limit = posterior(d, 1e8, {})
    # 100 DGP replications, T=240; descriptive recovery of known reduced-form coefficients.
    from tests.v1.fixtures import A

    errors = []
    cover = []
    for seed in range(100):
        data, c = fixture(240, 900 + seed)
        p = posterior(design(data, c), 0.2, {})
        a = p["mean"][1:].reshape(2, 2, 2).transpose(0, 2, 1)
        errors.append(a - A)
        r = fit_bvar(data, c)
        # True one-unit impact response of variable x to recursive policy shock is zero at h0.
        from macrolab.models.var import moving_average
        from tests.v1.fixtures import P

        truth = (moving_average(A, 12) @ P)[:, :, 1] * (r["irf"]["shock_size"] / P[1, 1])
        band = r["bvar"]["bands"]["0.9"]
        cover.append((truth >= np.array(band["lower"])) & (truth <= np.array(band["upper"])))
    report = dict(
        posterior=rows,
        ols_limit_max=float(np.max(abs(limit["mean"] - ols.params.to_numpy()))),
        recovery=dict(
            replications=100,
            T=240,
            coefficient_max_absolute_bias=float(np.max(abs(np.mean(errors, axis=0)))),
            coefficient_rmse=float(np.sqrt(np.mean(np.array(errors) ** 2))),
            irf_90_coverage=np.mean(cover, axis=0).tolist(),
            caveat=(
                "Bayesian credible bands are prior-conditional; repeated-sample coverage "
                "is diagnostic, not a guarantee."
            ),
        ),
    )
    (OUT / "bvar-native-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
