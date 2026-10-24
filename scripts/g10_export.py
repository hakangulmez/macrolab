"""Local-only v1.1 candidates on accepted public ancestry; no remote operations."""

from __future__ import annotations

import json
import os

from g9_export import inventory, local_commit
from p2_export_repo import ROOT, digest, git, plan


def main():
    out = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g10")
    for name in (
        "browser-validation",
        "export-verification",
        "native-regression-v101",
        "native-regression",
        "v0-browser-regression",
    ):
        assert json.loads((out / f"{name}.json").read_text())["passed"], name
    if git(ROOT, "status", "--porcelain", isolated=True).strip():
        raise ValueError("Commit the reviewed development changes before export")
    report, files = plan(ROOT)
    assert not report["broken_local_markdown_links"], report["broken_local_markdown_links"]
    scope, mode = files["EXPORT_SCOPE.md"]
    scope = scope.replace(
        (
            b"One new initial commit records this source tree. No original commits, "
            b"remotes or author history were copied. Publication remains unapproved."
        ),
        (
            b"One v1.1 candidate commit follows public main d5ce053. Only public ancestry "
            b"is retained; private development history and remotes are excluded. "
            b"Exact-artifact P5 approval is required before publication."
        ),
    )
    files["EXPORT_SCOPE.md"] = (scope, mode)
    parents = {
        "main": "d5ce0535b42aaeb61767f575f3a86ae2ac2ffe97",
        "gh-pages": "fc5a603e659c1b5ee3ed74fb2dc9d70c5c0b8d72",
    }
    artifacts = {}
    for branch, folder in (("main", "sanitised-repo"), ("gh-pages", "pages-repo")):
        payload = (
            files
            if branch == "main"
            else {
                r["path"]: ((out / "site" / r["path"]).read_bytes(), "100644")
                for r in inventory(out / "site")["files"]
            }
        )
        head = local_commit(
            ROOT / "runs/v101" / folder,
            out / folder,
            branch,
            parents[branch],
            payload,
            message="MacroLab v1.1: historical decomposition and optional crisis analysis",
        )
        content = inventory(out / folder)
        assert {r["path"]: r["sha256"] for r in content["files"]} == {
            p: digest(v[0]) for p, v in payload.items()
        }
        (out / f"{folder}-inventory.json").write_text(json.dumps(content, indent=2) + "\n")
        (out / f"{folder}-files.txt").write_text(
            "\n".join(r["path"] for r in content["files"]) + "\n"
        )
        if branch == "main":
            (out / "source.patch").write_bytes(
                git(out / folder, "diff", "--binary", parents[branch], "HEAD", isolated=True)
            )
            (out / "source-diff.txt").write_bytes(
                git(out / folder, "diff", "--stat", parents[branch], "HEAD", isolated=True)
            )
        else:
            assert inventory(out / "site") == content
        artifacts[branch] = {
            "commit": head,
            "parent": parents[branch],
            **{k: v for k, v in content.items() if k != "files"},
        }
    report.pop("files", None)
    report.update(
        artifacts=artifacts,
        published=False,
        network_requests=0,
        remotes=[],
        development_head=git(ROOT, "rev-parse", "HEAD", isolated=True).decode().strip(),
    )
    (out / "candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(artifacts, indent=2))


if __name__ == "__main__":
    main()
