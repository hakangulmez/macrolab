import { version } from "../package.json";
export const buildVersion = `v${version.replace(/\.0$/, "")}`;
export const snapshotDate = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(`${value}T00:00:00Z`))
    : "…";
