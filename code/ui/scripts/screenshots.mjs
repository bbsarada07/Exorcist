// npm run shots [-- scene ...]   (requires `npm run build`; uses a locally installed Chrome/Edge, no download)
// Serves dist/ with `vite preview`, drives the UI with playwright-core and writes JPEGs to code/docs/ui/.
// Also measures the hero's frame rate in this headless browser (indicative only).
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "..", "..", "docs", "ui");
const PORT = 4179;
const URL = `http://localhost:${PORT}/`;
const CANDIDATES = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/chromium",
].filter(Boolean);
const exe = CANDIDATES.find((p) => existsSync(p));
if (!exe) throw new Error("No Chrome/Edge found; set CHROME_PATH");

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const server = spawn(process.platform === "win32" ? "npx.cmd" : "npx", ["vite", "preview", "--port", String(PORT), "--strictPort"],
  { cwd: join(here, ".."), shell: process.platform === "win32", stdio: "ignore" });

async function ready() {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(URL)).ok) return; } catch { /* not up yet */ } await wait(250); }
  throw new Error("preview server did not start");
}

const scenes = {
  async "01-hero-dark"(page) {
    await page.goto(URL); await wait(1800);
    await page.mouse.move(520, 330, { steps: 12 }); await wait(900);
  },
  async "02-hero-summoned"(page) {
    await page.goto(URL); await wait(1200);
    await page.mouse.move(980, 520, { steps: 8 });
    await page.mouse.click(700, 400); await wait(5200);
  },
  async "03-graveyard-grid"(page) {
    await page.goto(URL + "#graveyard"); await wait(800);
    await page.evaluate(() => document.getElementById("graveyard")?.scrollIntoView()); await wait(1500);
    const stone = page.locator("[data-stone]").nth(140);
    await stone.hover(); await wait(700);
  },
  async "04-graveyard-ledger"(page) {
    await page.goto(URL); await wait(600);
    await page.evaluate(() => document.getElementById("graveyard")?.scrollIntoView()); await wait(600);
    await page.getByRole("tab", { name: /ledger/i }).click(); await wait(900);
  },
  async "05-case-haunted"(page) {
    await page.goto(URL + "#/case/case_483"); await wait(2600);
  },
  async "06-reported-vs-reality"(page) {
    await page.goto(URL + "#/case/case_526"); await wait(2400);
    await page.evaluate(() => document.getElementById("reality-rift")?.scrollIntoView({ block: "center" })); await wait(1800);
  },
  async "07-exorcism-mid"(page) {
    await page.goto(URL + "#/case/case_483"); await wait(1800);
    await page.locator("#exorcism").scrollIntoViewIfNeeded(); await wait(400);
    await page.getByRole("button", { name: /perform the exorcism/i }).click(); await wait(3500);
  },
  async "08-exorcism-sealed"(page) {
    await page.goto(URL + "#/case/case_483"); await wait(1800);
    await page.locator("#exorcism").scrollIntoViewIfNeeded(); await wait(400);
    await page.getByRole("button", { name: /perform the exorcism/i }).click(); await wait(400);
    await page.keyboard.press("Space"); await wait(1600);
  },
  async "09-case-proven"(page) {
    await page.goto(URL + "#/case/case_44"); await wait(2400);
    await page.locator("#proof").scrollIntoViewIfNeeded(); await wait(900);
  },
  async "11-keyboard-palette"(page) {
    await page.goto(URL); await wait(600);
    await page.keyboard.press("/"); await wait(300);
    const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
    await page.keyboard.type("backup"); await page.keyboard.press("Enter"); await wait(300);
    await page.keyboard.press("j"); await page.keyboard.press("j"); await wait(200);
    const cursor = await page.evaluate(() => document.activeElement?.getAttribute("data-case"));
    await page.keyboard.press("Enter"); await wait(900);
    const opened = await page.evaluate(() => location.hash);
    await page.keyboard.press("Escape"); await wait(400);
    await page.keyboard.press("Control+k"); await wait(500);
    await page.keyboard.type("evidence_94"); await wait(900);
    console.log("  keyboard:", JSON.stringify({ slashFocus: focused, jCursor: cursor, enterOpened: opened }));
  },
  async "10-lite-mode"(page) {
    await page.addInitScript(() => localStorage.setItem("exorcist.lite", "1"));
    await page.goto(URL); await wait(1500);
  },
};

async function measureFps(page) {
  await page.goto(URL); await wait(2000);
  await page.mouse.click(700, 400); await wait(800);
  return page.evaluate(() => new Promise((res) => {
    let frames = 0; const t0 = performance.now();
    const f = () => { frames++; if (performance.now() - t0 < 3000) requestAnimationFrame(f); else res({ fps: Math.round(frames / ((performance.now() - t0) / 1000)), particles: document.querySelector("canvas")?.dataset.particles, tier: document.querySelector("canvas")?.dataset.tier }); };
    requestAnimationFrame(f);
  }));
}

try {
  await ready();
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: exe, headless: true, args: ["--force-color-profile=srgb"] });
  // default set = the 8 shots committed in docs/ui; name any scene (e.g. "ledger", "05") to capture extras
  const DEFAULT = ["01", "02", "03", "06", "07", "08", "09", "10"];
  const want = process.argv.slice(2);
  for (const [name, run] of Object.entries(scenes)) {
    if (want.length ? !want.some((w) => name.includes(w)) : !DEFAULT.some((d) => name.startsWith(d))) continue;
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.log(`  [${name}] pageerror:`, e.message.split(/\r?\n/)[0]));
    page.on("console", (m) => m.type() === "error" && console.log(`  [${name}] console:`, m.text().split(/\r?\n/)[0]));
    try {
      await run(page);
      await page.screenshot({ path: join(OUT, `${name}.jpg`), type: "jpeg", quality: 82 });
      console.log("shot", name);
    } catch (e) { console.log("FAILED", name, e.message.split("\n")[0]); }
    await ctx.close();
  }
  if (!want.length || want.includes("fps")) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    console.log("hero fps (headless, indicative):", JSON.stringify(await measureFps(await ctx.newPage())));
    await ctx.close();
  }
  await browser.close();
} finally {
  server.kill();
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(server.pid), "/T", "/F"], { stdio: "ignore", shell: true });
}
