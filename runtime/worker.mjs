/* global self */
/* Same-origin Pyodide worker. Cancellation is worker.terminate(), never a partial result. */
let runtime;
let busy = false;
const localFetch = globalThis.fetch.bind(globalThis);

globalThis.fetch = (resource, options) => {
  const url = new URL(
    resource instanceof Request ? resource.url : String(resource),
    self.location.href,
  );
  if (url.origin !== self.location.origin) {
    throw new Error(`Runtime outbound request refused: ${url.origin}`);
  }
  return localFetch(resource, options);
};

async function initialise(message) {
  if (runtime) throw new Error("Runtime already initialised");
  const started = performance.now();
  self.postMessage({ type: "progress", text: "Loading local Python runtime…" });
  const indexURL = new URL(message.indexURL, self.location.href);
  const wheelURL = new URL(message.wheelURL, self.location.href);
  if (
    indexURL.origin !== self.location.origin ||
    wheelURL.origin !== self.location.origin
  ) {
    throw new Error("Runtime assets must be served from the local application");
  }
  const { loadPyodide } = await import(new URL("pyodide.mjs", indexURL).href);
  runtime = await loadPyodide({
    indexURL: indexURL.href,
    lockFileURL: new URL("pyodide-lock.json", indexURL).href,
    stdout: (text) => self.postMessage({ type: "log", text }),
    stderr: (text) => self.postMessage({ type: "log", text }),
  });
  self.postMessage({ type: "progress", text: "Loading numerical libraries…" });
  await runtime.loadPackage(["numpy", "pandas", "scipy", "statsmodels"]);
  self.postMessage({ type: "progress", text: "Verifying MacroLab models…" });
  const wheel = await fetch(wheelURL).then((response) => {
    if (!response.ok) throw new Error("Portable model wheel is unavailable");
    return response.arrayBuffer();
  });
  const digest = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", wheel)),
  )
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  if (digest !== message.wheelSHA256)
    throw new Error("Portable model wheel checksum differs");
  const destination = runtime.runPython(
    "import site; site.getsitepackages()[0]",
  );
  runtime.unpackArchive(wheel, "zip", { extractDir: destination });
  runtime.globals.set("__ml_code_version", message.codeVersion);
  runtime.globals.set(
    "__ml_reproduction_json",
    JSON.stringify(message.reproductionEnvironment ?? null),
  );
  const versions = JSON.parse(
    runtime.runPython(`
import os, json, platform, importlib.metadata
os.environ["MACROLAB_CODE_VERSION"] = __ml_code_version
json.dumps({"python": platform.python_version(), **{
    name: importlib.metadata.version(name)
    for name in ("numpy", "pandas", "scipy", "statsmodels", "patsy", "packaging")
}})
`),
  );
  self.postMessage({ type: "progress", text: "Preparing analysis libraries…" });
  // Import the same code used by an estimate while Builder is open. No model is
  // fitted here; runtime readiness includes the one-time scientific import cost.
  await runtime.runPythonAsync(`
from macrolab.analysis.engine import run_analysis, compatibility
from macrolab.analysis.config import encode_config, decode_config
from macrolab.analysis.sensitivity import build_sensitivity
from macrolab.checks.core import evaluate_checks, postfit_checks
from macrolab.export.script import standalone
`);
  self.postMessage({ type: "progress", text: "Analysis runtime ready" });
  return {
    versions,
    wheel_sha256: digest,
    initialisation_ms: performance.now() - started,
  };
}

self.onmessage = async ({ data: message }) => {
  const { id, type } = message;
  if (busy) {
    self.postMessage({
      id,
      type: "error",
      message: "An analysis is already running",
    });
    return;
  }
  busy = true;
  try {
    let result;
    if (type === "init") {
      result = await initialise(message);
    } else if (type === "relationship") {
      if (!runtime) throw new Error("Initialise the analysis runtime first");
      runtime.globals.set("__ml_chart_json", JSON.stringify(message));
      // Data projection only: reuse the accepted preparation/design functions.
      // No estimator is called and no existing result/export field is modified.
      result = JSON.parse(
        await runtime.runPythonAsync(`
from copy import deepcopy
import json
import pandas as pd
from macrolab.analysis.data import prepare_country
from macrolab.analysis.transforms import label, period_frequency
from macrolab.models.linear import regression_data
from macrolab.models.panel import fe_design
_req = json.loads(__ml_chart_json)
_config, _result = _req["config"], _req["result"]
_coefficients = {r["term"]: r["estimate"] for r in _result["coefficients_table"]}
_panel = _result["model_id"] == "panel.fe"
_samples = _result["panel"]["country_samples"] if _panel else {_result["country"]: _result["actual_sample"]}
_xid = next(s["concept_id"] for s in _config["series"] if s["role"] == "regressor")
_yid = next(s["concept_id"] for s in _config["series"] if s["role"] == "dependent")
_points, _intercepts = [], []
for _country, _sample in _samples.items():
    _c = deepcopy(_config)
    _c.update(deepcopy(_sample["preparation_config"]))
    _data, _checks = prepare_country(_c, _req["bundle"], _country)
    if any(v["level"] == "block" for v in _checks):
        raise ValueError("Relationship data could not reproduce the recorded estimation sample")
    if _panel:
        _d = fe_design(_data, _c)
        _idx = pd.PeriodIndex(_sample["periods"], freq=period_frequency(_c["frequency"]))
        _x, _y = _d["x"].loc[_idx], _d["y"].loc[_idx]
    else:
        _y, _x = regression_data(_data, _c)
        _x, _y = _x.loc[_sample["periods"]], _y.loc[_sample["periods"]]
    _controls = sum((_x[k] * b for k, b in _coefficients.items() if k != _xid and k in _x), start=pd.Series(0.0, index=_x.index))
    _raw_x, _raw_y = _x[_xid], _y
    if _panel:
        _xx = _raw_x - _raw_x.mean()
        _adjusted = _raw_y - _controls
        _yy = _adjusted - _adjusted.mean()
        _intercepts.append(0.0)
    else:
        _xx, _yy = _raw_x, _raw_y
        _intercepts.append(float(_controls.mean()))
    for _i in range(len(_x)):
        _points.append({"country": _country, "period": label(_x.index[_i]) if _panel else str(_x.index[_i]), "x": float(_xx.iloc[_i]), "y": float(_yy.iloc[_i]), "raw_x": float(_raw_x.iloc[_i]), "raw_y": float(_raw_y.iloc[_i])})
json.dumps({"points": _points, "x_id": _xid, "y_id": _yid, "slope": _coefficients[_xid], "intercept": _intercepts[0], "pooled": _panel}, allow_nan=False)
`),
      );
    } else if (
      [
        "run",
        "compatibility",
        "export",
        "export-methods",
        "methods",
        "encode",
        "decode",
      ].includes(type)
    ) {
      if (!runtime) throw new Error("Initialise the analysis runtime first");
      runtime.globals.set("__ml_config_json", JSON.stringify(message.config));
      runtime.globals.set("__ml_bundle_json", JSON.stringify(message.bundle));
      runtime.globals.set("__ml_token", message.token ?? "");
      runtime.globals.set("__ml_operation", type);
      runtime.globals.set("__ml_response", message.response ?? "");
      runtime.globals.set("__ml_country", message.country ?? "");
      self.postMessage({
        type: "progress",
        text: {
          run: "Estimating the selected model…",
          methods: "Estimating VAR and LP on the same dates and shock…",
          "export-methods": "Preparing matched-comparison reproduction…",
          compatibility: "Checking the selection…",
          export: "Preparing the reproduction script…",
          encode: "Preparing the configuration link…",
          decode: "Reading the shared configuration…",
        }[type],
      });
      runtime.globals.set("__ml_progress", (raw) => {
        const detail = JSON.parse(raw);
        if (detail.phase === "template_result") {
          self.postMessage({ id, type: "partial", result: detail.result });
          return;
        }
        self.postMessage({
          id,
          type: "progress",
          text: detail.phase.startsWith("forecast_")
            ? `${detail.phase === "forecast_evaluation" ? "Forecast origins" : detail.phase === "forecast_order_search" ? "ARIMA order search" : "Forecast bootstrap"}: ${detail.completed}/${detail.total}…`
            : detail.phase === "bvar_draws"
              ? `BVAR posterior: ${detail.completed}/${detail.total} draws…`
              : detail.phase === "panel_horizon"
                ? `Panel horizon ${detail.completed}/${detail.total}…`
                : detail.phase === "template_sensitivity"
                  ? `Sensitivity ${detail.completed + 1}/${detail.total}: ${detail.variant.replaceAll("_", " ")}…`
                  : detail.phase === "joint_bootstrap"
                    ? `Joint bootstrap: ${detail.completed}/${detail.total} draws`
                    : detail.phase === "country_comparison"
                      ? `Country ${detail.completed}/${detail.total}: ${detail.country}`
                      : "Identifying the common first-stage shock…",
          detail,
        });
      });
      result = JSON.parse(
        await runtime.runPythonAsync(`
from macrolab.analysis.engine import run_analysis, compatibility
from macrolab.analysis.config import encode_config, decode_config
from macrolab.export.script import standalone
if __ml_operation == "encode":
    __ml_result = encode_config(json.loads(__ml_config_json))
elif __ml_operation == "decode":
    __ml_result = decode_config(__ml_token)
elif __ml_operation == "methods":
    from macrolab.compare.methods import matched_pair
    __ml_result = matched_pair(json.loads(__ml_config_json), json.loads(__ml_bundle_json), __ml_response, __ml_country)
elif __ml_operation in {"export", "export-methods"}:
    __ml_result = standalone(json.loads(__ml_config_json), json.loads(__ml_bundle_json),
                             reproduction_environment=json.loads(__ml_reproduction_json),
                             method_pair={"response": __ml_response, "country": __ml_country} if __ml_operation == "export-methods" else None)
else:
    __ml_function = run_analysis if __ml_operation == "run" else compatibility
    __ml_options = {"progress": lambda detail: __ml_progress(json.dumps(detail))} if __ml_operation == "run" else {}
    __ml_result = __ml_function(json.loads(__ml_config_json), bundle=json.loads(__ml_bundle_json), **__ml_options)
json.dumps(__ml_result, sort_keys=True, allow_nan=False)
`),
      );
    } else {
      throw new Error("Unknown runtime operation");
    }
    self.postMessage({ id, type: "result", result });
  } catch (error) {
    self.postMessage({ id, type: "error", message: String(error) });
  } finally {
    busy = false;
  }
};
