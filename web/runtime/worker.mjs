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
          text:
            detail.phase === "template_sensitivity"
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
