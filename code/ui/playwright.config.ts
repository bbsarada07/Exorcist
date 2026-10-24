// End-to-end tests run against the production build served by `vite preview` (npm run build && npm run preview).
// They drive a locally installed Chrome/Edge (no browser download) with the real GPU enabled, so the WebGL
// fluid is exercised the way a judge's laptop would run it. Set CHROME_PATH to point at another browser.
import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const PORT = 4173;
const exe = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome", "/usr/bin/chromium",
].find((p) => p && existsSync(p));

export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "test-results/artifacts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  workers: 3,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
  webServer: {
    command: `npm run build && npx vite preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}/`,
    timeout: 240_000,
    reuseExistingServer: !!process.env.E2E_REUSE,
    stdout: "ignore",
  },
  use: {
    baseURL: `http://localhost:${PORT}/`,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    launchOptions: {
      executablePath: exe,
      args: [...(process.env.SOFTWARE_GL ? ["--use-angle=swiftshader"] : ["--enable-gpu"]), "--ignore-gpu-blocklist", "--force-color-profile=srgb"],
    },
    trace: "off",
    video: "off",
  },
  projects: [
    { name: "functional", testIgnore: /perf\.spec\.ts/ },
    // timing-sensitive: runs alone, after everything else has finished
    { name: "perf", testMatch: /perf\.spec\.ts/, dependencies: ["functional"], fullyParallel: false },
  ],
});
