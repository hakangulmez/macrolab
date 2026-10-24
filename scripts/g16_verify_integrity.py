"""Readback all protected inputs and pinned assets; disclose evidence-file deviations."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g16"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = json.loads((OUT / "accepted-files-before.json").read_text())
    changed = []
    for name, old in before.items():
        p = ROOT / name
        assert p.exists(), name
        after = dict(bytes=p.stat().st_size, sha256=sha(p))
        if old != after:
            changed.append(dict(path=name, before=old, after=after))
    disclosure = json.loads((OUT / "evidence-overwrite.json").read_text())
    assert {r["path"] for r in changed} == {r["path"] for r in disclosure["files"]}
    assert not any(r["path"].startswith("data/") for r in changed)
    runtime = []
    for folder in ["runtime/pyodide", "licences/runtime"]:
        for old in sorted((ROOT / "runs/g10_1/site" / folder).rglob("*")):
            if not old.is_file():
                continue
            rel = old.relative_to(ROOT / "runs/g10_1/site")
            fresh = OUT / "site" / rel
            assert fresh.read_bytes() == old.read_bytes(), rel
            runtime.append(dict(path=str(rel), sha256=sha(fresh), bytes=fresh.stat().st_size))
    m = json.loads((OUT / "site/data/manifest.json").read_text())
    for name, metadata in m["country_files"].items():
        p = OUT / "site/data/countries" / (name + ".json")
        assert sha(p) == metadata["sha256"]
        assert p.stat().st_size == metadata["bytes"]
        assert not json.loads(p.read_text())["country"].get("notes")

    def snapshot_neutral(v):
        if isinstance(v, dict):
            return {k: snapshot_neutral(x) for k, x in v.items() if k != "snapshot_id"}
        if isinstance(v, list):
            return [snapshot_neutral(x) for x in v]
        return v

    for t in m["templates"]:
        original = json.loads((ROOT / "configs/templates" / (t["id"] + ".json")).read_text())
        assert snapshot_neutral(t["config"]) == snapshot_neutral(original), t["id"]
    result = dict(
        passed=True,
        protected_files=len(before),
        unchanged_files=len(before) - len(changed),
        old_snapshot_and_raw_files_unchanged=sum(p.startswith("data/") for p in before),
        disclosed_evidence_overwrites=changed,
        pinned_files=runtime,
        country_file_hashes_verified=len(m["country_files"]),
        country_narratives="withheld",
        unchanged_template_defaults=len(m["templates"]),
    )
    (OUT / "integrity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        {
            k: v
            for k, v in result.items()
            if k not in ["pinned_files", "disclosed_evidence_overwrites"]
        }
    )


if __name__ == "__main__":
    main()
