# UI design notes (for the AI Judge interview)

## Intent
The engine's job is to prove whether deleted data is really gone. The UI tells that story in four beats:
**summon** (data you can't see is still there) → **graveyard** (every case at once) → **reported vs reality** (the
legacy claim versus what the evidence shows) → **exorcism** (the plan, visualised step by step, then proven).

## Hard decisions
1. **Read-only and data-honest.** The UI never computes a verdict. `npm run export-data` converts the engine's
   outputs into static JSON; every number on screen traces to a field listed in `docs/UI_DATA_NOTES.md`. Risk is
   labelled "heuristic", guessed links carry a "needs review" badge with the queue's own reason text.
2. **No real PII on screen or in the bundle.** Hero fragments are generic masked patterns. Subject emails are masked
   at export time (`abc••@••••.tld`); raw identifier lists are dropped.
3. **Animation is driven by the plan, not decoration.** The exorcism timeline is generated from the case's
   REMEDIATION steps in output order (disable flows → block restores → delete → redact → anonymise). Redaction bars
   cover exactly the identifier kinds the decision trace says are exposed. Retained records (VERIFY_RECORD_PRESENT)
   are shielded and never animated. COMPLETE cases get a proof view instead of an exorcism, and NOT_APPLICABLE cases
   say why nothing happens.
4. **Status is never colour alone.** Chips carry a dot + text label; tombstones carry a glyph (`!`, `✓`, `–`) plus
   an aria-label and tooltip text; the ledger view shows everything as text.
5. **Accessibility.** All interactive elements are buttons or links; keyboard: `/` search, `j`/`k` move, Enter open,
   Esc close, `ctrl/cmd+K` palette, Space skips the exorcism. A live region announces exorcism steps. Text colours meet
   ≥ 4.5:1 on both ink and panel (computed WCAG ratios, ink / panel): bone 16.6 / 15.8, green 16.1 / 15.3,
   muted #A9A5B8 8.4 / 8.0, violet 7.3 / 7.0, ember 7.1 / 6.8, grey 5.8 / 5.5.

## Performance choices (the "performance law")
- **Canvas 2D, no WebGL/three.js.** Typed arrays and `fillRect`; ~2.9k particles on a high-tier laptop, 900 on low
  tier (`lib/perf.ts` reads cores, memory, pointer type and viewport; DPR capped at 1–1.5).
- **One loop.** `effects/ticker.ts` multiplexes every canvas callback onto GSAP's ticker; Lenis is driven from the same
  ticker. The loop detaches when idle, when the tab is hidden, and the hero unsubscribes when scrolled off-screen.
- **Transform/opacity only** for DOM motion (FLIP zoom, curtain wipe, redaction bars as `scaleX`, ripple as
  `translate/scale`). No layout-animating properties.
- **Lazy hero.** The particle engine is a separate 2 KB chunk loaded after first paint; the wordmark exists as real
  text first.
- **Bundle:** initial JS 136 KB gzipped + CSS 10 KB gzipped (budget 1.5 MB). Data loads separately:
  `summary.json` 5 KB gz up front, `details.json` 88 KB gz only when a case or the palette is opened.
- **Measured:** headless Chrome on the dev machine holds ~143 fps on the hero with 2,880 particles
  (`npm run shots` prints it). Indicative only — the cap scales down on weaker devices.
- **Lite mode** (visible toggle, defaults on with `prefers-reduced-motion`): no canvas, grain, glitch, dust, shake or
  tendrils; all information and states remain.

## Look
Ink `#07070B`, bone `#EDE9E0`; spectral green = proven, ember = haunted, violet = active flows. Instrument Serif for
display (tight tracking, italic accents), Inter for UI, JetBrains Mono for ids — all bundled locally via Fontsource
(offline). Hairline glass panels (`#0F0F16`, 1 px `#23232F`, 12 px radius), film grain and vignette overlays.

## Trade-offs
- Tombstones are DOM buttons (accessible, focusable) rather than a canvas; 518 elements are cheap, and hover effects
  touch ≤ 25 nodes imperatively.
- The tendril target uses lineage edges when one connects the flow to a remediated record; otherwise it points at
  the records column (lineage only covers some flows).
- No router dependency: a hash route (`#/case/<id>`) in the Zustand store keeps deep links and the back button.
- Dev dependency audit: `postcss-selector-parser` (via Tailwind 3) has a moderate CSS-parsing DoS advisory; it only
  parses our own stylesheet at build time. Vite pinned to 6.4.4 (patched dev-server advisories, ≥ 2 weeks old).
