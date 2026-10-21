"""Copy verified, ignored local review inputs into this checkout; never download.

Use only an existing local MacroLab checkout you are authorised to read. Source
code, virtual environments, node_modules, public assets and builds are not copied.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_EVIDENCE = ROOT / "docs/G1_1_VERIFICATION.json"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def inside(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Input paths must be relative without parent traversal")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input path escapes its checkout")
    return path


def seed(source: Path, target: Path = ROOT) -> dict[str, Any]:
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError("Use a distinct existing checkout as the input source")
    lock = json.loads((target / "web/runtime/assets.lock.json").read_text())
    source_data = inside(source, "data/processed/current")
    manifest_bytes = inside(source_data.resolve(), "processed_manifest.json").read_bytes()
    accepted = json.loads(ACCEPTED_EVIDENCE.read_text())
    if digest(manifest_bytes) != accepted["processed_manifest_sha256"]:
        raise ValueError("Snapshot manifest differs from the committed accepted G1.1 evidence")
    manifest = json.loads(manifest_bytes)
    snapshot = manifest["snapshot_id"]
    if snapshot != accepted["snapshot_id"]:
        raise ValueError("Snapshot identity differs from the committed accepted G1.1 evidence")
    if not snapshot.replace("-", "").isalnum() or not manifest.get("validation_passed"):
        raise ValueError("Only a validated named snapshot can seed a review checkout")
    expected_ids = {
        json.loads(p.read_text())["snapshot_id"]
        for p in (target / "configs/templates").glob("*.json")
    }
    if expected_ids != {snapshot}:
        raise ValueError("Local inputs must match every template's pinned snapshot")
    destination = inside(target, f"data/processed/snapshots/{snapshot}")
    pending: dict[str, bytes] = {}
    for relative, expected in manifest["files"].items():
        payload = inside(source_data.resolve(), relative).read_bytes()
        if digest(payload) != expected["sha256"] or len(payload) != expected["bytes"]:
            raise ValueError(f"Snapshot integrity mismatch: {relative}")
        if relative.startswith("browser/") and relative.endswith(".json"):
            bundle = json.loads(payload)
            if "country" in bundle and bundle.get("publication_approved") is not False:
                raise ValueError("Country inputs must retain the local-only boundary")
        pending[f"data/processed/snapshots/{snapshot}/{relative}"] = payload
    pending[f"data/processed/snapshots/{snapshot}/processed_manifest.json"] = manifest_bytes
    npm_path = f".cache/pyodide-discovery/pyodide-{lock['pyodide_version']}.tgz"
    archive = inside(source, npm_path).read_bytes()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode()
    if integrity != lock["runtime_npm_integrity"]:
        raise ValueError("Pinned Pyodide npm archive integrity mismatch")
    pending[npm_path] = archive
    for entry in lock["packages"].values():
        relative = f".cache/pyodide/{lock['pyodide_version']}/{entry['file_name']}"
        payload = inside(source, relative).read_bytes()
        if digest(payload) != entry["sha256"] or len(payload) != entry["bytes"]:
            raise ValueError(f"Pinned scientific asset mismatch: {entry['file_name']}")
        pending[relative] = payload
    # Validate all destinations before copying; never replace different input bytes.
    for relative, payload in pending.items():
        path = inside(target, relative)
        if path.is_symlink() or (path.exists() and path.read_bytes() != payload):
            raise ValueError(f"Refusing to replace a different local input: {relative}")
    current = target / "data/processed/current"
    if current.exists() or current.is_symlink():
        if not current.is_symlink() or current.resolve() != destination.resolve():
            raise ValueError("Refusing to replace the current snapshot pointer")
    for relative, payload in pending.items():
        path = inside(target, relative)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if not current.is_symlink():
        current.symlink_to(f"snapshots/{snapshot}", target_is_directory=True)
    evidence = {
        "snapshot_id": snapshot,
        "source_checkout": str(source),
        "destination_checkout": str(target),
        "publication_approved": False,
        "network_requests": 0,
        "processed_manifest_sha256": digest(manifest_bytes),
        "files": {name: {"sha256": digest(b), "bytes": len(b)} for name, b in pending.items()},
        "total_bytes": sum(map(len, pending.values())),
    }
    output = inside(target, "runs/g4/input-seed.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", type=Path, required=True)
    args = parser.parse_args()
    result = seed(args.source)
    print(json.dumps({k: result[k] for k in ("snapshot_id", "total_bytes", "network_requests")}))
