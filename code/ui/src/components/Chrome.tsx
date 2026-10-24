import { useUI } from "../lib/store";

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
    <button
      onClick={() => setLite(!lite)}
      aria-pressed={lite}
      className="chip tone-bone hover:border-proven hover:text-proven"
      title="Lite mode disables particles and shaders; every number and label stays visible"
    >
      lite mode · {lite ? "on" : "off"}
    </button>
  );
}

export function TopBar() {
  const open = useUI((s) => s.open);
  const setPalette = useUI((s) => s.setPalette);
  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex items-center justify-between bg-gradient-to-b from-ink via-ink/85 to-transparent px-5 pb-8 pt-4 md:px-8">
      <button onClick={() => { open(null); window.scrollTo({ top: 0 }); }} className="pointer-events-auto flex items-baseline gap-3">
        <span className="display text-2xl italic text-bone">Exorcist</span>
        <span className="mono hidden text-[10px] uppercase tracking-[0.25em] text-muted sm:inline">deletion audit</span>
      </button>
      <div className="pointer-events-auto flex items-center gap-2">
        <button onClick={() => setPalette(true)} className="chip tone-bone hidden sm:inline-flex" aria-label="Open command palette">
          search · <span className="kbd !border-0 !bg-transparent !p-0">ctrl K</span>
        </button>
        <LiteToggle />
      </div>
    </header>
  );
}
