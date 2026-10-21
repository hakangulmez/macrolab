"""Prepare a selective source export without full input datasets or old history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
NAME = "Hakan Zeki Gülmez"
EMAIL = "hakanzekigulmez@gmail.com"
PUBLIC_DOCS = {
    "SOURCES.md",
    "OECD_MAPPING_NOTES.md",
    "SUPPLEMENTAL_MAPPING_NOTES.md",
    "WORLDBANK_MAPPING_NOTES.md",
    "G1_1_PRICE_SOURCES.md",
    "G1_1_CLI_SOURCES.md",
    "P1_SOFTWARE_NOTICES.md",
    "P2_OECD_METADATA_REVIEW.md",
    "P2_OECD_METADATA_REVIEW.json",
    "P2_EIA_AUDIT.md",
    "P2_STATIC_REVIEW.md",
}
PRIVATE_ROOTS = (
    "data/",
    "runs/",
    ".cache/",
    ".venv/",
    "web/node_modules/",
    "web/dist/",
    "dist/",
    "build/",
    ".git/",
)
README = """# MacroLab

Explore, model and stress-test macroeconomic relationships across countries.
MacroLab provides 33 national indicators, two included P2 global factors, twelve v0 methods,
four template configurations, visible data checks, sensitivity comparisons and
reproducible exports. Models include single-equation regressions, VARs, recursive
identification, filters, stationarity tests and descriptive comparisons.
The commodity index remains visibly excluded; Brent uses EIA and the US policy
factor uses BIS.

This is a **source-only local export** with a new Git history. It contains no
full input datasets, review screenshots, generated result arrays, compiled site,
runtime binaries, dependency cache or country narratives. Synthetic test fixtures
and three public-domain EIA audit observations remain documented. No push,
deployment or publication is performed by this export.

## Install and check

Use an existing Python 3.11 and a Node version satisfying `web/package.json`, plus
`uv` on PATH. Dependencies are pinned by `uv.lock` and `web/package-lock.json`.

```sh
make setup
make quick
make test lint typecheck
# Compile the interface source; this does not prepare a data-bearing site:
cd web && npm run build
```

Setup retrieves dependencies from PyPI/npm; Python auto-downloads and npm lifecycle
scripts are disabled. `make quick` uses seeded synthetic data without network.
Tests use local fixtures/mocks; checks that require an accepted private snapshot
are skipped when it is absent. No data is fetched by these checking commands.

## Data and a runnable local site

Real-data operation additionally needs an independently obtained, verified snapshot
and the exact scientific runtime assets listed in `web/runtime/assets.lock.json`.
Those assets and full input datasets are deliberately absent here. Review [data terms and
publication policy](DATA.md) before preparing any data-bearing artifact. Source
retrieval is an explicit operation; `make data` fetches from the configured official
providers. Local preparation commands do not silently retrieve missing runtime files.

The original gate-specific seeding/report commands refer to private review evidence
that this source export omits. They are retained as development utilities, not as a
claim that the original local review can be reconstructed from code alone. Public
country metadata retains adoption/currency/source fields while narrative notes are
empty; candidate preparation also withholds generated narratives.

## Documentation

- [Model methods](docs/models/README.md)
- [Source mappings and transformations](docs/SOURCES.md)
- [Data attribution and redistribution policy](DATA.md)
- [Software notices](docs/P1_SOFTWARE_NOTICES.md)
- [Pinned runtime notices and source availability](third_party/runtime/SOURCE_AVAILABILITY.md)
- [Explicit export omissions and modifications](EXPORT_SCOPE.md)

MacroLab code is MIT licensed; third-party code, fonts and data retain their own
terms. A shared configuration is not a data licence or publication approval.
"""
PATTERNS = {
    "personal_path": re.compile(r"/(?:Users|home)/[^\s\"'`<>]+"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "openai_key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b"),
    "credential_url": re.compile(r"https?://[^/\s:@]+:[^/\s@]+@"),
}


def git(root: Path, *args: str, isolated: bool = False) -> bytes:
    env = os.environ.copy()
    if isolated:
        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_COMMON_DIR",
        ):
            env.pop(key, None)
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_AUTHOR_NAME=NAME,
            GIT_AUTHOR_EMAIL=EMAIL,
            GIT_COMMITTER_NAME=NAME,
            GIT_COMMITTER_EMAIL=EMAIL,
        )
    return subprocess.check_output(["git", "-C", str(root), *args], env=env)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exclusion(path: str) -> str | None:
    if (
        path.startswith(PRIVATE_ROOTS)
        or path.startswith("web/public/")
        and path != "web/public/.gitignore"
    ):
        return "Private/generated input, cache or compiled artifact"
    if path.startswith("docs/screenshots/"):
        return "All review screenshots and their indexes are omitted"
    if path in {"DECISIONS.md", "OPEN_ISSUES.md"}:
        return "Private gate review/decision record"
    if path.startswith("docs/") and not path.startswith("docs/models/"):
        if path.removeprefix("docs/") not in PUBLIC_DOCS:
            return "Review report/evidence omitted, including all verification and result reports"
    if re.search(r"(?:^|/)(?:\.env(?:\..*)?|id_rsa|id_ed25519|credentials(?:\..*)?)$", path):
        if path != ".env.example":
            return "Sensitive filename is never included"
    return None


def transformed(path: str, content: bytes) -> tuple[bytes, str | None]:
    if path == "README.md":
        return README.encode(), "Dedicated source-export instructions replace local review links"
    if path == "configs/country_notes.yaml":
        data = yaml.safe_load(content)
        data["notes"] = []
        data["status"] = "withheld_pending_review"
        data["scope_note"] = (
            "Country metadata is intersected with live OECD membership. "
            "Narrative country notes are withheld from this source export."
        )
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode(), (
            "Narrative notes removed; adoption, currency and source metadata preserved"
        )
    return content, None


def plan(root: Path) -> tuple[dict[str, Any], dict[str, tuple[bytes, str]]]:
    files: dict[str, tuple[bytes, str]] = {}
    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    modifications: list[dict[str, Any]] = []
    for record in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        meta, path_bytes = record.split(b"\t", 1)
        mode, oid, stage = meta.decode().split()
        path = path_bytes.decode()
        if stage != "0" or mode not in {"100644", "100755"}:
            raise ValueError(f"Export requires ordinary merged files: {path}")
        reason = exclusion(path)
        if reason:
            omitted.append({"path": path, "reason": reason})
            continue
        original = git(root, "cat-file", "blob", oid)
        content, change = transformed(path, original)
        try:
            text = content.decode()
        except UnicodeDecodeError as exc:
            raise ValueError(f"Unreviewed binary in source export: {path}") from exc
        for kind, pattern in PATTERNS.items():
            if pattern.search(text):
                if kind == "credential_url" and path == "tests/data/test_source_probes.py":
                    continue  # Known intentionally invalid negative-test fixture; never a key.
                raise ValueError(f"Sensitive-content pattern {kind} in {path}")
        files[path] = (content, mode)
        included.append(
            {
                "path": path,
                "bytes": len(content),
                "sha256": digest(content),
                "source_blob": oid,
                "mode": mode,
            }
        )
        if change:
            modifications.append({"path": path, "change": change})
    if not files:
        raise ValueError("No tracked source files to export")
    link_pattern = re.compile(r"!?\[([^\]]+)\]\(([^\s)]+)\)")
    broken_links = []
    for path, (content, mode) in list(files.items()):
        if not path.endswith(".md"):
            continue
        changed: list[str] = []

        def review_link(
            match: re.Match[str], *, document: str = path, omitted_targets: list[str] = changed
        ) -> str:
            link = urlsplit(match.group(2))
            if link.scheme or link.netloc or not link.path:
                return match.group(0)
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(document), unquote(link.path))
            )
            if target in files or target == "EXPORT_SCOPE.md":
                return match.group(0)
            if target.startswith("docs/") and exclusion(target):
                omitted_targets.append(target)
                return match.group(1) + " (local review record omitted from source export)"
            broken_links.append({"path": document, "target": target})
            return match.group(0)

        updated = link_pattern.sub(review_link, content.decode()).encode()
        if changed:
            files[path] = (updated, mode)
            modifications.append(
                {
                    "path": path,
                    "change": "Links to omitted review records replaced by explicit omission text",
                    "omitted_link_targets": sorted(set(changed)),
                }
            )
            included_record = next(item for item in included if item["path"] == path)
            included_record.update(bytes=len(updated), sha256=digest(updated))
    scope = [
        "# Source export scope",
        "",
        "This export excludes the following tracked review "
        "material. Ignored local datasets, caches, runtime binaries and the original Git "
        "directory were never candidates for copying.",
        "",
        "## Explicit omissions",
        "",
    ]
    scope.extend(f"- `{item['path']}` — {item['reason']}." for item in omitted)
    scope += ["", "## Export-only modifications", ""]
    scope.extend(f"- `{item['path']}` — {item['change']}." for item in modifications)
    scope += [
        "",
        "One new initial commit records this source tree. No original commits, "
        "remotes or author history were copied. Publication remains unapproved.",
        "",
    ]
    files["EXPORT_SCOPE.md"] = ("\n".join(scope).encode(), "100644")
    included.append(
        {
            "path": "EXPORT_SCOPE.md",
            "bytes": len(files["EXPORT_SCOPE.md"][0]),
            "sha256": digest(files["EXPORT_SCOPE.md"][0]),
            "source_blob": None,
            "mode": "100644",
        }
    )
    fingerprint = digest(json.dumps(included, sort_keys=True, separators=(",", ":")).encode())
    return {
        "source_head": git(root, "rev-parse", "HEAD").decode().strip(),
        "selected_source_sha256": fingerprint,
        "files": included,
        "omitted": omitted,
        "modifications": modifications,
        "file_count": len(included),
        "total_bytes": sum(item["bytes"] for item in included),
        "publication_approved": False,
        "broken_local_markdown_links": broken_links,
    }, files


def create(root: Path, expected: str) -> dict[str, Any]:
    root = root.resolve()
    report, files = plan(root)
    if report.get("broken_local_markdown_links"):
        raise ValueError("Source export has dangling local Markdown links")
    if report["selected_source_sha256"] != expected:
        raise ValueError("Reviewed source fingerprint changed; inspect a new plan before export")
    target = root / "runs/p2/sanitised-repo"
    if target.exists() or target.is_symlink():
        raise ValueError("Fresh export target already exists; never overwrite a reviewed export")
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError("Export must remain inside MacroLab")
    target.mkdir(parents=True)
    for relative, (content, mode) in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755 if mode == "100755" else 0o644)
    git(target, "-c", "init.templateDir=", "init", "--initial-branch=main", isolated=True)
    git(target, "config", "user.name", NAME, isolated=True)
    git(target, "config", "user.email", EMAIL, isolated=True)
    git(target, "add", "--all", isolated=True)
    git(
        target,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "Initial MacroLab source export",
        isolated=True,
    )
    count = int(git(target, "rev-list", "--all", "--count", isolated=True))
    identity = (
        git(target, "log", "-1", "--format=%an%n%ae%n%cn%n%ce", isolated=True).decode().splitlines()
    )
    if count != 1 or identity != [NAME, EMAIL, NAME, EMAIL]:
        raise ValueError("Fresh-history identity or commit count does not match approval")
    if (
        git(target, "remote", isolated=True).strip()
        or git(target, "status", "--porcelain", isolated=True).strip()
    ):
        raise ValueError("Export must have no remote and a clean worktree")
    for item in report["files"]:
        payload = (target / item["path"]).read_bytes()
        if digest(payload) != item["sha256"] or len(payload) != item["bytes"]:
            raise ValueError("Export readback mismatch")
    report.update(
        export_directory="runs/p2/sanitised-repo",
        commit_count=count,
        commit=git(target, "rev-parse", "HEAD", isolated=True).decode().strip(),
        author={"name": identity[0], "email": identity[1]},
        committer={"name": identity[2], "email": identity[3]},
        remotes=[],
        copied_original_git=False,
        readback_passed=True,
        network_requests=0,
    )
    (root / "runs/p2/repository-export.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--expected-source-sha256")
    args = parser.parse_args()
    if args.create:
        if not args.expected_source_sha256:
            parser.error("--create requires a reviewed --expected-source-sha256")
        report = create(ROOT, args.expected_source_sha256)
    else:
        report, _ = plan(ROOT)
        (ROOT / "runs/p2").mkdir(parents=True, exist_ok=True)
        (ROOT / "runs/p2/export-plan.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in {"files", "omitted"}}, indent=2))


if __name__ == "__main__":
    main()
