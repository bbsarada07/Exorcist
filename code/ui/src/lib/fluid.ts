// Shared, mutable state for the "ink in water" fluid. React sets scene *targets* from real data; GSAP tweens
// the purge; the renderer eases its uniforms toward the targets every frame (no React re-render per frame).
//
// Data -> fluid mapping (documented in docs/DESIGN_NOTES.md):
//   ratio  = haunted share = INCOMPLETE / (INCOMPLETE + COMPLETE) on hero + graveyard; 1 for an INCOMPLETE case,
//            0 for a COMPLETE case, 0.5 (neutral) for NOT_APPLICABLE. Ember area grows with ratio, green fills the rest.
//   violet = share of deletion cases whose failure modes include an active data flow (hero + graveyard), or
//            min(1, DISABLE_DATA_FLOW steps / 2) on a case page.
//   purge  = 0..1 exorcism wave: green floods out from the seal point, ember is pushed to the edges and fades.
export const fluid = {
  target: { ratio: 0.5, violet: 0, bright: 1 },
  purge: { v: 0 },
  origin: [0.5, 0.5] as [number, number],          // purge origin in normalised viewport coords (y up)
  bloom: { x: 0.5, y: 0.5, t0: -1e9 },              // last ink-bloom click (ms timestamp)
  pointer: { x: 0.5, y: 0.5, vx: 0, vy: 0 },        // damped stir velocity
  scene: "landing" as string,
};

export function setFluidScene(scene: string, ratio: number, violet: number) {
  fluid.scene = scene;
  fluid.target.ratio = Math.max(0, Math.min(1, ratio));
  fluid.target.violet = Math.max(0, Math.min(1, violet));
  // the CSS fallback gradient uses the same mapping
  const root = document.documentElement.style;
  root.setProperty("--fluid-ember", fluid.target.ratio.toFixed(3));
  root.setProperty("--fluid-green", (1 - fluid.target.ratio).toFixed(3));
  root.setProperty("--fluid-violet", fluid.target.violet.toFixed(3));
  document.documentElement.dataset.fluidScene = scene;
}

export function bloomAt(clientX: number, clientY: number) {
  fluid.bloom = { x: clientX / innerWidth, y: 1 - clientY / innerHeight, t0: performance.now() };
}

export function purgeOrigin(clientX: number, clientY: number) {
  fluid.origin = [clientX / innerWidth, 1 - clientY / innerHeight];
}
