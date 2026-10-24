"""Exact within-runtime regressions and separately requested G10 extensions."""

from __future__ import annotations

import json
import os
from pathlib import Path

from g9_fixture import bundle
from p2_validate import EXCLUDED, differences
from regress_v0 import approved_shadow_copy

from macrolab.analysis.engine import run_analysis
from macrolab.compare.methods import matched_pair

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g10")


def main():
    EXCLUDED.clear()
    EXCLUDED.update({"runtime_ms", "code_version"})
    b = bundle()
    m = json.loads((ROOT / "runs/v101/site/data/manifest.json").read_text())
    rows = []
    for t in m["templates"]:
        name = t["id"]
        c = json.loads(
            json.dumps(t["config"]),
            parse_float=lambda x: int(float(x)) if float(x).is_integer() else float(x),
        )
        r = run_analysis(c, b)
        (OUT / (name + ".json")).write_text(json.dumps(r) + "\n")
        cases = [(name, r)]
        if name in {"monetary_policy", "tur_pass_through"}:
            pair = matched_pair(
                r["config"],
                b,
                "gdp_real" if name == "monetary_policy" else "cpi",
                c["countries"][0],
            )
            cases.append((name + "-methods", pair))
        for key, value in cases:
            (OUT / (key + ".json")).write_text(json.dumps(value) + "\n")
            old = json.loads((ROOT / "runs/v101" / f"{key}.json").read_text())
            delta, struct, n = differences(old, value)
            approved = [d for d in struct if approved_shadow_copy(d)]
            struct = [d for d in struct if d not in approved]
            rows.append(
                {
                    "id": key,
                    "numeric_fields": n,
                    "max_difference": max((abs(v["difference"]) for v in delta), default=0),
                    "structural": struct,
                    "approved_text_changes": approved,
                    "passed": not delta and not struct,
                }
            )
            print(key, rows[-1], flush=True)
    report = {
        "cases": rows,
        "fields": sum(r["numeric_fields"] for r in rows),
        "passed": all(r["passed"] for r in rows),
    }
    (OUT / "native-regression-v101.json").write_text(json.dumps(report, indent=2) + "\n")
    assert report["passed"] and report["fields"] == 51472


if __name__ == "__main__":
    main()
