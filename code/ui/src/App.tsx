import { useEffect, useState } from "react";
import Lenis from "lenis";
import { loadSummary, type Summary } from "./lib/data";
import { useUI } from "./lib/store";
import { Atmosphere, TopBar } from "./components/Chrome";
import { Hero } from "./screens/Hero";

export function App() {
  const lite = useUI((s) => s.lite);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => { loadSummary().then(setSummary); }, []);
  useEffect(() => { document.documentElement.classList.toggle("lite", lite); }, [lite]);

  // smooth scrolling (off in Lite / reduced motion)
  useEffect(() => {
    if (lite) return;
    const lenis = new Lenis({ lerp: 0.12 });
    let id = 0;
    const raf = (t: number) => { lenis.raf(t); id = requestAnimationFrame(raf); };
    id = requestAnimationFrame(raf);
    return () => { cancelAnimationFrame(id); lenis.destroy(); };
  }, [lite]);

  return (
    <div className="relative min-h-screen bg-ink text-bone">
      {!lite && <Atmosphere />}
      <TopBar />
      <main>
        <Hero summary={summary} />
      </main>
    </div>
  );
}
