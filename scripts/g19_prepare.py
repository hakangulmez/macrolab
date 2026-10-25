"""Build the v2.1 UI from the exact accepted P7 static payload; no network."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from g9_export import inventory
from ui_snapshot import create

ROOT = Path(__file__).resolve().parents[1]
P7_TREE = "908607a6eddbb76572b748c9c5b50a66e221d52786965263e21946ff8d7636e0"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-site", type=Path, default=ROOT / "runs/g17/site")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/g19")
    args = parser.parse_args()
    accepted, out = args.accepted_site.resolve(), args.output.resolve()
    assert accepted != out and accepted not in out.parents and out not in accepted.parents, (
        "Preserve the accepted site"
    )
    baseline = inventory(accepted)
    assert baseline["tree_sha256"] == P7_TREE, "Expected the exact accepted P7 site"
    assert not (out / "candidate.json").exists(), "An inventoried candidate is immutable"
    public = out / "public"
    public.mkdir(parents=True, exist_ok=True)
    for folder in ["data", "runtime", "licences", "schemas", "validation"]:
        shutil.copytree(accepted / folder, public / folder, dirs_exist_ok=True)
    shutil.copy2(accepted / ".nojekyll", public / ".nojekyll")
    shutil.copytree(
        ROOT / "third_party/fonts/jetbrains-mono",
        public / "licences/fonts/jetbrains-mono",
        dirs_exist_ok=True,
    )
    create(accepted, public / "ui/inflation.json")
    manifest = json.loads((public / "data/manifest.json").read_text())
    runtime = manifest["runtime"]
    wheel_file = Path(runtime["wheel_url"]).name
    wheel = {
        "wheel_file": wheel_file,
        "wheel_sha256": runtime["wheel_sha256"],
        "wheel_bytes": (public / "runtime" / wheel_file).stat().st_size,
        "code_version": runtime["code_version"],
        "source_archive_sha256": runtime["source_archive_sha256"],
    }
    (out / "runtime_wheel.json").write_text(json.dumps(wheel, indent=2) + "\n")
    shutil.copy2(public / "runtime" / wheel_file, out / wheel_file)
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
    shipped = {row["path"]: row for row in fresh["files"]}
    fixed = [
        row
        for row in baseline["files"]
        if not row["path"].startswith("assets/") and row["path"] != "index.html"
    ]
    for row in fixed:
        assert shipped[row["path"]] == row, row["path"]
    chunks = sorted(
        [row for row in fresh["files"] if row["path"].endswith(".js")],
        key=lambda row: row["bytes"],
        reverse=True,
    )
    assert chunks[0]["bytes"] < 500_000
    (out / "site-inventory.json").write_text(json.dumps(fresh, indent=2) + "\n")
    report = {
        "passed": True,
        "web_version": json.loads((ROOT / "web/package.json").read_text())["version"],
        "runtime_version": runtime["code_version"],
        "snapshot": manifest["snapshot_id"],
        "accepted_site_tree_sha256": P7_TREE,
        "byte_identical_payload_files": len(fixed),
        "network_requests": 0,
        "chunks": chunks,
        **{key: value for key, value in fresh.items() if key != "files"},
    }
    (out / "preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
