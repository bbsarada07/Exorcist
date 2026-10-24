// 12. axe-core: no serious/critical violations on hero, grid and case detail, sampled at three fluid frames
import AxeBuilder from "@axe-core/playwright";
import { test, expect, pick, gotoCase, gotoGrid, wait } from "./fixtures";

const scenes = {
  hero: async (page: import("@playwright/test").Page) => { await page.goto("/"); await page.keyboard.press("Enter"); await wait(2500); },
  grid: async (page: import("@playwright/test").Page) => { await gotoGrid(page); },
  "case detail": async (page: import("@playwright/test").Page) => { await gotoCase(page, pick("INCOMPLETE").id); await wait(1500); },
};

test.describe("12 · accessibility", () => {
  for (const [name, go] of Object.entries(scenes)) {
    test(`${name}: 0 serious/critical at three fluid frames`, async ({ page }) => {
      await go(page);
      const report: string[] = [];
      for (let frame = 0; frame < 3; frame++) {
        const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
        const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        report.push(...bad.map((v) => `frame ${frame}: ${v.id} (${v.impact}) × ${v.nodes.length}: ${v.nodes[0]?.target.join(" ")}`));
        await wait(900);
      }
      expect(report).toEqual([]);
    });
  }

  test("visible focus rings on search, chips and stones", async ({ page }) => {
    await gotoGrid(page);
    const ring = (sel: string) => page.locator(sel).first().evaluate((e: HTMLElement) => {
      e.focus({ preventScroll: true });
      const cs = getComputedStyle(e);
      return (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 1) || (cs.boxShadow !== "none" && cs.boxShadow !== "");
    });
    await page.keyboard.press("Tab");                 // switch Chrome to keyboard modality so :focus-visible applies
    for (const sel of ['[data-filter="INCOMPLETE"]', '[data-stone][data-match="1"]', "[data-lite-toggle]"]) expect(await ring(sel), sel).toBe(true);
  });
});
