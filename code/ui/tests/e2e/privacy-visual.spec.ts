// 14. privacy scan   15. visual review screenshots (test-results/visual/, reviewed by eye; curated copies in docs/ui/)
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test, expect, UI, pick, gotoCase, gotoGrid, wait } from "./fixtures";

test("14 · privacy: npm run test:privacy reports 0 leaks", () => {
  const out = execFileSync(process.execPath, [join(UI, "scripts", "test-privacy.mjs")], { cwd: UI, encoding: "utf8" });
  expect(out).toMatch(/privacy check passed/);
});

test("14 · privacy: exported emails are masked in every rendered case", async ({ page }) => {
  for (const id of [pick("INCOMPLETE").id, pick("COMPLETE").id, pick("NOT_APPLICABLE").id]) {
    await gotoCase(page, id);
    const text = await page.locator("[data-case-view]").innerText();
    expect(text).not.toMatch(/[A-Za-z0-9._%+-]{2,}@(?!••)[A-Za-z0-9-]+\.[A-Za-z]{2,}/);
  }
});

const DIR = join(UI, "test-results", "visual");
for (const vp of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
  test(`15 · visual review set at ${vp.width}×${vp.height}`, async ({ page }) => {
    test.setTimeout(120_000);
    mkdirSync(DIR, { recursive: true });
    await page.setViewportSize(vp);
    const shot = (n: string) => page.screenshot({ path: join(DIR, `${vp.width}-${n}.jpg`), type: "jpeg", quality: 80 });
    await page.goto("/"); await wait(1500); await shot("01-hero-dark");
    await page.keyboard.press("Enter"); await wait(4000); await shot("02-hero-summoned");
    await gotoGrid(page); await wait(1200); await shot("03-grid");
    await page.getByLabel("Search cases").fill("case_483"); await wait(2500); await shot("04-search");
    await page.locator("[data-clear]").click(); await page.locator('[data-filter="REVIEW"]').click(); await wait(2500); await shot("05-review-filter");
    const inc = pick("INCOMPLETE", (s) => s.some((x) => x[1] === "DISABLE_DATA_FLOW"));
    await gotoCase(page, inc.id); await wait(2200); await shot("06-case");
    await page.locator("#exorcism").scrollIntoViewIfNeeded(); await wait(400);
    await page.getByRole("button", { name: /perform the exorcism/i }).click(); await wait(2500); await shot("07-exorcism-mid");
    await page.keyboard.press("Space"); await wait(2800); await shot("08-exorcism-end");
    await page.locator("#runbook").scrollIntoViewIfNeeded(); await wait(800); await shot("09-runbook");
    await gotoCase(page, pick("COMPLETE").id); await page.locator("#proof").scrollIntoViewIfNeeded(); await wait(1500); await shot("10-proof");
  });
}
