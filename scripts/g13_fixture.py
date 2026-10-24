"""G13 fixed-snapshot workloads; never modifies accepted G12 evidence."""

import json
from copy import deepcopy
from pathlib import Path

from macrolab.analysis.config import encode_config, validated_config
from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g13"


def main():
    original = json.loads((ROOT / "runs/g12/bvar-fixture.json").read_text())
    bundle = original["bundle"]
    base = deepcopy(original["cases"]["bvar_fixed"])
    base.update(
        identification=None,
        outputs={"confidence": 0.95},
        comparison={"enabled": False},
        special_periods={"covid": "include"},
    )
    base["series"] = [dict(concept_id="unemp", role="dependent", transform="level")]
    base["aggregation"] = {"unemp": "mean"}
    base["sample"]["end"] = "2025-Q3"
    base["model"] = dict(id="uni.arima", params={})
    cases = {"arima_search": validated_config(base)}
    fixed = deepcopy(base)
    fixed["model"]["params"] = {"order_selection": "fixed", "p": 1, "d": 0, "q": 0}
    cases["arima_fixed"] = validated_config(fixed)
    mult = deepcopy(base)
    mult["series"].append(dict(concept_id="policy_rate", role="endogenous", transform="level"))
    mult["aggregation"]["policy_rate"] = "mean"
    for kind in ["ols", "bvar"]:
        c = deepcopy(mult)
        c["model"] = dict(id="fc.var", params=dict(estimator=kind, lags=2))
        cases["forecast_" + kind] = validated_config(c)
    ev = deepcopy(mult)
    ev["model"] = dict(id="fc.eval", params={})
    cases["forecast_evaluation"] = validated_config(ev)
    log = deepcopy(fixed)
    log["series"][0]["transform"] = "log"
    cases["arima_log"] = validated_config(log)
    monthly = deepcopy(log)
    monthly["countries"] = ["DEU"]
    monthly["frequency"] = "M"
    monthly["series"] = [dict(concept_id="cpi", role="dependent", transform="log")]
    monthly["aggregation"] = {"cpi": "mean"}
    monthly["sample"].update(start="2003-01", end="2025-09")
    monthly["model"]["params"].update(d=1, seasonal_p=1, horizon=12)
    cases["arima_monthly"] = validated_config(monthly)
    exogenous = deepcopy(cases["forecast_ols"])
    exogenous["series"].append(dict(concept_id="oil_brent", role="exogenous", transform="log"))
    exogenous["aggregation"]["oil_brent"] = "mean"
    exogenous["model"]["params"]["future_exog"] = "hold_last"
    cases["forecast_exogenous"] = validated_config(exogenous)
    OUT.mkdir(exist_ok=True)
    (OUT / "forecast-fixture.json").write_text(
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
            round(r["runtime_ms"]),
            [x["message"] for x in r["checks"] if x["level"] == "block"],
            flush=True,
        )
        assert r["status"] == "ok"


if __name__ == "__main__":
    main()
