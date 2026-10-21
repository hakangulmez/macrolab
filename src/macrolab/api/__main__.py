"""Start the analysis API on the loopback interface only."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    uvicorn.run("macrolab.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
