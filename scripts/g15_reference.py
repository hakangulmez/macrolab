"""Independent native checks of the new template wiring and economic summaries."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from statsmodels.tsa.statespace.sarimax import SARIMAX

from macrolab.analysis.panel import prepare_panel
from macrolab.analysis.templates_v2 import base_config
from macrolab.models.arima import choose_order
from macrolab.models.forecast_common import prepare_forecast, training
from macrolab.models.forecast_eval import origin_forecast
from macrolab.models.panel import fe_design

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g15"


def main():
    fixture = json.loads((OUT / "template-fixture.json").read_text())
    b = fixture["bundle"]
    fe = json.loads((OUT / "ea_phillips_pooled.json").read_text())
    c = fe["effective_config"]
    data, _, _ = prepare_panel(c, b)
    frames = []
    for country, d in data.items():
        design = fe_design(d, c)
        frame = design["x"].loc[design["mask"]].copy()
        frame["y"] = design["y"].loc[design["mask"]]
        frame.index = pd.MultiIndex.from_arrays(
            [
                [country] * len(frame),
                frame.index.to_timestamp(),
            ]
        )
        frames.append(frame)
    joined = pd.concat(frames)
    reference = PanelOLS(joined.y, joined.drop(columns="y"), entity_effects=True).fit(
        cov_type="kernel", kernel="bartlett", bandwidth=4, debiased=True
    )
    rows = fe["results"][0]["coefficients_table"]
    coefficient_diff = max(abs(r["estimate"] - reference.params[r["term"]]) for r in rows)
    se_diff = max(abs(r["std_error"] - reference.std_errors[r["term"]]) for r in rows)
    assert max(coefficient_diff, se_diff) <= 1e-10
    fc = json.loads((OUT / "ea_inflation_horse_race.json").read_text())
    c = base_config(fc["config"])
    raw, _ = prepare_forecast(c, b, "EA")
    expected = 100 * (raw.frame.cpi / raw.frame.cpi.shift(4) - 1)
    evaluation = fc["results"][0]["evaluation"]
    actual_diff = max(
        abs(r["actual"] - expected.loc[r["target"]]) for r in evaluation["predictions"]
    )
    assert actual_diff == 0
    fixed = dict(
        ar_order=evaluation["origins"][0]["ar_order"], arima=evaluation["origins"][0]["arima"]
    )
    references = []
    for origin in ["2008-Q4", "2020-Q2", "2021-Q1"]:
        stop = list(raw.frame.index).index(origin) + 1
        trained = training(raw, c, stop)
        one = deepcopy(c)
        one["series"] = [s for s in c["series"] if s["concept_id"] == "cpi"]
        fit = choose_order(trained, one, fixed=fixed["arima"])
        y = np.round((trained.frame.cpi.to_numpy() - fit["location"]) / fit["scale"], 12)
        order = tuple(fixed["arima"]["order"])
        model = SARIMAX(
            y,
            order=order,
            seasonal_order=(0, 0, 0, 0),
            trend="c",
            simple_differencing=True,
            enforce_stationarity=True,
            enforce_invertibility=True,
        )
        filtered = model.filter(fit["fit"].params)
        predicted = filtered.get_forecast(8).predicted_mean
        if order[1]:
            predicted = y[-1] + np.cumsum(predicted)
        predicted = fit["location"] + fit["scale"] * predicted
        points, _ = origin_forecast(raw, c, stop, 8, fixed)
        delta = float(np.max(np.abs(points["ARIMA"] - predicted)))
        assert delta <= 1e-8
        altered = deepcopy(raw)
        altered.frame.iloc[stop:] = altered.frame.iloc[stop:] * 3 + 50
        changed, _ = origin_forecast(altered, c, stop, 8, fixed)
        assert all(np.array_equal(points[k], changed[k]) for k in points)
        references.append(
            dict(
                origin=origin,
                training_observations=len(trained.frame),
                sarimax_at_identical_parameters_max_diff=delta,
                all_four_models_post_origin_perturbation_exact=True,
            )
        )
    loss = []
    invariant = []
    for stop in range(44, len(raw.frame)):
        altered = deepcopy(raw)
        altered.frame.iloc[stop:] = altered.frame.iloc[stop:] * 3 + 50
        pair = []
        for source in [raw, altered]:
            try:
                points, detail = origin_forecast(source, c, stop, 8, fixed)
                pair.append(dict(points={k: v.tolist() for k, v in points.items()}, detail=detail))
            except ValueError as exc:
                pair.append(dict(failure=str(exc)))
        assert pair[0] == pair[1], str(raw.frame.index[stop - 1])
        invariant.append(
            dict(origin=str(raw.frame.index[stop - 1]), exact=True, failed="failure" in pair[0])
        )
    for model in evaluation["models"]:
        rs = [r for r in evaluation["predictions"] if r["horizon"] == 8]
        total = sum((r["actual"] - r["predictions"][model]) ** 2 for r in rs)
        shares = {}
        for label, keep in [
            ("covid_origin_share", lambda r: "2020" <= r["origin"][:4] <= "2021"),
            ("surge_target_share", lambda r: "2021-Q3" <= r["target"] <= "2023-Q4"),
        ]:
            shares[label] = (
                sum((r["actual"] - r["predictions"][model]) ** 2 for r in rs if keep(r)) / total
            )
        loss.append(dict(model=model, horizon=8, **shares))
    result = dict(
        passed=True,
        panelols_version="7.0 (native test only)",
        phillips_coefficient_max_diff=coefficient_diff,
        phillips_dk_se_max_diff=se_diff,
        inflation_target_definition_max_diff=actual_diff,
        sarimax_references=references,
        every_origin_post_origin_perturbation=invariant,
        h8_loss_attribution=loss,
    )
    (OUT / "template-reference-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
