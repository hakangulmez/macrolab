"""Run only the specifications committed before estimation at 82ff653."""

import json
import os
from pathlib import Path

from g11_panel_fixture import fixtures

from macrolab.analysis.config import encode_config, required_concepts, required_countries
from macrolab.analysis.engine import run_analysis
from macrolab.analysis.templates_v2 import catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g15")


def main():
    m = json.loads((ROOT / "runs/g10_1/site/data/manifest.json").read_text())
    cases = {t["id"]: t["config"] for t in catalogue(m["templates"], m["snapshot_id"])}
    _, bundle = fixtures()
    codes = {code for c in cases.values() for code in required_countries(c)}
    concepts = {name for c in cases.values() for name in required_concepts(c)}
    bundle["countries"] = {
        code: {**d, "series": {k: v for k, v in d["series"].items() if k in concepts}}
        for code, d in bundle["countries"].items()
        if code in codes
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "template-fixture.json").write_text(
        json.dumps(
            dict(
                preregistration_commit="82ff653ecb72582c0a7c62b938116d5d2523cc1a",
                cases=cases,
                tokens={k: encode_config(c) for k, c in cases.items()},
                bundle=bundle,
            )
        )
        + "\n"
    )
    for name, c in cases.items():
        print("Starting", name, flush=True)
        r = run_analysis(c, bundle)
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        print(
            name,
            r["status"],
            r.get("template_timing"),
            [x["message"] for x in r["checks"] if x["level"] == "block"],
            flush=True,
        )
        for row in r.get("template_sensitivity", []):
            print(
                "  ",
                row["id"],
                row["status"],
                [x["message"] for x in row["checks"] if x["level"] == "block"],
                flush=True,
            )


if __name__ == "__main__":
    main()
