"""Independent, prefix-only G13 loss diagnostic; preserves accepted artifacts."""

import json
import warnings
from pathlib import Path

import numpy as np
from g12_fixture import numbers
from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.statespace.sarimax import SARIMAX

from macrolab.analysis.engine import run_analysis
from macrolab.models.forecast_common import prepare_forecast

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g13-diagnostic"


def main():
    OUT.mkdir(exist_ok=True)
    fixture = json.loads((ROOT / "runs/g13/forecast-fixture.json").read_text())
    (OUT / "forecast-fixture.json").write_text(json.dumps(fixture) + "\n")
    config = fixture["cases"]["forecast_evaluation"]
    old = json.loads((ROOT / "runs/g13/forecast_evaluation.json").read_text())
    evaluation = old["results"][0]["evaluation"]
    raw, _ = prepare_forecast(config, fixture["bundle"], "USA")
    attribution = {}
    for label, predicate in [
        ("All targets", lambda r: True),
        ("Exclude 2020–2021 targets", lambda r: not "2020" <= r["target"][:4] <= "2021"),
    ]:
        rows = [r for r in evaluation["predictions"] if r["horizon"] == 8 and predicate(r)]
        attribution[label] = {}
        for model in evaluation["models"]:
            losses = [
                {
                    "origin": r["origin"],
                    "target": r["target"],
                    "actual": r["actual"],
                    "prediction": r["predictions"][model],
                    "squared_error": (r["actual"] - r["predictions"][model]) ** 2,
                }
                for r in rows
            ]
            total = sum(r["squared_error"] for r in losses)
            covid = sum(r["squared_error"] for r in losses if "2020" <= r["origin"][:4] <= "2021")
            attribution[label][model] = dict(
                n=len(rows),
                sse=total,
                covid_origin_share=covid / total,
                top_five=sorted(losses, key=lambda r: r["squared_error"], reverse=True)[:5],
            )
    references = []
    for origin in ["2020-Q2", "2021-Q1"]:
        y = raw.frame.loc[:origin, "unemp"].to_numpy()
        location, scale = y.mean(), y.std()
        z = np.round((y - location) / scale, 12)
        # Independent native fitting: default statsmodels starts, no MacroLab optimizer.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = SARIMAX(
                z,
                order=(0, 1, 3),
                trend="c",
                simple_differencing=True,
                enforce_stationarity=True,
                enforce_invertibility=True,
            ).fit(
                method="nm",
                maxiter=10000,
                xtol=1e-12,
                ftol=1e-12,
                disp=False,
            )
        arima = location + scale * (z[-1] + np.cumsum(fitted.get_forecast(8).predicted_mean))
        ar = AutoReg(y, lags=2, trend="c", old_names=False).fit().predict(len(y), len(y) + 7)
        comparisons = []
        for r in evaluation["predictions"]:
            if r["origin"] == origin:
                h = r["horizon"]
                comparisons.append(
                    dict(
                        horizon=h,
                        target=r["target"],
                        arima_native=float(arima[h - 1]),
                        arima_accepted=r["predictions"]["ARIMA"],
                        ar_native=float(ar[h - 1]),
                        ar_accepted=r["predictions"]["AR (BIC)"],
                        arima_difference=float(abs(arima[h - 1] - r["predictions"]["ARIMA"])),
                        ar_difference=float(abs(ar[h - 1] - r["predictions"]["AR (BIC)"])),
                    )
                )
        references.append(
            dict(
                origin=origin,
                n=len(y),
                order=[0, 1, 3],
                ar_order=2,
                converged=bool(fitted.mle_retvals["converged"]),
                native_llf=float(fitted.llf),
                comparisons=comparisons,
            )
        )
        assert fitted.mle_retvals["converged"]
        assert max(c["arima_difference"] for c in comparisons) < 0.001
        assert max(c["ar_difference"] for c in comparisons) < 1e-10
    current = run_analysis(config, fixture["bundle"])
    (OUT / "forecast_evaluation.json").write_text(json.dumps(current) + "\n")
    for name in ["arima_fixed"]:
        result = run_analysis(fixture["cases"][name], fixture["bundle"])
        (OUT / (name + ".json")).write_text(json.dumps(result) + "\n")
    # Compare the accepted contract exactly; only the explicitly requested row is new.
    new_row = current["results"][0]["sensitivity"]["variants"].pop()
    differences = numbers(old, current)
    count, difference = len(differences), max(differences, default=0)
    assert difference == 0
    report = dict(
        attribution=attribution,
        independent_references=references,
        accepted_fields=count,
        maximum_difference=difference,
        origin_exclusion=new_row,
    )
    (OUT / "diagnostic.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# G13 unemployment loss attribution",
        "",
        "Eight-quarter errors, USA unemployment in percentage points. Snapshot 20261023-1634; 1999 Q1–2025 Q3. Orders fixed at the first origin: AR(2), ARIMA(0,1,3). Squared errors have units pp². No loss clipping or re-estimation is used in either exclusion sensitivity.",  # noqa: E501 - generated Markdown table/prose
        "",
    ]
    for label, models in attribution.items():
        lines += [
            "## " + label,
            "",
            "| Model | n | Total SSE | SSE from 2020–2021 origins |",
            "|---|---:|---:|---:|",
        ]
        for model, result in models.items():
            lines.append(
                f"| {model} | {result['n']} | {result['sse']:.3f} | {100 * result['covid_origin_share']:.2f}% |"  # noqa: E501 - generated Markdown table/prose
            )
        lines += [
            "",
            "| Model | Origin → target | Prediction | Actual | Squared error |",
            "|---|---|---:|---:|---:|",
        ]
        for model, result in models.items():
            for row in result["top_five"]:
                lines.append(
                    f"| {model} | {row['origin']} → {row['target']} | {row['prediction']:.3f} | {row['actual']:.3f} | {row['squared_error']:.3f} |"  # noqa: E501 - generated Markdown table/prose
                )
        lines.append("")
    lines += [
        "## Independent checks",
        "",
        "Plain native statsmodels SARIMAX (default starts, Nelder–Mead), same standardized prefix, constant and fixed order; restore simple differences by cumulative addition. AutoReg independently checks AR(2). No future observations enter either fit. These independently optimized fits are not the same-parameter cross-runtime parity test.",  # noqa: E501 - generated Markdown table/prose
        "",
        "| Origin | n | h8 ARIMA native / accepted | h8 AR native / accepted | Max ARIMA difference at h1/4/8 |",  # noqa: E501 - generated Markdown table/prose
        "|---|---:|---:|---:|---:|",
    ]
    for ref in references:
        r = ref["comparisons"][-1]
        lines.append(
            f"| {ref['origin']} | {ref['n']} | {r['arima_native']:.8f} / {r['arima_accepted']:.8f} | {r['ar_native']:.8f} / {r['ar_accepted']:.8f} | {max(x['arima_difference'] for x in ref['comparisons']):.3g} |"  # noqa: E501 - generated Markdown table/prose
        )
    lines += [
        "",
        "The COVID-origin errors are real fitted-model outcomes, not a date-alignment or inverse-transform defect. ARIMA extrapolates the unprecedented jump using a first-origin MA order; AR(2) also extrapolates a large increase. BVAR's largest losses instead originate in 2009. Excluding COVID targets alone retains the forecasts made during COVID for 2022–2023 targets. Both exclusions are descriptive scoring sensitivities, not evidence of real-time performance.",  # noqa: E501 - generated Markdown table/prose
        "",
        f"All {count:,} existing evaluation numeric fields remain exact. The new origin-exclusion metrics and dated-error charts use the stored predictions only.",  # noqa: E501 - generated Markdown table/prose
    ]
    (ROOT / "docs/G13_LOSS_ATTRIBUTION.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(dict(fields=count, max_difference=difference, references=references), indent=2)
    )


if __name__ == "__main__":
    main()
