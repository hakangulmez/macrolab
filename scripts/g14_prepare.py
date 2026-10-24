"""Local G14 review build from accepted data and pinned runtime bytes."""

import argparse
import os

os.environ.setdefault("MACROLAB_REVIEW_DIR", "runs/g14")
from g11_prepare import prepare  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    prepare(parser.parse_args().build, label="G14 local diagnostic-model review")
