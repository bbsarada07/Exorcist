// 13. performance: fps + p95 frame time over 10 s under 4x CPU throttle, auto-downgrade, gzipped bundle.
// Results are written to test-results/perf.json and copied into docs/UI_TEST_REPORT.md.
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { test, expect, gotoGrid, fluidStats, wait, UI } from "./fixtures";

const OUT = join(UI, "test-results", process.env.SOFTWARE_GL ? "perf-swiftshader.json" : "perf.json");
const results: Record<string, unknown> = existsSync(OUT) ? JSON.parse(readFileSync(OUT, "utf8")) : {};
const save = (k: string, v: unknown) => { results[k] = v; mkdirSync(join(UI, "test-results"), { recursive: true }); writeFileSync(OUT, JSON.stringify(results, null, 2)); };

/** rAF frame deltas for `ms`, while the pointer keeps moving (stirs the fluid, triggers hovers). */
async function measure(page: import("@playwright/test").Page, ms: number) {
  const run = page.evaluate((ms) => new Promise<number[]>((done) => {
    const d: number[] = []; let last = performance.now(); const end = last + ms;
    const f = (t: number) => { d.push(t - last); last = t; if (t < end) requestAnimationFrame(f); else done(d); };
    requestAnimationFrame(f);
  }), ms);
  const box = page.viewportSize()!;
  for (let i = 0; i < ms / 500; i++) { await page.mouse.move(200 + ((i * 137) % (box.width - 400)), 250 + ((i * 89) % (box.height - 400)), { steps: 6 }); await wait(450); }
  const d = (await run).slice(5);
  const sorted = [...d].sort((a, b) => a - b);
  const avg = d.reduce((a, b) => a + b, 0) / d.length;
  return { frames: d.length, avgFps: +(1000 / avg).toFixed(1), p95Ms: +sorted[Math.floor(sorted.length * 0.95)].toFixed(1), worstMs: +sorted[sorted.length - 1].toFixed(1) };
}

test.describe("13 · performance", () => {
  for (const scene of ["hero", "grid"] as const) {
    test(`${scene}: ≥ 50 fps average under 4× CPU throttle`, async ({ page }) => {
      test.setTimeout(90_000);
      if (scene === "hero") { await page.goto("/"); await page.keyboard.press("Enter"); await wait(3500); }
      else { await gotoGrid(page); await wait(1500); }
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
      await wait(1500);
      const m = await measure(page, 10_000);
      const st = await fluidStats(page);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
      save(`${scene}_4x`, { ...m, fluidScale: st?.scale, fluidOctaves: st?.octaves, downgrades: st?.downgrades, gl: process.env.SOFTWARE_GL ? "swiftshader" : "gpu" });
      expect(m.avgFps).toBeGreaterThanOrEqual(50);
    });
  }

  test("auto mode downgrades 0.5 → 0.35 → 0.25 when frames stay slow", async ({ page }) => {
    await page.goto("/");
    await expect.poll(async () => (await fluidStats(page))?.frames ?? 0).toBeGreaterThan(20);
    const start = (await fluidStats(page))!;
    expect(start.mode).toBe("auto");
    await page.evaluate(() => window.__exorcist!.fluid!.simulateLoad(32));     // ~30 fps worth of extra work per frame
    await expect.poll(async () => (await fluidStats(page))!.scale, { timeout: 20_000 }).toBe(0.25);
    // still slow at the lowest scale → hands over to the CSS gradient (last rung)
    await expect(page.locator("html")).toHaveAttribute("data-fluid", "css", { timeout: 15_000 });
    await expect(page.locator(".fluid-css")).toHaveCSS("opacity", "1");
    const st = (await fluidStats(page))!;
    await page.evaluate(() => window.__exorcist!.fluid!.simulateLoad(0));
    // a contiguous ladder ending in the CSS hand-over (it may already have stepped down before `start` was read)
    const ladder = [[0.5, 0.35], [0.35, 0.25], [0.25, 0]];
    expect(st.downgrades.map((d) => [d.from, d.to])).toEqual(ladder.slice(ladder.length - st.downgrades.length));
    expect(st.downgrades.length).toBeGreaterThanOrEqual(start.scale === 0.5 ? 3 : 2);
    await expect(page.locator("[data-slow-hint]")).toBeVisible();
    await page.locator("[data-slow-hint]").click();
    await expect(page.locator("html")).toHaveClass(/lite/);
    await expect(page.locator("[data-slow-hint]")).toHaveCount(0);
    save("downgrade", { startScale: start.scale, steps: st.downgrades });
  });

  test("performance control: High and Low pin the render scale", async ({ page }) => {
    await page.goto("/");
    await expect.poll(async () => (await fluidStats(page))?.frames ?? 0).toBeGreaterThan(5);
    await page.locator('[data-perf="low"]').click();
    await expect.poll(async () => (await fluidStats(page))!.scale).toBe(0.25);
    await page.locator('[data-perf="high"]').click();
    await expect.poll(async () => (await fluidStats(page))!.scale).toBe(0.5);
    await page.evaluate(() => window.__exorcist!.fluid!.simulateLoad(32));
    await wait(2500);
    expect((await fluidStats(page))!.scale, "High never downgrades").toBe(0.5);
    await page.evaluate(() => window.__exorcist!.fluid!.simulateLoad(0));
    await page.locator('[data-perf="auto"]').click();
  });

  test("initial bundle < 1.5 MB gzipped", () => {
    const dist = join(UI, "dist");
    const html = readFileSync(join(dist, "index.html"), "utf8");
    const initial = [...html.matchAll(/(?:src|href)="(?:\.?\/)?(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]);
    const gz = (f: string) => gzipSync(readFileSync(join(dist, f))).length;
    const initialGz = initial.reduce((s, f) => s + gz(f), 0) + gzipSync(html).length;
    const all: string[] = [];
    const walk = (d: string) => readdirSync(d).forEach((f) => { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : all.push(p); });
    walk(join(dist, "assets"));
    const lazy = all.filter((p) => p.endsWith(".js") && !initial.some((i) => p.replace(/\\/g, "/").endsWith(i)));
    save("bundle", {
      initialFiles: initial, initialGzipKB: +(initialGz / 1024).toFixed(1),
      lazyChunksGzipKB: Object.fromEntries(lazy.map((p) => [p.split(/[\\/]/).pop(), +(gzipSync(readFileSync(p)).length / 1024).toFixed(1)])),
      fontsKB: +(all.filter((p) => /\.woff2?$/.test(p)).reduce((s, p) => s + statSync(p).size, 0) / 1024).toFixed(1),
    });
    expect(initial.length).toBeGreaterThan(0);
    expect(initialGz).toBeLessThan(1.5 * 1024 * 1024);
  });
});
