"""G11 real-data model workloads, not new product templates; no data refresh."""

import json
import os
from copy import deepcopy
from pathlib import Path

from macrolab.analysis.config import encode_config, validated_config
from macrolab.analysis.engine import run_analysis
from macrolab.models.panel import PanelLPPlugin

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g11")


def fixtures():
    path = ROOT / "runs/g10_1/site/data"
    m = json.loads((path / "manifest.json").read_text())
    bundle = {
        "schema_version": 1,
        "snapshot_id": m["snapshot_id"],
        "as_of_date": m["as_of_date"],
        "countries": {},
        "variants": json.loads((path / "global-variants.json").read_text())["variants"],
    }
    for code in m["country_files"]:
        d = json.loads((path / "countries" / f"{code}.json").read_text())
        cards = {c["concept_id"]: c for c in d["cards"]}
        bundle["countries"][code] = {
            "metadata": d["country"],
            "series": {
                k: {"metadata": cards[k], "observations": v} for k, v in d["series"].items()
            },
        }
    eleven = ["AUT", "BEL", "FIN", "FRA", "DEU", "IRL", "ITA", "LUX", "NLD", "PRT", "ESP"]
    fe = {
        "schema_version": 1,
        "snapshot_id": m["snapshot_id"],
        "countries": eleven,
        "frequency": "Q",
        "series": [
            {"concept_id": "cpi", "role": "dependent", "transform": "yoy_pct"},
            {"concept_id": "unemp", "role": "regressor", "transform": "level"},
            {"concept_id": "oil_brent", "role": "exogenous", "transform": "yoy_pct"},
        ],
        "aggregation": {"cpi": "mean", "unemp": "mean", "oil_brent": "mean"},
        "sample": {"start": "1999-Q1", "end": "latest"},
        "model": {"id": "panel.fe", "params": {}},
        "comparison": {"enabled": True},
        "special_periods": {"covid": "dummy"},
    }
    original = deepcopy(next(t for t in m["templates"] if t["id"] == "same_ecb_shock")["config"])
    lp = deepcopy(original)
    lp["model"]["id"] = "panel.lp"
    p = {
        k: v
        for k, v in original["model"]["params"].items()
        if k in PanelLPPlugin.params["properties"] and k != "template_id"
    }
    p.update(
        first_stage_source="ecb_dfr",
        covariance="Driscoll-Kraay",
        response_mode="cumulative_log",
        horizon=20,
        country_window="common",
    )
    lp["model"]["params"] = p
    for s in lp["series"]:
        if s["role"] == "response" and s["concept_id"] != "gdp_real":
            s["role"] = "endogenous"
    seventeen = deepcopy(lp)
    seventeen["countries"] = eleven + ["GRC", "SVN", "SVK", "EST", "DNK", "SWE"]
    seventeen["model"]["params"]["country_window"] = "own"
    cases = {
        "panel_fe_11": validated_config(fe),
        "panel_lp_4": validated_config(lp),
        "panel_lp_17": validated_config(seventeen),
    }
    return cases, bundle


if __name__ == "__main__":
    cases, b = fixtures()
    OUT.mkdir(exist_ok=True)
    (OUT / "panel-fixture.json").write_text(
        json.dumps(
            {"cases": cases, "tokens": {k: encode_config(c) for k, c in cases.items()}, "bundle": b}
        )
        + "\n"
    )
    for name, c in cases.items():
        r = run_analysis(c, b)
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        print(
            name,
            r["status"],
            round(r["runtime_ms"]),
            [x["message"] for x in r["checks"] if x["level"] == "block"],
            flush=True,
        )
        assert r["status"] == "ok"
