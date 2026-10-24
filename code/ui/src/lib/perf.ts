// Device capability detection: caps particle counts and decides the default for Lite mode.
export const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export interface DeviceBudget {
  tier: "low" | "mid" | "high";
  particles: number;
  dpr: number;
}

export function deviceBudget(): DeviceBudget {
  const nav = navigator as Navigator & { deviceMemory?: number };
  const cores = nav.hardwareConcurrency ?? 4;
  const mem = nav.deviceMemory ?? 4;
  const area = window.innerWidth * window.innerHeight;
  const touch = matchMedia("(pointer: coarse)").matches;
  const tier: DeviceBudget["tier"] = cores <= 4 || mem <= 4 || touch ? "low" : cores >= 12 && mem >= 8 ? "high" : "mid";
  const perPixel = { low: 1 / 1100, mid: 1 / 650, high: 1 / 450 }[tier];
  const cap = { low: 900, mid: 2200, high: 3600 }[tier];
  return { tier, particles: Math.min(cap, Math.round(area * perPixel)), dpr: Math.min(window.devicePixelRatio || 1, tier === "low" ? 1 : 1.5) };
}
