import { createContext } from "react";
import type { PngContext } from "./pngExport";

export const ChartExportContext = createContext<PngContext | undefined>(
  undefined,
);
