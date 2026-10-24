import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { animate, motion } from "framer-motion";
import { loadDetails, type CaseDetail as Detail, type Phase, type StepRow } from "../lib/data";
import { useUI } from "../lib/store";
import { OP_VERB, REPORTED_LABEL, STATUS_LABEL, STATUS_TONE, fmtDate, modeLabel, verdictLabel } from "../lib/labels";
import { Chip, ConfidenceMeter, ReportedChip, ReviewBadge, StatusChip } from "../components/Chips";
import { useInView } from "../components/Motion";
import { Exorcism } from "./Exorcism";

const PHASES: Phase[] = ["FINDING", "REMEDIATION", "VERIFICATION"];
const STATE_TONE: Record<string, "haunted" | "proven" | "flow" | "bone"> = {
  PRESENT: "haunted", ACTIVE: "flow", ABSENT: "proven", REDACTED: "proven", ANONYMIZED: "proven", DISABLED: "proven", BLOCKED: "proven",
};

export function CaseDetailView() {
  const { caseId, open, originRect, lite } = useUI();
  const [d, setD] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setD(null); setMissing(false);
    loadDetails().then((all) => (all[caseId] ? setD(all[caseId]) : setMissing(true)));
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !useUI.getState().palette && open(null);
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [caseId, open]);

  if (!caseId) return null;
  return (
    <motion.div data-lenis-prevent className="scrollbar-thin fixed inset-0 z-40 overflow-y-auto bg-ink"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: lite ? 0 : 0.35 }}>
      <div className="mx-auto max-w-[1400px] px-5 pb-32 pt-24 md:px-10">
        <button onClick={() => open(null)} className="mono text-xs uppercase tracking-[0.25em] text-muted hover:text-bone">← graveyard <span className="kbd ml-1">esc</span></button>
        {missing && <p className="mt-10 text-muted">Unknown case <span className="mono">{caseId}</span>.</p>}
        {d && <Body d={d} origin={originRect} lite={lite} />}
      </div>
    </motion.div>
  );
}

function FlyingStone({ d, origin, lite }: { d: Detail; origin: { x: number; y: number; w: number; h: number } | null; lite: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  // shared-element zoom: start at the clicked tombstone's rect, settle into the header (transform only)
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !origin || lite) return;
    const f = el.getBoundingClientRect();
    animate(el, { x: [origin.x - f.left, 0], y: [origin.y - f.top, 0], scale: [origin.w / f.width, 1] },
            { duration: 0.75, ease: [0.2, 0.8, 0.2, 1] });
  }, [origin, lite, d.id]);
  const tone = STATUS_TONE[d.status];
  return (
    <div ref={ref} aria-hidden className="stone !h-[92px] !w-[70px] origin-top-left !rounded-[30px_30px_8px_8px] !text-3xl" data-tone={tone}
         data-review={d.review ? 1 : 0} style={{ ["--g" as string]: d.status === "INCOMPLETE" ? 0.8 : 0 }}>
      {d.status === "INCOMPLETE" ? "!" : d.status === "COMPLETE" ? "✓" : "–"}
    </div>
  );
}

function Body({ d, origin, lite }: { d: Detail; origin: { x: number; y: number; w: number; h: number } | null; lite: boolean }) {
  const [sel, setSel] = useState<number | null>(null);
  return (
    <>
      <header className="mt-8 flex flex-wrap items-end gap-8">
        <FlyingStone d={d} origin={origin} lite={lite} />
        <div className="min-w-0 flex-1">
          <p className="mono text-[11px] uppercase tracking-[0.3em] text-muted">case file</p>
          <h1 className="display mt-1 text-7xl text-bone md:text-9xl">{d.id.replace("_", " ")}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <StatusChip status={d.status} />
            <ReportedChip reported={d.reported} />
            {d.review && <ReviewBadge reasons={d.review.reasons} />}
            {d.risk && <Chip tone="haunted" title="Transparent heuristic from risk_scores.json, not a financial estimate">risk {d.risk.score} · heuristic</Chip>}
          </div>
        </div>
        <ConfidenceMeter value={d.confidence} />
      </header>

      <section className="mt-10 grid gap-4 md:grid-cols-3">
        <div className="panel p-5 md:col-span-2">
          <p className="mono text-[10px] uppercase tracking-[0.25em] text-muted">the request</p>
          <blockquote className="display mt-3 text-2xl italic leading-snug text-bone md:text-3xl">“{d.request_text}”</blockquote>
          <p className="mono mt-3 text-[11px] text-muted">intent · {d.intent}</p>
        </div>
        <dl className="panel mono grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-5 text-[12px]">
          <dt className="text-muted">subject</dt><dd className="text-bone">{d.user_id ?? "—"}</dd>
          <dt className="text-muted">email</dt><dd className="text-bone">{d.email ?? "—"} <span className="text-muted">(masked)</span></dd>
          <dt className="text-muted">matched</dt><dd className="text-bone">{d.identity_match} identifier</dd>
          <dt className="text-muted">requested</dt><dd className="text-bone">{fmtDate(d.requested_at)}</dd>
          <dt className="text-muted">claimed</dt><dd className="text-bone">{fmtDate(d.reported_at)}</dd>
          <dt className="text-muted">audit cut</dt><dd className="text-bone">{fmtDate(d.audit_at)}</dd>
        </dl>
      </section>

      {d.review && (
        <div className="panel mt-4 border-flow/40 p-4 text-sm">
          <p className="mono text-[10px] uppercase tracking-[0.25em] text-flow">in the review queue — why</p>
          <ul className="mt-2 space-y-1 text-bone">
            {d.review.reasons.map((r) => <li key={r}>· {r}</li>)}
            {d.review.links.map((l) => <li key={l.resource_id} className="mono text-[12px] text-muted">guessed link: {l.resource_id} ({l.kind.replace(/_/g, " ")}, margin {l.margin ?? "—"})</li>)}
          </ul>
        </div>
      )}

      <RealityRift d={d} />

      {d.status === "INCOMPLETE" && <Exorcism d={d} />}
      {d.status === "COMPLETE" && <ProofView d={d} />}
      {d.status === "NOT_APPLICABLE" && (
        <section className="panel mt-10 p-8 text-center">
          <p className="display text-4xl text-bone">Nothing to exorcise.</p>
          <p className="mt-3 text-muted">The request does not authorise deletion ({d.intent}), so the answer is <span className="mono text-bone">NOT_APPLICABLE</span> with an empty step list.</p>
        </section>
      )}

      {d.steps.length > 0 && <Runbook d={d} sel={sel} setSel={setSel} />}

      {(d.conflicts.length > 0 || d.lineage.length > 0) && (
        <section className="mt-10 grid gap-4 md:grid-cols-2">
          {d.conflicts.length > 0 && (
            <div className="panel p-5">
              <p className="mono text-[10px] uppercase tracking-[0.25em] text-muted">conflicting sources · conflicts.jsonl</p>
              <ul className="mt-3 space-y-2 text-sm">
                {d.conflicts.slice(0, 6).map((c, i) => (
                  <li key={i}><span className="mono text-bone">{c.r}</span> <span className="text-muted">— {c.type.replace(/_/g, " ")}; trusted {c.trusted}. {c.why}</span></li>
                ))}
              </ul>
            </div>
          )}
          {d.lineage.length > 0 && (
            <div className="panel p-5">
              <p className="mono text-[10px] uppercase tracking-[0.25em] text-muted">recreation paths · lineage.json</p>
              <ul className="mono mt-3 space-y-2 text-[12px]">
                {d.lineage.map((e, i) => (
                  <li key={i} className="text-bone">{e.from} <span className="text-flow">—{e.kind.replace(/_/g, " ").toLowerCase()}→</span> {e.to} <span className="text-muted">{e.via}{e.at ? ` · ${e.at.slice(0, 10)}` : ""}</span></li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </>
  );
}

function RealityRift({ d }: { d: Detail }) {
  const [ref, seen] = useInView<HTMLElement>(0.35);
  const lite = useUI((s) => s.lite);
  const claimed = REPORTED_LABEL[d.reported] ?? d.reported;
  const truth = d.status === "NOT_APPLICABLE" ? "No deletion requested" : STATUS_LABEL[d.status];
  const tone = STATUS_TONE[d.status];
  return (
    <section id="reality-rift" ref={ref} className="relative mt-12 grid overflow-hidden rounded-panel border border-line md:grid-cols-2">
      <div className="scanlines relative bg-[#0b0b12] p-8 md:p-10">
        <p className="mono text-[10px] uppercase tracking-[0.3em] text-muted">reported · the legacy workflow said</p>
        <p className="display glitch mt-6 text-6xl text-bone md:text-7xl" data-text={claimed}>{claimed}</p>
        <p className="mono mt-6 text-[11px] text-muted">reported_status = {d.reported} · at {fmtDate(d.reported_at)}</p>
      </div>
      <div className="relative bg-panel p-8 md:p-10">
        <p className="mono text-[10px] uppercase tracking-[0.3em] text-muted">reality · reconstructed from evidence at audit_at</p>
        <p className={`display mt-6 text-6xl md:text-7xl tone-${tone}`}>{truth}</p>
        <p className="mt-4 text-sm text-bone">{verdictLabel(d.verdict)}</p>
        {d.failure_modes.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {d.failure_modes.map((m) => <Chip key={m} tone={m.includes("flow") ? "flow" : "haunted"}>{modeLabel(m)}</Chip>)}
          </div>
        )}
        <p className="mono mt-6 text-[11px] text-muted">source · lie_report.json{d.verdict ? ` verdict "${d.verdict}"` : ""}</p>
        {/* reveal curtain: transform-only wipe */}
        <motion.div aria-hidden className="absolute inset-0 origin-right bg-ink"
          initial={{ scaleX: lite ? 0 : 1 }} animate={{ scaleX: seen || lite ? 0 : 1 }} transition={{ duration: 1.1, ease: [0.7, 0, 0.2, 1], delay: 0.25 }} />
      </div>
      <div aria-hidden className="pointer-events-none absolute inset-y-0 left-1/2 hidden w-px bg-gradient-to-b from-transparent via-haunted to-transparent shadow-[0_0_24px_4px_rgba(255,107,71,.45)] md:block" />
    </section>
  );
}

function StepLine({ s, i, active, onClick }: { s: StepRow; i: number; active: boolean; onClick: () => void }) {
  const [phase, op, system, resource, state, ev] = s;
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`grid w-full grid-cols-[2rem_1fr_auto] items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${active ? "bg-white/[0.07]" : "hover:bg-white/[0.035]"}`}>
      <span className="mono pt-0.5 text-[11px] text-muted">{String(i + 1).padStart(2, "0")}</span>
      <span className="min-w-0">
        <span className="block text-sm text-bone">{OP_VERB[op] ?? op}</span>
        <span className="mono block truncate text-[11px] text-muted">{op}</span>
        <span className="mono block truncate text-[12px] text-bone/90">{system} / {resource}</span>
        <span className="mono block text-[11px] text-muted">evidence · {ev || (phase === "FINDING" ? "—" : "future work (\"\")")}</span>
      </span>
      <span className={`chip tone-${STATE_TONE[state] ?? "bone"}`}>{state}</span>
    </button>
  );
}

function Runbook({ d, sel, setSel }: { d: Detail; sel: number | null; setSel: (i: number | null) => void }) {
  const why = sel !== null ? d.why[sel] : null;
  return (
    <section id="runbook" className="mt-12">
      <div className="flex items-end justify-between">
        <h2 className="display text-5xl text-bone">The runbook</h2>
        <p className="mono text-[11px] text-muted">exact rows from output.csv · click a step for its decision trace</p>
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr_1fr_minmax(0,22rem)]">
        {PHASES.map((p) => {
          const rows = d.steps.map((s, i) => [s, i] as const).filter(([s]) => s[0] === p);
          return (
            <div key={p} className="panel p-3">
              <p className="mono px-3 pb-2 pt-1 text-[10px] uppercase tracking-[0.25em] text-muted">{p.toLowerCase()} · {rows.length}</p>
              {rows.length === 0 && <p className="px-3 pb-3 text-xs text-muted">none</p>}
              {rows.map(([s, i]) => <StepLine key={i} s={s} i={i} active={sel === i} onClick={() => setSel(sel === i ? null : i)} />)}
            </div>
          );
        })}
        <aside className="panel p-5 lg:sticky lg:top-24 lg:self-start" aria-live="polite">
          <p className="mono text-[10px] uppercase tracking-[0.25em] text-muted">why this step exists · decision_trace.jsonl</p>
          {sel === null || !why ? (
            <p className="mt-4 text-sm text-muted">Select a step to see the rule, the policy category and the evidence chain behind it.</p>
          ) : (
            <dl className="mono mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-[12px]">
              <dt className="text-muted">step</dt><dd className="text-bone">{sel + 1} · {d.steps[sel][1]}</dd>
              <dt className="text-muted">rule</dt><dd className="text-bone">{why[0]}</dd>
              <dt className="text-muted">category</dt><dd className="text-bone">{why[1]} <span className="text-muted">(from {why[2].replace(/_/g, " ")})</span></dd>
              <dt className="text-muted">verdict</dt><dd className="text-bone">{why[3]}</dd>
              <dt className="text-muted">agent</dt><dd className="text-bone">{why[4]}</dd>
              <dt className="text-muted">linked by</dt><dd className="text-bone">{why[5] ?? "—"}</dd>
              <dt className="text-muted">evidence</dt>
              <dd className="flex flex-wrap gap-1">{why[6].length ? why[6].map((e) => <span key={e} className="rounded border border-line px-1.5 text-proven">{e}</span>) : <span className="text-muted">—</span>}</dd>
            </dl>
          )}
        </aside>
      </div>
    </section>
  );
}

function ProofView({ d }: { d: Detail }) {
  const [ref, seen] = useInView<HTMLElement>(0.2);
  const lite = useUI((s) => s.lite);
  const ver = d.steps.map((s, i) => [s, i] as const).filter(([s]) => s[0] === "VERIFICATION");
  return (
    <section id="proof" ref={ref} className="panel glow-proven relative mt-12 overflow-hidden p-8 md:p-10">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="mono text-[10px] uppercase tracking-[0.3em] text-proven">proof view · nothing to fix</p>
          <h2 className="display mt-2 text-5xl text-bone md:text-6xl">Proven <span className="italic">clean</span>.</h2>
          <p className="mt-3 max-w-xl text-sm text-muted">Every check below cites evidence captured before the audit cut. There is no remediation to perform, so there is no exorcism, only proof.</p>
        </div>
        <div className="grid h-28 w-28 place-items-center rounded-full border-2 border-proven text-center text-proven shadow-[0_0_40px_-6px_rgba(124,255,178,.6)]">
          <span className="mono text-[10px] uppercase leading-tight tracking-[0.2em]">verified<br />{ver.length} of {ver.length}</span>
        </div>
      </div>
      <ol className="mt-8 space-y-2">
        {ver.map(([s, i], k) => (
          <motion.li key={i} initial={{ opacity: lite ? 1 : 0, x: lite ? 0 : -10 }} animate={seen ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: lite ? 0 : 0.15 * k, duration: 0.45 }}
            className="grid grid-cols-[1.5rem_1fr_auto] items-center gap-3 rounded-lg border border-line bg-ink/40 px-4 py-3">
            <span className="text-proven" aria-label="passed">✓</span>
            <span className="min-w-0">
              <span className="block text-sm text-bone">{OP_VERB[s[1]]} · <span className="mono text-[12px]">{s[2]} / {s[3]}</span></span>
              <span className="mono block text-[11px] text-muted">{d.why[i]?.[3]} · rule {d.why[i]?.[0]}</span>
            </span>
            <span className="mono text-[12px] text-proven">{s[5]}</span>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
