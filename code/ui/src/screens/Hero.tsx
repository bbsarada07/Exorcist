import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { Summary } from "../lib/data";
import { useUI } from "../lib/store";
import { deviceBudget } from "../lib/perf";
import { Odometer } from "../components/Odometer";
import type { GhostField } from "../effects/ghostField";

export const HEADLINE = "Deleted data does not stay dead unless you prove it.";

export function Hero({ summary }: { summary: Summary | null }) {
  const lite = useUI((s) => s.lite);
  const perf = useUI((s) => s.perf);
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
      const count = perf === "low" ? Math.round(b.particles * 0.45) : perf === "high" ? Math.round(b.particles * 1.2) : b.particles;
      fieldRef.current = new GhostField(canvas, { count, dpr: b.dpr });
      canvas.dataset.particles = String(count);
      canvas.dataset.tier = b.tier;
      if (summonedRef.current) fieldRef.current.summon();
    });
    const onResize = () => fieldRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => { alive = false; window.removeEventListener("resize", onResize); fieldRef.current?.destroy(); fieldRef.current = null; };
  }, [lite, perf]);

  const summonedRef = useRef(summoned);
  summonedRef.current = summoned;
  const summon = useCallback(() => {
    if (summonedRef.current) return;
    setSummoned(true);
    fieldRef.current?.summon();
    window.setTimeout(() => setWordmarkDone(true), lite ? 0 : 1400);
  }, [lite]);

  useEffect(() => {
    if (lite) { setSummoned(true); setWordmarkDone(true); return; }
    const onWheel = (e: WheelEvent) => e.deltaY > 0 && summon();
    const onKey = (e: KeyboardEvent) => (e.key === "Enter" || e.key === "ArrowDown") && !useUI.getState().caseId &&
      (e.target as HTMLElement)?.tagName !== "INPUT" && summon();
    const auto = window.setTimeout(summon, 6500);   // never leave the demo on an empty stage
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(auto); window.removeEventListener("wheel", onWheel); window.removeEventListener("keydown", onKey); };
  }, [summon, lite]);

  const t = summary?.totals;
  const lie = summary?.lie.headline;
  const counters = [
    { label: "cases audited", value: t?.cases ?? 0, tone: "text-bone", key: "total" },
    { label: "haunted · incomplete", value: t?.status.INCOMPLETE ?? 0, tone: "text-haunted", key: "haunted", beat: true },
    { label: "proven · complete", value: t?.status.COMPLETE ?? 0, tone: "text-proven", key: "proven" },
    { label: "not applicable", value: t?.status.NOT_APPLICABLE ?? 0, tone: "text-na", key: "na" },
  ];

  return (
    <section
      id="summoning"
      className="relative h-[100svh] min-h-[720px] w-full overflow-hidden"
      onPointerMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); fieldRef.current?.pointer(e.clientX - r.left, e.clientY - r.top); }}
      onPointerLeave={() => fieldRef.current?.pointer(-9999, -9999)}
      onClick={summon}
    >
      {!lite && <canvas ref={canvasRef} data-hero-canvas className="absolute inset-0 h-full w-full" aria-hidden />}

      <div className="absolute left-5 top-24 flex items-center gap-4 md:left-8" data-parallax="0.35">
        <span className="panel micro px-3 py-1.5 !text-bone">01 · the summoning</span>
        <span className="hairline-rule hidden w-40 md:block" />
      </div>

      {/* wordmark: drawn by particles; real text for assistive tech and Lite mode */}
      <h1 className={lite ? "display absolute inset-x-0 top-[24%] text-center text-[17vw] text-bone md:text-[15vw]" : "sr-only"}>EXORCIST</h1>

      {!summoned && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6, duration: 1.2 }}
          className="pointer-events-none absolute inset-x-0 bottom-[15%] flex justify-center px-6">
          <div className="panel flex flex-col items-center gap-2 px-6 py-4 text-center">
            <p className="micro">move your light through the dark</p>
            <p className="display text-3xl italic text-bone md:text-4xl">something was never deleted.</p>
            <p className="mono text-xs text-muted">click · scroll · or press Enter to summon</p>
          </div>
        </motion.div>
      )}

      {summoned && (
        <div className="absolute inset-x-0 bottom-20 flex justify-center px-4">
          <div className="panel-strong w-full max-w-5xl px-6 py-6 text-center md:px-10 [@media(max-height:820px)]:py-4" data-hero-panel>
            <h2 className="display text-4xl text-bone md:text-6xl [@media(max-height:820px)]:md:text-5xl" aria-label={HEADLINE} data-headline>
              <span className={`line-mask ${wordmarkDone ? "in" : ""}`} aria-hidden><span>Deleted data does not stay <em className="text-haunted">dead</em></span></span>
              <span className={`line-mask ${wordmarkDone ? "in" : ""}`} aria-hidden><span style={{ transitionDelay: "180ms" }}>unless you <em className="text-proven">prove</em> it.</span></span>
            </h2>
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-5 [@media(max-height:820px)]:mt-4">
              {counters.map((c) => (
                <div key={c.key} className="flex flex-col items-center" data-counter={c.key}>
                  <span className={`display text-5xl md:text-6xl [@media(max-height:820px)]:md:text-5xl ${c.tone} ${c.beat && !lite ? "heartbeat" : ""}`}>
                    <Odometer value={c.value} run={wordmarkDone} label={c.label} />
                  </span>
                  <span className="micro mt-1 !tracking-[0.16em]">{c.label}</span>
                </div>
              ))}
              <div className="col-span-2 flex flex-col items-center md:col-span-1" data-counter="lie">
                <span className="display text-5xl italic text-haunted md:text-6xl [@media(max-height:820px)]:md:text-5xl">
                  <Odometer value={lie?.reported_COMPLETE_but_incomplete_pct ?? 0} decimals={1} suffix="%" run={wordmarkDone} label="of legacy complete claims were false" />
                </span>
                <span className="micro mt-1 !tracking-[0.16em]">legacy “complete” claims false</span>
              </div>
            </div>
            <p className="mono mt-5 text-xs text-muted">
              {lie ? `${lie.reported_COMPLETE_cases} cases claimed “complete” · sources: output.csv, lie_report.json · ${summary?.decoys.avoided ?? 0} look-alike decoys rejected` : ""}
            </p>
          </div>
        </div>
      )}

      <a href="#graveyard" className="panel micro absolute bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 !text-bone hover:!text-proven">
        enter the graveyard ↓
      </a>
    </section>
  );
}
