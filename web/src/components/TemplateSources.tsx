import { useEffect, useState } from "react";
import type { AnalysisConfig, JsonRecord } from "../types";
import { getTemplateSources } from "../runtime";
import { text } from "../format";
export function TemplateSources({ config }: { config: AnalysisConfig }) {
  const [cards, setCards] = useState<JsonRecord[]>([]),
    [error, setError] = useState("");
  const measure = String(config.model.params.policy_measure ?? "dfr");
  useEffect(() => {
    let active = true;
    void getTemplateSources(measure)
      .then((value) => {
        if (active) {
          setCards(value);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [measure]);
  return (
    <details>
      <summary>
        Selected EA source cards ·{" "}
        {measure === "dfr"
          ? "ECB DFR"
          : measure === "bis"
            ? "BIS policy rate"
            : "EA 3-month rate"}{" "}
        and SA HICP
      </summary>
      <p className="small">
        These override the catalogue’s generic policy/price concepts for stage
        1. National prices retain their original NSA HICP and calendar controls.
      </p>
      {error && <p role="alert">{error}</p>}
      {cards.map((card, i) => (
        <article key={i}>
          <strong>{text(card.title ?? card.source_series_id)}</strong>
          <p className="small">{text(card.attribution)}</p>
          <a href={text(card.source_url)} target="_blank" rel="noreferrer">
            Official source metadata / data
          </a>
        </article>
      ))}
    </details>
  );
}
