import { create } from "zustand";
import { prefersReducedMotion } from "./perf";
import type { Status } from "./data";
import type { PerfMode } from "../effects/fluid";

export type View = "grid" | "ledger";

interface UIState {
  lite: boolean;               // Lite mode: no particles/shaders, all information kept
  caseId: string | null;       // open case (mirrors #/case/<id>)
  view: View;
  query: string;
  statusFilter: Status | "ALL";
  reviewOnly: boolean;
  cursor: number;              // keyboard focus index in the filtered graveyard
  palette: boolean;
  originRect: { x: number; y: number; w: number; h: number } | null; // tombstone rect for the shared-element zoom
  perf: PerfMode;              // fluid/particle quality: auto (adaptive) | high | low
  fluidKind: "webgl" | "css";  // which background is actually running
  slow: boolean;               // auto mode gave up the shader: the device is struggling, offer Lite
  setSlow: (v: boolean) => void;
  setPerf: (p: PerfMode) => void;
  setFluidKind: (k: "webgl" | "css") => void;
  setLite: (v: boolean) => void;
  open: (id: string | null, origin?: DOMRect | null) => void;
  setView: (v: View) => void;
  setQuery: (q: string) => void;
  setStatusFilter: (s: Status | "ALL") => void;
  setReviewOnly: (v: boolean) => void;
  setCursor: (i: number) => void;
  setPalette: (v: boolean) => void;
}

const storedLite = (() => {
  try {
    const v = localStorage.getItem("exorcist.lite");
    return v === null ? null : v === "1";
  } catch {
    return null;
  }
})();

const storedPerf = (() => {
  try { const v = localStorage.getItem("exorcist.perf"); return v === "high" || v === "low" ? v : "auto"; } catch { return "auto"; }
})() as PerfMode;

const caseFromHash = () => {
  const m = location.hash.match(/^#\/case\/([\w-]+)$/);
  return m ? m[1] : null;
};

export const useUI = create<UIState>((set) => ({
  lite: storedLite ?? prefersReducedMotion(),
  caseId: caseFromHash(),
  view: "grid",
  query: "",
  statusFilter: "ALL",
  reviewOnly: false,
  cursor: 0,
  palette: false,
  originRect: null,
  perf: storedPerf,
  fluidKind: "css",
  slow: false,
  setSlow: (slow) => set({ slow }),
  setPerf: (perf) => { try { localStorage.setItem("exorcist.perf", perf); } catch { /* storage unavailable */ } set({ perf }); },
  setFluidKind: (fluidKind) => set({ fluidKind }),
  setLite: (lite) => {
    try { localStorage.setItem("exorcist.lite", lite ? "1" : "0"); } catch { /* storage unavailable */ }
    set({ lite });
  },
  open: (caseId, origin = null) => {
    const target = caseId ? `#/case/${caseId}` : "#/";
    if (location.hash !== target) history.pushState(null, "", target);
    set({ caseId, originRect: origin ? { x: origin.left, y: origin.top, w: origin.width, h: origin.height } : null });
  },
  setView: (view) => set({ view }),
  setQuery: (query) => set({ query, cursor: 0 }),
  setStatusFilter: (statusFilter) => set({ statusFilter, cursor: 0 }),
  setReviewOnly: (reviewOnly) => set({ reviewOnly, cursor: 0 }),
  setCursor: (cursor) => set({ cursor }),
  setPalette: (palette) => set({ palette }),
}));

window.addEventListener("popstate", () => useUI.setState({ caseId: caseFromHash() }));
