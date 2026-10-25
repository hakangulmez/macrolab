import type { JsonRecord } from "./types";
import { record } from "./format";
import { specificationLabel } from "./resultData";

/** Approved UI wording only. Export serializers retain the original labels. */
export function sensitivityDisplayLabel(variant: JsonRecord): string {
  const original = specificationLabel(variant);
  if (original === "requested sing.rolling") {
    const params = record(record(record(variant.config).model).params);
    return params.mode === "rolling" ? "Rolling-window regression" : original;
  }
  const labels: Record<string, string> = {
    "lags 4": "4 lags",
    "lags 6": "6 lags",
    hac: "HAC inference",
    "covariance HC1": "HC1 standard errors",
    "recent half": "Recent half of the sample",
    "end 2019": "End sample in 2019",
    "common window": "Common sample window",
    "country-clustered": "Country-clustered standard errors",
    conventional: "Conventional standard errors",
    "different method and different identification":
      "National VAR · different method and different identification",
  };
  return labels[original] ?? original;
}
