import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { loadDetails, type CaseDetail, type Summary } from "../lib/data";
import { useUI } from "../lib/store";
import { STATUS_LABEL } from "../lib/labels";

type Item = { kind: "case" | "system" | "evidence"; label: string; hint: string; run: () => void };

/** ctrl/cmd+K: jump to cases, filter by system, or find every case citing an evidence id. */
export function CommandPalette({ summary }: { summary: Summary | null }) {
  const { palette, setPalette, open, setQuery, setStatusFilter } = useUI();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [details, setDetails] = useState<Record<string, CaseDetail> | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(!useUI.getState().palette); }
      if (e.key === "Escape" && useUI.getState().palette) setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPalette]);

  useEffect(() => {
    if (!palette) return;
    setQ(""); setSel(0);
    loadDetails().then(setDetails);
    setTimeout(() => input.current?.focus(), 30);
  }, [palette]);

  const evidenceIndex = useMemo(() => {
    const idx = new Map<string, string[]>();
    if (!details) return idx;
    for (const d of Object.values(details)) for (const s of d.steps) if (s[5]) {
      const arr = idx.get(s[5]) ?? [];
      if (!arr.includes(d.id)) arr.push(d.id);
      idx.set(s[5], arr);
    }
    return idx;
  }, [details]);

  const items = useMemo<Item[]>(() => {
    const s = q.toLowerCase().trim();
    const out: Item[] = [];
    const goGrid = () => { open(null); setTimeout(() => document.getElementById("graveyard")?.scrollIntoView(), 60); };
    for (const c of summary?.cases ?? []) {
      if (out.length >= 8) break;
      if (!s || c.id.includes(s)) out.push({ kind: "case", label: c.id, hint: `${STATUS_LABEL[c.s]} · ${c.f} findings${c.q ? " · needs review" : ""}`, run: () => open(c.id) });
    }
    const systems = [...new Set((summary?.cases ?? []).flatMap((c) => c.sys))].sort();
    for (const sys of systems.filter((x) => !s || x.includes(s)).slice(0, 5))
      out.push({ kind: "system", label: sys, hint: `filter the graveyard to ${(summary?.cases ?? []).filter((c) => c.sys.includes(sys)).length} cases`,
                 run: () => { setStatusFilter("ALL"); setQuery(sys); goGrid(); } });
    if (s.length >= 3) for (const [ev, ids] of [...evidenceIndex.entries()].filter(([e]) => e.includes(s)).slice(0, 6))
      out.push({ kind: "evidence", label: ev, hint: `cited by ${ids.length} case${ids.length > 1 ? "s" : ""}: ${ids.slice(0, 4).join(", ")}${ids.length > 4 ? "…" : ""}`,
                 run: () => open(ids[0]) });
    return out;
  }, [q, summary, evidenceIndex, open, setQuery, setStatusFilter]);

  const choose = (it: Item | undefined) => { if (!it) return; setPalette(false); it.run(); };

  return (
    <AnimatePresence>
      {palette && (
        <motion.div className="fixed inset-0 z-[80] flex items-start justify-center bg-ink/70 px-4 pt-[14vh] backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setPalette(false)}>
          <motion.div role="dialog" aria-label="Command palette" className="panel w-full max-w-xl overflow-hidden"
            initial={{ y: -12, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: -8, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 border-b border-line px-4 py-3">
              <span className="mono text-xs text-proven">⌘K</span>
              <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") { e.preventDefault(); setSel((x) => Math.min(items.length - 1, x + 1)); }
                  if (e.key === "ArrowUp") { e.preventDefault(); setSel((x) => Math.max(0, x - 1)); }
                  if (e.key === "Enter") choose(items[sel]);
                }}
                placeholder="case_93, search_service, evidence_92…" className="mono w-full bg-transparent text-sm text-bone placeholder:text-muted/70 focus:outline-none" />
            </div>
            <ul className="scrollbar-thin max-h-[50vh] overflow-auto py-2" role="listbox">
              {items.map((it, i) => (
                <li key={`${it.kind}-${it.label}`} role="option" aria-selected={i === sel}
                  onMouseEnter={() => setSel(i)} onClick={() => choose(it)}
                  className={`flex cursor-pointer items-center gap-3 px-4 py-2 ${i === sel ? "bg-white/[0.06]" : ""}`}>
                  <span className={`mono w-16 text-[10px] uppercase tracking-widest ${it.kind === "case" ? "text-bone" : it.kind === "system" ? "text-flow" : "text-proven"}`}>{it.kind}</span>
                  <span className="mono text-sm text-bone">{it.label}</span>
                  <span className="ml-auto truncate text-xs text-muted">{it.hint}</span>
                </li>
              ))}
              {!items.length && (
                <li className="px-4 py-6 text-center text-sm text-muted">
                  {q.trim().length < 3 ? "Type 3+ characters to search evidence ids." : "No case, system or cited evidence id matches."}
                </li>
              )}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
