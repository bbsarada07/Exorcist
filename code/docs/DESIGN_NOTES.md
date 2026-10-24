# UI design notes (for the AI Judge interview)

## Intent
The engine's job is to prove whether deleted data is really gone. The UI tells that story in four beats:
**summon** (data you can't see is still there) → **graveyard** (every case at once) → **reported vs reality** (the
legacy claim versus what the evidence shows) → **exorcism** (the plan, visualised step by step, then proven). Behind
all of it sits an "ink in water" fluid whose colours are the audit's own numbers.

## Hard decisions
1. **Read-only and data-honest.** The UI never computes a verdict. `npm run export-data` converts the engine's
   outputs into static JSON; every number on screen traces to a field listed in `docs/UI_DATA_NOTES.md`. Risk is
   labelled "heuristic"; guessed links carry a "needs review" badge with the queue's own reason text. An e2e test
   fails if any dataset number (518, 355, 153, 64, 254, 64.2) appears as a literal in `src/`.
2. **No real PII on screen or in the bundle.** Hero fragments are generic masked patterns. Subject emails are masked
   at export time (`abc••@••••.tld`); raw identifier lists and the customers' request texts are not exported
   (`npm run test:privacy` scans `public/data`, `src` and `dist/data` and fails on any email, phone, 64-hex hash,
   dataset name, request text or non-derived field).
3. **Animation is driven by the plan, not decoration.** The exorcism timeline is generated from the case's
   REMEDIATION steps in output order (disable flows → block restores → delete → redact → anonymise). Redaction bars
   cover exactly the identifier kinds the decision trace says are exposed. Retained records (VERIFY_RECORD_PRESENT)
   are shielded and never animated (an e2e test watches them with a MutationObserver). COMPLETE cases get a proof
   view instead of an exorcism; NOT_APPLICABLE cases say why nothing happens.
4. **The fluid carries meaning but never information.** Its colours are computed from real numbers (mapping below),
   but nothing is conveyed *only* by the fluid: it sits behind dark glass, under every text block, and Lite /
   reduced motion replace it with a still gradient without losing a single number or label.
5. **Status is never colour alone.** Chips carry a dot + text label; tombstones carry a glyph (`!`, `✓`, `–`) plus
   an aria-label and tooltip text; runbook rows show the state as text; the ledger view is all text.
6. **Accessibility.** All interactive elements are buttons or links; keyboard: `/` search, `j`/`k` move, Enter open,
   Esc clear/close, `ctrl/cmd+K` palette, Space skips the exorcism. Live regions announce search results and exorcism
   steps. axe-core (WCAG 2.1 A/AA) reports 0 serious/critical issues on hero, grid and case detail, sampled at three
   fluid frames each.

## Data → fluid mapping
The shader (`effects/fluid.ts`) is a domain-warped fbm ("ink in water"). Three uniforms come from the data; the
renderer eases toward them every frame, so page changes flow rather than cut.

| Uniform | Hero + graveyard | Case page | Source |
|---|---|---|---|
| `u_ratio` (ember share; green fills the rest) | INCOMPLETE / (INCOMPLETE + COMPLETE) = 355 / 508 = **0.699** | INCOMPLETE → 1 · COMPLETE → 0 · NOT_APPLICABLE → 0.5 | `summary.json` totals / case status |
| `u_violet` (active-flow tint) | cases with an `active_data_flow` failure mode / deletion cases = 113 / 508 = **0.222** | min(1, DISABLE_DATA_FLOW steps / 2) | `lie_report.json` / the case's steps |
| `u_purge` (0 → 1) | 0 | the exorcism: each banished target adds a little; the final seal floods green outward from the seal's position while ember is pushed to the edges; Replay resets it to 0 | GSAP timeline |

Interaction: the cursor stirs the flow (damped velocity), a click drops an ink bloom. The CSS fallback reads the same
values from `--fluid-ember / --fluid-green / --fluid-violet`, which `setFluidScene()` writes alongside the uniforms.
Brightness stays low: the brightest measured fluid pixel is rgb(52,35,30) on the landing page and rgb(35,63,51) at the
end of the purge.

## Contrast (computed WCAG ratios)
Every text block sits on glass (`.panel` 66 % ink + 14 px blur, `.panel-strong` 78 % + 16 px). Worst case = the panel
over the brightest fluid pixel measured above:

| Text | on ink | on `.panel` over brightest ember | on `.panel` over brightest purge green |
|---|---|---|---|
| bone `#EDE9E0` | 16.6 | 15.3 | 14.3 |
| green `#7CFFB2` | 16.1 | 14.8 | 13.9 |
| muted `#B8B4C6` | 9.9 | 9.1 | 8.6 |
| violet `#B3A8FF` | 9.5 | 8.8 | 8.2 |
| grey `#A3A0B0` | 7.9 | 7.2 | 6.8 |
| ember `#FF6B47` | 7.1 | 6.6 | 6.2 |

Minimum UI font size is 12 px; borders are `#34344A`.

## Performance
Budget: ≥ 50 fps average with the CPU throttled 4× (Chrome DevTools protocol), one animation loop, initial bundle
< 1.5 MB gzipped. Measured by `tests/e2e/perf.spec.ts` (numbers in `docs/UI_TEST_REPORT.md`).

- **One loop.** `effects/ticker.ts` multiplexes every canvas callback (fluid, hero particles, grid glow, dust) onto
  GSAP's ticker; Lenis smooth-scroll runs on the same ticker. It detaches when idle or when the tab is hidden; the
  hero and grid unsubscribe when scrolled off-screen.
- **Fluid.** Raw WebGL 1, one full-screen triangle, rendered at 0.5× resolution, capped at 60 fps, paused when hidden.
  **Auto** steps down 0.5 → 0.35 → 0.25 after ~0.75 s of frames slower than 24 ms, and hands over to the CSS gradient
  after a further ~2.5 s slower than 28 ms at 0.25 — then offers Lite ("running slow · try lite"), never switching
  silently. **High** pins 0.5 / 5 octaves; **Low** pins 0.25 / 3 octaves (and an explicit choice revives the shader).
- **Grid.** The breathing glow of high-finding pebbles is one canvas with a cached sprite drawn at ~30 fps; the
  first version used one CSS animation per pebble, which profiling showed cost ~10× more frame time (16 → 90 fps idle
  under 4× throttle after the change). The tooltip owns its own state, so hovering re-renders the tooltip, not 518
  stones. Ripple and tilt are imperative transform writes on ≤ ~30 nodes.
- **Hero.** Canvas 2D particles (typed arrays, `fillRect`), count from `deviceBudget()` and the Performance control;
  the module is a 2 KB lazy chunk. Its IntersectionObserver uses a non-zero threshold (an edge-adjacent hero used to
  count as visible and kept animating behind the grid).
- **Lite** (visible toggle, defaults on with `prefers-reduced-motion`): no canvas at all, still gradient, opaque glass
  without backdrop blur, no grain/glitch/dust/shake/tendrils — every number, label, step and state remains. On a
  software-rendered GPU (SwiftShader) with 4× throttle Lite runs at 144 fps.
- **Bundle:** initial JS + CSS 148 KB gzipped; fluid and particle modules are lazy chunks of 2.9 KB and 2.1 KB;
  fonts 364 KB (bundled, offline). Data: `summary.json` up front, `details.json` only when a case or the palette opens.

## Look
Ink `#07070B`, bone `#EDE9E0`; spectral green = proven, ember = haunted, violet = active flows. Instrument Serif for
display (tight tracking, italic accents), Inter for UI, JetBrains Mono for ids — all bundled via Fontsource.
Frosted-glass pebbles, numbered hairline sections (01 summoning · 02 case explorer · 03 exorcism), odometer counters,
a heartbeat on the haunted count, magnetic buttons, mask-reveal headline, ink bloom when a case opens.

## Trade-offs
- Tombstones are DOM buttons (accessible, focusable); only their glow is a canvas.
- The tendril target uses lineage edges when one connects the flow to a remediated record; otherwise it points at
  the records column (lineage only covers some flows).
- No router dependency: a hash route (`#/case/<id>`) in the Zustand store keeps deep links and the back button.
- `preserveDrawingBuffer: true` on the fluid costs a little GPU bandwidth but lets the tests read real pixels.
- Playwright 1.62.1 (1.52's runner hangs on Node 24); tests drive the locally installed Chrome, nothing is downloaded.
- Dev dependency audit: `postcss-selector-parser` (via Tailwind 3) has a moderate CSS-parsing DoS advisory; it only
  parses our own stylesheet at build time. Vite pinned to 6.4.4 (patched dev-server advisories, ≥ 2 weeks old).
