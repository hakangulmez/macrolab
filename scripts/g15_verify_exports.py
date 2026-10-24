"""Replay the three new downloads with network access denied by the OS."""

import json
import os
import subprocess
from pathlib import Path

from g12_fixture import numbers

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g15")


def without_timing(value):
    if isinstance(value, dict):
        return {
            k: without_timing(v)
            for k, v in value.items()
            if k not in {"template_timing", "export_metadata"}
        }
    if isinstance(value, list):
        return [without_timing(v) for v in value]
    return value


def main():
    confinement = OUT / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    fixture = json.loads((OUT / "template-fixture.json").read_text())
    rows = []
    for name in fixture["cases"]:
        replay = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(OUT / "template-downloads" / f"{name}.py"),
            ],
            cwd=OUT,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        native = json.loads(replay.stdout)
        browser = json.loads((OUT / f"{name}.browser.json").read_text())
        assert native["export_metadata"]["config_hash"] == browser["config_hash"]
        delta = numbers(without_timing(browser), without_timing(native))
        assert max(delta) <= 1e-8, (name, max(delta))
        (OUT / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
        csv = (OUT / "template-downloads" / f"{name}.csv").read_text()
        assert "snapshot" in csv and "check" in csv
        if name == "same_ecb_shock_pooled":
            assert "gdp_real" in csv and "cpi" in csv and "end_2019" in csv
        if name == "ea_inflation_horse_race":
            assert "exclude_inflation_surge_targets" in csv
        pngs = list((OUT / "template-downloads").glob(name + "*.png"))
        assert pngs and all(p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in pngs)
        rows.append(
            dict(
                name=name,
                fields=len(delta),
                max_difference=max(delta),
                network="OS-denied",
                pngs=len(pngs),
                passed=True,
            )
        )
        print(name, rows[-1], flush=True)
    (OUT / "template-export-verification.json").write_text(
        json.dumps(dict(passed=True, cases=rows), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
