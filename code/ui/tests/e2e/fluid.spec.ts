// 3. fluid "ink in water": WebGL path, data-driven uniforms, CSS fallbacks
import { test, expect, summary, pick, gotoCase, fluidStats, wait } from "./fixtures";

const s = summary.totals.status;
const landingRatio = s.INCOMPLETE / (s.INCOMPLETE + s.COMPLETE);
const landingViolet = (summary.lie.failure_modes.active_data_flow?.cases ?? 0) / summary.lie.deletion_cases;

/** Mean luminance + a coarse fingerprint of the fluid canvas (preserveDrawingBuffer keeps it readable). */
const sample = (page: import("@playwright/test").Page) => page.evaluate(() => {
  const c = document.querySelector<HTMLCanvasElement>("[data-fluid-canvas]")!;
  const o = document.createElement("canvas"); o.width = 64; o.height = 36;
  const g = o.getContext("2d")!; g.drawImage(c, 0, 0, 64, 36);
  const px = g.getImageData(0, 0, 64, 36).data;
  let sum = 0, min = 255, max = 0; const fp: number[] = [];
  for (let i = 0; i < px.length; i += 4) { const l = (px[i] + px[i + 1] + px[i + 2]) / 3; sum += l; min = Math.min(min, l); max = Math.max(max, l); fp.push(l); }
  return { mean: sum / (px.length / 4), min, max, fp };
});

test.describe("3 · fluid", () => {
  test("WebGL context, shader compiled, frames rendering", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-fluid", "webgl");
    await expect.poll(async () => (await fluidStats(page))?.frames ?? 0).toBeGreaterThan(20);
    const st = (await fluidStats(page))!;
    expect(st.ok).toBe(true);
    expect([0.5, 0.35, 0.25]).toContain(st.scale);
    expect(await page.locator("[data-fluid-canvas]").evaluate((c: HTMLCanvasElement) => !!c.getContext("webgl"))).toBe(true);
  });

  test("pixels are non-blank, dark (text-safe) and moving", async ({ page }) => {
    await page.goto("/");
    await expect.poll(async () => (await fluidStats(page))?.frames ?? 0).toBeGreaterThan(30);
    const a = await sample(page);
    await wait(1200);
    const b = await sample(page);
    expect(a.max - a.min, "fluid has structure, not a flat fill").toBeGreaterThan(4);
    expect(a.mean, "fluid stays low-brightness behind text").toBeLessThan(90);
    const diff = a.fp.reduce((d, v, i) => d + Math.abs(v - b.fp[i]), 0) / a.fp.length;
    expect(diff, "fluid changes between frames").toBeGreaterThan(0.05);
  });

  test("landing uniforms equal the real haunted share and active-flow share", async ({ page }) => {
    await page.goto("/");
    await expect.poll(async () => (await fluidStats(page))?.target.ratio).toBeCloseTo(landingRatio, 4);
    const st = (await fluidStats(page))!;
    expect(st.target.violet).toBeCloseTo(landingViolet, 4);
    await expect.poll(async () => Math.abs(((await fluidStats(page))?.uniforms.ratio ?? 9) - landingRatio), { timeout: 15000 }).toBeLessThan(0.01);
    await expect(page.locator("html")).toHaveAttribute("data-fluid-scene", "landing");
  });

  test("case page: INCOMPLETE turns ember, COMPLETE turns green", async ({ page }) => {
    const inc = pick("INCOMPLETE"), com = pick("COMPLETE");
    await gotoCase(page, inc.id);
    await expect.poll(async () => (await fluidStats(page))?.target.ratio).toBe(1);
    await expect(page.locator("html")).toHaveAttribute("data-fluid-scene", "case:INCOMPLETE");
    await gotoCase(page, com.id);
    await expect.poll(async () => (await fluidStats(page))?.target.ratio).toBe(0);
    await expect(page.locator("html")).toHaveAttribute("data-fluid-scene", "case:COMPLETE");
  });

  test("active data flows add violet in proportion to DISABLE_DATA_FLOW steps", async ({ page }) => {
    const flows = pick("INCOMPLETE", (st) => st.some((x) => x[1] === "DISABLE_DATA_FLOW"));
    const n = flows.steps.filter((x) => x[1] === "DISABLE_DATA_FLOW").length;
    await gotoCase(page, flows.id);
    await expect.poll(async () => (await fluidStats(page))?.target.violet).toBeCloseTo(Math.min(1, n / 2), 4);
  });

  test("no WebGL → CSS gradient fallback carrying the same mapping", async ({ page }) => {
    await page.addInitScript(() => {
      const orig = HTMLCanvasElement.prototype.getContext;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (HTMLCanvasElement.prototype as any).getContext = function (type: string, ...rest: unknown[]) {
        return /webgl/.test(type) ? null : orig.call(this, type as "2d", ...(rest as []));
      };
    });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-fluid", "css");
    await expect(page.locator(".fluid-css")).toHaveCSS("opacity", "1");
    await expect(page.locator("[data-stone]")).toHaveCount(summary.totals.cases);
    const ember = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--fluid-ember").trim());
    expect(Number(ember)).toBeCloseTo(landingRatio, 2);
  });

  test("reduced motion → CSS gradient, no canvas at all", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-fluid", "css");
    await expect(page.locator("canvas")).toHaveCount(0);
  });
});
