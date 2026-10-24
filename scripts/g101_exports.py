"""Audit every G10.1 download against G10, including embedded offline inputs."""

from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD, NEW = ROOT / "runs/g10", ROOT / "runs/g10_1"


def copy_update(value: str) -> str:
    return value.replace(
        "Shadow rates are not available in v0.",
        "Shadow rates are not available in MacroLab.",
    ).replace("January 2003 onward (existing row)", "January 2003 onward")


def same_existing(a, b, path="") -> int:
    """Check all existing values; only approved prose and runtime metadata differ."""
    if path.endswith("/runtime_ms") or path.endswith("/source_archive_sha256"):
        return 0
    if path == "/crisis_analysis/agreement_rule":
        assert "more than 50%" in b and "not a significance test" in b
        return 0
    if isinstance(a, dict):
        assert isinstance(b, dict), path
        return sum(same_existing(v, b[k], path + "/" + k) for k, v in a.items())
    if isinstance(a, list):
        if path == "/crisis_analysis/agreement":
            b = [next(v for v in b if v["horizon"] == old["horizon"]) for old in a]
        assert len(a) == len(b), path
        return sum(
            same_existing(x, y, path + "/" + str(i))
            for i, (x, y) in enumerate(zip(a, b, strict=True))
        )
    if isinstance(a, str):
        assert copy_update(a) == b, path
    else:
        assert a == b, (path, a, b)
    return int(isinstance(a, (int, float)) and not isinstance(a, bool))


def python_parts(path):
    out = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"INPUTS", "SOURCE_ARCHIVE"}:
                out[name] = ast.literal_eval(node.value)
            elif name == "METADATA":
                out[name] = json.loads(ast.literal_eval(node.value.args[0]))
    return out


def main():
    rows = []
    old_files = {p.name for p in (OLD / "downloads").iterdir() if p.is_file()}
    new_files = {p.name for p in (NEW / "downloads").iterdir() if p.is_file()}
    assert old_files == new_files
    for name in sorted(old_files):
        before, after = OLD / "downloads" / name, NEW / "downloads" / name
        a, b = before.read_bytes(), after.read_bytes()
        row = {
            "file": name,
            "changed": a != b,
            "before_sha256": hashlib.sha256(a).hexdigest(),
            "after_sha256": hashlib.sha256(b).hexdigest(),
            "bytes": len(b),
        }
        if a == b:
            row["assessment"] = "Byte-identical"
        elif after.suffix == ".py":
            x, y = python_parts(before), python_parts(after)
            assert x["INPUTS"] == y["INPUTS"]
            same_existing(x["METADATA"], y["METADATA"])
            xa = zipfile.ZipFile(io.BytesIO(base64.b64decode(x["SOURCE_ARCHIVE"])))
            ya = zipfile.ZipFile(io.BytesIO(base64.b64decode(y["SOURCE_ARCHIVE"])))
            assert xa.namelist() == ya.namelist()
            changed = [f for f in xa.namelist() if xa.read(f) != ya.read(f)]
            assert changed == ["macrolab/analysis/crisis.py", "macrolab/checks/core.py"]
            for f in changed:
                xa.read(f).decode()
                ya.read(f).decode()
            count = same_existing(
                json.loads((OLD / f"{after.stem}.export-result.json").read_text()),
                json.loads((NEW / f"{after.stem}.export-result.json").read_text()),
            )
            row.update(
                existing_numeric_fields_exact=count,
                embedded_inputs_byte_identical=True,
                assessment=(
                    "Text source bundle/hash updated; identical inputs "
                    "and existing numerical outputs"
                ),
            )
        elif after.suffix == ".csv":
            x = list(csv.DictReader(io.StringIO(a.decode())))
            y = list(csv.DictReader(io.StringIO(b.decode())))
            assert len(x) == len(y)
            for old, new in zip(x, y, strict=True):
                assert set(new) - set(old) <= {"magnitude_assessment"}
                for k, v in old.items():
                    assert copy_update(v) == new[k], (name, k)
            row["assessment"] = (
                "Text-only: label cleanup and descriptive magnitude assessment"
                if name == "crisis.csv"
                else "Text-only: approved shadow-rate sentence"
            )
        elif after.suffix == ".json":
            count = same_existing(json.loads(a), json.loads(b))
            row.update(
                existing_numeric_fields_exact=count,
                assessment=(
                    "Scientific values exact; new crisis summaries and run-time metadata"
                    if name == "crisis.json"
                    else "Text-only warning and run-time metadata; HD precision unchanged"
                ),
            )
        else:
            raise AssertionError(f"Unexpected changed binary: {name}")
        rows.append(row)
    result = {
        "passed": True,
        "exports": rows,
        "changed_count": sum(r["changed"] for r in rows),
        "unchanged_count": sum(not r["changed"] for r in rows),
    }
    (NEW / "export-diff.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# G10.1 export byte audit",
        "",
        "Compared all downloads with the preserved G10 exports. "
        "Every existing scientific value is exact. "
        "Python inputs are byte-identical; only two embedded UTF-8 source files "
        "and their hash changed. "
        "The warning correction is text-only. The crisis JSON additionally carries the requested "
        "derived ranges and materiality metadata; it is not a change to estimated responses. "
        "JSON runtime_ms records naturally differ between runs. PNG binaries are byte-identical.",
        "",
        "| Changed export | Verified difference |",
        "|---|---|",
    ]
    lines.extend(f"| `{r['file']}` | {r['assessment']} |" for r in rows if r["changed"])
    lines += [
        "",
        f"Changed: {result['changed_count']}; byte-identical: {result['unchanged_count']}. "
        "Full before/after hashes: `export-diff.json`.",
    ]
    (NEW / "EXPORT_DIFF.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "exports"}))


if __name__ == "__main__":
    main()
