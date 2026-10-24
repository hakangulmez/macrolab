export const v2Template = (id: unknown) =>
  [
    "ea_phillips_pooled",
    "same_ecb_shock_pooled",
    "ea_inflation_horse_race",
  ].includes(String(id));
