import type { Indicator } from "./types";
// Display geography only; concept definitions and numerical inputs are unchanged.
const EU = new Set([
  "EA",
  "AUT",
  "BEL",
  "BGR",
  "HRV",
  "CYP",
  "CZE",
  "DNK",
  "EST",
  "FIN",
  "FRA",
  "DEU",
  "GRC",
  "HUN",
  "IRL",
  "ITA",
  "LVA",
  "LTU",
  "LUX",
  "MLT",
  "NLD",
  "POL",
  "PRT",
  "ROU",
  "SVK",
  "SVN",
  "ESP",
  "SWE",
]);
const EA = new Set([
  "EA",
  "AUT",
  "BEL",
  "BGR",
  "HRV",
  "CYP",
  "EST",
  "FIN",
  "FRA",
  "DEU",
  "GRC",
  "IRL",
  "ITA",
  "LVA",
  "LTU",
  "LUX",
  "MLT",
  "NLD",
  "PRT",
  "SVK",
  "SVN",
  "ESP",
]);
export function countryIndicators(
  indicators: Indicator[],
  country: string,
): Indicator[] {
  return indicators.map((indicator) => ({
    ...indicator,
    title:
      indicator.concept_id === "cpi"
        ? `${EU.has(country) ? "HICP" : "CPI"} · headline prices`
        : indicator.concept_id === "cpi_core"
          ? `${EU.has(country) ? "HICP" : "CPI"} · core prices`
          : indicator.concept_id === "policy_rate"
            ? EA.has(country)
              ? "Policy rate · ECB"
              : "Policy rate"
            : indicator.title,
  }));
}
