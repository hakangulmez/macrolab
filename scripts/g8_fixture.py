"""G8 offline evidence: six defaults and separate matched-method pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from macrolab.analysis.engine import run_analysis
from macrolab.compare.methods import matched_pair

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g8"


def bundle():
    path = OUT / "public/data"
    m = json.loads((path / "manifest.json").read_text())
    b = {
        "schema_version": 1,
        "snapshot_id": m["snapshot_id"],
        "as_of_date": m["as_of_date"],
        "countries": {},
        "variants": json.loads((path / "global-variants.json").read_text())["variants"],
    }
    for code in ["USA", "GBR", "CAN", "ESP", "EA", "DEU", "FRA", "ITA", "TUR"]:
        d = json.loads((path / "countries" / f"{code}.json").read_text())
        cards = {c["concept_id"]: c for c in d["cards"]}
        b["countries"][code] = {
            "metadata": d["country"],
            "series": {
                k: {"metadata": cards[k], "observations": v} for k, v in d["series"].items()
            },
        }
    return b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template")
    parser.add_argument("--pairs-only", action="store_true")
    args = parser.parse_args()
    b = bundle()
    m = json.loads((OUT / "public/data/manifest.json").read_text())
    for t in m["templates"]:
        if args.template and t["id"] != args.template:
            continue
        name = t["id"]
        # Mirror JSON.stringify input integers without changing production canonicalization.
        c = json.loads(
            json.dumps(t["config"]),
            parse_float=lambda x: int(float(x)) if float(x).is_integer() else float(x),
        )
        r = (
            json.loads((OUT / f"{name}.json").read_text())
            if args.pairs_only
            else run_analysis(c, b)
        )
        (OUT / f"{name}.json").write_text(json.dumps(r, allow_nan=False) + "\n")
        print(name, r["status"], round(r["runtime_ms"]), flush=True)
        if name in {"monetary_policy", "tur_pass_through"}:
            response = "gdp_real" if name == "monetary_policy" else "cpi"
            pair = matched_pair(r["config"], b, response, c["countries"][0])
            (OUT / f"{name}-methods.json").write_text(json.dumps(pair, allow_nan=False) + "\n")
            print("pair", pair["status"], flush=True)


if __name__ == "__main__":
    main()
