// 11. Lite and reduced motion keep ALL information, with no canvas running
import { test, expect, summary, output, pick, gotoCase, gotoGrid } from "./fixtures";

const T = summary.totals;
const inc = pick("INCOMPLETE");

for (const mode of ["lite", "reduced-motion"] as const) {
  test.describe(`11 · ${mode}`, () => {
    test.beforeEach(async ({ page }) => {
      if (mode === "lite") await page.addInitScript(() => localStorage.setItem("exorcist.lite", "1"));
      else await page.emulateMedia({ reducedMotion: "reduce" });
    });

    test("landing: every number, label and stone present; no canvas", async ({ page }) => {
      await page.goto("/");
      await expect(page.locator("html")).toHaveClass(/lite/);
      await expect(page.getByRole("heading", { name: "EXORCIST", level: 1 })).toBeVisible();
      for (const [key, v] of [["total", T.cases], ["haunted", T.status.INCOMPLETE], ["proven", T.status.COMPLETE], ["na", T.status.NOT_APPLICABLE]] as const)
        await expect(page.locator(`[data-counter="${key}"] [data-value]`)).toHaveAttribute("data-value", String(v));
      await expect(page.locator("[data-headline]")).toBeVisible();
      await gotoGrid(page);
      for (const [st, n] of Object.entries(T.status)) await expect(page.locator(`[data-stone][data-status="${st}"]`)).toHaveCount(n);
      await expect(page.locator('[data-stone][data-review="1"]')).toHaveCount(summary.review.count);
      await expect(page.locator("canvas")).toHaveCount(0);
      await expect(page.locator("html")).toHaveAttribute("data-fluid", "css");
      // search still works
      await page.getByLabel("Search cases").fill("case_483");
      await expect(page.locator('[data-stone][data-match="1"]')).toHaveCount(1);
      await expect(page.locator("[data-strip-text]")).toContainText("1 match: case_483");
    });

    test("case: full runbook and the exorcism end state", async ({ page }) => {
      await gotoCase(page, inc.id);
      await expect(page.locator("#runbook [data-step]")).toHaveCount(output[inc.id].steps.length);
      await expect(page.locator("#reality-rift")).toContainText(`reported_status = ${inc.reported}`);
      await page.locator("#exorcism").scrollIntoViewIfNeeded();
      await page.getByRole("button", { name: /perform the exorcism/i }).click();
      await page.keyboard.press("Space");
      await expect(page.locator("#exorcism")).toHaveAttribute("data-phase", "done");
      await expect(page.locator("#exorcism [data-final]")).toHaveCSS("opacity", "1");
      await expect(page.locator("canvas")).toHaveCount(0);
    });
  });
}

test("Lite toggle switches the running fluid off and back on", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-fluid", "webgl");
  await page.locator("[data-lite-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-fluid", "css");
  await expect(page.locator("canvas")).toHaveCount(0);
  await page.locator("[data-lite-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-fluid", "webgl");
});
