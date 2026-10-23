"""Fixed, public synthetic DGPs; no real observations."""

from copy import deepcopy

import numpy as np
import pandas as pd

from macrolab.analysis.config import validated_config
from macrolab.models.base import AnalysisData

A = np.array([[[0.45, 0.10], [0.05, 0.35]], [[-0.10, 0.0], [0.02, -0.08]]])
P = np.array([[1.0, 0.0], [0.35, 0.8]])


def simulate(n=160, seed=20261022):
    rng = np.random.default_rng(seed)
    e = rng.normal(size=(n + 300, 2))
    z = np.zeros_like(e)
    y = np.zeros(n + 300)
    eta = rng.normal(scale=0.7, size=n + 300)
    for t in range(2, len(z)):
        z[t] = A[0] @ z[t - 1] + A[1] @ z[t - 2] + P @ e[t]
        y[t] = 0.5 * y[t - 1] - 0.1 * y[t - 2] + 0.6 * e[t, 1] + eta[t]
    return z[300:], e[300:], y[300:]


def dates(n):
    return [str(p).replace("Q", "-Q") for p in pd.period_range("1999Q1", periods=n, freq="Q")]


def lp_case(n=160, seed=20261022):
    z, e, _ = simulate(n, seed)
    data = AnalysisData(
        pd.DataFrame({"y": z[:, 1], "x": z[:, 0], "shock": e[:, 0]}, index=dates(n))
    )
    config = {
        "schema_version": 1,
        "snapshot_id": "g6-synthetic",
        "countries": ["SYN"],
        "frequency": "Q",
        "series": [
            {"concept_id": "y", "role": "response", "transform": "level"},
            {"concept_id": "x", "role": "endogenous", "transform": "level"},
            {"concept_id": "shock", "role": "shock", "transform": "level"},
        ],
        "model": {"id": "lp.ols", "params": {"lags": 2, "horizon": 12}},
        "sample": {"start": "1999-Q1", "end": "latest"},
        "comparison": {"enabled": False},
    }
    return data, validated_config(config)


def two_stage(n=160, seed=20261023):
    z, _, y = simulate(n, seed)
    first = AnalysisData(pd.DataFrame(z, columns=["x", "policy"], index=dates(n)), country="EA")
    first_config = {
        "schema_version": 1,
        "snapshot_id": "g6-synthetic",
        "countries": ["EA"],
        "frequency": "Q",
        "series": [
            {"concept_id": "x", "role": "endogenous", "transform": "level"},
            {"concept_id": "policy", "role": "shock", "transform": "level"},
        ],
        "model": {"id": "ident.external_series", "params": {"lags": 2}},
        "identification": {"id": "recursive", "params": {"order": ["x", "policy"]}},
        "outputs": {"irf": {"shock_mode": "one_sd", "horizon": 12}},
        "comparison": {"enabled": False},
        "sample": {"start": "1999-Q1", "end": "latest"},
    }
    first_config = validated_config(first_config)
    country = AnalysisData(pd.DataFrame({"y": y[2:]}, index=dates(n)[2:]), country="AAA")
    _, config = lp_case(n, seed)
    config["countries"] = ["AAA"]
    config["series"] = [
        {"concept_id": "y", "role": "response", "transform": "level"},
        {"concept_id": "identified_impulse", "role": "shock", "transform": "level"},
    ]
    return first, first_config, country, validated_config(config)


def bundle_from(data):
    bundle = {"snapshot_id": "g6-synthetic", "countries": {}}
    for country, frame in data.items():
        bundle["countries"][country] = {"metadata": {"iso3": country}, "series": {}}
        for name in frame:
            bundle["countries"][country]["series"][name] = {
                "metadata": {
                    "concept_id": name,
                    "frequency": "Q",
                    "status": "available",
                    "flags": [],
                    "warnings": [],
                    "first_date": str(frame.index[0]),
                    "last_date": str(frame.index[-1]),
                },
                "observations": list(zip(map(str, frame.index), frame[name].tolist(), strict=True)),
            }
    return bundle


def common_case():
    first, first_config, country, lp = two_stage()
    config = deepcopy(lp)
    config["model"]["id"] = "cmp.common_shock"
    config["model"]["params"]["first_stage"] = first_config
    bundle = bundle_from({"EA": first.frame, "AAA": country.frame})
    return validated_config(config), bundle
