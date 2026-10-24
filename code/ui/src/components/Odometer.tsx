import { useEffect, useRef, useState } from "react";
import { useUI } from "../lib/store";

/** Odometer counter: each digit is a column 0-9 moved with translateY (transform only).
 *  The final value is always in the accessible label; Lite / reduced motion jump straight to it. */
export function Odometer({ value, decimals = 0, suffix = "", run, label }: { value: number; decimals?: number; suffix?: string; run: boolean; label: string }) {
  const lite = useUI((s) => s.lite);
  const text = value.toFixed(decimals) + suffix;
  const [shown, setShown] = useState(lite);
  useEffect(() => { if (run) { const id = requestAnimationFrame(() => setShown(true)); return () => cancelAnimationFrame(id); } }, [run]);
  return (
    <span className="odo-wrap inline-flex" role="img" aria-label={`${text} ${label}`} data-value={text}>
      {[...text].map((ch, i) => /\d/.test(ch) ? (
        <span key={i} className="odo" aria-hidden>
          <span className="odo-col" style={{ transform: `translateY(${shown ? -Number(ch) : 0}em)`, transitionDelay: `${i * 70}ms` }}>
            {Array.from({ length: 10 }, (_, d) => <span key={d}>{d}</span>)}
          </span>
        </span>
      ) : <span key={i} aria-hidden>{ch}</span>)}
    </span>
  );
}

/** Button that leans toward the cursor (transform only). */
export function Magnetic({ children, className = "", strength = 0.25, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { strength?: number }) {
  const ref = useRef<HTMLButtonElement>(null);
  const lite = useUI((s) => s.lite);
  return (
    <button ref={ref} {...rest} className={`${className} transition-transform duration-200 ease-out`}
      onPointerMove={(e) => {
        if (lite || !ref.current) return;
        const r = ref.current.getBoundingClientRect();
        ref.current.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * strength}px, ${(e.clientY - r.top - r.height / 2) * strength}px)`;
      }}
      onPointerLeave={() => { if (ref.current) ref.current.style.transform = ""; }}>
      {children}
    </button>
  );
}
