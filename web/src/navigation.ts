import type { Screen } from "./types";

export interface Route {
  screen: Screen;
  methodsOpen: boolean;
}
export function routeFromHash(hash: string): Route | null {
  const name = hash.replace(/^#/, "");
  if (["", "home", "explore", "templates"].includes(name))
    return { screen: "home", methodsOpen: false };
  if (["models", "library"].includes(name))
    return { screen: "builder", methodsOpen: true };
  if (["builder", "build"].includes(name))
    return { screen: "builder", methodsOpen: false };
  if (
    [
      "methods",
      "about",
      "models-methods",
      "methods-validation",
      "source-terms",
      "diagnostic-rules",
      "method-families",
      "official-sources",
    ].includes(name)
  )
    return { screen: "methods", methodsOpen: false };
  if (["data", "catalogue", "results"].includes(name))
    return { screen: name as Screen, methodsOpen: false };
  // In-page anchors (including Skip to content) do not change screens.
  return null;
}
export function screenHash(screen: Screen): string {
  return screen === "home"
    ? ""
    : screen === "library"
      ? "models"
      : screen === "methods"
        ? "about"
        : screen;
}
