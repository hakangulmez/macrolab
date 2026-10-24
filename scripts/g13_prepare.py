"""G13 local candidate, accepted snapshot and pinned scientific runtime only."""

import argparse
import os

os.environ.setdefault("MACROLAB_REVIEW_DIR", "runs/g13")
from g11_prepare import prepare  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    prepare(parser.parse_args().build, label="G13 local forecasting review")
