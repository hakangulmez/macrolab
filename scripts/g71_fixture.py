"""Local G7.1 real-template evidence on the accepted G5 snapshot; no downloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]


def bundle():
    path = ROOT / "runs/g6/public/data"
    manifest = json.loads((path / "manifest.json").read_text())
    out = {
        "snapshot_id": manifest["snapshot_id"],
        "as_of_date": manifest["as_of_date"],
        "countries": {},
        "variants": json.loads((path / "global-variants.json").read_text())["variants"],
    }
    for code in ["EA", "DEU", "FRA", "ITA", "ESP", "TUR"]:
        d = json.loads((path / "countries" / f"{code}.json").read_text())
        cards = {c["concept_id"]: c for c in d["cards"]}
        out["countries"][code] = {
            "metadata": d["country"],
            "series": {
                cid: {"metadata": cards[cid], "observations": obs}
                for cid, obs in d["series"].items()
            },
        }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", default="same_ecb_shock")
    parser.add_argument("--no-sensitivity", action="store_true")
    parser.add_argument("--joint", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / f"configs/templates/{args.template}.json").read_text())
    if args.no_sensitivity:
        config["comparison"]["enabled"] = False
    if args.joint:
        config["model"]["params"].update(country_window="common", displayed_band="joint")
    result = run_analysis(
        config,
        bundle(),
        progress=lambda x: print(
            x["phase"], len(x.get("result", {}).get("template_sensitivity", [])), flush=True
        ),
    )
    suffix = "-joint" if args.joint else ""
    (ROOT / f"runs/g71/{args.template}{suffix}.json").write_text(
        json.dumps(result, allow_nan=False) + "\n"
    )
    print(result["status"], result["runtime_ms"], flush=True)
    if result["status"] == "ok":
        print(
            [
                (
                    s["country"],
                    s["response"],
                    round(s["peak"], 5),
                    s["horizon"],
                    s["sample"]["nobs"],
                )
                for s in result["template_summary"]
            ]
        )
        print(
            [
                (v["variant_id"], v["status"], v.get("reason", ""))
                for v in result["template_sensitivity"]
            ]
        )
    else:
        print(result["checks"])


if __name__ == "__main__":
    main()
