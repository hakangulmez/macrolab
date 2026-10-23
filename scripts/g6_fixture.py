"""Prepare native/browser validation artifacts without touching accepted candidates."""

from __future__ import annotations

import json
import platform
import sys
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_runtime_assets import build_wheel  # noqa: E402
from p2_validate import bundle as p2_bundle  # noqa: E402

from macrolab.analysis.engine import run_analysis  # noqa: E402
from macrolab.export.script import standalone  # noqa: E402
from tests.v1.fixtures import bundle_from, common_case, lp_case, two_stage  # noqa: E402


def prepare():
    out = ROOT / "runs/g6"
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    data, config = lp_case()
    for mode in ["HAC", "HC1"]:
        c = deepcopy(config)
        c["model"]["params"]["covariance"] = mode
        cases.append({"id": f"lp-{mode}", "config": c, "bundle": bundle_from({"SYN": data.frame})})
    augmented = deepcopy(cases[0])
    augmented["id"] = "lp-augmented"
    augmented["config"]["model"]["params"]["lag_augmented"] = True
    cases.append(augmented)
    for mode in ["cumulative_log", "growth_log"]:
        frame = data.frame.copy()
        frame["y"] = np.exp(4 + np.cumsum(frame.y) / 100)
        c = deepcopy(config)
        c["series"][0]["transform"] = "log"
        c["model"]["params"].update(response_mode=mode, growth_scale=4)
        b = bundle_from({"SYN": frame})
        b["countries"]["SYN"]["series"]["y"]["metadata"]["sa_flag"] = "NSA"
        cases.append({"id": "lp-" + mode, "config": c, "bundle": b})
    first, fc, country, _ = two_stage()
    for kind in ["ident.external_series", "out.hd"]:
        c = deepcopy(fc)
        c["model"]["id"] = kind
        cases.append({"id": kind, "config": c, "bundle": bundle_from({"EA": first.frame})})
    for enabled in [False, True]:
        c, b = common_case()
        c["model"]["params"].update(joint_bootstrap=enabled, bootstrap_draws=200)
        for code in ["BBB", "CCC", "DDD"]:
            b["countries"][code] = deepcopy(b["countries"]["AAA"])
            b["countries"][code]["metadata"]["iso3"] = code
            # Different known national scales; innovation resampling remains paired.
            factor = {"BBB": 0.8, "CCC": 1.2, "DDD": 1.5}[code]
            b["countries"][code]["series"]["y"]["observations"] = [
                [p, v * factor] for p, v in b["countries"][code]["series"]["y"]["observations"]
            ]
        c["countries"] = ["AAA", "BBB", "CCC", "DDD"]
        cases.append(
            {"id": "common-joint" if enabled else "common-conditional", "config": c, "bundle": b}
        )
    multi = deepcopy(next(c for c in cases if c["id"] == "common-conditional"))
    multi["id"] = "common-multi"
    multi["config"]["series"].append({"concept_id": "w", "role": "response", "transform": "level"})
    rng = np.random.default_rng(889)
    for code in multi["config"]["countries"]:
        original = multi["bundle"]["countries"][code]["series"]["y"]
        extra = deepcopy(original)
        extra["metadata"]["concept_id"] = "w"
        extra["observations"] = [
            [p, 0.7 * y + noise]
            for (p, y), noise in zip(
                original["observations"],
                rng.normal(size=len(original["observations"])),
                strict=True,
            )
        ]
        multi["bundle"]["countries"][code]["series"]["w"] = extra
    cases.append(multi)
    for item in cases:
        result = run_analysis(item["config"], item["bundle"])
        if result["status"] != "ok" or result.get("joint_bootstrap", {}).get("status") == "blocked":
            raise ValueError(f"Blocked fixture {item['id']}: {result['checks']}")
        item["expected"] = result
        (out / f"{item['id']}.native.json").write_text(json.dumps(result, allow_nan=False) + "\n")
        (out / f"{item['id']}.export.py").write_text(standalone(item["config"], item["bundle"]))
        print("Prepared", item["id"], round(result["runtime_ms"], 1), "ms", flush=True)
    v0 = []
    manifest = json.loads((ROOT / "runs/p2/public/data/manifest.json").read_text())
    for template in manifest["templates"]:
        name, config = template["id"], template["config"]
        v0.append(
            {
                "id": name,
                "config": config,
                "bundle": p2_bundle(config),
                "expected": json.loads((ROOT / f"runs/p2/{name}.browser-result.json").read_text()),
            }
        )
    (out / "browser-fixture.json").write_text(
        json.dumps(
            {
                "cases": cases,
                "v0": v0,
                "reproduction_environment": {
                    "python_version": platform.python_version(),
                    "dependencies": {
                        name: version(name)
                        for name in [
                            "numpy",
                            "pandas",
                            "scipy",
                            "statsmodels",
                            "patsy",
                            "packaging",
                        ]
                    },
                },
            },
            allow_nan=False,
        )
        + "\n"
    )
    wheel = build_wheel(out)
    print("Portable wheel:", wheel["wheel_sha256"], flush=True)


if __name__ == "__main__":
    prepare()
