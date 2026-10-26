import { useState } from "react";
import type { AnalysisConfig } from "../types";
import { Field } from "./Common";
import { analysisErrorMessage } from "../analysisErrors";

/** Explicit input only: never infer or change a first-stage specification. */
export function FirstStageInput({
  config,
  update,
}: {
  config: AnalysisConfig;
  update: (fn: (next: AnalysisConfig) => void) => void;
}) {
  const [value, setValue] = useState(
    JSON.stringify(config.model.params.first_stage ?? null, null, 2),
  );
  const [error, setError] = useState("");
  return (
    <div className="stack">
      <Field label="First-stage configuration (JSON)">
        <textarea
          id="first-stage-config"
          rows={6}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </Field>
      <p className="small muted">
        Paste the exported configuration of a recursive VAR with one country and
        an explicit ordering. Both stages must use the same snapshot and
        frequency.
      </p>
      <button
        onClick={() => {
          try {
            const first: unknown = JSON.parse(value);
            if (!first || typeof first !== "object" || Array.isArray(first))
              throw new Error(
                "Enter a complete first-stage configuration object.",
              );
            update((next) => {
              next.model.params.first_stage = first;
            });
            setError("");
          } catch (e) {
            setError(analysisErrorMessage(e));
          }
        }}
      >
        Use first-stage configuration
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
