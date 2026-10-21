"""Serve an ignored P1 static candidate on loopback under its project base path."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", choices=("cleared", "all"), default="cleared")
    parser.add_argument("--candidate", choices=("p1", "p2"), default="p1")
    parser.add_argument("--port", type=int, default=5175)
    parser.add_argument("--base-path", default="/macrolab/")
    arguments = parser.parse_args()
    base = arguments.base_path
    if not base.startswith("/") or not base.endswith("/") or ".." in base:
        raise ValueError("Use a simple absolute project base path")
    directory = (
        ROOT
        / "runs/p1"
        / ("cleared" if arguments.sources == "cleared" else "all-local-only")
        / "site"
    )
    if arguments.candidate == "p2":
        if arguments.sources != "cleared":
            raise ValueError("P2 only serves the reviewed policy-filtered candidate")
        directory = ROOT / "runs/p2/site"
    if not (directory / "index.html").is_file() or directory.is_symlink():
        raise ValueError("Build the isolated static candidate before serving it")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def send_head(self):
            path = urlsplit(self.path).path
            if path == base.rstrip("/"):
                self.send_response(301)
                self.send_header("Location", base)
                self.end_headers()
                return None
            if not path.startswith(base):
                self.send_error(404, "Outside the candidate base path")
                return None
            self.path = "/" + self.path[len(base) :]
            return super().send_head()

    print(f"Static candidate only: http://127.0.0.1:{arguments.port}{base}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
