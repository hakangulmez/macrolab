"""Build a separate local G7 candidate using accepted bytes, without downloads."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from build_runtime_assets import build_wheel

from macrolab.models.registry import catalogue

ROOT = Path(__file__).resolve().parents[1]


def prepare(build=False):
    target = ROOT / "runs/g7"
    public = target / "public"
    shutil.copytree(ROOT / "runs/g6/public", public, dirs_exist_ok=True)
    wheel = build_wheel(target)
    shutil.copy2(target / wheel["wheel_file"], public / "runtime" / wheel["wheel_file"])
    shutil.copy2(ROOT / "web/runtime/worker.mjs", public / "runtime/worker.mjs")
    path = public / "data/manifest.json"
    m = json.loads(path.read_text())
    m["runtime"].update(
        wheel_sha256=wheel["wheel_sha256"], source_archive_sha256=wheel["source_archive_sha256"]
    )
    m["publication"]["candidate"] = "G7 local template review"
    m["models"] = catalogue()
    for name, title, description in [
        (
            "same_ecb_shock",
            "Same ECB shock",
            "One EA DFR innovation, national local projections. Conditional and joint uncertainty.",
        ),
        (
            "tur_pass_through",
            "Türkiye exchange-rate pass-through",
            "Monthly prices after a 1% depreciation. Conditional association, not a causal shock.",
        ),
    ]:
        m["templates"].append(
            {
                "id": name,
                "title": title,
                "description": description,
                "new_in_v1": True,
                "config": json.loads((ROOT / f"configs/templates/{name}.json").read_text()),
            }
        )
    path.write_text(json.dumps(m, indent=2) + "\n")
    schema_path = public / m["schema_url"].removeprefix("/macrolab/").lstrip("/")
    shutil.copy2(ROOT / "schemas/analysis_config.schema.json", schema_path)
    if build:
        env = {
            **os.environ,
            "MACROLAB_BASE_PATH": "/macrolab/",
            "MACROLAB_PUBLIC_DIR": str(public),
            "MACROLAB_BUILD_DIR": str(target / "site"),
        }
        subprocess.run(
            ["npm", "run", "build", "--", "--emptyOutDir"], cwd=ROOT / "web", env=env, check=True
        )
    return {"public": str(public.relative_to(ROOT)), "built": build, "publication_approved": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true")
    print(prepare(p.parse_args().build))
