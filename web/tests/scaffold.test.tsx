import { buildVersion } from "../src/version";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

describe("G3 application boot", () => {
  it("renders labelled navigation and honest pending state before local assets load", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    try {
      const markup = renderToStaticMarkup(<App />);
      expect(markup).toContain('href="#main-content"');
      expect(markup).toContain('id="main-content"');
      expect(markup).toContain('aria-label="Main navigation"');
      for (const screen of [
        "home",
        "builder",
        "library",
        "results",
        "data",
        "methods",
      ]) {
        expect(markup).toContain(`data-testid="nav-${screen}"`);
      }
      expect(markup).toContain("Preparing your workspace");
      expect(markup).toContain(`${buildVersion} · Data snapshot …`);
      expect(markup).toContain('href="https://hakangulmez.github.io/"');
      expect(markup).not.toContain("Analysis complete");
      expect(markup).not.toContain("G0 tooling scaffold");
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      fetch.mockRestore();
    }
  });
});
