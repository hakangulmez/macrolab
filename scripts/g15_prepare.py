"""Local G15 candidate; accepted observation/runtime-package bytes retained."""

import os

os.environ.setdefault("MACROLAB_REVIEW_DIR", "runs/g15")
from g11_prepare import prepare  # noqa: E402

if __name__ == "__main__":
    prepare(build=True, label="G15 local template review", v2_templates=True)
