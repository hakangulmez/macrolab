"""Verify the six actual G9 browser downloads offline and preserve accepted inputs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from g2_browser_fixture import difference

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "runs/g9"
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
    protected = json.loads((out / "accepted-files-before.json").read_text())
    for relative, expected in protected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    (out / "accepted-files-after.json").write_text(json.dumps(protected, indent=2) + "\n")
    old = ROOT / "runs/p2/site"
    new = out / "site"
    preserved = []
    for tree in ["runtime/pyodide", "licences/runtime"]:
        for path in (old / tree).rglob("*"):
            if path.is_file():
                relative = path.relative_to(old)
                assert path.read_bytes() == (new / relative).read_bytes(), str(relative)
                preserved.append(str(relative))
    manifest = json.loads((new / "data/manifest.json").read_text())
    for country, item in manifest["country_files"].items():
        content = (new / "data/countries" / f"{country}.json").read_bytes()
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        assert len(content) == item["bytes"]
        assert not json.loads(content)["country"].get("notes")
    accepted = {"protected_files": len(protected), "all_sha256_unchanged": True}
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
