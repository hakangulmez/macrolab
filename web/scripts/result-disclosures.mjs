/* global document, innerHeight */
import assert from "node:assert/strict";

/** Browser regression: use real clicks, then poll observable DOM state. */
export async function checkResultDisclosures(page) {
  const outer = page.getByTestId("result-details");
  const findings = page.locator("#all-findings");
  const cases = [];
  for (const initiallyOpen of [false, true]) {
    if ((await outer.getAttribute("open")) === null)
      await outer.locator(":scope > summary").click();
    if ((await findings.getAttribute("open")) !== null)
      await findings.locator(":scope > summary").click();
    if (!initiallyOpen) await outer.locator(":scope > summary").click();
    await page.waitForFunction(
      (open) =>
        document.querySelector('[data-testid="result-details"]').open === open,
      initiallyOpen,
      { timeout: 5000 },
    );
    await page
      .getByRole("button", {
        name: "All findings, source notes & technical details ↗",
        exact: true,
      })
      .click();
    await page.waitForFunction(
      () => {
        const container = document.querySelector(
          '[data-testid="result-details"]',
        );
        const target = document.querySelector("#all-findings");
        return container?.open && target?.open;
      },
      undefined,
      { timeout: 5000 },
    );
    await page.waitForFunction(
      () => {
        const target = document.querySelector("#all-findings > summary");
        const box = target.getBoundingClientRect();
        return (
          box.top >= 0 &&
          box.bottom <= innerHeight &&
          document.activeElement === target
        );
      },
      undefined,
      { timeout: 5000 },
    );
    cases.push({
      initiallyOpen,
      outerOpen: true,
      findingsOpen: true,
      targetVisible: true,
      targetFocused: true,
    });
  }
  // All rail sensitivity links share the disclosure helper, including each row.
  const links = page
    .locator(".result-rail button")
    .filter({ hasNotText: "All findings" });
  for (const link of await links.all()) {
    if ((await outer.getAttribute("open")) !== null)
      await outer.locator(":scope > summary").click();
    await link.click();
    await page.waitForFunction(
      () => document.querySelector('[data-testid="result-details"]')?.open,
      undefined,
      { timeout: 5000 },
    );
    const target = page
      .locator(
        '[data-testid="v2-template-sensitivity"], .sensitivity-section, [data-testid="forecast-results"]',
      )
      .first();
    assert(await target.isVisible(), "Sensitivity target must be visible");
    cases.push({
      link: await link.innerText(),
      outerOpen: true,
      targetVisible: true,
    });
  }
  return cases;
}
