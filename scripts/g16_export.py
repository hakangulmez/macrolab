"""Prepare local v2.0 successors on accepted public ancestry, without remotes."""

import json

from g9_export import inventory, local_commit
from p2_export_repo import ROOT, digest, git, plan


def main():
    out = ROOT / "runs/g16"
    assert json.loads((out / "verification-summary.json").read_text())["passed"]
    assert not git(ROOT, "status", "--porcelain", isolated=True).strip()
    report, files = plan(ROOT)
    assert not report["broken_local_markdown_links"], report["broken_local_markdown_links"]
    scope, mode = files["EXPORT_SCOPE.md"]
    scope = scope.replace(
        b"One new initial commit records this source tree. No original commits, remotes or "
        b"author history were copied. Publication remains unapproved.",
        b"One v2.0 candidate commit follows public main 23969e8. Public ancestry only; "
        b"private development history and remotes excluded. "
        b"Exact-artifact P6 approval is required.",
    )
    files["EXPORT_SCOPE.md"] = (scope, mode)
    parents = {
        "main": "23969e83edd419466bf8b2583989872e6da8df51",
        "gh-pages": "7db551465cbe99093ef2bad0ad2f07581c16c9de",
    }
    artifacts = {}
    for branch, folder in [("main", "sanitised-repo"), ("gh-pages", "pages-repo")]:
        payload = (
            files
            if branch == "main"
            else {
                r["path"]: ((out / "site" / r["path"]).read_bytes(), "100644")
                for r in inventory(out / "site")["files"]
            }
        )
        head = local_commit(
            ROOT / "runs/g10_1" / folder,
            out / folder,
            branch,
            parents[branch],
            payload,
            message="MacroLab v2.0: nine validated templates and audited October 24 snapshot",
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
        artifacts[branch] = dict(
            commit=head,
            parent=parents[branch],
            **{k: v for k, v in content.items() if k != "files"},
        )
    report.pop("files", None)
    report.pop("selected_source_sha256", None)
    report.update(
        file_count=artifacts["main"]["file_count"],
        total_bytes=artifacts["main"]["total_bytes"],
        source_patch_sha256=digest((out / "source.patch").read_bytes()),
    )
    report.update(
        artifacts=artifacts,
        published=False,
        remotes=[],
        private_history_copied=False,
        network_requests=0,
        development_head=git(ROOT, "rev-parse", "HEAD", isolated=True).decode().strip(),
    )
    (out / "candidate.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(artifacts, indent=2))


if __name__ == "__main__":
    main()
