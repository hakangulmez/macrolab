"""Build the presentation release with byte-exact accepted P19 data/runtime."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from g9_export import inventory

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_TREE = "50c04a0a05527daeaddb1ea58984d68f2ab82a36f47cf8ee8d8a27feb0903e76"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accepted-site", type=Path, default=ROOT / "runs/g29/replacement/pages-repo"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "runs/g30/build")
    args = parser.parse_args()
    accepted, out = args.accepted_site.resolve(), args.output.resolve()
    assert accepted != out and accepted not in out.parents and out not in accepted.parents
    assert not (out / "candidate.json").exists(), "Inventoried candidates are immutable"
    before = inventory(accepted)
    assert before["tree_sha256"] == ACCEPTED_TREE
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
    by_path = {row["path"]: row for row in fresh["files"]}
    protected = [
        row
        for row in before["files"]
        if not row["path"].startswith("assets/") and row["path"] != "index.html"
    ]
    assert all(by_path[row["path"]] == row for row in protected)
    chunks = sorted(
        [row for row in fresh["files"] if row["path"].endswith(".js")],
        key=lambda row: row["bytes"],
        reverse=True,
    )
    assert chunks[0]["bytes"] < 500_000
    for name, payload in [
        ("site-inventory", fresh),
        ("protected-payload", {"passed": True, "files": protected, "allowlist": []}),
    ]:
        (out / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {"passed": True, "protected": len(protected), "largest_js_bytes": chunks[0]["bytes"]}
        )
    )


if __name__ == "__main__":
    main()
