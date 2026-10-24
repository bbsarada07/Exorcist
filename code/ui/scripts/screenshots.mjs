// npm run shots [-- scene ...]   (requires `npm run build`; uses a locally installed Chrome/Edge, no download)
// Serves dist/ with `vite preview`, drives the UI with playwright-core and writes JPEGs to code/docs/ui/
// (or $SHOTS_DIR, e.g. code/docs/ui/before for the comparison set).
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = process.env.SHOTS_DIR ? resolve(process.env.SHOTS_DIR) : join(here, "..", "..", "docs", "ui");
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

const toGrid = async (page) => {
  await page.goto(URL); await wait(700);
  await page.evaluate(() => document.getElementById("graveyard")?.scrollIntoView()); await wait(1400);
};
const startExorcism = async (page) => {
  await page.goto(URL + "#/case/case_483"); await wait(1800);
  await page.locator("#exorcism").scrollIntoViewIfNeeded(); await wait(500);
  await page.getByRole("button", { name: /perform the exorcism/i }).click();
};

const scenes = {
  async "01-hero-dark"(page) { await page.goto(URL); await wait(1800); await page.mouse.move(520, 330, { steps: 12 }); await wait(900); },
  async "02-hero-summoned"(page) { await page.goto(URL); await wait(1200); await page.mouse.move(980, 520, { steps: 8 }); await page.mouse.click(700, 400); await wait(5200); },
  async "03-grid-default"(page) { await toGrid(page); await page.locator("[data-stone]").nth(140).hover({ force: true }); await wait(900); },
  async "04-grid-search-case_483"(page) { await toGrid(page); await page.getByLabel("Search cases").fill("case_483"); await wait(2800); },
  async "05-grid-filter-haunted"(page) { await toGrid(page); await page.getByRole("button", { name: /^haunted/i }).first().click(); await wait(2600); },
  async "06-case-detail"(page) { await page.goto(URL + "#/case/case_483"); await wait(2600); },
  async "07-exorcism-start"(page) { await startExorcism(page); await wait(700); },
  async "08-exorcism-mid"(page) { await startExorcism(page); await wait(3500); },
  async "09-exorcism-end"(page) { await startExorcism(page); await wait(400); await page.keyboard.press("Space"); await wait(1800); },
  async "10-proof-view"(page) { await page.goto(URL + "#/case/case_44"); await wait(2400); await page.locator("#proof").scrollIntoViewIfNeeded(); await wait(1200); },
  async "11-lite-mode"(page) { await page.addInitScript(() => localStorage.setItem("exorcist.lite", "1")); await page.goto(URL); await wait(1500); },
  async "12-reported-vs-reality"(page) {
    await page.goto(URL + "#/case/case_526"); await wait(2400);
    await page.evaluate(() => document.getElementById("reality-rift")?.scrollIntoView({ block: "center" })); await wait(1800);
  },
};

try {
  await ready();
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: exe, headless: true, args: ["--force-color-profile=srgb", ...(process.env.SOFTWARE_GL ? ["--use-angle=swiftshader"] : ["--enable-gpu"]), "--ignore-gpu-blocklist"] });
  const want = process.argv.slice(2);
  for (const [name, run] of Object.entries(scenes)) {
    if (want.length && !want.some((w) => name.includes(w))) continue;
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
  await browser.close();
} finally {
  server.kill();
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(server.pid), "/T", "/F"], { stdio: "ignore", shell: true });
}
