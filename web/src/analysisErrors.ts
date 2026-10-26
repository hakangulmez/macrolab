/** Keep Python diagnostics out of user-facing error messages. */
export function analysisErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const lines = raw.split("\n");
  const last = [...lines]
    .reverse()
    .find((line) =>
      /^(?:[\w.]+\.)?\w*(?:Error|Exception):\s*\S/.test(line.trim()),
    );
  const message = (last ?? raw)
    .trim()
    .replace(/^(?:(?:[\w.]+\.)?\w*(?:Error|Exception):\s*)+/, "");
  return /Traceback|PythonError|File "[^"\n]+", line \d|\n\s+at /.test(message)
    ? "The analysis could not be completed. Review the model and its inputs."
    : message;
}
export function errorControl(message: string, model?: string) {
  if (
    model === "cmp.common_shock" &&
    /first.stage|recursive|identification/i.test(message)
  )
    return {
      id: "first-stage-config",
      label: "Review first-stage configuration",
    };
  if (/recursive|identification/i.test(message))
    return {
      id: "identification-control",
      label: "Review recursive identification",
    };
  if (/series|variable|role|transform/i.test(message))
    return { id: "step-Indicators", label: "Review indicators and roles" };
  return { id: "step-Model", label: "Review model and sample" };
}
