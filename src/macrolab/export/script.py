"""Portable offline Python exports containing the exact model sources and data bundle."""

from __future__ import annotations

import base64
import hashlib
import io
import platform
import zipfile
import zlib
from importlib.metadata import version
from pathlib import Path
from typing import Any

DEPENDENCIES = ("numpy", "pandas", "scipy", "statsmodels", "patsy", "packaging")


def source_archive() -> bytes:
    """Archive only the portable analysis package; no dataset, API or credential files."""
    package = Path(__file__).resolve().parents[1]
    files = [package / "__init__.py"]
    for folder in ("analysis", "models", "checks", "export", "outputs", "ident", "compare"):
        files.extend((package / folder).rglob("*.py"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            if path.is_symlink() or not path.resolve().is_relative_to(package):
                raise ValueError("Runtime sources must remain inside the MacroLab package")
            item = zipfile.ZipInfo("macrolab/" + path.relative_to(package).as_posix())
            item.date_time = (2026, 1, 1, 0, 0, 0)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, path.read_bytes())
    return output.getvalue()


def config_script(config: dict[str, Any]) -> str:
    """Resolve the named local vintage and export a fully self-contained analysis."""
    from macrolab.analysis.config import normalise_config, required_concepts, required_countries
    from macrolab.analysis.data import snapshot_bundle

    normalised = normalise_config(config)
    bundle = snapshot_bundle(
        normalised["snapshot_id"],
        required_countries(normalised),
        required_concepts(normalised),
    )
    if normalised["model"]["params"].get("template_id") == "same_ecb_shock_pooled" or (
        normalised["model"]["id"] == "test.break"
        and normalised["model"]["params"].get("source_variant", "none") != "none"
    ):
        from macrolab.analysis.engine import _inputs

        bundle = _inputs(normalised, None)
    return standalone(normalised, bundle)


def standalone(
    config: dict[str, Any],
    bundle: dict[str, Any],
    reproduction_environment: dict[str, Any] | None = None,
    method_pair: dict[str, str] | None = None,
) -> str:
    """Embed inputs, exact source and expected sample; dependencies must already be installed."""
    from macrolab.analysis.config import canonical_json
    from macrolab.analysis.engine import run_analysis

    reference = run_analysis(config, bundle=bundle)
    if reference.get("status") != "ok":
        raise ValueError("Resolve blocking compatibility checks before exporting an analysis")
    if method_pair:
        from macrolab.compare.methods import matched_pair

        if matched_pair(config, bundle, **method_pair)["status"] != "ok":
            raise ValueError("Resolve matched-comparison checks before exporting")
    archive = source_archive()
    inputs = canonical_json({"config": reference["config"], "bundle": bundle}).encode()
    generated_with = {
        "python_version": platform.python_version(),
        "dependencies": {name: version(name) for name in DEPENDENCIES},
    }
    target = reproduction_environment or generated_with
    if (
        set(target) != {"python_version", "dependencies"}
        or not isinstance(target["python_version"], str)
        or not isinstance(target["dependencies"], dict)
        or set(target["dependencies"]) != set(DEPENDENCIES)
        or not all(isinstance(value, str) and value for value in target["dependencies"].values())
    ):
        raise ValueError("Reproduction environment must explicitly pin Python and every dependency")
    metadata = {
        "schema_version": 1,
        "snapshot_id": reference["snapshot_id"],
        "config_hash": reference["config_hash"],
        "code_version": reference["code_version"],
        "python_version": target["python_version"],
        "dependencies": target["dependencies"],
        "generated_with": generated_with,
        "numerical_tolerance": 1e-8,
        "reproduction_target": "declared native environment"
        if reproduction_environment
        else "generation environment",
        "source_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "inputs_sha256": hashlib.sha256(inputs).hexdigest(),
        "actual_samples": reference["actual_samples"],
        "publication_approved": False,
    }
    if method_pair:
        metadata["method_pair"] = method_pair
    return (
        _TEMPLATE.replace("__METADATA_LITERAL__", repr(canonical_json(metadata)))
        .replace("__SOURCE_LITERAL__", repr(base64.b64encode(archive).decode()))
        .replace("__INPUT_LITERAL__", repr(base64.b64encode(zlib.compress(inputs, 9)).decode()))
    )


_TEMPLATE = '''#!/usr/bin/env python3
"""MacroLab offline reproduction: python macrolab_analysis.py > result.json.

This script embeds its configuration, snapshot observations and exact Python model
sources. It downloads nothing and needs no MacroLab checkout. Install the dependency
versions shown in METADATA separately before running. Data remains DRAFT/local-only;
export is not permission to redistribute source observations or publish results.
METADATA records the generation runtime separately when this download targets the
validated native Python environment. Browser and native results use numerical,
not bit-for-bit, equivalence.
"""
import base64
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import zipfile
import zlib

METADATA = json.loads(__METADATA_LITERAL__)
SOURCE_ARCHIVE = __SOURCE_LITERAL__
INPUTS = __INPUT_LITERAL__


def same_sample(expected, actual):
    if isinstance(expected, dict) and isinstance(actual, dict):
        return set(expected) == set(actual) and all(
            same_sample(expected[key], actual[key]) for key in expected
        )
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            same_sample(left, right) for left, right in zip(expected, actual)
        )
    if type(expected) is float and type(actual) is float:
        return math.isfinite(expected) and math.isfinite(actual) and math.isclose(
            expected, actual, rel_tol=0, abs_tol=METADATA["numerical_tolerance"]
        )
    return type(expected) is type(actual) and expected == actual


def main():
    missing = []
    for name, expected in METADATA["dependencies"].items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            missing.append(f"{name}=={expected} (found {actual})")
    if missing:
        raise SystemExit("Reproduction requires: " + "; ".join(missing))
    source = base64.b64decode(SOURCE_ARCHIVE)
    inputs = zlib.decompress(base64.b64decode(INPUTS))
    if hashlib.sha256(source).hexdigest() != METADATA["source_archive_sha256"]:
        raise SystemExit("Embedded source checksum does not match")
    if hashlib.sha256(inputs).hexdigest() != METADATA["inputs_sha256"]:
        raise SystemExit("Embedded input checksum does not match")
    data = json.loads(inputs)
    with tempfile.TemporaryDirectory(prefix="macrolab-reproduce-") as temporary:
        target = Path(temporary).resolve()
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            if any(not (target / name).resolve().is_relative_to(target)
                   for name in archive.namelist()):
                raise SystemExit("Unsafe embedded archive path")
            archive.extractall(target)
        sys.path.insert(0, str(target))
        os.environ["MACROLAB_CODE_VERSION"] = METADATA["code_version"]
        import macrolab
        if not Path(macrolab.__file__).resolve().is_relative_to(target):
            raise SystemExit("Reproduction did not import the embedded source package")
        from macrolab.analysis.engine import run_analysis
        result = run_analysis(data["config"], bundle=data["bundle"])
        if result["config_hash"] != METADATA["config_hash"]:
            raise SystemExit("Reproduced configuration hash differs")
        if not same_sample(METADATA["actual_samples"], result["actual_samples"]):
            raise SystemExit("Reproduced actual sample or transformation metadata differs")
        if METADATA.get("method_pair"):
            from macrolab.compare.methods import matched_pair
            result["method_pair"] = matched_pair(
                data["config"], data["bundle"], **METADATA["method_pair"]
            )
        result["export_metadata"] = METADATA
        print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
'''
