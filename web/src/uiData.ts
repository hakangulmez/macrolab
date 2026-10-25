import type { Country, Manifest } from "./types";
import { records } from "./format";
export interface CoverageCell {
  country: string;
  concept_id: string;
  status: string;
  first_date: string | null;
  last_date: string | null;
  observations: number;
  frequency: string;
  sources: string[];
  stale: boolean;
}
export const statuses = ["available", "available_note", "limited", "missing"];
export const coverage = (manifest: Manifest) =>
  records(manifest.coverage) as unknown as CoverageCell[];
export function datasetCounts(manifest: Manifest) {
  const cells = coverage(manifest);
  return {
    economies: manifest.countries.length,
    indicators: manifest.indicators.length,
    national: manifest.indicators.filter((i) => i.scope === "national").length,
    global: manifest.indicators.filter((i) => i.scope === "global").length,
    cells: cells.length,
    populated: cells.filter((c) => c.observations > 0).length,
    methods: manifest.models.length,
    templates: manifest.templates.length,
    statuses: Object.fromEntries(
      statuses.map((s) => [s, cells.filter((c) => c.status === s).length]),
    ),
  };
}
export const regionNames = [
  "Euro area",
  "Rest of Europe",
  "Americas",
  "Asia-Pacific & Israel",
];
export function region(c: Country) {
  return c.monetary_union === "EA"
    ? regionNames[0]
    : c.region === "OECD Europe"
      ? regionNames[1]
      : c.region === "OECD America"
        ? regionNames[2]
        : regionNames[3];
}
export function sortedCountries(countries: Country[]) {
  return [...countries].sort(
    (a, b) =>
      regionNames.indexOf(region(a)) - regionNames.indexOf(region(b)) ||
      a.name.localeCompare(b.name),
  );
}
export const templateTags: Record<string, string> = {
  monetary_policy: "VAR · Recursive",
  taylor_rule: "OLS · HAC",
  phillips_curve: "OLS · Rolling",
  okuns_law: "OLS · HAC",
  same_ecb_shock: "Local projections · HC1",
  tur_pass_through: "Local projections · HC1",
  ea_phillips_pooled: "Panel FE · Driscoll–Kraay",
  same_ecb_shock_pooled: "Panel LP · Driscoll–Kraay",
  ea_inflation_horse_race: "Forecast · RW, AR, ARIMA, BVAR",
};
export const templateCountries: Record<string, string> = {
  ea_phillips_pooled: "11 founding members",
  same_ecb_shock: "DE · FR · IT · ES",
  same_ecb_shock_pooled: "DE · FR · IT · ES",
  ea_inflation_horse_race: "Euro area",
};
export const newInV2 = new Set([
  "ea_phillips_pooled",
  "same_ecb_shock_pooled",
  "ea_inflation_horse_race",
]);
export const methodFamilies = [
  {
    name: "Explore & test",
    ids: [
      "desc.plot",
      "desc.corr",
      "desc.compare",
      "test.adf_kpss_pp",
      "test.granger",
    ],
  },
  { name: "Regression", ids: ["sing.ols", "sing.ardl", "sing.rolling"] },
  { name: "Trends & gaps", ids: ["filter.hp", "filter.hamilton"] },
  { name: "VAR & local projections", ids: ["var.ols", "lp.ols"] },
  {
    name: "Identify & compare",
    ids: [
      "ident.recursive",
      "ident.external_series",
      "cmp.common_shock",
      "out.hd",
    ],
  },
  { name: "Panel models", ids: ["panel.fe", "panel.lp"] },
  {
    name: "Bayesian & forecasting",
    ids: ["bvar.minn", "uni.arima", "fc.var", "fc.eval"],
  },
  { name: "Long run & breaks", ids: ["test.coint", "vecm", "test.break"] },
];
