// Shared test fixtures. Every expected number is read from the exported data files (public/data, derived from
// code/out) or from the repository's output.csv — nothing is hardcoded. Every test fails if the page tries to
// reach the network beyond the local preview server or throws an uncaught error.
import { test as base, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

declare global { interface Window { __exorcist?: any } }   // eslint-disable-line @typescript-eslint/no-explicit-any

export const UI = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (p: string) => readFileSync(join(UI, p), "utf8");

type Status = "INCOMPLETE" | "COMPLETE" | "NOT_APPLICABLE";
export interface CaseRow { id: string; s: Status; r: string; f: number; n: number; q: number; c: number; v: string | null; sys: string[]; ev: string[] }
export type Step = [string, string, string, string, string, string];
export interface Detail { id: string; status: Status; reported: string; steps: Step[]; review: { reasons: string[] } | null; [k: string]: unknown }

export const summary = JSON.parse(read("public/data/summary.json")) as {
  totals: { cases: number; status: Record<Status, number> };
  lie: { headline: { reported_COMPLETE_but_incomplete_pct: number; reported_COMPLETE_cases: number }; deletion_cases: number;
         failure_modes: Record<string, { cases: number }> };
  review: { count: number };
  cases: CaseRow[];
};
export const details = JSON.parse(read("public/data/details.json")) as Record<string, Detail>;

/** output.csv at the repository root, parsed (RFC 4180 quoting). Read-only. */
export const output: Record<string, { status: string; steps: { step_no: number; phase: string; operation: string; system_id: string; resource_id: string; state: string; evidence_id: string }[] }> = (() => {
  const text = readFileSync(join(UI, "..", "..", "output.csv"), "utf8");
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...data] = rows.filter((r) => r.length > 1);
  const ix = (k: string) => head.indexOf(k);
  return Object.fromEntries(data.map((r) => [r[ix("case_id")], { status: r[ix("deletion_status")], steps: JSON.parse(r[ix("steps_json")]) }]));
})();

export const byStatus = (s: Status) => summary.cases.filter((c) => c.s === s);
/** The first case (in id order) of a status that satisfies a predicate on its output.csv steps. */
export const pick = (s: Status, pred: (steps: Detail["steps"]) => boolean = () => true) =>
  byStatus(s).map((c) => details[c.id]).find((d) => pred(d.steps))!;

export const test = base.extend<{ blocked: string[] }>({
  blocked: async ({ context }, use) => {
    const blocked: string[] = [];
    await context.route("**/*", (route) => {
      const u = new URL(route.request().url());
      if (u.hostname === "localhost" || u.hostname === "127.0.0.1") return route.continue();
      blocked.push(u.href);
      return route.abort("blockedbyclient");
    });
    await use(blocked);
    expect(blocked, "the UI must not reach the network").toEqual([]);
  },
  page: async ({ page, blocked }, use) => {
    void blocked;
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await use(page);
    expect(errors, "uncaught page errors").toEqual([]);
  },
});
export { expect };

export const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Landing page, data loaded, scrolled to the graveyard. */
export async function gotoGrid(page: Page) {
  await page.goto("/");
  await expect(page.locator("[data-stone]")).toHaveCount(summary.totals.cases);
  await page.evaluate(() => document.getElementById("graveyard")?.scrollIntoView());
  await wait(600);
}

export async function gotoCase(page: Page, id: string) {
  await page.goto(`/#/case/${id}`);
  await expect(page.locator("[data-case-view]")).toBeVisible();
  await expect(page.locator("h1", { hasText: id.replace("_", " ") })).toBeVisible();
}

export const fluidStats = (page: Page) => page.evaluate(() => {
  const f = window.__exorcist?.fluid;
  return f ? JSON.parse(JSON.stringify({ ok: f.ok, scale: f.scale, octaves: f.octaves, frames: f.frames, emaMs: f.emaMs, mode: f.mode,
    downgrades: f.downgrades, uniforms: f.uniforms, target: f.target })) : null;
}) as Promise<null | { ok: boolean; scale: number; octaves: number; frames: number; emaMs: number; mode: string;
  downgrades: { from: number; to: number }[]; uniforms: { ratio: number; violet: number; purge: number }; target: { ratio: number; violet: number } }>;
