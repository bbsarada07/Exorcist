import { useEffect, useState } from "react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { loadSummary, type Summary } from "./lib/data";
import { useUI } from "./lib/store";
import { Atmosphere, TopBar } from "./components/Chrome";
import { CommandPalette } from "./components/CommandPalette";
import { Hero } from "./screens/Hero";
import { Graveyard } from "./screens/Graveyard";
import { CaseDetailView } from "./screens/CaseDetail";

export function App() {
  const lite = useUI((s) => s.lite);
  const caseId = useUI((s) => s.caseId);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => { loadSummary().then(setSummary); }, []);
  useEffect(() => { document.documentElement.classList.toggle("lite", lite); }, [lite]);

  // smooth scrolling for the landing page (off in Lite / reduced motion, paused while a case is open).
  // Driven by the shared GSAP ticker so the page keeps a single animation loop.
  useEffect(() => {
    if (lite || caseId) return;
    const lenis = new Lenis({ lerp: 0.12, autoRaf: false });
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    return () => { gsap.ticker.remove(tick); lenis.destroy(); };
  }, [lite, caseId]);

  return (
    <div className="relative min-h-screen bg-ink text-bone">
      {!lite && <Atmosphere />}
      <TopBar />
      <main aria-hidden={!!caseId}>
        <Hero summary={summary} />
        <Graveyard summary={summary} />
      </main>
      <CaseDetailView />
      <CommandPalette summary={summary} />
    </div>
  );
}
