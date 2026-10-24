// 8. case detail   9. exorcism   10. reported vs reality
import { test, expect, output, details, pick, gotoCase, fluidStats, wait } from "./fixtures";
import { REPORTED_LABEL, STATUS_LABEL } from "../../src/lib/labels";

const PHASE_ORDER = ["FINDING", "REMEDIATION", "VERIFICATION"];
const steps = (page: import("@playwright/test").Page) => page.locator("#runbook [data-step]").evaluateAll((els) =>
  els.map((e) => ({ n: Number(e.getAttribute("data-step")), phase: e.getAttribute("data-phase")!, op: e.getAttribute("data-op")!, ev: e.getAttribute("data-ev") ?? "" })));

const inc = pick("INCOMPLETE", (s) => s.some((x) => x[1] === "VERIFY_RECORD_PRESENT") && s.some((x) => x[1] === "DISABLE_DATA_FLOW"))
         ?? pick("INCOMPLETE");
const com = pick("COMPLETE");
const na = pick("NOT_APPLICABLE");

test.describe("8 · case detail", () => {
  test(`INCOMPLETE ${inc.id}: runbook equals output.csv, phases in order`, async ({ page }) => {
    const want = output[inc.id];
    expect(want.status).toBe("INCOMPLETE");
    await gotoCase(page, inc.id);
    const got = await steps(page);
    expect(got.length).toBe(want.steps.length);
    expect(got.map((g) => g.n)).toEqual(want.steps.map((s) => s.step_no));
    expect(got.map((g) => [g.phase, g.op, g.ev])).toEqual(want.steps.map((s) => [s.phase, s.operation, s.evidence_id]));
    const idx = got.map((g) => PHASE_ORDER.indexOf(g.phase));
    expect(idx).toEqual([...idx].sort((a, b) => a - b));
    await expect(page.locator("#exorcism")).toBeVisible();
  });

  test(`COMPLETE ${com.id}: only verifications, each with evidence`, async ({ page }) => {
    const want = output[com.id];
    expect(want.status).toBe("COMPLETE");
    await gotoCase(page, com.id);
    const got = await steps(page);
    expect(got.length).toBe(want.steps.length);
    expect(got.every((g) => g.phase === "VERIFICATION" && g.ev.length > 0)).toBe(true);
    await expect(page.locator("#proof [data-proof-step]")).toHaveCount(want.steps.length);
    await expect(page.locator("#exorcism")).toHaveCount(0);
  });

  test(`NOT_APPLICABLE ${na.id}: no steps`, async ({ page }) => {
    expect(output[na.id].steps).toEqual([]);
    await gotoCase(page, na.id);
    await expect(page.getByText("Nothing to exorcise.")).toBeVisible();
    await expect(page.locator("[data-step]")).toHaveCount(0);
    await expect(page.locator("#exorcism, #proof, #runbook")).toHaveCount(0);
  });

  test("review-queue case shows its reason", async ({ page }) => {
    const r = Object.values(details).find((d) => d.review)!;
    await gotoCase(page, r.id);
    await expect(page.getByText("in the review queue — why")).toBeVisible();
    await expect(page.getByText(`· ${r.review!.reasons[0]}`, { exact: true })).toBeVisible();
  });
});

test.describe("9 · exorcism", () => {
  test("runs, purges ember to green, seals, is skippable and replayable; retained records untouched", async ({ page }) => {
    await gotoCase(page, inc.id);
    const section = page.locator("#exorcism");
    await section.scrollIntoViewIfNeeded();
    await expect(section).toHaveAttribute("data-phase", "idle");
    await expect.poll(async () => (await fluidStats(page))?.target.ratio).toBe(1);

    // watch retained cards: no attribute/style writes at all during the run
    const retained = section.locator("[data-retained]");
    const nRetained = await retained.count();
    await page.evaluate(() => {
      const w = window as unknown as { __retainedMut: number };
      w.__retainedMut = 0;
      document.querySelectorAll("[data-retained]").forEach((el) =>
        new MutationObserver((m) => { w.__retainedMut += m.length; }).observe(el, { attributes: true }));
    });
    const before = await retained.evaluateAll((els) => els.map((e) => [e.textContent, getComputedStyle(e).transform, getComputedStyle(e).opacity]));

    await page.getByRole("button", { name: /perform the exorcism/i }).click();
    await expect(section).toHaveAttribute("data-phase", "running");
    await wait(1500);
    const mid = (await fluidStats(page))!;
    expect(mid.uniforms.purge).toBeGreaterThan(0);
    await page.keyboard.press("Space");                                    // skip
    await expect(section).toHaveAttribute("data-phase", "done");
    await expect(section.locator("[data-final]")).toHaveCSS("opacity", "1");
    await expect.poll(async () => (await fluidStats(page))?.uniforms.purge).toBe(1);
    await expect.poll(async () => (await fluidStats(page))?.target.ratio).toBe(0);
    await expect(page.locator("html")).toHaveAttribute("data-fluid-scene", "case:EXORCISED");
    await expect.poll(async () => (await fluidStats(page))?.uniforms.ratio ?? 1, { timeout: 15000 }).toBeLessThan(0.1);
    await expect(section.locator("[data-check]").first()).toHaveCSS("opacity", "1");

    const after = await retained.evaluateAll((els) => els.map((e) => [e.textContent, getComputedStyle(e).transform, getComputedStyle(e).opacity]));
    expect(after).toEqual(before);
    expect(await page.evaluate(() => (window as unknown as { __retainedMut: number }).__retainedMut)).toBe(0);
    expect(nRetained).toBe(output[inc.id].steps.filter((s) => s.operation === "VERIFY_RECORD_PRESENT").length);

    // replay resets ember and runs again
    await page.getByRole("button", { name: /replay the exorcism/i }).click();
    await expect(section).toHaveAttribute("data-phase", "running");
    expect((await fluidStats(page))!.target.ratio).toBe(1);
    expect((await fluidStats(page))!.uniforms.purge).toBeLessThan(0.35);
    await page.keyboard.press("Space");
    await expect(section).toHaveAttribute("data-phase", "done");
  });

  test("plays to the end on its own without input", async ({ page }) => {
    await gotoCase(page, inc.id);
    await page.locator("#exorcism").scrollIntoViewIfNeeded();
    await page.getByRole("button", { name: /perform the exorcism/i }).click();
    await expect(page.locator("#exorcism")).toHaveAttribute("data-phase", "done", { timeout: 40000 });
  });
});

test.describe("10 · reported vs reality", () => {
  // a legacy "complete" claim the evidence disproves
  const lieCase = Object.values(details).find((d) => d.reported === "COMPLETE" && d.status === "INCOMPLETE")!;
  test(`${lieCase.id}: legacy claim vs reconstructed truth`, async ({ page }) => {
    await gotoCase(page, lieCase.id);
    const rift = page.locator("#reality-rift");
    await rift.scrollIntoViewIfNeeded();
    await expect(rift).toContainText(`reported_status = ${lieCase.reported}`);
    await expect(rift).toContainText(REPORTED_LABEL[lieCase.reported]);
    await expect(rift).toContainText(STATUS_LABEL[lieCase.status]);
    await expect(rift).toContainText("lie_report.json");
  });
});
