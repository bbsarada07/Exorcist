# UI test report

**Result: 56 / 56 Playwright tests pass, the privacy scan reports 0 findings, and the performance budget is met
(GPU, 4× CPU throttle).** The final run was a clean clone of `deletion-audit-agent` (`npm ci && npm test`) on
2026-10-24: 56 passed in 2.4 min, 0 flaky, 0 skipped. Four earlier full local runs during the final round of fixes
were also all green.

## How to run

```bash
cd code/ui
npm ci
npm test               # = npm run test:privacy && npm run test:e2e
```

`test:e2e` builds the app (`npm run build`), serves it with `vite preview` on port 4173 and drives a locally installed
Chrome or Edge (`CHROME_PATH` overrides it). No browser is downloaded. `SOFTWARE_GL=1` switches to software WebGL
(SwiftShader) to simulate a machine without a usable GPU.

What every test enforces:

- **Offline.** All requests outside `localhost` are blocked, and any attempted request fails the test.
- **No uncaught page errors.**
- **No invented numbers.** Expected values are read from `public/data/*.json` or the repository's `output.csv`, never
  typed into the tests.

Environment: Windows 11, Node 24.14.1, Playwright 1.62.1, Chrome 156.0.8078.47 headless with
`--enable-gpu --ignore-gpu-blocklist`, AMD Ryzen 5 8645HS with Radeon 760M, 1440×900 viewport unless stated.

## Results by area

| # | Area | What is checked | Result |
|---|---|---|---|
| 1 | Load + data | Only `/data/summary.json` and `/data/details.json` are fetched. Hero counters equal `summary.json` (518 / 355 / 153 / 10 / 64.2 %). No dataset number appears as a literal anywhere in `src/` | 3 / 3 pass |
| 2 | Hero | Section label, prompt, particle canvas with a particle count. Enter summons the headline (both mask lines revealed), five counters and the heartbeat. The `EXORCIST` h1 is in the a11y tree. Enter does **not** open a case. Auto-summon happens within 9 s. Body text contains no unmasked email or 64-hex hash | 3 / 3 pass |
| 3 | Fluid | WebGL context, shader compiled, frames advancing. Pixels have structure (max − min > 4), stay dark (mean < 90 / 255) and change between samples. Landing `target.ratio` = 355/508 and `target.violet` = 113/508 (4 dp), and the live uniform converges within 0.01. Case pages: INCOMPLETE → 1, COMPLETE → 0, violet = DISABLE_DATA_FLOW steps / 2. With WebGL disabled the page uses the CSS gradient with `--fluid-ember` = 0.699. Reduced motion renders no canvas at all | 7 / 7 pass |
| 4 | Grid | 518 stones; 355 / 153 / 10 by status; 64 review markers. One glyph per status, three distinct glyphs, and a text label in every aria-label. Glow `--g` = findings / max | 3 / 3 pass |
| 5 | Search | `case_483` → exactly 1 match. Strip text is exact (`1 match: case_483 · INCOMPLETE · 4 findings · press Enter to open`). The stone gets a ring and `scale` 1.4 and is scrolled into view; non-matches go to opacity 0.08 with grayscale; Enter opens the case. `case_48` → several. A system name and an evidence id match the same cases as the documented rule. Gibberish shows the explicit "no matches" state; ✕ clear restores 518. Count, strip and clear button never overflow and stay on-screen at 1280×720 and 1920×1080 | 8 / 8 pass |
| 6 | Filters | INCOMPLETE 355, COMPLETE 153, NOT_APPLICABLE 10, REVIEW 64 (`aria-pressed`). INCOMPLETE + REVIEW + `search_service` combine to the intersection computed from the data | 5 / 5 pass |
| 7 | Keyboard | `/` focuses search; Esc clears, then blurs. `j` `j` `k` focuses the 2nd stone; Enter opens; Esc closes. `ctrl+K` → type a case id → Enter opens it | 3 / 3 pass |
| 8 | Case detail | INCOMPLETE case: runbook step numbers, phases, operations and evidence ids equal `output.csv` exactly, with phases in order. COMPLETE case: only VERIFICATION steps, each citing evidence, and a matching proof list. NOT_APPLICABLE case: no steps, no exorcism, no runbook. A review-queue case shows its reason | 4 / 4 pass |
| 9 | Exorcism | Run (purge > 0 mid-run), then Space skips to the sealed end (`data-final` opacity 1, purge = 1, target ratio 0, scene `case:EXORCISED`, live ratio < 0.1, checks visible). Retained cards: zero attribute mutations, identical text/transform/opacity, and count = VERIFY_RECORD_PRESENT steps. Replay resets ember (target 1, purge < 0.35). Plays to the end without input | 2 / 2 pass |
| 10 | Reported vs reality | For a legacy COMPLETE claim that the evidence disproves: `reported_status = COMPLETE`, the "Complete" label, the "Haunted" truth label and the `lie_report.json` source | 1 / 1 pass |
| 11 | Lite + reduced motion | Both modes: every counter, the headline and h1, 518 stones with status and review counts, working search, full runbook, exorcism end state, and **0 `<canvas>` elements**. The Lite toggle turns WebGL off and back on | 5 / 5 pass |
| 12 | Accessibility | axe-core WCAG 2.1 A/AA: **0 serious/critical** on hero, grid and case detail, each sampled at three fluid frames. Visible focus rings on a filter chip, a stone and the Lite toggle | 4 / 4 pass |
| 13 | Performance | Numbers below. Hero and grid ≥ 50 fps average under 4× throttle. Auto ladder 0.5 → 0.35 → 0.25 → CSS, then the "try lite" hint switches Lite on. High pins 0.5 and never downgrades; Low pins 0.25. Initial bundle < 1.5 MB gzipped | 5 / 5 pass |
| 14 | Privacy | `npm run test:privacy` passes. Rendered INCOMPLETE, COMPLETE and NOT_APPLICABLE cases show only masked emails | 2 / 2 pass |
| 15 | Visual review | Ten scenes captured at 1280×720 and 1920×1080 (`test-results/visual/`), reviewed by eye. The 1280×720 set is kept in `docs/ui/review-1280x720/` | 2 / 2 pass |

## Performance (measured)

CPU throttled 4× through the Chrome DevTools protocol. Each scene is measured with `requestAnimationFrame` for 10 s
while the pointer moves every 0.5 s (stirring the fluid and triggering hovers). The display is 144 Hz, so values can
exceed 60 fps. The fluid itself is capped at 60.

| Scene (GPU) | Avg fps, clean-clone run | Avg fps, range over 6 runs | p95 frame | Fluid at end |
|---|---|---|---|---|
| Hero (summoned) | **131.4** | 104 – 138 | 7 – 14 ms | 0.5 (one run stepped to 0.35) |
| Graveyard (hovering) | **65.3** | 59 – 82 | 42 – 63 ms | 0.25 or CSS (Auto stepped down; see below) |

- **Auto ladder** (artificial 32 ms/frame load): 0.5 → 0.35 at 1.8 s, 0.35 → 0.25 at 2.7 s, 0.25 → CSS at 5.5 s;
  the "running slow · try lite" hint then appears. Under real 4× throttle on the grid, Auto walked the same ladder
  by itself (0.35 at 1.4 s, 0.25 at 6.5 s, CSS at 9.1 s).
- **No usable GPU** (SwiftShader + 4× throttle): the full experience misses the budget. The hero runs at 17.9 fps and
  the grid at 14.1 fps even after Auto hands over to CSS, because every blur and composite is rendered in software.
  This is the case the slow-device hint is for: **Lite on the same setup runs at 144 fps on both scenes** (p95 7 ms).
- **Bundle:** initial JS + CSS **148 KB gzipped** (budget 1.5 MB). Lazy chunks: fluid 2.9 KB and particles 2.1 KB.
  Bundled fonts: 364 KB.

## Privacy scan

```text
scanned 27 files (public/data, src, dist/data); public/data size 1160 KB
  unmasked_email       0 found
  phone_number         0 found
  hex64_hash           0 found
  dataset_person_name  0 found
  raw_request_text     0 found
  non_derived_field    0 found
privacy check passed
```

## Issues the tests found, and the fixes

| Found by | Problem | Fix |
|---|---|---|
| Hero test | Pressing Enter to summon also opened the first case, because the graveyard's Enter shortcut listened page-wide | The graveyard's Enter only acts once the graveyard is on screen |
| Keyboard test | Text typed straight after `ctrl+K` was lost: the input took focus 30 ms after opening | `autoFocus` on the palette input |
| Perf test | Grid ran at 7.6 fps under throttle: 355 per-stone CSS breathing/pulse animations (the pulse used `var()` in keyframes, so it ran on the main thread) | One glow canvas with a cached sprite on the shared ticker; static halos (idle went from 16 to 90 fps) |
| Perf profile | Every hover re-rendered all 518 stones (tooltip state lived in the grid) | Tooltip owns its state |
| Perf profile | Hero particles kept animating behind the grid: an edge-adjacent IntersectionObserver entry counts as "intersecting" | Pause unless more than 1 % visible |
| Software-GL run | Auto bottomed out at 0.25 at about 18 fps with no further step | Last rung to the CSS gradient, plus a "try lite" hint; Lite drops backdrop blur and gradient motion (35 → 144 fps on the grid) |
| Visual review | 1280×720 hero: the "enter the graveyard" link overlapped counters and footnote | Panel anchored above the link, compact on short screens |
| Visual review | After a search scrolled to the match, the result strip was off-screen | Strip is sticky under the top bar |
| Visual review | The "Exorcised" seal covered two check rows in the end state | Seal gets its own reserved slot below the checks |
| Visual review | Runbook ids were truncated at 1280 px; a desired PRESENT read as an ember alarm | Chip wraps with the title, the resource id has its own line, and planned or verified states use the proven tone |
| Visual review | The wax "sealed" stamp covered the restore card's text | Right padding reserved for it |
| Visual review | Page content showed through the transparent top bar | Near-opaque scrim behind the bar |
| Toolchain | The Playwright 1.52 runner hung on Node 24 before loading any config | Upgraded to 1.62.1 (July 2026) |

## Known limits

- All performance numbers come from one laptop (Ryzen 5 8645HS, Radeon 760M). 4× CDP throttling emulates a slower CPU
  but not a slower GPU. The SwiftShader run is the stand-in for a weak GPU, and there only Lite meets the budget.
- Grid p95 frame time under 4× throttle is 42–63 ms: occasional long frames on hover (ripple and tilt). The average
  stays above 50.
- axe-core cannot compute contrast for text over a canvas. Contrast is therefore computed by hand against the
  brightest measured fluid pixel (all ≥ 6.2:1; table in `docs/DESIGN_NOTES.md`), and every text block sits on a dark
  glass panel.
- Tested in Chromium (Chrome) only. Firefox and Safari were not run.
- The visual review is by eye on the captured screenshots. There is no pixel-diff baseline, because the fluid is
  intentionally non-deterministic.
