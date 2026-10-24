import { useUI } from "../lib/store";
import type { PerfMode } from "../effects/fluid";
import { Magnetic } from "./Odometer";

export function Atmosphere() {
  return (
    <>
      <div className="vignette" aria-hidden />
      <div className="grain" aria-hidden />
    </>
  );
}

export function LiteToggle() {
  const lite = useUI((s) => s.lite);
  const setLite = useUI((s) => s.setLite);
  return (
    <Magnetic onClick={() => setLite(!lite)} aria-pressed={lite} data-lite-toggle
      className="chip tone-bone hover:border-proven hover:text-proven"
      title="Lite mode disables the fluid, particles and effects; every number and label stays visible">
      lite mode · {lite ? "on" : "off"}
    </Magnetic>
  );
}

/** Shown only after Auto had to give up the shader: the device is struggling, so offer Lite (never switched silently). */
function SlowHint() {
  const show = useUI((s) => s.slow && !s.lite);
  const setLite = useUI((s) => s.setLite);
  if (!show) return null;
  return (
    <button onClick={() => setLite(true)} data-slow-hint className="chip tone-flow" aria-live="polite"
      title="The fluid already fell back to a static gradient; Lite mode also stops particles and motion">
      running slow · try lite
    </button>
  );
}

function PerfControl() {
  const perf = useUI((s) => s.perf);
  const setPerf = useUI((s) => s.setPerf);
  const lite = useUI((s) => s.lite);
  return (
    <div className="panel hidden items-center gap-1 rounded-full p-1 md:flex" role="radiogroup" aria-label="Performance">
      <span className="mono px-2 text-xs uppercase tracking-widest text-muted">perf</span>
      {(["auto", "high", "low"] as PerfMode[]).map((m) => (
        <button key={m} role="radio" aria-checked={perf === m} disabled={lite} onClick={() => setPerf(m)} data-perf={m}
          className={`mono rounded-full px-2.5 py-0.5 text-xs uppercase tracking-widest transition-colors ${perf === m ? "bg-bone text-ink" : "text-muted hover:text-bone"} disabled:opacity-60`}>
          {m}
        </button>
      ))}
    </div>
  );
}

export function TopBar() {
  const open = useUI((s) => s.open);
  const setPalette = useUI((s) => s.setPalette);
  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex items-center justify-between px-5 pb-7 pt-4 md:px-8"
      style={{ background: "linear-gradient(to bottom, rgba(7,7,11,.97) 0%, rgba(7,7,11,.92) 62%, rgba(7,7,11,0) 100%)" }}>
      <button onClick={() => { open(null); window.scrollTo({ top: 0 }); }} className="pointer-events-auto flex items-baseline gap-3" aria-label="Exorcist home">
        <span className="display text-3xl italic text-bone">Exorcist</span>
        <span className="micro hidden sm:inline">deletion audit</span>
      </button>
      <div className="pointer-events-auto flex items-center gap-2">
        <PerfControl />
        <Magnetic onClick={() => setPalette(true)} className="chip tone-bone hidden sm:inline-flex" aria-label="Open command palette (ctrl K)">
          search · ctrl K
        </Magnetic>
        <SlowHint />
        <LiteToggle />
      </div>
    </header>
  );
}
