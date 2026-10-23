"""Separate G6 browser-only candidate; preserve the accepted G5/P2/P3.1 trees."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from build_runtime_assets import build_wheel

ROOT = Path(__file__).resolve().parents[1]


def prepare(build=False):
    target = ROOT / "runs/g6"
    public = target / "public"
    shutil.copytree(ROOT / "runs/g5/public", public, dirs_exist_ok=True)
    wheel = build_wheel(target)
    shutil.copy2(target / wheel["wheel_file"], public / "runtime" / wheel["wheel_file"])
    shutil.copy2(ROOT / "web/runtime/worker.mjs", public / "runtime/worker.mjs")
    manifest_path = public / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["runtime"].update(
        wheel_sha256=wheel["wheel_sha256"], source_archive_sha256=wheel["source_archive_sha256"]
    )
    manifest["publication"]["candidate"] = "G6 local model validation"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copy2(ROOT / "configs/v1_data.json", public / "data/v1-data-policy.json")
    if build:
        environment = {
            **os.environ,
            "MACROLAB_BASE_PATH": "/macrolab/",
            "MACROLAB_PUBLIC_DIR": str(public),
            "MACROLAB_BUILD_DIR": str(target / "site"),
        }
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", env=environment, check=True)
    return {
        "public": str(public.relative_to(ROOT)),
        "built": build,
        "publication_approved": False,
        "data_snapshot": "accepted G5, no refresh",
        "v1_views": "G8; existing v0 UI preserved",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    print(json.dumps(prepare(parser.parse_args().build), indent=2))
