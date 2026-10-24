"""Independent numerical reference differences; timings use the browser harness."""

import json
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import t
from statsmodels.tsa.statespace.sarimax import SARIMAX

from macrolab.models.arima import ForecastSARIMAX, fit_order, joint_prediction
from macrolab.models.forecast_eval import dm_hln

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g13"


def main():
    warnings.filterwarnings("ignore")
    rows = []
    rng = np.random.default_rng(914)
    y = rng.normal(size=160)
    for order, seasonal in [
        ((2, 0, 2), (0, 0, 0, 0)),
        ((2, 1, 1), (0, 0, 0, 0)),
        ((1, 0, 1), (1, 0, 1, 12)),
    ]:
        options = dict(order=order, seasonal_order=seasonal, trend="c", simple_differencing=True)
        model, ref = ForecastSARIMAX(y, **options), SARIMAX(y, **options)
        theta = np.repeat(0.15, model.k_params)
        theta[-1] = 1
        params = ref.transform_params(theta)
        a, b = model.filter(params), ref.filter(params)
        pa, pb = a.get_forecast(12), b.get_forecast(12)
        rows.append(
            dict(
                order=order,
                seasonal=seasonal,
                likelihood_diff=abs(a.llf - b.llf),
                mean_diff=float(np.max(abs(pa.predicted_mean - pb.predicted_mean))),
                variance_diff=float(np.max(abs(pa.var_pred_mean - pb.var_pred_mean))),
            )
        )
    y = np.zeros(180)
    for i in range(1, len(y)):
        y[i] = 0.2 + 0.6 * y[i - 1] + rng.normal() * 0.4
    model = SARIMAX(y, order=(1, 0, 0), trend="c", simple_differencing=True)
    ref = model.fit(
        disp=False,
        method="lbfgs",
        maxiter=300,
        optim_score="approx",
        optim_complex_step=True,
        pgtol=1e-10,
        factr=10,
    )
    fit = fit_order(y, np.zeros((len(y), 0)), (1, 0, 0), (0, 0, 0, 0))
    fitted_diff = dict(
        parameters=float(np.max(abs(fit.params - ref.params))),
        likelihood=abs(fit.llf - ref.llf),
        mean=float(
            np.max(abs(fit.get_forecast(12).predicted_mean - ref.get_forecast(12).predicted_mean))
        ),
    )
    fixed = model.filter([0.2, 0.6, 0.16])
    mean, cov = joint_prediction(fixed, np.zeros((12, 0)), 12)
    h = np.arange(1, 13)
    exact_mean = 0.6**h * y[-1] + 0.2 * (1 - 0.6**h) / 0.4
    exact_variance = 0.16 * (1 - 0.6 ** (2 * h)) / (1 - 0.6**2)
    closed = dict(
        mean=float(np.max(abs(mean - exact_mean))),
        variance=float(np.max(abs(np.diag(cov) - exact_variance))),
    )
    dm = []
    for horizon in (1, 4, 8):
        a, b = rng.normal(size=(2, 90))
        d = a * a - b * b
        z, n = d - d.mean(), len(d)
        gamma = np.correlate(z, z, "full")[n - 1 : n - 1 + horizon] / n
        variance = gamma[0] + 2 * sum(gamma[1:])
        if variance < 0:
            variance = gamma[0] + 2 * sum(gamma[j] * (1 - j / horizon) for j in range(1, horizon))
        stat = (
            d.mean()
            / np.sqrt(variance / n)
            * np.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
        )
        actual = dm_hln(a, b, horizon)
        dm.append(
            dict(
                horizon=horizon,
                statistic_diff=abs(actual["statistic"] - stat),
                p_diff=abs(actual["p_value"] - 2 * t.sf(abs(stat), n - 1)),
            )
        )
    report = dict(
        sarimax_initialization=rows,
        sarimax_fitted=fitted_diff,
        ar1_closed_form=closed,
        dm_hln=dm,
    )
    (OUT / "reference-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
