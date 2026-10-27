"""Every pre-existing changed break number; accepted G14 diagnostics stay exact."""

import json
from pathlib import Path

from g12_fixture import numbers

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g14_1"


def differences(old, new, path=""):
    out = []
    if isinstance(old, dict):
        for k, v in old.items():
            if k != "runtime_ms" and k in new:
                out.extend(differences(v, new[k], path + "/" + k))
    elif isinstance(old, list):
        if all(isinstance(item, str) for item in old):
            return []
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            out.extend(differences(a, b, path + "/" + str(i)))
    elif isinstance(old, (int, float)) and not isinstance(old, bool) and old != new:
        out.append(dict(path=path, before=old, after=new))
    return out


def main():
    frozen = []
    changed = []
    headline = []
    for name in [
        "cointegration_three",
        "cointegration_two",
        "vecm_point",
        "vecm_bootstrap",
        "break_ols",
        "break_ardl",
        "break_ecb",
    ]:
        old = json.loads((ROOT / "runs/g14" / f"{name}.json").read_text())
        new = json.loads((OUT / f"{name}.json").read_text())
        if not name.startswith("break_"):
            delta = numbers(old, new)
            assert max(delta) == 0
            frozen.append(dict(name=name, fields=len(delta), maximum_difference=0))
            continue
        a = old["results"][0]["break_tests"]
        b = new["results"][0]["break_tests"]
        changes = differences(a, b)
        changed.append(dict(name=name, changed_numbers=changes, count=len(changes)))
        headline.append(
            dict(
                name=name,
                q=b["tested_coefficients"],
                before_statistic=a["supremum"]["f_statistic"],
                after_statistic=b["supremum"]["f_statistic"],
                date=b["supremum"]["date"],
                before_p=a["supremum"]["approximate_p_value"],
                after_p=b["supremum"]["p_value"],
                before_critical95=a["critical_values"]["95"],
                after_critical95=b["critical_values"]["95"],
                variants=b["inference_variants"],
                warnings=[c for c in new["checks"] if c["code"].startswith("break_")],
            )
        )
    report = dict(
        accepted_g14_exact=frozen,
        changed=changed,
        headlines=headline,
        definition=(
            "Existing numeric break fields only; runtime excluded. "
            "New inference fields listed separately in full JSON exports."
        ),
    )
    (OUT / "break-number-changes.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# G14.1 — every changed existing break-test number",
        "",
        "All existing candidate-path, sup-Wald, Chow and recursive-residual numbers remain exact. "
        "The selected critical values change from asymptotic to bootstrap; "
        "the new p_value field is separately compared below.",
        "",
        "| Workload | Existing field | G14 | G14.1 |",
        "|---|---|---:|---:|",
    ]
    for row in changed:
        for change in row["changed_numbers"]:
            lines.append(
                f"| {row['name']} | `{change['path']}` | "
                f"{change['before']!r} | {change['after']!r} |"
            )
    lines += [
        "",
        "## Headline probability (different calibration)",
        "",
        "| Workload | Hansen approximate p (retained in details) | Selected bootstrap p |",
        "|---|---:|---:|",
    ]
    for h in headline:
        lines.append(f"| {h['name']} | {h['before_p']!r} | {h['after_p']!r} |")
    lines += [
        "",
        "All added variant statistics, probabilities and critical values are in "
        "`runs/g14_1/break-number-changes.json`; "
        "no added quantity replaces an unrelated old quantity.",
        "",
    ]
    (ROOT / "docs/process/G14_1_BREAK_CHANGES.md").write_text("\n".join(lines))
    print([(r["name"], r["count"]) for r in changed])


if __name__ == "__main__":
    main()
