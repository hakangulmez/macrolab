"""Prepare local, sanitised P4 commits from the accepted public branch ancestry."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from p2_export_repo import EMAIL, NAME, ROOT, digest, git, plan


def inventory(directory: Path) -> dict:
    files = []
    sizes: dict[str, int] = defaultdict(int)
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"Candidate symlink: {relative}")
        content = path.read_bytes()
        files.append({"path": str(relative), "bytes": len(content), "sha256": digest(content)})
        sizes[relative.parts[0]] += len(content)
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "by_top_directory": dict(sizes),
        "tree_sha256": digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()),
    }


def local_commit(
    source: Path,
    target: Path,
    branch: str,
    base: str,
    files: dict,
    *,
    message: str = "MacroLab v1.0: reviewed release candidate, 23 October snapshot",
) -> str:
    if target.exists():
        raise ValueError("Never overwrite an existing reviewed candidate")
    if git(source, "rev-parse", "HEAD", isolated=True).decode().strip() != base:
        raise ValueError("Accepted public base moved")
    git(
        ROOT,
        "clone",
        "--no-hardlinks",
        "--single-branch",
        "--branch",
        branch,
        str(source),
        str(target),
        isolated=True,
    )
    git(target, "remote", "remove", "origin", isolated=True)
    for path in git(target, "ls-files", "-z", isolated=True).decode().split("\0"):
        if path:
            (target / path).unlink()
    for name, (content, mode) in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if mode == "100755" else 0o644)
    git(target, "add", "--all", isolated=True)
    git(
        target,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        message,
        isolated=True,
    )
    assert git(target, "rev-parse", "HEAD^", isolated=True).decode().strip() == base
    assert not git(target, "remote", isolated=True).strip()
    assert not git(target, "status", "--porcelain", isolated=True).strip()
    identity = git(target, "log", "-1", "--format=%an%n%ae%n%cn%n%ce", isolated=True)
    assert identity.decode().splitlines() == [NAME, EMAIL, NAME, EMAIL]
    return git(target, "rev-parse", "HEAD", isolated=True).decode().strip()


def main():
    out = ROOT / "runs/g9"
    if git(ROOT, "diff", "--name-only", "--", isolated=True).strip():
        raise ValueError("Commit the reviewed development changes before export")
    report, files = plan(ROOT)
    if report["broken_local_markdown_links"]:
        raise ValueError(report["broken_local_markdown_links"])
    scope, mode = files["EXPORT_SCOPE.md"]
    scope = scope.replace(
        b"One new initial commit records this source tree. No original commits, "
        b"remotes or author history were copied. Publication remains unapproved.",
        b"One candidate commit follows the already-public main commit 0dfffd6. "
        b"Only public ancestry is retained; private development history and remotes "
        b"are excluded. This local candidate awaits separate P4 publication approval.",
    )
    files["EXPORT_SCOPE.md"] = (scope, mode)
    source = ROOT / "runs/p2/sanitised-repo"
    source_base = git(source, "rev-parse", "0dfffd6", isolated=True).decode().strip()
    source_target = out / "sanitised-repo"
    source_commit = local_commit(source, source_target, "main", source_base, files)
    source_inventory = inventory(source_target)
    assert set(files) == {r["path"] for r in source_inventory["files"]}
    for item in source_inventory["files"]:
        assert item["sha256"] == digest(files[item["path"]][0])
    (out / "source.patch").write_bytes(
        git(source_target, "diff", "--binary", source_base, "HEAD", isolated=True)
    )
    (out / "source-diff.txt").write_bytes(
        git(source_target, "diff", "--stat", source_base, "HEAD", isolated=True)
    )
    (out / "source-files.txt").write_text(
        "\n".join(r["path"] for r in source_inventory["files"]) + "\n"
    )
    site_inventory = inventory(out / "site")
    site_files = {
        r["path"]: ((out / "site" / r["path"]).read_bytes(), "100644")
        for r in site_inventory["files"]
    }
    assert site_files[".nojekyll"][0] == b""
    pages = ROOT / "runs/publication/pages-repo"
    pages_base = git(pages, "rev-parse", "5002f83", isolated=True).decode().strip()
    pages_target = out / "pages-repo"
    pages_commit = local_commit(pages, pages_target, "gh-pages", pages_base, site_files)
    assert inventory(pages_target) == site_inventory
    (out / "site-files.txt").write_text(
        "\n".join(r["path"] for r in site_inventory["files"]) + "\n"
    )
    report.update(
        source_commit=source_commit,
        source_parent=source_base,
        source_inventory=source_inventory,
        pages_commit=pages_commit,
        pages_parent=pages_base,
        site_inventory=site_inventory,
        publication_approved=False,
        network_requests=0,
        remotes=[],
        private_history_copied=False,
        readback_passed=True,
        source_patch_sha256=digest((out / "source.patch").read_bytes()),
        source_commit_count=int(git(source_target, "rev-list", "--all", "--count", isolated=True)),
        source_git_bytes=sum(
            p.stat().st_size for p in (source_target / ".git").rglob("*") if p.is_file()
        ),
    )
    # The final inventories include the G9-only EXPORT_SCOPE text, unlike the P2 plan.
    report.pop("selected_source_sha256", None)
    report.pop("files", None)
    report["file_count"] = source_inventory["file_count"]
    report["total_bytes"] = source_inventory["total_bytes"]
    for name, value in [
        ("candidate.json", report),
        ("site-inventory.json", site_inventory),
        ("source-inventory.json", source_inventory),
    ]:
        (out / name).write_text(json.dumps(value, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "source_commit",
                    "pages_commit",
                    "source_parent",
                    "pages_parent",
                    "file_count",
                    "total_bytes",
                    "source_commit_count",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
