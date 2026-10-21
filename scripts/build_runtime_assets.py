"""Build a local-only Pyodide runtime from pinned, explicitly approved artifacts."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "web/runtime/assets.lock.json"
LIMIT = 100 * 1024 * 1024


class ExactArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Do not expand the human-approved nine-URL exception through redirects."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        raise ValueError(f"Unexpected artifact redirect refused: {newurl}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(download: bool = False) -> dict[str, Any]:
    lock = json.loads(LOCK.read_text())
    target = ROOT / ".cache/pyodide" / lock["pyodide_version"]
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT / ".cache/pyodide-discovery" / f"pyodide-{lock['pyodide_version']}.tgz"
    tar_bytes = source.read_bytes()
    actual_integrity = "sha512-" + base64.b64encode(hashlib.sha512(tar_bytes).digest()).decode()
    if actual_integrity != lock["runtime_npm_integrity"]:
        raise ValueError("npm runtime archive integrity differs from the reviewed lock")
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as archive:
        for name, expected in lock["runtime_files"].items():
            member = archive.extractfile(f"package/{name}")
            if member is None:
                raise ValueError(f"Missing runtime member: {name}")
            payload = member.read()
            if len(payload) != expected["bytes"] or sha256(payload) != expected["sha256"]:
                raise ValueError(f"Runtime member checksum mismatch: {name}")
            (target / name).write_bytes(payload)
    opener = urllib.request.build_opener(ExactArtifactRedirect)
    total = 0
    packages = {}
    for name, entry in lock["packages"].items():
        path = target / entry["file_name"]
        if path.exists():
            payload = path.read_bytes()
        elif download:
            expected_url = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/" + entry["file_name"]
            if entry["url"] != expected_url:
                raise ValueError("Artifact URL differs from the approved pinned CDN path")
            request = urllib.request.Request(entry["url"], headers={"Accept": "application/zip"})
            with opener.open(request, timeout=60) as response:
                payload = response.read(LIMIT - total + 1)
        else:
            raise FileNotFoundError(f"Pinned asset is not cached: {path.name}")
        total += len(payload)
        if total > LIMIT:
            raise ValueError("Approved 100 MiB scientific-asset ceiling exceeded")
        if sha256(payload) != entry["sha256"]:
            raise ValueError(f"Scientific asset checksum mismatch: {name}")
        if not path.exists():
            path.write_bytes(payload)
        entry["bytes"] = len(payload)
        packages[name] = dict(entry)
        print(f"Verified {name} {entry['version']}: {len(payload):,} bytes", flush=True)
    lock["scientific_total_bytes"] = total
    lock["size_note"] = (
        "All nine approved artifacts were downloaded once to the project cache and SHA-256 "
        "verified against the official npm Pyodide lock. No additional CDN files are required."
    )
    if lock != json.loads(LOCK.read_text()):
        LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    manifest = {
        "schema_version": 1,
        "pyodide_version": lock["pyodide_version"],
        "runtime_info": lock["runtime_info"],
        "runtime_npm_integrity": actual_integrity,
        "runtime_files": lock["runtime_files"],
        "packages": packages,
        "scientific_total_bytes": total,
        "runtime_total_bytes": sum(item["bytes"] for item in lock["runtime_files"].values()),
        "download_byte_limit": LIMIT,
        "all_hashes_verified": True,
        "local_directory": str(target.relative_to(ROOT)),
    }
    output = ROOT / "runs/g2"
    output.mkdir(parents=True, exist_ok=True)
    (output / "runtime_assets.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def build_wheel(output_dir: Path | None = None) -> dict[str, Any]:
    """Package the exact portable model source, excluding data ingestion and HTTP services."""
    import macrolab
    from macrolab import __version__
    from macrolab.export import script as export_script
    from macrolab.export.script import source_archive

    package_root = ROOT.resolve() / "src/macrolab"
    for module, relative in ((macrolab, "__init__.py"), (export_script, "export/script.py")):
        path = Path(module.__file__).resolve() if module.__file__ else None
        if (
            path is None
            or path != (package_root / relative).resolve()
            or not path.is_relative_to(package_root)
        ):
            raise ValueError(
                "Runtime source must be imported from this checkout's src/macrolab; "
                "use its own editable installation and remove conflicting PYTHONPATH entries"
            )
    source = source_archive()
    dist = f"macrolab_runtime-{__version__}.dist-info"
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files[f"{dist}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: MacroLab local runtime builder\n"
        b"Root-Is-Purelib: true\nTag: py3-none-any\n"
    )
    files[f"{dist}/METADATA"] = (
        f"Metadata-Version: 2.4\nName: macrolab-runtime\nVersion: {__version__}\n"
        "Summary: Exact portable MacroLab analysis sources\nRequires-Python: >=3.11\n"
    ).encode()
    record = io.StringIO(newline="")
    writer = csv.writer(record)
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", len(data)])
    writer.writerow([f"{dist}/RECORD", "", ""])
    files[f"{dist}/RECORD"] = record.getvalue().encode()
    output = output_dir if output_dir is not None else ROOT / "runs/g2"
    if not output.resolve().is_relative_to((ROOT / "runs").resolve()):
        raise ValueError(
            "Runtime wheel output must remain inside the project's ignored runs directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    wheel = output / f"macrolab_runtime-{__version__}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, payload)
    manifest = {
        "code_version": __version__,
        "source_archive_sha256": sha256(source),
        "wheel_sha256": sha256(wheel.read_bytes()),
        "wheel_bytes": wheel.stat().st_size,
        "wheel_file": wheel.name,
        "source_files": {
            name: sha256(payload) for name, payload in files.items() if name.endswith(".py")
        },
    }
    (output / "runtime_wheel.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-approved-assets", action="store_true")
    parser.add_argument("--wheel-only", action="store_true")
    arguments = parser.parse_args()
    if not arguments.wheel_only:
        build(arguments.download_approved_assets)
    print(json.dumps(build_wheel(), indent=2))
