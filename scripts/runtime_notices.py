"""Verify and copy the approved, pinned runtime notice bundle without network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def copy_runtime_notices(root: Path, public: Path) -> dict[str, Any]:
    """Return additive software-notice metadata for a P2 static candidate."""
    root = root.resolve()
    if not public.resolve().is_relative_to(root):
        raise ValueError("Runtime notices must be copied inside this repository")
    directory = root / "third_party/runtime"
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.resolve().is_relative_to(root):
        raise ValueError("Runtime notice manifest must stay inside this repository")
    manifest = json.loads(manifest_path.read_text())
    lock = json.loads((root / "web/runtime/assets.lock.json").read_text())
    if (
        manifest.get("schema_version") != 1
        or manifest.get("pyodide_version") != lock["pyodide_version"]
        or manifest.get("python_version") != lock["runtime_info"]["python"]
        or manifest.get("runtime_npm_integrity") != lock["runtime_npm_integrity"]
    ):
        raise ValueError("Runtime notice versions do not match the pinned runtime")
    files = []
    records = list(manifest["files"])
    records.append(
        {
            "path": "manifest.json",
            "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "bytes": manifest_path.stat().st_size,
        }
    )
    for record in records:
        relative = Path(record["path"])
        source = directory / relative
        destination = public / "licences/runtime" / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or source.is_symlink()
            or not source.resolve().is_relative_to(directory.resolve())
            or destination.is_symlink()
            or not destination.resolve().is_relative_to(public.resolve())
        ):
            raise ValueError("Runtime notice paths must be contained regular files")
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != record["sha256"] or len(content) != record["bytes"]:
            raise ValueError(f"Runtime notice checksum mismatch: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        files.append(
            {
                "path": destination.relative_to(public).as_posix(),
                "sha256": digest,
                "bytes": len(content),
            }
        )
    return {
        "status": "pinned_runtime_notices_packaged",
        "files": files,
        "runtime_components": manifest["components"],
        "runtime_notice_manifest_url": "licences/runtime/manifest.json",
        "source_availability_url": "licences/runtime/SOURCE_AVAILABILITY.md",
        "unresolved": [],
        "scope": manifest["scope"],
        "publication_approved": False,
    }
