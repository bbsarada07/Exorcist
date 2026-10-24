# Effects — what each one does, how it stays cheap, and its Lite fallback

All canvas work runs on **one loop**: `ticker.ts` subscribes callbacks to GSAP's ticker (GSAP timelines, the canvas
effects and Lenis smooth-scroll all share that single `requestAnimationFrame`). The loop detaches itself when nobody
is subscribed or when the tab is hidden (`visibilitychange`). DOM animation uses **transform and opacity only**.

| Effect | Where | How it works | Cost control | Lite / reduced-motion fallback |
|---|---|---|---|---|
| Ghost particles + flashlight (`ghostField.ts`) | Hero | Typed-array particles on a sin/cos drift field drawn with `fillRect`; pointer position (smoothed) brightens nearby particles and reveals masked PII fragments within a radius | count from `deviceBudget()` (≈900 / 2200 / 3600 cap by tier), DPR capped at 1–1.5, `IntersectionObserver` unsubscribes when the hero is off-screen, constant colour strings + `globalAlpha` (no per-particle allocation), module lazy-loaded after first paint | canvas not mounted; `EXORCIST` rendered as real text |
| Wordmark summon (`ghostField.summon`) | Hero | Text drawn once on an offscreen canvas, alpha-sampled to target points; particles ease to their targets with a smoothstep ramp | sampling step scales with particle count; done once per resize | wordmark is static text |
| Masked PII fragments | Hero | Generic patterns only (`k.r••@••••.com`, `••• •• 4417`), jittered 7×4 grid so the light always finds some | ≤28 `fillText` calls, glow only while lit | hidden (decorative) |
| Counters / typewriter (`components/Motion.tsx`) | Hero | GSAP tweens on a plain object, React renders the number/text | one tween each | final values shown immediately |
| Film grain + vignette (`styles/index.css`) | Global | Inline SVG `feTurbulence` tile, stepped `transform` keyframes; radial-gradient vignette | fixed layers, no repaint of content | not rendered |
| Tombstone ripple (`screens/Graveyard.tsx`) | Graveyard | On hover, ≤ ~25 neighbours get an inline `transform` (lift + scale) with a CSS transition | imperative style writes, no React re-render of the 518 stones | no ripple; hover tooltip and focus ring remain |
| Shared-element zoom (`screens/CaseDetail.tsx`) | Case open | FLIP: the header stone starts at the clicked tombstone's rect and animates `x / y / scale` to identity | one element | instant |
| Chromatic-aberration glitch | Reported vs Reality | `::before/::after` copies of the text in red/cyan with stepped `transform` keyframes | CSS only | pseudo-elements removed; plain text |
| Reality curtain | Reported vs Reality | Ink cover `scaleX(1→0)` when the section scrolls into view | transform only | already revealed |
| Exorcism timeline (`screens/Exorcism.tsx`) | Case detail | GSAP timeline generated from the case's REMEDIATION steps: tendril halves (SVG, split with de Casteljau) drift apart, wax seal stamps (`back.out`), records shake + dust burst, black redaction bars `scaleX` over the exposed identifier kinds, anonymise = text scramble, verification ticks cascade, final seal slam + stage shake + green pulse | opacity/transform only; Space jumps to `progress(1)` | 2.6× time scale, no dust, no shake, no tendrils — every state label and tick still shown |
| Dust burst (`dust.ts`) | Exorcism | One overlay canvas, motes spawned from the card's rect, gravity-less drift + fade | capped at 1,400 motes, subscribes to the ticker only while motes are alive | not created |
