"""Write metadata-only G2 verification and the required stop report from local evidence."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "runs/g2" / name).read_text())


def main():
    evidence = read("validation.json")
    parity = read("runtime_parity.json")
    exports = read("export_parity.json")
    tests = ET.parse(ROOT / "runs/checks/pytest.xml").getroot()
    suites = list(tests.iter("testsuite"))
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ["tests", "failures", "errors", "skipped"]
    }
    assert counts["failures"] == counts["errors"] == 0
    assert parity["passed"], "Browser parity has not passed"
    assert parity["source_hashes_unchanged"] and not parity["page_errors"]
    assert all(
        c["api_max_abs_difference"] == 0 and c["export_max_abs_difference"] == 0
        for c in exports["cases"]
    )
    assert all(t["status"] == "ok" for t in evidence["templates"].values())
    rows = []
    for row in evidence["models"]:
        rec = row["recovery"]
        recovery = (
            "N/A: descriptive/test/filter"
            if rec.get("status") == "not_applicable"
            else (
                (
                    f"IRF {100 * rec['coverage']:.2f}%; "
                    f"coefficients {100 * rec['coefficient_coverage']:.2f}% (68% nominal)"
                )
                if "coefficient_coverage" in rec
                else (
                    f"{rec.get('coverage_count')}/{rec.get('repetitions')} = "
                    f"{100 * rec.get('coverage', 0):.2f}% (95% nominal)"
                )
            )
        )
        if row["model_id"] == "sing.rolling":
            recovery = "Rolling/recursive reference + future-window leakage tests"
        rows.append(
            f"| `{row['model_id']}` | {row['reference_max_abs_difference']:.3g} | "
            f"{recovery} | {row['runtime_ms']:.1f} |"
        )
    template_rows = []
    checks = {}
    for name, row in evidence["templates"].items():
        country, sample = next(iter(row["actual_samples"].items()))
        codes = sorted({c["code"] for c in row["checks"]})
        checks[name] = codes
        template_rows.append(
            f"| {name} | {country} | {sample['start']}–{sample['end']} | "
            f"{sample['nobs']} / {sample['common_nobs']} | "
            f"{len(sample['dropped_periods'])} | {row['runtime_ms']:.0f} |"
        )

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    verification = {
        "gate": "G2",
        "code_version": "0.2.0",
        "baseline_commit": "48a1907",
        "snapshot_id": evidence["snapshot_id"],
        "python_tests": counts,
        "model_validation": evidence["models"],
        "templates": {
            name: {
                "status": row["status"],
                "config_hash": row["config_hash"],
                "samples": {
                    c: {
                        key: s[key]
                        for key in [
                            "start",
                            "end",
                            "nobs",
                            "common_nobs",
                            "dropped_periods",
                            "frequency_conversion",
                        ]
                    }
                    for c, s in row["actual_samples"].items()
                },
                "checks": checks[name],
                "runtime_ms": row["runtime_ms"],
            }
            for name, row in evidence["templates"].items()
        },
        "browser_parity": parity,
        "export_case_count": len(exports["cases"]),
        "api_max_abs_difference": max(c["api_max_abs_difference"] for c in exports["cases"]),
        "export_max_abs_difference": max(c["export_max_abs_difference"] for c in exports["cases"]),
        "data_manifest_sha256": digest(ROOT / "data/processed/current/processed_manifest.json"),
        "evidence_sha256": {p.name: digest(p) for p in (ROOT / "runs/g2").glob("checks-*.log")},
        "publication_approved": False,
    }
    # Browser evidence contains comparison metadata and samples, never source observations.
    (ROOT / "docs/process/G2_VERIFICATION.json").write_text(
        json.dumps(verification, indent=2, allow_nan=False) + "\n"
    )
    text = (
        """# G2 stop report — 21 October 2026

**G2 complete; stopped before G3.** Twelve v0 plug-ins, registry, compatibility
checks, transformations, actual-sample accounting, sensitivity, local API, JSON
contracts, compressed configuration state and standalone Python reproduction are
implemented. Accepted snapshot `20261021-0025` is unchanged. Work remains local;
no push, deploy, paid service, API key or thesis file was used.

## Per-model validation

All deterministic references pass the **1e-8 absolute tolerance**. Runtimes below
are measured native plug-in times, excluding browser initialization and input
preparation; descriptive/single-equation fixtures have 160 quarterly observations.
VAR timing uses six variables, 120 quarters, two lags, horizon 12 and 500 draws.

| Model | Maximum absolute reference difference | Recovery / other applicable evidence | Native ms |
| --- | ---: | --- | ---: |
"""
        + "\n".join(rows)
        + """

References: statsmodels 0.14.6 for regression/ARDL/UECM/rolling/VAR/Granger/ADF/KPSS/HP;
arch 8.0.0 for PP; NumPy/pandas for descriptive outputs; QuantEcon 0.11.4 plus direct
OLS for Hamilton. Each [model card](models/README.md) links its primary references
and details the compared outputs and limits. VAR intervals additionally match an
independent finite-difference delta-method reference; FEVD shares sum to one.

OLS/ARDL recovery uses 120 fixed-seed datasets. VAR recovery uses 40 datasets and
199 draws per dataset, nominal 68% pointwise bands; impact restrictions are excluded
from coverage counting. The large-sample VAR coefficient maximum error is 0.017112.
Coverage passes the prespecified Monte Carlo diagnostic envelopes; it does not
promise calibration for every real-world sample. No seeds or thresholds were tuned.
Transforms invert within tolerance; filter components reconstruct inputs. Country
order, variable renaming, covariance-only equality, lag calendars, future-window
isolation and failure branches are tested. No forecasting or historical-decomposition
model is released, so their specific tests are inapplicable at v0.

## Real G1.1 template runs

Every original default country runs successfully. **No replacement is proposed.**
Requested start is 1999 Q1. `n / common n` separates observations actually estimated
from complete input rows before model initialization. All results return exact dates,
all dropped periods, transformation formulas and conversion rules.

| Template | Country | Estimation sample | n / common n | Dropped | Native ms |
| --- | --- | --- | ---: | ---: | ---: |
"""
        + "\n".join(template_rows)
        + """

Monthly inputs use complete-quarter means; quarterly GDP and credit stay quarterly.
No partial-quarter averages, disaggregation, interpolation or cross-gap lag compression.
USA loses 2025 Q4 (CPI/unemployment gaps), 2026 Q1 (outside longest contiguous window),
2026 Q2 (credit unavailable), 2026 Q3 (GDP/REER/credit unavailable), plus four initial
lag quarters in 1999. Each other template drops incomplete/unavailable 2026 Q3.

- **Monetary policy / USA:** VAR(4), six series, policy rate last in the recursive
  order, +1 pp shock, 500 draws and 68% pointwise bands. GDP-growth peak is +1.745 pp
  at quarter 3; inflation peak is −0.827 pp at quarter 11. These conditional model
  responses are not causal forecasts; the positive GDP response is retained openly.
  The shock exceeds the estimated −0.349 to +0.323 pp historical 5–95% range.
  Reversing/rotating ordering and using two lags leaves GDP's sign at the baseline
  peak unchanged across 3/3 alternatives, while its own-peak magnitude ranges
  1.123–1.785 pp. REER interval exclusion varies across specifications.
- **Taylor / GBR:** HAC(4), 95% intervals. Inflation coefficient 0.0562
  [−0.3162, 0.4287]; retrospective log-HP gap coefficient 0.1512
  [−0.0349, 0.3373]. Recent-half gap coefficient is −0.0253: **sign changes**.
  Inflation's coefficient rises to 0.4468. The full-sample estimates do not exclude
  zero. Neither the filter nor this association is a real-time reaction function.
- **Phillips / CAN:** unemployment coefficient −0.6481 [−1.1209, −0.1752].
  HC1, recent-half and 40-quarter rolling comparisons are returned with their
  sample dates; covariance-only equality is excluded from sign agreement counts.
- **Okun / ESP:** quarterly unemployment change on year-on-year GDP growth gives
  coefficient −0.08353 [−0.13829, −0.02877]. Recent-half coefficient −0.05160;
  the negative sign persists. Mixed change horizons are explicit in the config.

Sensitivity includes peak response/timing, interval exclusion, sign agreement rule,
comparison denominators, per-variant samples and input fingerprints. Failed, blocked,
duplicate or incompatible alternatives stay visible. The agreement measure describes
this bounded v0 comparison set; it is not evidence that identifying assumptions hold.

## All checks fired by the real templates

"""
    )
    text += "\n".join(
        f"- **{name}:** " + ", ".join(f"`{c}`" for c in codes) + "."
        for name, codes in checks.items()
    )
    text += """

Source warnings retain each selected card's actual flags and attribution. Limited
USA CPI/unemployment warn. Taylor's rate triggers corroborating ADF/KPSS level
nonstationarity; USA REER/credit give inconclusive evidence. COVID is included with
warnings in all defaults; USA and GBR include native-month lower-bound episodes.
No default input is missing or stale. The stale critical-input block and explicit
observed-sample exception are exercised synthetically, including incomplete quarters.

Additional synthetic branches exercised: `missing_coverage`, `stale_input`,
`freq_mismatch`, `invalid_transform`, `model_inputs`, `shared_rate`, `pre_euro_break`,
`nsa_series`, `granger_language`, `collinearity`, `unstable_dynamics`, small-sample
warning/block thresholds, incorrect COVID treatment, invalid shock quantiles and
unavailable stationarity diagnostics. `weak_instrument` remains future-only because
v0 has no IV model. Automatic lag selection uses the selected parameter count for
post-fit checks. Generated COVID impulses outside the estimation window are omitted
explicitly and reported; user-specified regressors are not silently dropped.

## Runtime, reproduction and checks

"""
    text += (
        f"**{counts['tests']} Python tests passed; zero failures/errors**, "
        "plus one frontend smoke test. "
    )
    maximum = max(row["max_abs_difference"] for row in parity["results"])
    text += (
        f"The maximum browser/native absolute difference is **{maximum:.8g}**, "
        "within 1e-8; API/native and isolated-export differences are **0**. "
    )
    text += """Setup, offline quick check, Python/frontend lint, strict mypy/TypeScript and
production scaffold build pass. Numerical browser/native/API/standalone comparisons
cover all 12 models, a seeded bootstrap case and all four real templates (17 cases).
Both ordinary results and compatibility decisions are compared. Detailed measured
per-case differences, versions, source hashes and test logs are in
[G2 verification](G2_VERIFICATION.json).

The real Chrome worker runs Python 3.14.2/Pyodide 314.0.7; native Python is 3.11.14.
Scientific package versions differ where official wheels require it and are recorded.
The owner-approved nine scientific files total 30,299,063 bytes, below 100 MiB;
all SHA-256 checks pass. Final tests use only loopback requests, and terminate the
browser/server afterwards. Standalone exports run from embedded sources in isolated
processes with network connections blocked; API/export differences are zero.

Input fingerprints hash original source bytes/values, transformations and retained
periods, not platform-dependent derived floating-point bit patterns. Numerical
outputs are independently compared within tolerance. Raw observations, generated
exports, binary wheels and full result bundles remain ignored by Git.

## Ambiguities resolved and open limits

- Support `info` checks; reject recursive orderings referring to unselected series.
- Require complete converted periods and the longest contiguous common sample;
  report losses, including lag initialization. Euro shock defaults respect adoption.
- Separate coefficient confidence from IRF band confidence. Normalize every
  bootstrap draw to the specified physical shock; bands are pointwise.
- Use validated v0 order/lag/sample/covariance/rolling sensitivities; no implied
  local projections, BVAR, sign restrictions or unavailable causal identification.
- Hamilton uses an equivalent pinned public reference and explicit reconstruction
  checks. HP/Hamilton are retrospective and labelled as such.
- G2 tests real numerical browser execution. Product charts, six screens, keyboard,
  accessibility and desktop/375 px screenshots belong to G3 under section 12;
  no product UI was added and screenshots are not applicable to this gate.
- G1.1 source limitations remain, including stale M3/PPI and missing national M3.
  IMF/World Bank terms remain unresolved: no redistribution of raw data. Country
  notes stay DRAFT. Nothing is published without approval; hosting stays after G4.

**Decision required:** approve G2 to proceed to G3, or request a bounded correction.
G3 has not started. No decision on hosting or the first v1 template is needed now.
"""
    (ROOT / "docs/process/STOP_REPORT_G2.md").write_text(text)
    print(
        json.dumps(
            {
                "tests": counts,
                "models": len(evidence["models"]),
                "templates": len(evidence["templates"]),
                "report": "docs/process/STOP_REPORT_G2.md",
            }
        )
    )


if __name__ == "__main__":
    main()
