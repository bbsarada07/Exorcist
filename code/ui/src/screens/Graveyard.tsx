import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { CaseSummary, Status, Summary } from "../lib/data";
import { useUI } from "../lib/store";
import { REPORTED_LABEL, STATUS_LABEL, STATUS_TONE, verdictLabel } from "../lib/labels";
import { StatusChip } from "../components/Chips";

const STONE_W = 26, GAP = 7;
const GLYPH: Record<Status, string> = { INCOMPLETE: "!", COMPLETE: "✓", NOT_APPLICABLE: "–" };

export function matches(c: CaseSummary, q: string, status: Status | "ALL", reviewOnly: boolean) {
  if (status !== "ALL" && c.s !== status) return false;
  if (reviewOnly && !c.q) return false;
  if (!q) return true;
  const s = q.toLowerCase().trim();
  return c.id.includes(s) || c.sys.some((x) => x.includes(s)) || STATUS_LABEL[c.s].toLowerCase().includes(s) ||
    c.s.toLowerCase().includes(s) || (c.v ?? "").toLowerCase().includes(s) || (c.r ?? "").toLowerCase().includes(s);
}

export function Graveyard({ summary }: { summary: Summary | null }) {
  const { view, setView, query, setQuery, statusFilter, setStatusFilter, reviewOnly, setReviewOnly, cursor, setCursor, open, caseId } = useUI();
  const cases = summary?.cases ?? [];
  const searchRef = useRef<HTMLInputElement>(null);
  const filtered = useMemo(() => cases.filter((c) => matches(c, query, statusFilter, reviewOnly)), [cases, query, statusFilter, reviewOnly]);
  const visible = useMemo(() => new Set(filtered.map((c) => c.id)), [filtered]);
  const current = filtered[Math.min(cursor, Math.max(0, filtered.length - 1))];

  // keyboard: "/" search, j/k move, Enter open
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (caseId || useUI.getState().palette) return;
      const typing = (e.target as HTMLElement)?.tagName === "INPUT";
      if (e.key === "/" && !typing) { e.preventDefault(); searchRef.current?.focus(); document.getElementById("graveyard")?.scrollIntoView(); return; }
      if (typing) { if (e.key === "Escape" || e.key === "Enter") (e.target as HTMLInputElement).blur(); return; }
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        const next = Math.max(0, Math.min(filtered.length - 1, cursor + (e.key === "j" ? 1 : -1)));
        setCursor(next);
        document.querySelector<HTMLElement>(`[data-case="${filtered[next]?.id}"]`)?.focus({ preventScroll: false });
      }
      if (e.key === "Enter" && current && document.activeElement?.getAttribute("data-case") == null) {
        const el = document.querySelector<HTMLElement>(`[data-case="${current.id}"]`);
        open(current.id, el?.getBoundingClientRect() ?? null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, cursor, current, caseId, open, setCursor]);

  const counts = summary?.totals.status;
  const filters: { key: Status | "ALL"; label: string }[] = [
    { key: "ALL", label: `all · ${summary?.totals.cases ?? 0}` },
    { key: "INCOMPLETE", label: `haunted · ${counts?.INCOMPLETE ?? 0}` },
    { key: "COMPLETE", label: `proven · ${counts?.COMPLETE ?? 0}` },
    { key: "NOT_APPLICABLE", label: `n/a · ${counts?.NOT_APPLICABLE ?? 0}` },
  ];

  return (
    <section id="graveyard" className="relative mx-auto min-h-screen max-w-[1500px] px-5 pb-24 pt-28 md:px-10">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="mono text-[11px] uppercase tracking-[0.3em] text-muted">case explorer</p>
          <h2 className="display mt-2 text-6xl text-bone md:text-8xl">The <span className="italic">graveyard</span></h2>
          <p className="mt-3 max-w-xl text-sm text-muted">
            Every tombstone is one deletion request from <span className="mono text-bone">output.csv</span>. Ember = still haunted,
            green = deletion proven, grey = no deletion requested. Glow grows with the number of findings; a dashed violet ring
            means the case is in the review queue.
          </p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="flex items-center gap-2">
            <label className="panel flex items-center gap-2 px-3 py-2">
              <span className="kbd">/</span>
              <input ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="case, system, verdict…"
                className="mono w-56 bg-transparent text-sm text-bone placeholder:text-muted/70 focus:outline-none" aria-label="Search cases" />
            </label>
            <div className="panel flex p-1" role="tablist" aria-label="View">
              {(["grid", "ledger"] as const).map((v) => (
                <button key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
                  className={`mono rounded-lg px-3 py-1.5 text-xs uppercase tracking-widest ${view === v ? "bg-bone text-ink" : "text-muted hover:text-bone"}`}>
                  {v}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {filters.map((f) => (
              <button key={f.key} onClick={() => setStatusFilter(f.key)} aria-pressed={statusFilter === f.key}
                className={`chip ${f.key === "ALL" ? "tone-bone" : `tone-${STATUS_TONE[f.key]}`} ${statusFilter === f.key ? "!bg-white/10" : "opacity-70 hover:opacity-100"}`}>
                {f.label}
              </button>
            ))}
            <button onClick={() => setReviewOnly(!reviewOnly)} aria-pressed={reviewOnly}
              className={`chip tone-flow ${reviewOnly ? "!bg-white/10" : "opacity-70 hover:opacity-100"}`}>
              needs review · {summary?.review.count ?? 0}
            </button>
          </div>
        </div>
      </div>

      <div className="mono mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-muted" aria-live="polite">
        <span>{filtered.length} of {cases.length} shown</span>
        <span><span className="kbd">j</span> <span className="kbd">k</span> move · <span className="kbd">enter</span> open · <span className="kbd">ctrl K</span> palette</span>
      </div>

      <div className="mt-6">
        {view === "grid"
          ? <StoneGrid cases={cases} visible={visible} currentId={current?.id ?? null} onOpen={open} />
          : <Ledger cases={filtered} onOpen={open} />}
      </div>
    </section>
  );
}

function StoneGrid({ cases, visible, currentId, onOpen }: { cases: CaseSummary[]; visible: Set<string>; currentId: string | null;
                                                          onOpen: (id: string, r: DOMRect) => void }) {
  const wrap = useRef<HTMLDivElement>(null);
  const els = useRef<(HTMLButtonElement | null)[]>([]);
  const [cols, setCols] = useState(30);
  const [tip, setTip] = useState<{ c: CaseSummary; x: number; y: number } | null>(null);
  const lit = useRef<number[]>([]);
  const lite = useUI((s) => s.lite);
  const maxF = useMemo(() => Math.max(1, ...cases.map((c) => c.f)), [cases]);

  useLayoutEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setCols(Math.max(8, Math.floor((e.contentRect.width + GAP) / (STONE_W + GAP)))));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const ripple = (i: number | null) => {
    for (const j of lit.current) { const el = els.current[j]; if (el) el.style.transform = ""; }
    lit.current = [];
    if (i === null || lite) return;
    const r0 = Math.floor(i / cols), c0 = i % cols;
    for (let dr = -3; dr <= 3; dr++) for (let dc = -3; dc <= 3; dc++) {
      const d = Math.hypot(dr, dc);
      if (d > 3.2) continue;
      const r = r0 + dr, c = c0 + dc;
      if (c < 0 || c >= cols || r < 0) continue;
      const j = r * cols + c, el = els.current[j];
      if (!el) continue;
      const k = 1 - d / 3.6;
      el.style.transform = d === 0 ? "translateY(-7px) scale(1.35)" : `translateY(${(-5 * k).toFixed(1)}px) scale(${(1 + 0.12 * k).toFixed(3)})`;
      lit.current.push(j);
    }
  };

  return (
    <div ref={wrap} className="relative" onPointerLeave={() => { ripple(null); setTip(null); }}>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${cols}, ${STONE_W}px)`, gap: `${GAP + 4}px ${GAP}px`, justifyContent: "space-between" }}>
        {cases.map((c, i) => (
          <button
            key={c.id}
            ref={(el) => { els.current[i] = el; }}
            data-stone
            data-case={c.id}
            data-tone={STATUS_TONE[c.s]}
            data-review={c.q}
            data-dim={visible.has(c.id) ? 0 : 1}
            data-cursor={currentId === c.id ? 1 : 0}
            tabIndex={visible.has(c.id) ? 0 : -1}
            style={{ ["--g" as string]: (c.f / maxF).toFixed(3) }}
            className="stone"
            aria-label={`${c.id}: ${STATUS_LABEL[c.s]} (${c.s}), ${c.f} findings, claimed ${REPORTED_LABEL[c.r] ?? c.r}${c.q ? ", needs review" : ""}`}
            onPointerEnter={(e) => {
              ripple(i);
              const el = e.currentTarget;
              setTip({ c, x: el.offsetLeft + STONE_W / 2, y: el.offsetTop });
            }}
            onFocus={(e) => { const el = e.currentTarget; setTip({ c, x: el.offsetLeft + STONE_W / 2, y: el.offsetTop }); }}
            onClick={(e) => onOpen(c.id, e.currentTarget.getBoundingClientRect())}
          >
            <span aria-hidden>{GLYPH[c.s]}</span>
          </button>
        ))}
      </div>
      <AnimatePresence>
        {tip && (
          <motion.div key="tip" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
            className="panel pointer-events-none absolute z-20 w-64 p-3"
            style={{ left: Math.min(Math.max(tip.x - 128, 0), (wrap.current?.clientWidth ?? 600) - 256), top: tip.y - 150 }}>
            <div className="flex items-center justify-between">
              <span className="mono text-sm text-bone">{tip.c.id}</span>
              <StatusChip status={tip.c.s} />
            </div>
            <dl className="mono mt-2 grid grid-cols-2 gap-y-1 text-[11px]">
              <dt className="text-muted">claimed</dt><dd className="text-bone">{REPORTED_LABEL[tip.c.r] ?? tip.c.r}</dd>
              <dt className="text-muted">findings</dt><dd className="text-bone">{tip.c.f}</dd>
              <dt className="text-muted">steps</dt><dd className="text-bone">{tip.c.n}</dd>
              <dt className="text-muted">confidence</dt><dd className="text-bone">{tip.c.c?.toFixed(2) ?? "—"}</dd>
            </dl>
            <p className="mt-2 text-[11px] leading-snug text-muted">{verdictLabel(tip.c.v)}</p>
            {tip.c.q === 1 && <p className="mono mt-1 text-[11px] text-flow">◆ needs review</p>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Ledger({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string, r: DOMRect) => void }) {
  return (
    <div className="panel overflow-hidden">
      <div className="scrollbar-thin max-h-[70vh] overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="mono sticky top-0 bg-panel text-[10px] uppercase tracking-[0.2em] text-muted">
            <tr>{["case", "reconstructed", "claimed", "verdict", "findings", "steps", "confidence", "review"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id} data-case={c.id} tabIndex={0} className="cursor-pointer border-t border-line hover:bg-white/[0.03] focus:bg-white/[0.05]"
                onClick={(e) => onOpen(c.id, e.currentTarget.getBoundingClientRect())}
                onKeyDown={(e) => e.key === "Enter" && onOpen(c.id, e.currentTarget.getBoundingClientRect())}>
                <td className="mono px-4 py-2.5 text-bone">{c.id}</td>
                <td className="px-4 py-2.5"><StatusChip status={c.s} /></td>
                <td className="px-4 py-2.5 text-muted">{REPORTED_LABEL[c.r] ?? c.r}</td>
                <td className="max-w-[18rem] truncate px-4 py-2.5 text-muted" title={verdictLabel(c.v)}>{verdictLabel(c.v)}</td>
                <td className="mono px-4 py-2.5 text-bone">{c.f}</td>
                <td className="mono px-4 py-2.5 text-bone">{c.n}</td>
                <td className="mono px-4 py-2.5 text-bone">{c.c?.toFixed(2) ?? "—"}</td>
                <td className="px-4 py-2.5">{c.q ? <span className="chip tone-flow">needs review</span> : <span className="mono text-xs text-muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
