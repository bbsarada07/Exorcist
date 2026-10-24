// 1. load + data counters   2. hero
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test, expect, summary, UI, wait } from "./fixtures";

const t = summary.totals;
const lie = summary.lie.headline;

test.describe("1 · load and data", () => {
  test("loads only local derived data files", async ({ page }) => {
    const data: string[] = [];
    page.on("request", (r) => { const p = new URL(r.url()).pathname; if (p.startsWith("/data/")) data.push(p); });
    await page.goto("/");
    await expect(page.locator("[data-stone]")).toHaveCount(t.cases);
    expect(data).toContain("/data/summary.json");
    expect(data.every((p) => /^\/data\/(summary|details)\.json$/.test(p))).toBe(true);
  });

  test("hero counters equal summary.json", async ({ page }) => {
    await page.goto("/");
    await page.locator("#summoning").click({ position: { x: 300, y: 300 } });
    const want = { total: t.cases, haunted: t.status.INCOMPLETE, proven: t.status.COMPLETE, na: t.status.NOT_APPLICABLE };
    for (const [key, value] of Object.entries(want)) {
      await expect(page.locator(`[data-counter="${key}"] [data-value]`)).toHaveAttribute("data-value", String(value));
    }
    await expect(page.locator('[data-counter="lie"] [data-value]')).toHaveAttribute("data-value", `${lie.reported_COMPLETE_but_incomplete_pct.toFixed(1)}%`);
    await expect(page.locator("[data-hero-panel]")).toContainText(`${lie.reported_COMPLETE_cases} cases claimed`);
  });

  test("no dataset number is hardcoded in the UI source", () => {
    const nums = [t.cases, t.status.INCOMPLETE, t.status.COMPLETE, summary.review.count, lie.reported_COMPLETE_cases, lie.reported_COMPLETE_but_incomplete_pct];
    const files: string[] = [];
    const walk = (d: string) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.(tsx?|css)$/.test(f) && files.push(p); });
    walk(join(UI, "src"));
    const hits = files.flatMap((f) => nums.filter((n) => new RegExp(`(?<![\\w.#-])${String(n).replace(".", "\\.")}(?![\\w.%-])`).test(readFileSync(f, "utf8"))).map((n) => `${f}: ${n}`));
    expect(hits).toEqual([]);
  });
});

test.describe("2 · hero", () => {
  test("dark stage, prompt, summon reveals headline and counters", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("01 · the summoning")).toBeVisible();
    await expect(page.getByText("something was never deleted.")).toBeVisible();
    const canvas = page.locator("[data-hero-canvas]");
    await expect(canvas).toHaveAttribute("data-particles", /^\d+$/);
    expect(Number(await canvas.getAttribute("data-particles"))).toBeGreaterThan(0);
    await page.keyboard.press("Enter");
    const headline = page.locator("[data-headline]");
    await expect(headline).toHaveAttribute("aria-label", "Deleted data does not stay dead unless you prove it.");
    await expect(headline.locator(".line-mask.in")).toHaveCount(2, { timeout: 5000 });
    await expect(page.locator("[data-counter]")).toHaveCount(5);
    await expect(page.locator('[data-counter="haunted"] .heartbeat')).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "EXORCIST", level: 1 })).toBeAttached();
    await expect(page, "Enter on the hero summons; it must not open a case").not.toHaveURL(/#\/case\//);
  });

  test("auto-summons so the demo never sits empty", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-hero-panel]")).toBeVisible({ timeout: 9000 });
  });

  test("hero shows no unmasked personal data", async ({ page }) => {
    await page.goto("/");
    await page.mouse.move(500, 320, { steps: 10 });
    await wait(1500);
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/[A-Za-z0-9._%+-]{2,}@(?!••)[A-Za-z0-9-]+\.[A-Za-z]{2,}/);
    expect(text).not.toMatch(/\b[0-9a-f]{64}\b/);
  });
});
