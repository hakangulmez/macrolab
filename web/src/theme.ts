import { useSyncExternalStore } from "react";
export type Theme = "dark" | "light";
export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("macrolab-theme");
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* Storage may be unavailable. */
  }
  try {
    if (typeof matchMedia === "function") {
      if (matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
      if (matchMedia("(prefers-color-scheme: light)").matches) return "light";
    }
  } catch {
    /* Dark is the final fallback. */
  }
  return "dark";
}
if (typeof document !== "undefined")
  document.documentElement.dataset.theme = initialTheme();
export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("macrolab-theme", theme);
  } catch {
    /* The current choice still works. */
  }
  window.dispatchEvent(new Event("macrolab-theme"));
}
const subscribe = (listener: () => void) => {
  window.addEventListener("macrolab-theme", listener);
  return () => window.removeEventListener("macrolab-theme", listener);
};
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () =>
      document.documentElement.dataset.theme === "light" ? "light" : "dark",
    () => "dark",
  );
}
export function chartTheme(theme: Theme) {
  const dark = theme === "dark";
  return {
    color: dark
      ? ["#4F7FEA", "#D86E2C", "#16A38D", "#9473DE"]
      : ["#1F4FD1", "#C2570C", "#00917F", "#6E3FB3"],
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: "Inter, sans-serif",
      color: dark ? "#B9C0CC" : "#3B4250",
    },
    tooltip: {
      backgroundColor: dark ? "#161B24" : "#FFFFFF",
      borderColor: dark ? "#454F60" : "#CED2DB",
      textStyle: {
        color: dark ? "#EEF1F6" : "#11151C",
        fontFamily: "Inter, sans-serif",
        fontSize: 12,
      },
      extraCssText:
        "max-width:320px;white-space:normal;border-radius:12px;line-height:1.6;box-shadow:none;",
    },
  };
}
export const escapeHtml = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
