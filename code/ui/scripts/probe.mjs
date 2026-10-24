// Dev helper: node scripts/probe.mjs  — prints live UI state from a headless run (fluid stats, scroll, search).
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const PORT = 4183, URL = `http://localhost:${PORT}/`;
const exe = [process.env.CHROME_PATH, "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome"].find((p) => p && existsSync(p));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const server = spawn(process.platform === "win32" ? "npx.cmd" : "npx", ["vite", "preview", "--port", String(PORT), "--strictPort"],
  { cwd: join(here, ".."), shell: process.platform === "win32", stdio: "ignore" });
try {
  for (let i = 0; i < 60; i++) { try { if ((await fetch(URL)).ok) break; } catch { /* starting */ } await wait(250); }
  const browser = await chromium.launch({ executablePath: exe, headless: true, args: [...(process.env.SOFTWARE_GL ? ["--use-angle=swiftshader"] : ["--enable-gpu"]), "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("console", (m) => console.log("  console:", m.type(), m.text().slice(0, 200)));
  await page.goto(URL); await wait(3500);
  console.log("fluid:", await page.evaluate(() => ({ kind: document.documentElement.dataset.fluid, stats: window.__exorcist?.fluid && {
    ok: window.__exorcist.fluid.ok, scale: window.__exorcist.fluid.scale, frames: window.__exorcist.fluid.frames, ema: window.__exorcist.fluid.emaMs,
    u: window.__exorcist.fluid.uniforms, target: window.__exorcist.fluid.target } })));
  await page.evaluate(() => document.getElementById("graveyard")?.scrollIntoView()); await wait(1200);
  await page.getByLabel("Search cases").fill("case_483"); await wait(1500);
  console.log("search:", await page.evaluate(() => ({
    scrollY, strip: document.querySelector("[data-strip-text]")?.textContent, count: document.querySelector("[data-count]")?.textContent,
    match: (() => { const r = document.querySelector('[data-case="case_483"]')?.getBoundingClientRect(); return r && [Math.round(r.top), Math.round(r.left)]; })(),
    header: Math.round(document.querySelector("header")?.getBoundingClientRect().top ?? -1),
    htmlTransform: getComputedStyle(document.querySelector("main")).transform,
  })));
  await browser.close();
} finally {
  server.kill();
  if (process.platform === "win32") spawn("taskkill", ["/pid", String(server.pid), "/T", "/F"], { stdio: "ignore", shell: true });
}
