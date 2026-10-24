// 4. grid   5. search   6. filters   7. keyboard
import { test, expect, summary, gotoGrid, wait, type CaseRow } from "./fixtures";

const T = summary.totals;
const search = (page: import("@playwright/test").Page) => page.getByLabel("Search cases");
const matched = (page: import("@playwright/test").Page) => page.locator('[data-stone][data-match="1"]');
const countText = (n: number) => `${n} of ${T.cases} shown`;
// the documented search semantics: partial case id, system name, exact cited evidence id (partial once >= 10 chars)
const hit = (c: CaseRow, q: string) => c.id.includes(q) || c.sys.some((x) => x.includes(q)) || c.ev.some((e) => e === q || (q.length >= 10 && e.includes(q)));
const expected = (q: string) => summary.cases.filter((c) => hit(c, q));

test.describe("4 · grid", () => {
  test("one stone per case, status counts and review markers from the data", async ({ page }) => {
    await gotoGrid(page);
    await expect(page.locator("[data-stone]")).toHaveCount(T.cases);
    for (const [st, n] of Object.entries(T.status)) await expect(page.locator(`[data-stone][data-status="${st}"]`)).toHaveCount(n);
    await expect(page.locator('[data-stone][data-review="1"]')).toHaveCount(summary.review.count);
  });

  test("status is never colour alone: glyph + text label on every stone", async ({ page }) => {
    await gotoGrid(page);
    const glyphs = await page.locator("[data-stone]").evaluateAll((els) => {
      const by: Record<string, Set<string>> = {};
      for (const el of els) (by[el.getAttribute("data-status")!] ??= new Set()).add(el.textContent!.trim());
      return Object.fromEntries(Object.entries(by).map(([k, v]) => [k, [...v]]));
    });
    expect(Object.values(glyphs).every((g) => g.length === 1)).toBe(true);
    expect(new Set(Object.values(glyphs).flat()).size).toBe(3);
    const labels = await page.locator("[data-stone]").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")!));
    expect(labels.every((l) => /(Haunted|Proven|Not applicable) \((INCOMPLETE|COMPLETE|NOT_APPLICABLE)\)/.test(l))).toBe(true);
  });

  test("glow scales with findings (hot stones are the high-finding cases)", async ({ page }) => {
    await gotoGrid(page);
    const rows = await page.locator("[data-stone]").evaluateAll((els) => els.map((e) => ({ id: e.getAttribute("data-case")!, g: Number(getComputedStyle(e).getPropertyValue("--g")) })));
    const maxF = Math.max(...summary.cases.map((c) => c.f));
    for (const r of rows.slice(0, 60)) expect(r.g).toBeCloseTo(summary.cases.find((c) => c.id === r.id)!.f / maxF, 2);
  });
});

test.describe("5 · search", () => {
  test("case_483 → exactly one match, strip text, ring, scrolled into view", async ({ page }) => {
    const c = summary.cases.find((x) => x.id === "case_483")!;
    await gotoGrid(page);
    await search(page).fill("case_483");
    await expect(matched(page)).toHaveCount(1);
    await expect(page.locator("[data-count]")).toHaveText(countText(1));
    await expect(page.locator("[data-strip-text]")).toHaveText(
      `1 match: case_483 · ${c.s.replace("_", " ")} · ${c.f} finding${c.f === 1 ? "" : "s"} · press Enter to open`);
    const stone = page.locator('[data-case="case_483"]');
    await expect(stone.locator(".ring")).toHaveCount(1);
    await expect(stone).toHaveCSS("scale", "1.4");
    await expect.poll(async () => {
      const b = (await stone.boundingBox())!; return b.y > 80 && b.y + b.height < 900;
    }, { timeout: 6000 }).toBe(true);
    // non-matches dim to ~8% and desaturate
    const other = page.locator('[data-stone][data-match="0"]').first();
    await expect(other).toHaveCSS("opacity", "0.08");
    expect(await other.evaluate((e) => getComputedStyle(e).filter)).toContain("grayscale");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#\/case\/case_483$/);
  });

  test("partial id case_48 → several matches", async ({ page }) => {
    const want = expected("case_48");
    expect(want.length).toBeGreaterThan(1);
    await gotoGrid(page);
    await search(page).fill("case_48");
    await expect(matched(page)).toHaveCount(want.length);
    await expect(page.locator("[data-strip-text]")).toContainText(`${want.length} matches: ${want[0].id}`);
  });

  test("system name matches every case that touches it", async ({ page }) => {
    const sys = summary.cases.flatMap((c) => c.sys).sort()[0];
    const want = expected(sys);
    await gotoGrid(page);
    await search(page).fill(sys);
    await expect(matched(page)).toHaveCount(want.length);
    await expect(page.locator("[data-count]")).toHaveText(countText(want.length));
  });

  test("evidence id matches the cases that cite it", async ({ page }) => {
    const ev = summary.cases.find((c) => c.ev.length)!.ev[0];
    const want = expected(ev);
    await gotoGrid(page);
    await search(page).fill(ev);
    await expect(matched(page)).toHaveCount(want.length);
    expect(want.length).toBeGreaterThan(0);
  });

  test("gibberish → explicit no-matches state; clear restores all", async ({ page }) => {
    await gotoGrid(page);
    await search(page).fill("zzqx-nothing");
    await expect(page.locator("[data-no-matches]")).toBeVisible();
    await expect(page.locator("[data-no-matches]")).toContainText("no matches");
    await expect(page.locator("[data-count]")).toHaveText(countText(0));
    await page.locator("[data-clear]").click();
    await expect(search(page)).toHaveValue("");
    await expect(page.locator("[data-count]")).toHaveText(countText(T.cases));
    await expect(matched(page)).toHaveCount(T.cases);
    await expect(page.locator("[data-clear]")).toHaveCount(0);
  });

  for (const vp of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }]) {
    test(`count and strip are not clipped at ${vp.width}×${vp.height}`, async ({ page }) => {
      await page.setViewportSize(vp);
      await gotoGrid(page);
      await search(page).fill("case_48");
      await wait(900);
      for (const sel of ["[data-count]", "[data-strip-text]", "[data-clear]"]) {
        const el = page.locator(sel);
        await expect(el).toBeVisible();
        const fit = await el.evaluate((e) => {
          const r = e.getBoundingClientRect();
          return { overflow: e.scrollWidth - e.clientWidth, inside: r.left >= 0 && r.right <= innerWidth };
        });
        expect(fit.overflow, `${sel} text overflows`).toBeLessThanOrEqual(0);
        expect(fit.inside, `${sel} is off-screen`).toBe(true);
      }
    });
  }
});

test.describe("6 · filters", () => {
  for (const [key, n] of [["INCOMPLETE", T.status.INCOMPLETE], ["COMPLETE", T.status.COMPLETE], ["NOT_APPLICABLE", T.status.NOT_APPLICABLE], ["REVIEW", summary.review.count]] as const) {
    test(`filter ${key} → ${n}`, async ({ page }) => {
      await gotoGrid(page);
      await page.locator(`[data-filter="${key}"]`).click();
      await expect(page.locator("[data-count]")).toHaveText(countText(n));
      await expect(matched(page)).toHaveCount(n);
      await expect(page.locator(`[data-filter="${key}"]`)).toHaveAttribute("aria-pressed", "true");
    });
  }

  test("filters combine with search", async ({ page }) => {
    const sys = "search_service";
    const want = expected(sys).filter((c) => c.s === "INCOMPLETE" && c.q);
    await gotoGrid(page);
    await page.locator('[data-filter="INCOMPLETE"]').click();
    await page.locator('[data-filter="REVIEW"]').click();
    await search(page).fill(sys);
    await expect(page.locator("[data-count]")).toHaveText(countText(want.length));
    await expect(matched(page)).toHaveCount(want.length);
    await page.locator("[data-clear]").click();
    await expect(page.locator("[data-count]")).toHaveText(countText(T.cases));
  });
});

test.describe("7 · keyboard", () => {
  test('"/" focuses search, Esc clears then blurs', async ({ page }) => {
    await gotoGrid(page);
    await page.locator("body").click({ position: { x: 5, y: 400 } });
    await page.keyboard.press("/");
    await expect(search(page)).toBeFocused();
    await page.keyboard.type("case_9");
    await page.keyboard.press("Escape");
    await expect(search(page)).toHaveValue("");
    await page.keyboard.press("Escape");
    await expect(search(page)).not.toBeFocused();
  });

  test("j/k move between stones, Enter opens, Esc closes", async ({ page }) => {
    await gotoGrid(page);
    await page.locator("body").click({ position: { x: 5, y: 400 } });
    await page.keyboard.press("j");
    await page.keyboard.press("j");
    await page.keyboard.press("k");
    const second = summary.cases[1].id;
    await expect(page.locator(`[data-case="${second}"]`)).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`#/case/${second}$`));
    await expect(page.locator("[data-case-view]")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-case-view]")).toHaveCount(0);
  });

  test("ctrl+K palette jumps to a case", async ({ page }) => {
    const target = summary.cases[summary.cases.length - 1].id;
    await gotoGrid(page);
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: "Command palette" });
    await expect(dialog).toBeVisible();
    await page.keyboard.type(target);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`#/case/${target}$`));
    await expect(dialog).toHaveCount(0);
  });
});
