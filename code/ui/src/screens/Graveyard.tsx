import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { CaseSummary, Status, Summary } from "../lib/data";
import { useUI } from "../lib/store";
import { REPORTED_LABEL, STATUS_LABEL, STATUS_TONE, verdictLabel } from "../lib/labels";
import { StatusChip } from "../components/Chips";
import { scrollToCenter } from "../lib/scroll";

const STONE_W = 30, GAP = 10;
const GLYPH: Record<Status, string> = { INCOMPLETE: "!", COMPLETE: "✓", NOT_APPLICABLE: "–" };
const FEW = 40;   // up to this many matches, matching pebbles also scale up 1.4x

/** Case matches the search text: case id (partial), system name, cited evidence id, status or verdict words. */
export function matches(c: CaseSummary, q: string, status: Status | "ALL", reviewOnly: boolean) {
  if (status !== "ALL" && c.s !== status) return false;
  if (reviewOnly && !c.q) return false;
  const s = q.toLowerCase().trim();
  if (!s) return true;
  return c.id.includes(s) || c.sys.some((x) => x.includes(s)) || (c.ev ?? []).some((e) => e === s || (s.length >= 10 && e.includes(s))) ||
    STATUS_LABEL[c.s].toLowerCase().includes(s) || c.s.toLowerCase() === s || (c.v ?? "").toLowerCase().includes(s);
}

export function Graveyard({ summary }: { summary: Summary | null }) {
  const { view, setView, query, setQuery, statusFilter, setStatusFilter, reviewOnly, setReviewOnly, cursor, setCursor, open, caseId } = useUI();
  const cases = useMemo(() => summary?.cases ?? [], [summary]);
  const searchRef = useRef<HTMLInputElement>(null);
  const filtered = useMemo(() => cases.filter((c) => matches(c, query, statusFilter, reviewOnly)), [cases, query, statusFilter, reviewOnly]);
  const visible = useMemo(() => new Set(filtered.map((c) => c.id)), [filtered]);
  const searching = !!query.trim() || statusFilter !== "ALL" || reviewOnly;
  const current = filtered[Math.min(cursor, Math.max(0, filtered.length - 1))];

  const openCase = (id: string) => open(id, document.querySelector<HTMLElement>(`[data-case="${id}"]`)?.getBoundingClientRect() ?? null);

  // keyboard: "/" search, j/k move, Enter open
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (caseId || useUI.getState().palette) return;
      const typing = (e.target as HTMLElement)?.tagName === "INPUT";
      if (e.key === "/" && !typing) { e.preventDefault(); searchRef.current?.focus(); return; }
      if (typing) return;
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        const next = Math.max(0, Math.min(filtered.length - 1, cursor + (e.key === "j" ? 1 : -1)));
        setCursor(next);
        document.querySelector<HTMLElement>(`[data-case="${filtered[next]?.id}"]`)?.focus({ preventScroll: false });
      }
      if (e.key === "Enter" && current && document.activeElement?.getAttribute("data-case") == null &&
          document.activeElement?.tagName !== "BUTTON" && document.activeElement?.tagName !== "A") openCase(current.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // the first match glides to the centre of the viewport whenever the query or a filter changes
  useEffect(() => {
    if (!searching || !filtered.length || view !== "grid") return;
    const id = setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`[data-case="${filtered[0].id}"]`);
      if (el) scrollToCenter(el, !useUI.getState().lite);
    }, 260);
    return () => clearTimeout(id);
  }, [query, statusFilter, reviewOnly, view]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts = summary?.totals.status;
  const filters: { key: Status | "ALL"; label: string }[] = [
    { key: "ALL", label: `all · ${summary?.totals.cases ?? 0}` },
    { key: "INCOMPLETE", label: `haunted · ${counts?.INCOMPLETE ?? 0}` },
    { key: "COMPLETE", label: `proven · ${counts?.COMPLETE ?? 0}` },
    { key: "NOT_APPLICABLE", label: `n/a · ${counts?.NOT_APPLICABLE ?? 0}` },
  ];
  const clearAll = () => { setQuery(""); setStatusFilter("ALL"); setReviewOnly(false); searchRef.current?.focus(); };

  return (
    <section id="graveyard" className="relative mx-auto min-h-screen max-w-[1560px] px-4 pb-[45vh] pt-28 md:px-10">
      <div className="panel-strong flex flex-wrap items-end justify-between gap-6 p-6 md:p-8">
        <div className="max-w-xl">
          <p className="micro !text-bone">02 · case explorer</p>
          <h2 className="display mt-2 text-6xl text-bone md:text-8xl">The <span className="italic">graveyard</span></h2>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Every tombstone is one deletion request from <span className="mono text-bone">output.csv</span>. Ember <span className="mono text-haunted">!</span> = still
            haunted, green <span className="mono text-proven">✓</span> = deletion proven, grey <span className="mono text-na">–</span> = no deletion requested.
            The halo grows with the number of findings; a dashed violet ring means the case is in the review queue.
          </p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <label className="panel flex items-center gap-2 px-3 py-2">
              <span className="kbd">/</span>
              <input ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="case, system or evidence id…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && filtered[0]) { e.preventDefault(); (e.target as HTMLInputElement).blur(); openCase(filtered[0].id); }
                  if (e.key === "Escape") { if (query) setQuery(""); else (e.target as HTMLInputElement).blur(); }
                }}
                className="mono w-64 bg-transparent text-sm text-bone placeholder:text-muted focus:outline-none" aria-label="Search cases" />
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
          <div className="flex flex-wrap justify-end gap-2" role="group" aria-label="Filters">
            {filters.map((f) => (
              <button key={f.key} onClick={() => setStatusFilter(f.key)} aria-pressed={statusFilter === f.key} data-filter={f.key}
                className={`chip ${f.key === "ALL" ? "tone-bone" : `tone-${STATUS_TONE[f.key]}`} ${statusFilter === f.key ? "!bg-white/15 ring-1 ring-current" : ""}`}>
                {f.label}
              </button>
            ))}
            <button onClick={() => setReviewOnly(!reviewOnly)} aria-pressed={reviewOnly} data-filter="REVIEW"
              className={`chip tone-flow ${reviewOnly ? "!bg-white/15 ring-1 ring-current" : ""}`}>
              needs review · {summary?.review.count ?? 0}
            </button>
          </div>
        </div>
      </div>

      <ResultStrip filtered={filtered} total={cases.length} searching={searching} query={query} onClear={clearAll} onOpen={openCase} />

      <div className="mt-4">
        {view === "grid"
          ? <StoneGrid cases={cases} visible={visible} searching={searching} few={filtered.length <= FEW} currentId={current?.id ?? null} onOpen={open} />
          : <Ledger cases={filtered} onOpen={open} />}
      </div>
    </section>
  );
}

function ResultStrip({ filtered, total, searching, query, onClear, onOpen }: { filtered: CaseSummary[]; total: number; searching: boolean; query: string;
                                                                              onClear: () => void; onOpen: (id: string) => void }) {
  const first = filtered[0];
  let message: React.ReactNode;
  if (!searching) message = <span className="text-muted">hover a tombstone for its summary · <span className="kbd">/</span> search · <span className="kbd">j</span> <span className="kbd">k</span> move · <span className="kbd">enter</span> open · <span className="kbd">ctrl K</span> palette</span>;
  else if (!filtered.length) message = <span className="text-haunted" data-no-matches>no matches{query ? ` for “${query}”` : ""} — try a case number, a system name or an evidence id</span>;
  else message = (
    <button onClick={() => onOpen(first.id)} className="text-left text-bone hover:text-proven" data-strip-first={first.id}>
      {filtered.length === 1 ? "1 match" : `${filtered.length} matches`}: <span className="text-bone">{first.id}</span> · {first.s.replace("_", " ")} · {first.f} finding{first.f === 1 ? "" : "s"}
      {filtered.length > 1 && <span className="text-muted"> (first of {filtered.length})</span>} · <span className="text-muted">press Enter to open</span>
    </button>
  );
  return (
    <div className="panel mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3" aria-live="polite" data-result-strip>
      <span className="mono shrink-0 whitespace-nowrap text-sm text-bone" data-count>{filtered.length} of {total} shown</span>
      <span className="mono min-w-0 flex-1 text-sm" data-strip-text>{message}</span>
      {searching && (
        <button onClick={onClear} className="chip tone-bone shrink-0" aria-label="Clear search and filters" data-clear>✕ clear</button>
      )}
    </div>
  );
}

function StoneGrid({ cases, visible, searching, few, currentId, onOpen }: { cases: CaseSummary[]; visible: Set<string>; searching: boolean; few: boolean;
  currentId: string | null; onOpen: (id: string, r: DOMRect) => void }) {
  const wrap = useRef<HTMLDivElement>(null);
  const tilt = useRef<HTMLDivElement>(null);
  const light = useRef<HTMLDivElement>(null);
  const els = useRef<(HTMLButtonElement | null)[]>([]);
  const [cols, setCols] = useState(30);
  const [tip, setTip] = useState<{ c: CaseSummary; x: number; y: number } | null>(null);
  const [live, setLive] = useState(false);
  const [waved, setWaved] = useState(false);
  const lit = useRef<number[]>([]);
  const lite = useUI((s) => s.lite);
  const maxF = useMemo(() => Math.max(1, ...cases.map((c) => c.f)), [cases]);

  useLayoutEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setCols(Math.max(8, Math.floor((e.contentRect.width + GAP) / (STONE_W + GAP)))));
    ro.observe(wrap.current);
    // animate (breathe / pulse) only while the grid is on screen; play the load wave the first time it appears
    const io = new IntersectionObserver(([e]) => { setLive(e.isIntersecting); if (e.isIntersecting) setWaved(true); }, { threshold: 0.05 });
    io.observe(wrap.current);
    return () => { ro.disconnect(); io.disconnect(); };
  }, []);

  const ripple = (i: number | null) => {
    for (const j of lit.current) { const el = els.current[j]; if (el) { el.style.translate = ""; el.style.scale = ""; } }
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
      el.style.translate = `0 ${d === 0 ? -8 : (-6 * k).toFixed(1)}px`;
      el.style.scale = d === 0 ? "1.35" : (1 + 0.12 * k).toFixed(3);
      lit.current.push(j);
    }
  };

  return (
    <div ref={wrap} className="panel relative overflow-hidden p-5 md:p-7" style={{ perspective: "1600px" }}
      onPointerMove={(e) => {
        if (lite || !wrap.current) return;
        const r = wrap.current.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
        if (tilt.current) tilt.current.style.transform = `rotateX(${(-y * 3).toFixed(2)}deg) rotateY(${(x * 4).toFixed(2)}deg)`;
        if (light.current) light.current.style.transform = `translate(${e.clientX - r.left - 260}px, ${e.clientY - r.top - 260}px)`;
      }}
      onPointerLeave={() => { ripple(null); setTip(null); if (tilt.current) tilt.current.style.transform = ""; if (light.current) light.current.style.transform = "translate(-9999px,0)"; }}>
      {!lite && <div ref={light} aria-hidden className="pointer-events-none absolute left-0 top-0 h-[520px] w-[520px] rounded-full opacity-60 mix-blend-screen"
                     style={{ transform: "translate(-9999px,0)", background: "radial-gradient(circle, rgba(237,233,224,.10), transparent 60%)" }} />}
      <div ref={tilt} className={`relative transition-transform duration-300 ease-out ${searching ? "searching" : ""} ${few ? "few" : ""} ${live && !lite ? "live" : ""} ${waved && !lite ? "wave-in" : ""}`}
           data-searching={searching ? 1 : 0}>
        <div className="grid" style={{ gridTemplateColumns: `repeat(${cols}, ${STONE_W}px)`, gap: `${GAP + 6}px ${GAP}px`, justifyContent: "space-between" }}>
          {cases.map((c, i) => {
            const match = visible.has(c.id);
            return (
              <button
                key={c.id}
                ref={(el) => { els.current[i] = el; }}
                data-stone
                data-case={c.id}
                data-tone={STATUS_TONE[c.s]}
                data-status={c.s}
                data-review={c.q}
                data-match={match ? 1 : 0}
                data-hot={c.f >= Math.max(2, Math.ceil(maxF * 0.5)) ? 1 : 0}
                data-cursor={currentId === c.id ? 1 : 0}
                tabIndex={match ? 0 : -1}
                style={{ ["--g" as string]: (c.f / maxF).toFixed(3), ["--d" as string]: `${(i % 11) * -0.5}s`,
                         ["--w" as string]: `${Math.min(900, (Math.floor(i / cols) + (i % cols)) * 14)}ms` }}
                className="stone"
                aria-label={`${c.id}: ${STATUS_LABEL[c.s]} (${c.s}), ${c.f} findings, claimed ${REPORTED_LABEL[c.r] ?? c.r}${c.q ? ", needs review" : ""}`}
                onPointerEnter={(e) => { ripple(i); const el = e.currentTarget; setTip({ c, x: el.offsetLeft + STONE_W / 2, y: el.offsetTop }); }}
                onFocus={(e) => { const el = e.currentTarget; setTip({ c, x: el.offsetLeft + STONE_W / 2, y: el.offsetTop }); }}
                onClick={(e) => onOpen(c.id, e.currentTarget.getBoundingClientRect())}
              >
                <span className="halo" aria-hidden />
                {searching && match && <span className="ring" aria-hidden />}
                <span aria-hidden className="relative">{GLYPH[c.s]}</span>
              </button>
            );
          })}
        </div>
        <AnimatePresence>
          {tip && (
            <motion.div key="tip" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
              className="panel-strong pointer-events-none absolute z-20 w-64 p-3" role="tooltip"
              style={{ left: Math.min(Math.max(tip.x - 128, 0), (tilt.current?.clientWidth ?? 600) - 256), top: Math.max(0, tip.y - 158) }}>
              <div className="flex items-center justify-between gap-2">
                <span className="mono text-sm text-bone">{tip.c.id}</span>
                <StatusChip status={tip.c.s} />
              </div>
              <dl className="mono mt-2 grid grid-cols-2 gap-y-1 text-xs">
                <dt className="text-muted">claimed</dt><dd className="text-bone">{REPORTED_LABEL[tip.c.r] ?? tip.c.r}</dd>
                <dt className="text-muted">findings</dt><dd className="text-bone">{tip.c.f}</dd>
                <dt className="text-muted">steps</dt><dd className="text-bone">{tip.c.n}</dd>
                <dt className="text-muted">confidence</dt><dd className="text-bone">{tip.c.c?.toFixed(2) ?? "—"}</dd>
              </dl>
              <p className="mt-2 text-xs leading-snug text-muted">{verdictLabel(tip.c.v)}</p>
              {tip.c.q === 1 && <p className="mono mt-1 text-xs text-flow">◆ needs review</p>}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Ledger({ cases, onOpen }: { cases: CaseSummary[]; onOpen: (id: string, r: DOMRect) => void }) {
  return (
    <div className="panel overflow-hidden">
      <div className="scrollbar-thin max-h-[70vh] overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="mono sticky top-0 bg-panel text-xs uppercase tracking-[0.16em] text-muted">
            <tr>{["case", "reconstructed", "claimed", "verdict", "findings", "steps", "confidence", "review"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id} data-case={c.id} tabIndex={0} className="cursor-pointer border-t border-line hover:bg-white/[0.04] focus:bg-white/[0.06]"
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
