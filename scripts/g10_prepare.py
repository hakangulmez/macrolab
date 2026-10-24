"""Prepare G10 from accepted release bytes; never refresh or fetch dependencies."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from build_runtime_assets import build_wheel
from g9_export import inventory

from macrolab.models.registry import catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g10")


def prepare(build: bool = False) -> None:
    accepted = ROOT / "runs/v101/site"
    public = OUT / "public"
    public.mkdir(parents=True, exist_ok=True)
    for folder in ("data", "runtime", "licences", "schemas"):
        if (accepted / folder).exists():
            shutil.copytree(accepted / folder, public / folder, dirs_exist_ok=True)
    (public / ".nojekyll").write_bytes(b"")
    wheel = build_wheel(OUT)
    # Retain pinned scientific files, replace only MacroLab's own source wheel.
    for path in (public / "runtime").glob("macrolab_runtime-*.whl"):
        path.unlink()
    shutil.copy2(OUT / wheel["wheel_file"], public / "runtime" / wheel["wheel_file"])
    shutil.copy2(ROOT / "web/runtime/worker.mjs", public / "runtime/worker.mjs")
    path = public / "data/manifest.json"
    m = json.loads(path.read_text())
    m["runtime"].update(
        code_version=wheel["code_version"],
        wheel_url="/macrolab/runtime/" + wheel["wheel_file"],
        wheel_sha256=wheel["wheel_sha256"],
        source_archive_sha256=wheel["source_archive_sha256"],
    )
    m["models"] = catalogue()
    m["validation"]["code_version"] = wheel["code_version"]
    m["publication"]["candidate"] = "G10 v1.1 technical release candidate"
    path.write_text(json.dumps(m, indent=2) + "\n")
    unchanged = []
    for p in sorted((accepted / "data").rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            q = public / p.relative_to(accepted)
            assert p.read_bytes() == q.read_bytes(), p
            unchanged.append(str(p.relative_to(accepted)))
    original = json.loads((accepted / "data/manifest.json").read_text())
    assert all(
        m[k] == v
        for k, v in original.items()
        if k not in {"runtime", "models", "validation", "publication"}
    )
    (OUT / "unchanged-data.json").write_text(
        json.dumps(
            {
                "snapshot": m["snapshot_id"],
                "byte_identical_files": unchanged,
                "manifest_exceptions": [
                    "runtime software hashes/version/URL",
                    "model capability metadata",
                    "validation code version",
                    "candidate label",
                ],
                "data_changed": False,
            },
            indent=2,
        )
        + "\n"
    )
    if build:
        subprocess.run(
            ["npm", "run", "build", "--", "--emptyOutDir"],
            cwd=ROOT / "web",
            check=True,
            env={
                **os.environ,
                "MACROLAB_BASE_PATH": "/macrolab/",
                "MACROLAB_PUBLIC_DIR": str(public),
                "MACROLAB_BUILD_DIR": str(OUT / "site"),
            },
        )
        (OUT / "site-inventory.json").write_text(
            json.dumps(inventory(OUT / "site"), indent=2) + "\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    prepare(parser.parse_args().build)
