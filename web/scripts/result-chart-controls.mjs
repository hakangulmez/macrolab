import assert from "node:assert/strict";

/** Retain the accepted page-wide chart counts and exercise relocated controls. */
export async function checkResultChartControls(page, template) {
  const primary = page.getByTestId("primary-chart");
  const cases = [];
  if (template === "same_ecb_shock") {
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      await primary.getByTestId("comparison-country").selectOption("ESP");
      for (const response of ["gdp_real", "cpi"]) {
        await primary.getByLabel("Compare response").selectOption(response);
        const caption = await primary.locator("figcaption").innerText();
        assert.match(caption, /Spain/);
        assert.match(caption, response === "cpi" ? /HICP/ : /GDP/);
        const charts = page.getByTestId("result-chart");
        assert.equal(await charts.count(), width === 375 ? 2 : 5);
        assert.equal(
          await charts
            .filter({ hasText: "Peak responses · descriptive ranking" })
            .count(),
          1,
        );
        assert.equal(
          await charts
            .filter({ hasText: "Peak responses · descriptive ranking" })
            .locator("[data-x-axis-title]")
            .getAttribute("data-x-axis-title"),
          "Country",
        );
        cases.push({
          width,
          response,
          country: "Spain",
          charts: await charts.count(),
        });
      }
    }
    await primary.getByLabel("Compare response").selectOption("gdp_real");
    await primary.getByTestId("comparison-country").selectOption("DEU");
  } else if (template === "same_ecb_shock_pooled") {
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      await primary.getByLabel("Overlay country").selectOption("ESP");
      for (const outcome of ["gdp_real", "cpi"]) {
        await primary.getByLabel("Pooled outcome").selectOption(outcome);
        const caption = await primary.locator("figcaption").innerText();
        assert.match(caption, /Spain/);
        assert.match(caption, outcome === "cpi" ? /HICP/ : /GDP/);
        cases.push({
          width,
          outcome,
          country: "Spain",
          adjacentControls: true,
        });
      }
    }
    await primary.getByLabel("Overlay country").selectOption("DEU");
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  return cases;
}
