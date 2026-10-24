"""Fixed accepted-snapshot G14 workloads; does not write accepted evidence."""

import json
import os
from copy import deepcopy
from pathlib import Path

from macrolab.analysis.config import encode_config, validated_config
from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g14")


def main():
    original = json.loads((ROOT / "runs/g13/forecast-fixture.json").read_text())
    bundle = original["bundle"]
    base = deepcopy(original["cases"]["forecast_evaluation"])
    base["series"] = [
        dict(concept_id=s, role="endogenous", transform="log")
        for s in ["gdp_real", "cpi", "credit_pnfs"]
    ]
    base["aggregation"] = {s["concept_id"]: "mean" for s in base["series"]}
    base["model"] = dict(id="test.coint", params={"lags": 2})
    cases = {"cointegration_three": validated_config(base)}
    two = deepcopy(base)
    two["series"] = two["series"][:2]
    two["aggregation"].pop("credit_pnfs")
    cases["cointegration_two"] = validated_config(two)
    for name, draws in [("vecm_point", 0), ("vecm_bootstrap", 200)]:
        c = deepcopy(base)
        c["model"] = dict(id="vecm", params=dict(lags=2, rank=1, draws=draws))
        cases[name] = validated_config(c)
    for host in ["sing.ols", "sing.ardl"]:
        c = deepcopy(original["cases"]["forecast_evaluation"])
        c["series"] = [
            dict(concept_id="unemp", role="dependent", transform="level"),
            dict(concept_id="gdp_real", role="regressor", transform="qoq_saar"),
        ]
        c["aggregation"] = {"unemp": "mean", "gdp_real": "mean"}
        c["model"] = dict(
            id="test.break", params=dict(host=host, lags=2, order=2, break_date="2020-Q2")
        )
        cases["break_" + host[5:]] = validated_config(c)
    panel = json.loads((ROOT / "runs/g12/panel-fixture.json").read_text())
    c = deepcopy(panel["cases"]["panel_lp_4"]["model"]["params"]["first_stage"])
    c["model"] = dict(
        id="test.break",
        params=dict(host="ident.external_series", lags=2, source_variant="dfr", break_date=""),
    )
    c["outputs"] = {"confidence": 0.95}
    cases["break_ecb"] = validated_config(c)
    OUT.mkdir(exist_ok=True)
    (OUT / "diagnostic-fixture.json").write_text(
        json.dumps(
            dict(cases=cases, tokens={k: encode_config(c) for k, c in cases.items()}, bundle=bundle)
        )
        + "\n"
    )
    for name, c in cases.items():
        r = run_analysis(c, bundle)
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        print(
            name,
            r["status"],
            round(r["runtime_ms"], 2),
            [x["message"] for x in r["checks"] if x["level"] == "block"],
            flush=True,
        )


if __name__ == "__main__":
    main()
