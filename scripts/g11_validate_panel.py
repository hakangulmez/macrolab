"""Seeded native panel references/recovery; no external data or runtime packages."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from macrolab.models.base import AnalysisData
from macrolab.models.panel import fit_panel, within_fit
from tests.v1.fixtures import dates

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g11"


def main():
    reference = []
    for unbalanced in [False, True]:
        for two_way in [False, True]:
            rng = np.random.default_rng(812)
            n, t = 11, 100
            entities = np.repeat(np.arange(n), t)
            time = np.tile(np.arange(t), n)
            x = rng.normal(size=(n * t, 3))
            y = (
                x @ np.array([0.4, -0.7, 0.2])
                + rng.normal(size=n)[entities]
                + rng.normal(size=t)[time]
                + rng.normal(size=n * t)
            )
            keep = rng.random(n * t) > 0.18 if unbalanced else np.ones(n * t, dtype=bool)
            x, y, entities, time = x[keep], y[keep], entities[keep], time[keep]
            ours = within_fit(y, x, entities, time, two_way=two_way)
            index = pd.MultiIndex.from_arrays([entities, time])
            m = PanelOLS(
                pd.Series(y, index=index),
                pd.DataFrame(x, index=index),
                entity_effects=True,
                time_effects=two_way,
            )
            for covariance, opts in [
                ("conventional", {"cov_type": "unadjusted"}),
                ("country-clustered", {"cov_type": "clustered", "cluster_entity": True}),
                ("Driscoll-Kraay", {"cov_type": "kernel", "kernel": "bartlett"}),
            ]:
                ref = m.fit(**opts)
                coef = float(np.max(np.abs(ours["beta"] - ref.params.to_numpy())))
                cov = float(np.max(np.abs(ours["covariances"][covariance] - ref.cov.to_numpy())))
                reference.append(
                    {
                        "unbalanced": unbalanced,
                        "two_way": two_way,
                        "covariance": covariance,
                        "coefficient_max_abs_difference": coef,
                        "covariance_max_abs_difference": cov,
                    }
                )
                assert max(coef, cov) < 1e-8
    recovery = []
    for kind in ["common", "country_specific"]:
        estimates = []
        for rep in range(200):
            rng = np.random.default_rng(20261024 + rep)
            n, t = 6, 240
            common = rng.normal(size=t + 100)
            countries = {}
            for i in range(n):
                shock = common if kind == "common" else rng.normal(size=t + 100)
                y = np.zeros(t + 100)
                noise = rng.normal(scale=0.6, size=t + 100)
                for tt in range(1, len(y)):
                    y[tt] = 0.5 * y[tt - 1] + 0.6 * shock[tt] + noise[tt] + i * 0.2
                countries[f"C{i:02}"] = AnalysisData(
                    pd.DataFrame({"y": y[100:], "shock": shock[100:]}, index=dates(t))
                )
            config = {
                "series": [
                    {"concept_id": "y", "role": "response", "transform": "level"},
                    {"concept_id": "shock", "role": "shock", "transform": "level"},
                ],
                "model": {
                    "id": "panel.lp",
                    "params": {
                        "horizon": 6,
                        "lags": 1,
                        "lag_augmented": True,
                        "response_mode": "level",
                        "shock_type": kind,
                    },
                },
            }
            result = fit_panel(countries, config)
            estimates.append([r["estimate"] for r in result["local_projection"]["horizons"]])
        mean = np.mean(estimates, axis=0)
        truth = 0.6 * 0.5 ** np.arange(7)
        error = np.abs(mean - truth)
        recovery.append(
            {
                "shock_type": kind,
                "replications": 200,
                "N": 6,
                "T": 240,
                "truth": truth.tolist(),
                "mean": mean.tolist(),
                "max_mean_abs_bias": float(error.max()),
                "criterion": 0.03,
                "passed": bool(error.max() < 0.03),
            }
        )
        assert error.max() < 0.03
    report = {
        "passed": True,
        "linearmodels_version": "7.0",
        "reference": reference,
        "recovery": recovery,
    }
    (OUT / "panel-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
