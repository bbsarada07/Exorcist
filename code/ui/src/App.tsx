import { useEffect, useState } from "react";
import Lenis from "lenis";
import { gsap } from "gsap";
import { loadSummary, type Summary } from "./lib/data";
import { useUI } from "./lib/store";
import { setFluidScene } from "./lib/fluid";
import { setLenis } from "./lib/scroll";
import { Atmosphere, TopBar } from "./components/Chrome";
import { CommandPalette } from "./components/CommandPalette";
import { FluidBackground } from "./components/FluidBackground";
import { Hero } from "./screens/Hero";
import { Graveyard } from "./screens/Graveyard";
import { CaseDetailView } from "./screens/CaseDetail";

/** Landing-page fluid mapping from real numbers: ember share = haunted / (haunted + proven); violet = share of
 *  deletion cases whose failure modes include an active data flow (lie_report.json). */
export function landingScene(s: Summary) {
  const h = s.totals.status.INCOMPLETE, p = s.totals.status.COMPLETE;
  const flows = s.lie.failure_modes.active_data_flow?.cases ?? 0;
  return { ratio: h / Math.max(1, h + p), violet: flows / Math.max(1, s.lie.deletion_cases) };
}

export function App() {
  const lite = useUI((s) => s.lite);
  const caseId = useUI((s) => s.caseId);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => { loadSummary().then(setSummary); }, []);
  useEffect(() => { document.documentElement.classList.toggle("lite", lite); }, [lite]);
  useEffect(() => {
    if (!summary || caseId) return;
    const { ratio, violet } = landingScene(summary);
    setFluidScene("landing", ratio, violet);
  }, [summary, caseId]);

  // smooth scrolling + parallax for the landing page (off in Lite / reduced motion, paused while a case is open).
  // Driven by the shared GSAP ticker so the page keeps a single animation loop.
  useEffect(() => {
    if (lite || caseId) return;
    const lenis = new Lenis({ lerp: 0.12, autoRaf: false });
    const tick = (time: number) => lenis.raf(time * 1000);
    const layers = () => document.querySelectorAll<HTMLElement>("[data-parallax]");
    lenis.on("scroll", ({ scroll }: { scroll: number }) => {
      layers().forEach((el) => { el.style.translate = `0 ${(scroll * Number(el.dataset.parallax)).toFixed(1)}px`; });
    });
    gsap.ticker.add(tick);
    setLenis(lenis);
    return () => { gsap.ticker.remove(tick); setLenis(null); lenis.destroy(); layers().forEach((el) => { el.style.translate = ""; }); };
  }, [lite, caseId]);

  return (
    <div className="relative min-h-screen text-bone">
      <FluidBackground />
      {!lite && <Atmosphere />}
      <TopBar />
      <main aria-hidden={!!caseId} className={caseId ? "invisible" : ""}>
        <Hero summary={summary} />
        <Graveyard summary={summary} />
      </main>
      <CaseDetailView />
      <CommandPalette summary={summary} />
    </div>
  );
}
