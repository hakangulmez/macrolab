"""Build locally from the accepted v2.4.0 payload and the approved annual fix."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from build_runtime_assets import build_wheel
from g9_export import inventory

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_TREE = "6ca99e2ad049a146c1bfc6c4f86e243d7905c1a567923dc38671da09135a8f63"
APPROVED_WHEEL = "a719d9f1dfdb8c7224c227ecde95d1ed4d43fd4d45bba2cfb6c28e311db88a57"
APPROVED_SOURCE = "cb34cc205d1414eb941124e733b8e7c9fe230e0431274fd07b801b961fced3ea"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-site", type=Path, default=ROOT / "runs/g27/pages-repo")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/g28/static-build")
    args = parser.parse_args()
    accepted, out = args.accepted_site.resolve(), args.output.resolve()
    assert accepted != out and accepted not in out.parents and out not in accepted.parents
    assert not (out / "candidate.json").exists(), "Inventoried candidates are immutable"
    baseline = inventory(accepted)
    assert baseline["tree_sha256"] == ACCEPTED_TREE, "Expected exact accepted v2.4.0 site"
    out.mkdir(parents=True, exist_ok=True)
    public = out / "public"
    public.mkdir(exist_ok=True)
    for source in accepted.iterdir():
        if source.name in {".git", "assets", "index.html"}:
            continue
        target = public / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    # Build only the application wheel. No downloads or dependency rebuilds.
    wheel = build_wheel(out)
    assert wheel["wheel_sha256"] == APPROVED_WHEEL
    assert wheel["source_archive_sha256"] == APPROVED_SOURCE
    original = (accepted / "data/manifest.json").read_bytes()
    manifest = json.loads(original)
    runtime = manifest["runtime"]
    assert wheel["code_version"] == runtime["code_version"]
    wheel_path = runtime["wheel_url"]
    assert Path(wheel_path).name == wheel["wheel_file"]
    shutil.copy2(out / wheel["wheel_file"], public / wheel_path)
    expected = json.loads(original)
    updated = original
    fields = ["wheel_sha256", "source_archive_sha256"]
    for key in fields:
        assert updated.count(runtime[key].encode()) == 1
        updated = updated.replace(runtime[key].encode(), wheel[key].encode())
        expected["runtime"][key] = wheel[key]
    assert json.loads(updated) == expected
    (public / "data/manifest.json").write_bytes(updated)
    assert (ROOT / "web/runtime/worker.mjs").read_bytes() == (
        accepted / "runtime/worker.mjs"
    ).read_bytes()
    with (out / "build.log").open("w") as log:
        subprocess.run(
            ["npm", "run", "build", "--", "--emptyOutDir"],
            cwd=ROOT / "web",
            env={
                **os.environ,
                "MACROLAB_BASE_PATH": "/macrolab/",
                "MACROLAB_PUBLIC_DIR": str(public),
                "MACROLAB_BUILD_DIR": str(out / "site"),
            },
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    fresh = inventory(out / "site")
    by_path = {r["path"]: r for r in fresh["files"]}
    protected = [
        r
        for r in baseline["files"]
        if not r["path"].startswith("assets/") and r["path"] != "index.html"
    ]
    allowlist = {wheel_path, "data/manifest.json"}
    assert all(by_path[r["path"]] == r for r in protected if r["path"] not in allowlist)
    assert by_path[wheel_path]["sha256"] == wheel["wheel_sha256"]
    assert (out / "site/data/manifest.json").read_bytes() == updated
    chunks = sorted(
        [r for r in fresh["files"] if r["path"].endswith(".js")],
        key=lambda r: r["bytes"],
        reverse=True,
    )
    assert chunks[0]["bytes"] < 500_000
    report = {
        "passed": True,
        "allowlist": sorted(allowlist),
        "manifest_fields": ["runtime." + k for k in fields],
        "files": [
            {
                "path": r["path"],
                "old_sha256": r["sha256"],
                "new_sha256": by_path[r["path"]]["sha256"],
                "unchanged": r == by_path[r["path"]],
            }
            for r in protected
        ],
    }
    for name, value in [
        ("protected-payload", report),
        ("site-inventory", fresh),
        ("runtime_wheel", wheel),
    ]:
        (out / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "files": fresh["file_count"],
                "protected": len(protected),
                "largest_js_bytes": chunks[0]["bytes"],
                "output": str(out),
            }
        )
    )


if __name__ == "__main__":
    main()
