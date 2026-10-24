import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Summary } from "../lib/data";
import { useUI } from "../lib/store";
import { deviceBudget } from "../lib/perf";
import { Counter, Typewriter } from "../components/Motion";
import type { GhostField } from "../effects/ghostField";

const HEADLINE = "Deleted data does not stay dead unless you prove it.";

export function Hero({ summary }: { summary: Summary | null }) {
  const lite = useUI((s) => s.lite);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fieldRef = useRef<GhostField | null>(null);
  const [summoned, setSummoned] = useState(lite);
  const [wordmarkDone, setWordmarkDone] = useState(lite);

  // lazy-load the particle engine after first paint (keeps it out of the initial bundle)
  useEffect(() => {
    if (lite || !canvasRef.current) return;
    let alive = true;
    const canvas = canvasRef.current;
    import("../effects/ghostField").then(({ GhostField }) => {
      if (!alive) return;
      const b = deviceBudget();
      fieldRef.current = new GhostField(canvas, { count: b.particles, dpr: b.dpr });
      canvas.dataset.particles = String(b.particles);
      canvas.dataset.tier = b.tier;
    });
    const onResize = () => fieldRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => { alive = false; window.removeEventListener("resize", onResize); fieldRef.current?.destroy(); fieldRef.current = null; };
  }, [lite]);

  const summon = useCallback(() => {
    if (summoned) return;
    setSummoned(true);
    fieldRef.current?.summon();
    window.setTimeout(() => setWordmarkDone(true), lite ? 0 : 1500);
  }, [summoned, lite]);

  useEffect(() => {
    if (lite) { setSummoned(true); setWordmarkDone(true); return; }
    const onWheel = (e: WheelEvent) => e.deltaY > 0 && summon();
    const onKey = (e: KeyboardEvent) => (e.key === "Enter" || e.key === "ArrowDown") && summon();
    const auto = window.setTimeout(summon, 6500);   // never leave the demo on an empty stage
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(auto); window.removeEventListener("wheel", onWheel); window.removeEventListener("keydown", onKey); };
  }, [summon, lite]);

  const t = summary?.totals;
  const lie = summary?.lie.headline;
  const counters = [
    { label: "cases audited", value: t?.cases ?? 0, tone: "text-bone" },
    { label: "haunted · incomplete", value: t?.status.INCOMPLETE ?? 0, tone: "text-haunted" },
    { label: "proven · complete", value: t?.status.COMPLETE ?? 0, tone: "text-proven" },
    { label: "not applicable", value: t?.status.NOT_APPLICABLE ?? 0, tone: "text-na" },
  ];

  return (
    <section
      id="summoning"
      className="relative h-[100svh] min-h-[640px] w-full overflow-hidden"
      onPointerMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); fieldRef.current?.pointer(e.clientX - r.left, e.clientY - r.top); }}
      onPointerLeave={() => fieldRef.current?.pointer(-9999, -9999)}
      onClick={summon}
    >
      {!lite && <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden />}

      {/* wordmark: drawn by particles; real text for assistive tech and Lite mode */}
      <h1 className={lite ? "display absolute inset-x-0 top-[31%] text-center text-[19vw] text-bone md:text-[17vw]" : "sr-only"}>EXORCIST</h1>

      {!summoned && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6, duration: 1.2 }}
          className="pointer-events-none absolute inset-x-0 bottom-[16%] flex flex-col items-center gap-3 text-center">
          <p className="mono text-xs uppercase tracking-[0.35em] text-muted">move your light through the dark</p>
          <p className="display text-3xl italic text-bone/90 md:text-4xl">something was never deleted.</p>
          <p className="mono text-[11px] text-muted">click · scroll · or press Enter to summon</p>
        </motion.div>
      )}

      {summoned && (
        <div className="pointer-events-none absolute inset-x-0 top-[57%] flex flex-col items-center px-6 text-center">
          <h2 className="display max-w-5xl text-balance text-4xl text-bone md:text-6xl">
            <Typewriter text={HEADLINE} run={wordmarkDone} />
          </h2>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={wordmarkDone ? { opacity: 1, y: 0 } : {}} transition={{ delay: lite ? 0 : 1.6, duration: 0.8 }}
            className="mt-10 grid w-full max-w-5xl grid-cols-2 gap-x-6 gap-y-6 md:grid-cols-5">
            {counters.map((c) => (
              <div key={c.label} className="flex flex-col items-center">
                <span className={`display text-5xl md:text-6xl ${c.tone}`}><Counter to={c.value} run={wordmarkDone} /></span>
                <span className="mono mt-1 text-[10px] uppercase tracking-[0.22em] text-muted">{c.label}</span>
              </div>
            ))}
            <div className="col-span-2 flex flex-col items-center md:col-span-1">
              <span className="display text-5xl italic text-haunted md:text-6xl">
                <Counter to={lie?.reported_COMPLETE_but_incomplete_pct ?? 0} run={wordmarkDone} decimals={1} suffix="%" />
              </span>
              <span className="mono mt-1 text-[10px] uppercase tracking-[0.22em] text-muted">of legacy “complete” claims were false</span>
            </div>
          </motion.div>
          <motion.p initial={{ opacity: 0 }} animate={wordmarkDone ? { opacity: 1 } : {}} transition={{ delay: lite ? 0 : 2.6 }}
            className="mono mt-8 text-[11px] text-muted">
            {lie ? `${lie.reported_COMPLETE_cases} cases claimed “complete” · sources: output.csv, lie_report.json · ${summary?.decoys.avoided ?? 0} look-alike decoys rejected` : ""}
          </motion.p>
        </div>
      )}

      <a href="#graveyard" className="mono absolute bottom-6 left-1/2 -translate-x-1/2 text-[11px] uppercase tracking-[0.3em] text-muted hover:text-bone">
        enter the graveyard ↓
      </a>
    </section>
  );
}
