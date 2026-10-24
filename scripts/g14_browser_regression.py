"""Exact browser-to-browser checks for accepted panel, BVAR and forecast fields."""

import json
import os
from pathlib import Path

from g12_fixture import numbers
from g14_regress_forecast import accepted_projection

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ.get("MACROLAB_REVIEW_DIR", "runs/g14")


def main():
    rows = []
    for group, accepted in [("panel", "g12"), ("bvar", "g12"), ("forecast", "g13")]:
        fixture = json.loads((OUT / f"{group}-fixture.json").read_text())
        for name in fixture["cases"]:
            old = json.loads((ROOT / "runs" / accepted / f"{name}.browser.json").read_text())
            new = json.loads((OUT / f"{name}.browser.json").read_text())
            if group == "forecast":
                new = accepted_projection(new)
            delta = numbers(old, new)
            assert max(delta) == 0, (name, max(delta))
            rows.append(
                dict(name=name, group=group, fields=len(delta), max_difference=0, exact=True)
            )
    (OUT / "browser-regression-models.json").write_text(
        json.dumps(dict(passed=True, fields=sum(r["fields"] for r in rows), cases=rows), indent=2)
        + "\n"
    )
    print(sum(r["fields"] for r in rows), "panel/BVAR/forecast browser fields exact")


if __name__ == "__main__":
    main()
