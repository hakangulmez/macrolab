"""Verify the six actual G8 browser downloads offline and preserve accepted inputs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "runs/g8"
    confinement = out / "no-network.sb"
    confinement.write_text("(version 1)\n(allow default)\n(deny network*)\n")
    rows = []
    for name in [
        "monetary_policy",
        "taylor_rule",
        "phillips_curve",
        "okuns_law",
        "same_ecb_shock",
        "tur_pass_through",
        "monetary_policy-methods",
        "tur_pass_through-methods",
    ]:
        completed = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(confinement),
                str(ROOT / ".venv/bin/python"),
                "-I",
                str(out / "downloads" / f"{name}.py"),
            ],
            cwd=out,
            env={**os.environ, "TMPDIR": str(ROOT / ".cache/tmp")},
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        )
        native = json.loads(completed.stdout)
        browser = json.loads((out / f"{name}.browser.json").read_text())
        if name.endswith("-methods"):
            native = native["method_pair"]
            # These hashes identify full-precision output bytes within one runtime.
            browser.pop("shock_fingerprint", None)
            native.pop("shock_fingerprint", None)
        delta = difference(browser, native)
        assert delta <= 1e-8
        (out / f"{name}.export-result.json").write_text(json.dumps(native) + "\n")
        rows.append(
            {"template": name, "maximum_difference": delta, "network": "OS-denied", "passed": True}
        )
    old = ROOT / "runs/g6/public"
    new = out / "public"
    preserved = []
    for tree in ["data", "runtime"]:
        for path in (old / tree).rglob("*"):
            if (
                not path.is_file()
                or path.name in {"manifest.json", "analysis_config.schema.json", "worker.mjs"}
                or path.suffix == ".whl"
            ):
                continue
            relative = path.relative_to(old)
            assert path.read_bytes() == (new / relative).read_bytes(), str(relative)
            preserved.append(
                {"path": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
    for path in (old / "runtime").rglob("*.whl"):
        if path.name == json.loads((out / "runtime_wheel.json").read_text())["wheel_file"]:
            continue
        assert path.read_bytes() == (new / path.relative_to(old)).read_bytes()
    accepted = {}
    for gate in ["p2", "p31", "g5", "g6"]:
        files = [p for p in (ROOT / f"runs/{gate}/site").rglob("*") if p.is_file()]
        accepted[gate] = {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}
    assert accepted["p2"] == {"files": 164, "bytes": 82654183}
    assert accepted["p31"] == {"files": 166, "bytes": 82655049}
    result = {
        "passed": True,
        "exports": rows,
        "preserved_input_runtime_files": preserved,
        "accepted_trees": accepted,
    }
    (out / "export-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"exports": rows, "preserved_files": len(preserved), "accepted_trees": accepted},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
