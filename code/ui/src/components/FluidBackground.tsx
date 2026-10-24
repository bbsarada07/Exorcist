import { useEffect, useRef } from "react";
import { useUI } from "../lib/store";
import { bloomAt, fluid } from "../lib/fluid";
import { deviceBudget, prefersReducedMotion } from "../lib/perf";
import type { FluidRenderer } from "../effects/fluid";

declare global {
  interface Window { __exorcist?: { fluid?: FluidRenderer["stats"] & { target: typeof fluid.target; simulateLoad: (ms: number) => void } } }
}

/** Full-screen atmosphere. WebGL "ink in water" when allowed; animated CSS gradient otherwise (Lite, reduced
 *  motion, no WebGL, or a shader failure). Either way it sits behind everything and never carries information. */
export function FluidBackground() {
  const { lite, perf, setFluidKind, fluidKind } = useUI();
  const canvas = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<FluidRenderer | null>(null);
  const useGL = !lite && !prefersReducedMotion();

  useEffect(() => {
    if (!useGL || !canvas.current) { setFluidKind("css"); return; }
    let alive = true;
    import("../effects/fluid").then(({ FluidRenderer }) => {
      if (!alive || !canvas.current) return;
      try {
        const r = new FluidRenderer(canvas.current, useUI.getState().perf, deviceBudget().tier === "low");
        renderer.current = r;
        r.onGiveUp = () => { setFluidKind("css"); useUI.getState().setSlow(true); };
        setFluidKind("webgl");
        window.__exorcist = { ...(window.__exorcist ?? {}),
          fluid: Object.assign(r.stats, { target: fluid.target, simulateLoad: (ms: number) => r.setLoad(ms) }) };
      } catch (e) {
        console.warn("fluid fallback:", (e as Error).message);
        setFluidKind("css");
      }
    });
    const onResize = () => renderer.current?.resize();
    let lx = 0, ly = 0, lt = 0;
    const onMove = (e: PointerEvent) => {
      const now = performance.now();
      const x = e.clientX / innerWidth, y = 1 - e.clientY / innerHeight;
      if (lt) {
        const dt = Math.max(8, now - lt);
        fluid.pointer.vx = Math.max(-0.6, Math.min(0.6, fluid.pointer.vx + ((x - lx) / dt) * 6));
        fluid.pointer.vy = Math.max(-0.6, Math.min(0.6, fluid.pointer.vy + ((y - ly) / dt) * 6));
      }
      fluid.pointer.x = x; fluid.pointer.y = y; lx = x; ly = y; lt = now;
    };
    const onDown = (e: PointerEvent) => bloomAt(e.clientX, e.clientY);
    addEventListener("resize", onResize);
    addEventListener("pointermove", onMove, { passive: true });
    addEventListener("pointerdown", onDown, { passive: true });
    return () => {
      alive = false;
      removeEventListener("resize", onResize); removeEventListener("pointermove", onMove); removeEventListener("pointerdown", onDown);
      renderer.current?.destroy(); renderer.current = null;
      if (window.__exorcist) delete window.__exorcist.fluid;
    };
  }, [useGL, setFluidKind]);

  useEffect(() => {
    const r = renderer.current;
    if (!r) return;
    r.applyMode(perf, deviceBudget().tier === "low");
    // an explicit High/Low choice brings the shader back after Auto handed over to the CSS gradient
    if (perf !== "auto" && useUI.getState().fluidKind === "css") { r.start(); setFluidKind("webgl"); }
  }, [perf, setFluidKind]);

  useEffect(() => { document.documentElement.dataset.fluid = fluidKind; }, [fluidKind]);

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
      <div className="fluid-css absolute inset-0" style={{ opacity: fluidKind === "css" ? 1 : 0 }}>
        <div className="fluid-css-a" /><div className="fluid-css-b" />
      </div>
      {useGL && <canvas ref={canvas} data-fluid-canvas className="absolute inset-0 h-full w-full"
                        style={{ imageRendering: "auto", visibility: fluidKind === "webgl" ? "visible" : "hidden" }} />}
    </div>
  );
}
