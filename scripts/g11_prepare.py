"""Prepare G11 from accepted release bytes; never refresh or fetch dependencies."""

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
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g11")


def prepare(
    build: bool = False, label: str = "G11 local panel-model review", *, v2_templates: bool = False
) -> None:
    accepted = ROOT / "runs/g10_1/site"
    public = OUT / "public"
    public.mkdir(parents=True, exist_ok=True)
    for folder in ("data", "runtime", "licences", "schemas"):
        if (accepted / folder).exists():
            shutil.copytree(accepted / folder, public / folder, dirs_exist_ok=True)
    (public / ".nojekyll").write_bytes(b"")
    (public / "schemas").mkdir(exist_ok=True)
    for schema_path in (ROOT / "schemas").glob("*.json"):
        shutil.copy2(schema_path, public / "schemas" / schema_path.name)
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
    m["schema_url"] = "schemas/analysis_config.schema.json"
    m["models"] = catalogue()
    if v2_templates:
        from macrolab.analysis.templates_v2 import catalogue as templates

        m["templates"].extend(templates(m["templates"], m["snapshot_id"]))
    m["validation"]["code_version"] = wheel["code_version"]
    m["publication"]["candidate"] = label
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
        if k not in {"runtime", "models", "validation", "publication", "schema_url"}
        and not (v2_templates and k == "templates")
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
                    "schema URL for new model IDs",
                ]
                + (["three preregistered G15 templates"] if v2_templates else []),
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
