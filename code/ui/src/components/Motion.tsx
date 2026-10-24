import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { useUI } from "../lib/store";

/** Counts up from 0 to `to` when `run` becomes true. Lite/reduced motion: shows the final value immediately. */
export function Counter({ to, run, decimals = 0, suffix = "" }: { to: number; run: boolean; decimals?: number; suffix?: string }) {
  const lite = useUI((s) => s.lite);
  const [v, setV] = useState(lite ? to : 0);
  useEffect(() => {
    if (!run) return;
    if (lite) { setV(to); return; }
    const o = { v: 0 };
    const tw = gsap.to(o, { v: to, duration: 1.8, ease: "expo.out", onUpdate: () => setV(o.v) });
    return () => { tw.kill(); };
  }, [run, to, lite]);
  return <span className="tabular-nums">{v.toFixed(decimals)}{suffix}</span>;
}

/** Types `text` in when `run` is true. The full text is always present for screen readers. */
export function Typewriter({ text, run, className = "" }: { text: string; run: boolean; className?: string }) {
  const lite = useUI((s) => s.lite);
  const [n, setN] = useState(lite ? text.length : 0);
  useEffect(() => {
    if (!run) return;
    if (lite) { setN(text.length); return; }
    const o = { n: 0 };
    const tw = gsap.to(o, { n: text.length, duration: text.length * 0.035, ease: "none", onUpdate: () => setN(Math.round(o.n)) });
    return () => { tw.kill(); };
  }, [run, text, lite]);
  return (
    <span className={className} aria-label={text}>
      <span aria-hidden>{text.slice(0, n)}</span>
      <span aria-hidden className="invisible">{text.slice(n)}</span>
      {run && n < text.length && <span aria-hidden className="ml-0.5 inline-block w-[0.06em] animate-pulse bg-proven align-baseline">&nbsp;</span>}
    </span>
  );
}

export function useInView<T extends Element>(threshold = 0.25) {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!ref.current || seen) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setSeen(true), { threshold });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [seen, threshold]);
  return [ref, seen] as const;
}
