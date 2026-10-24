import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import type { CaseDetail, StepRow } from "../lib/data";
import { useUI } from "../lib/store";
import { OP_VERB } from "../lib/labels";
import { DustLayer } from "../effects/dust";
import { fluid, purgeOrigin, setFluidScene } from "../lib/fluid";

interface Target {
  rid: string;
  sys: string;
  op: string;              // remediation operation
  before: string;          // state reported by the finding (PRESENT / ACTIVE)
  after: string;           // state the remediation produces
  cat: string | null;      // policy category from the decision trace
  fields: string[];        // identifier kinds the finding says are exposed (decision trace reason)
  step: number;            // remediation step index
}

const BEFORE: Record<string, string> = { DISABLE_DATA_FLOW: "ACTIVE", BLOCK_RESTORE: "ACTIVE" };
const SCRAMBLE = "▚▞▖▗▘▝#%@&$?*";

/** Identifier kinds named by the finding's decision-trace reason, e.g. "exposes ['email', 'hash']". */
function exposedFields(reason: string | undefined): string[] {
  const m = reason?.match(/\[(.*)\]/);
  return m ? m[1].split(",").map((x) => x.trim().replace(/'/g, "").replace("user_ref", "user reference")).filter(Boolean) : [];
}

function buildModel(d: CaseDetail) {
  const findings = new Map<string, number>();
  d.steps.forEach((s, i) => s[0] === "FINDING" && findings.set(s[3], i));
  const targets: Target[] = d.steps.flatMap((s: StepRow, i) => {
    if (s[0] !== "REMEDIATION") return [];
    const fi = findings.get(s[3]);
    return [{ rid: s[3], sys: s[2], op: s[1], before: fi !== undefined ? d.steps[fi][4] : BEFORE[s[1]] ?? "PRESENT",
              after: s[4], cat: d.why[i]?.[1] ?? null, fields: exposedFields(fi !== undefined ? d.why[fi]?.[3] : undefined), step: i }];
  });
  const retained = d.steps.filter((s) => s[0] === "VERIFICATION" && s[1] === "VERIFY_RECORD_PRESENT").map((s) => ({ rid: s[3], sys: s[2] }));
  const checks = d.steps.map((s, i) => [s, i] as const).filter(([s]) => s[0] === "VERIFICATION");
  return { targets, retained, checks };
}

// split a cubic bezier at t=0.5 (de Casteljau) so a snipped tendril can come apart in two halves
function splitCubic(p: number[][]) {
  const mid = (a: number[], b: number[]) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const [p0, p1, p2, p3] = p;
  const a = mid(p0, p1), b = mid(p1, p2), c = mid(p2, p3), e = mid(a, b), f = mid(b, c), g = mid(e, f);
  const path = (q: number[][]) => `M${q[0][0]},${q[0][1]} C${q[1][0]},${q[1][1]} ${q[2][0]},${q[2][1]} ${q[3][0]},${q[3][1]}`;
  return { a: path([p0, a, e, g]), b: path([g, f, c, p3]), mid: g };
}

export function Exorcism({ d }: { d: CaseDetail }) {
  const lite = useUI((s) => s.lite);
  const { targets, retained, checks } = useMemo(() => buildModel(d), [d]);
  const stage = useRef<HTMLDivElement>(null);
  const dustCanvas = useRef<HTMLCanvasElement>(null);
  const dust = useRef<DustLayer | null>(null);
  const tl = useRef<gsap.core.Timeline | null>(null);
  const [tendrils, setTendrils] = useState<{ rid: string; a: string; b: string; mid: number[] }[]>([]);
  const [phase, setPhase] = useState<"idle" | "running" | "done">("idle");
  const [announce, setAnnounce] = useState("");

  const flows = useMemo(() => targets.filter((t) => t.op === "DISABLE_DATA_FLOW" || t.op === "BLOCK_RESTORE"), [targets]);
  const records = useMemo(() => targets.filter((t) => !flows.includes(t)), [targets, flows]);

  // measure tendrils: each disabled flow reaches the record its lineage edge names, else the record column
  const measure = useCallback(() => {
    const st = stage.current;
    if (!st) return;
    const box = st.getBoundingClientRect();
    const rect = (sel: string) => st.querySelector(sel)?.getBoundingClientRect();
    const out: typeof tendrils = [];
    for (const f of flows.filter((x) => x.op === "DISABLE_DATA_FLOW")) {
      const from = rect(`[data-x="${f.rid}"]`);
      const edge = d.lineage.find((e) => e.from === f.rid && records.some((r) => r.rid === e.to));
      const to = edge ? rect(`[data-x="${edge.to}"]`) : rect("[data-col='records']");
      if (!from || !to) continue;
      // leave the flow card from its bottom edge and loop down and into the record it feeds
      const p0 = [from.left + from.width * 0.7 - box.left, from.bottom - box.top - 4];
      const p3 = [to.left + Math.min(to.width * 0.35, 120) - box.left, to.bottom - box.top - 6];
      out.push({ rid: f.rid, ...splitCubic([p0, [p0[0] + 10, p0[1] + 130], [p3[0] - 10, p3[1] + 130], p3]) });
    }
    setTendrils(out);
  }, [flows, records, d.lineage]);

  useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  useEffect(() => {
    if (lite || !dustCanvas.current) return;
    dust.current = new DustLayer(dustCanvas.current);
    return () => { dust.current?.destroy(); dust.current = null; };
  }, [lite]);

  const build = useCallback(() => {
    const st = stage.current!;
    const q = (sel: string) => st.querySelectorAll(sel);
    const violet = Math.min(1, targets.filter((x) => x.op === "DISABLE_DATA_FLOW").length / 2);
    const t = gsap.timeline({ paused: true, onComplete: () => {
      fluid.purge.v = 1;
      setFluidScene("case:EXORCISED", 0, 0);          // calm green flow once every check passes
      setPhase("done"); setAnnounce("Exorcism complete: every verification passes in the simulated end state.");
    } });
    t.timeScale(lite ? 2.6 : 1);
    t.to(q("[data-shield]"), { opacity: 1, duration: 0.4 }, 0);
    let at = 0.35;
    for (const x of targets) {
      const card = st.querySelector(`[data-x="${x.rid}"]`);
      if (!card) continue;
      const swap = () => {
        t.to(card.querySelectorAll("[data-before]"), { opacity: 0, duration: 0.2 }, ">-0.05");
        t.to(card.querySelectorAll("[data-after]"), { opacity: 1, duration: 0.25 }, "<");
        t.to(card.querySelectorAll("[data-heat]"), { opacity: 0, duration: 0.3 }, "<");
      };
      t.call(() => setAnnounce(`Step ${x.step + 1}: ${OP_VERB[x.op]} — ${x.sys} / ${x.rid}`), [], at);
      t.to(card, { scale: 1.035, duration: 0.18, yoyo: true, repeat: 1 }, at);
      if (x.op === "DISABLE_DATA_FLOW") {
        const halfA = st.querySelector(`[data-tendril-a="${x.rid}"]`), halfB = st.querySelector(`[data-tendril-b="${x.rid}"]`);
        const snip = st.querySelector(`[data-snip="${x.rid}"]`);
        if (snip) t.fromTo(snip, { scale: 0.2, opacity: 0 }, { scale: 1.6, opacity: 1, duration: 0.18, transformOrigin: "50% 50%" }, at + 0.25)
                   .to(snip, { opacity: 0, scale: 2.2, duration: 0.35 }, ">");
        if (halfB) t.to(halfB, { x: 18, y: 26, rotation: 9, opacity: 0, duration: 0.7, ease: "power2.in", transformOrigin: "0% 0%" }, at + 0.3);
        if (halfA) t.to(halfA, { opacity: 0.12, duration: 0.6 }, at + 0.3);
        swap();
      } else if (x.op === "BLOCK_RESTORE") {
        const seal = card.querySelector("[data-seal]");
        t.fromTo(seal, { scale: 2.8, opacity: 0, rotation: -28 }, { scale: 1, opacity: 1, rotation: -9, duration: 0.42, ease: "back.out(2.2)" }, at + 0.2);
        t.to(card, { y: 3, duration: 0.06, yoyo: true, repeat: 1 }, ">-0.12");
        swap();
      } else if (x.op === "DELETE_RECORD") {
        if (!lite) t.to(card, { keyframes: { x: [0, -3, 4, -2, 0] }, duration: 0.3 }, at + 0.1);
        t.call(() => {
          const r = card.querySelector("[data-body]")?.getBoundingClientRect(), b = st.getBoundingClientRect();
          if (r && dust.current) dust.current.burst({ x: r.left - b.left, y: r.top - b.top, w: r.width, h: r.height });
        }, [], at + 0.4);
        t.to(card.querySelectorAll("[data-body]"), { opacity: 0, scale: 0.94, duration: 0.55, ease: "power2.in" }, at + 0.4);
        swap();
      } else if (x.op === "REDACT_RECORD") {
        t.to(card.querySelectorAll("[data-bar]"), { scaleX: 1, duration: 0.32, stagger: 0.12, ease: "power2.inOut" }, at + 0.2);
        swap();
      } else if (x.op === "ANONYMIZE_RECORD") {
        const vals = card.querySelectorAll<HTMLElement>("[data-val]");
        const proxy = { p: 0 };
        t.to(proxy, { p: 1, duration: 0.9, ease: "none", onUpdate: () => vals.forEach((v) => {
          v.textContent = proxy.p < 0.95 ? Array.from({ length: 10 }, () => SCRAMBLE[(Math.random() * SCRAMBLE.length) | 0]).join("") : "∅ unlinked";
        }) }, at + 0.2);
        swap();
      }
      // each banished spirit drives a little ember out of the fluid
      t.to(fluid.purge, { v: ((targets.indexOf(x) + 1) / targets.length) * 0.3, duration: 0.6, ease: "sine.out" }, ">-0.3");
      at = t.duration() + 0.15;
    }
    t.call(() => setAnnounce("Verification checks"), [], at);
    t.to(q("[data-check]"), { opacity: 1, duration: 0.25, stagger: 0.14 }, at);
    t.fromTo(q("[data-tick]"), { scale: 0 }, { scale: 1, duration: 0.3, stagger: 0.14, ease: "back.out(3)" }, at);
    const end = t.duration();
    t.fromTo(q("[data-final]"), { scale: 3.2, opacity: 0, rotation: -14 }, { scale: 1, opacity: 1, rotation: -6, duration: 0.32, ease: "power4.in" }, end + 0.1);
    if (!lite) t.to(st, { keyframes: { x: [0, -7, 6, -4, 2, 0], y: [0, 4, -3, 2, -1, 0] }, duration: 0.38 }, ">");
    t.fromTo(q("[data-pulse]"), { scale: 0.4, opacity: 0.75 }, { scale: 2.4, opacity: 0, duration: 1.2, ease: "power2.out" }, "<");
    // THE PURGE: green floods out from the seal as a wave, ember is pushed to the edges and fades
    t.to(fluid.purge, { v: 1, duration: 2.6, ease: "power2.inOut" }, "<");
    t.call(() => setFluidScene("case:EXORCISED", 0, violet * 0.2), [], "<+=1.2");
    return t;
  }, [targets, lite]);

  const run = useCallback(() => {
    tl.current?.kill();
    const st = stage.current!;
    gsap.set(st.querySelectorAll("[data-before],[data-body],[data-heat],[data-tendril-a]"), { opacity: 1, scale: 1, x: 0, y: 0, rotation: 0 });
    gsap.set(st.querySelectorAll("[data-after],[data-check],[data-final],[data-seal],[data-snip],[data-shield]"), { opacity: 0 });
    gsap.set(st.querySelectorAll("[data-tendril-b]"), { opacity: 1, x: 0, y: 0, rotation: 0 });
    gsap.set(st.querySelectorAll("[data-bar]"), { scaleX: 0 });
    st.querySelectorAll<HTMLElement>("[data-val]").forEach((v) => (v.textContent = v.dataset.val ?? ""));
    dust.current?.resize();
    measure();
    // reset the fluid: ember again, purge origin = the seal's position on screen
    gsap.killTweensOf(fluid.purge);
    fluid.purge.v = 0;
    setFluidScene("case:INCOMPLETE", 1, Math.min(1, targets.filter((x) => x.op === "DISABLE_DATA_FLOW").length / 2));
    const seal = st.querySelector("[data-final]")?.getBoundingClientRect();
    if (seal) purgeOrigin(seal.left + seal.width / 2, seal.top + seal.height / 2);
    tl.current = build();
    setPhase("running");
    tl.current.play(0);
  }, [build, measure]);

  // Space skips to the sealed end state
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (phase === "running" && tl.current) { e.preventDefault(); tl.current.progress(1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase]);
  useEffect(() => () => { tl.current?.kill(); gsap.killTweensOf(fluid.purge); fluid.purge.v = 0; }, []);

  return (
    <section id="exorcism" className="mt-12" data-phase={phase}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="micro !text-haunted">03 · the exorcism · driven by this case's remediation steps</p>
          <h2 className="display mt-2 text-5xl text-bone md:text-6xl">{targets.length} spirit{targets.length === 1 ? "" : "s"} to banish</h2>
        </div>
        <div className="flex items-center gap-3">
          {phase === "running" && <span className="mono text-xs text-muted"><span className="kbd">space</span> skip</span>}
          <button onClick={run} className="group relative overflow-hidden rounded-full border border-haunted px-6 py-3 text-bone glow-haunted transition-transform hover:scale-[1.02]">
            <span className="mono text-xs uppercase tracking-[0.25em]">{phase === "idle" ? "Perform the Exorcism" : "Replay the exorcism"}</span>
          </button>
        </div>
      </div>
      <p className="sr-only" aria-live="polite">{announce}</p>

      <div ref={stage} className="panel relative mt-6 overflow-hidden p-6 md:p-8" style={{ minHeight: 460 }}>
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(255,107,71,.10),transparent_60%)]" data-heat />
        <svg aria-hidden className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-visible">
          {!lite && tendrils.map((t) => (
            <g key={t.rid}>
              {/* the CSS pulse lives on the group; GSAP fades the paths (opacities multiply, no fight) */}
              <g className="animate-pulse" style={{ filter: "drop-shadow(0 0 6px #9B8DFF)" }}>
                <path data-tendril-a={t.rid} d={t.a} fill="none" stroke="#9B8DFF" strokeWidth="2.2" strokeLinecap="round" />
                <path data-tendril-b={t.rid} d={t.b} fill="none" stroke="#9B8DFF" strokeWidth="2.2" strokeLinecap="round" />
              </g>
              <g data-snip={t.rid} style={{ opacity: 0 }} transform={`translate(${t.mid[0]} ${t.mid[1]})`}>
                <g><line x1="-12" y1="-12" x2="12" y2="12" stroke="#EDE9E0" strokeWidth="2" /><line x1="-12" y1="12" x2="12" y2="-12" stroke="#EDE9E0" strokeWidth="2" /></g>
              </g>
            </g>
          ))}
        </svg>

        <div className="relative grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_minmax(0,1fr)]">
          <Column title="paths that recreate data" empty="no active flow or open restore">
            {flows.map((x) => <TargetCard key={x.rid} x={x} />)}
          </Column>
          <Column title="records" empty="no record changes needed" col="records">
            {records.map((x) => <TargetCard key={x.rid} x={x} />)}
          </Column>
          <Column title="retained by policy · untouched" empty="no retained record">
            {retained.map((r) => (
              <div key={r.rid} data-retained={r.rid} className="relative rounded-xl border border-proven/50 bg-ink/70 p-4">
                <div data-shield aria-hidden className="pointer-events-none absolute -inset-1 rounded-xl border border-proven/50 shadow-[0_0_28px_-4px_rgba(124,255,178,.55)]" style={{ opacity: 0 }} />
                <p className="mono text-xs text-muted">{r.sys}</p>
                <p className="mono text-sm text-bone">{r.rid}</p>
                <p className="mt-2 flex items-center gap-2 text-xs text-proven"><span aria-hidden>⛨</span> shielded · VERIFY_RECORD_PRESENT</p>
              </div>
            ))}
          </Column>
        </div>

        <div className="relative mt-8 border-t border-line pt-5">
          <p className="mono text-xs uppercase tracking-[0.25em] text-muted">checks that must pass afterwards · {checks.length}</p>
          <ol className="mt-3 grid gap-2 md:grid-cols-2">
            {checks.map(([s, i]) => (
              <li key={i} data-check
                className="flex items-center gap-3 rounded-lg border border-line bg-ink/40 px-3 py-2 opacity-40">
                <span data-tick className="grid h-5 w-5 place-items-center rounded-full border border-proven text-xs text-proven" aria-hidden>✓</span>
                <span className="text-sm text-bone">{OP_VERB[s[1]]}</span>
                <span className="mono ml-auto truncate text-xs text-muted">{s[3]}</span>
              </li>
            ))}
          </ol>
        </div>

        {/* the seal lands in its own slot below the checks, so the end state never covers a check */}
        <div aria-hidden className="pointer-events-none relative mt-6 grid h-44 place-items-center">
          <div className="absolute h-40 w-40 rounded-full border border-dashed border-line" />
          <div data-pulse className="absolute h-56 w-56 rounded-full border-2 border-proven" style={{ opacity: 0 }} />
          <div data-final style={{ opacity: 0 }} className="relative grid h-40 w-40 place-items-center rounded-full border-[3px] border-proven bg-ink/80 text-center text-proven shadow-[0_0_60px_-4px_rgba(124,255,178,.7)]">
            <span className="flex flex-col items-center gap-2">
              <span className="display text-4xl italic leading-none">Exorcised</span>
              <span className="mono text-xs uppercase tracking-[0.22em]">plan proven by<br />simulation</span>
            </span>
          </div>
        </div>
        {!lite && <canvas ref={dustCanvas} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />}
      </div>
      <p className="mono mt-3 text-xs text-muted">
        A visualisation of the plan in output.csv applied to the reconstructed state. Nothing in any system is changed.
      </p>
    </section>
  );
}

function Column({ title, empty, children, col }: { title: string; empty: string; children: React.ReactNode; col?: string }) {
  const has = Array.isArray(children) ? children.length > 0 : !!children;
  return (
    <div data-col={col}>
      <p className="mono mb-3 text-xs uppercase tracking-[0.25em] text-muted">{title}</p>
      <div className="space-y-3">{has ? children : <p className="text-xs text-muted">{empty}</p>}</div>
    </div>
  );
}

function TargetCard({ x }: { x: Target }) {
  const flow = x.op === "DISABLE_DATA_FLOW";
  const tone = flow ? "border-flow/60" : "border-haunted/60";
  return (
    <div data-x={x.rid} className={`relative rounded-xl border ${tone} bg-ink/60 p-4`}>
      <div data-heat aria-hidden className={`pointer-events-none absolute inset-0 rounded-xl ${flow ? "shadow-[0_0_30px_-8px_rgba(155,141,255,.7)]" : "shadow-[0_0_30px_-8px_rgba(255,107,71,.7)]"}`} />
      <p className="mono truncate text-xs text-muted">{x.sys}{x.cat ? ` · ${x.cat}` : ""}</p>
      <div className="mt-0.5 flex items-center justify-between gap-2">
        <p className="mono min-w-0 truncate text-sm text-bone">{x.rid}</p>
        <div className="relative h-6 shrink-0">
          <span data-before className={`chip ${flow ? "tone-flow" : "tone-haunted"}`}>{x.before}</span>
          <span data-after className="chip tone-proven absolute right-0 top-0" style={{ opacity: 0 }}>{x.after}</span>
        </div>
      </div>
      <p className="mt-1 text-xs text-muted">{OP_VERB[x.op]} · <span className="mono">{x.op}</span></p>
      <div data-body className="mt-3 space-y-1.5">
        {(x.op === "REDACT_RECORD" || x.op === "ANONYMIZE_RECORD") && (x.fields.length ? x.fields : ["identifiers"]).map((f) => (
          <div key={f} className="relative flex items-center justify-between overflow-hidden rounded bg-white/[0.04] px-2 py-1">
            <span className="mono text-xs text-muted">{f}</span>
            <span className="mono text-xs text-bone" data-val="••••••••">••••••••</span>
            {x.op === "REDACT_RECORD" && <span data-bar aria-hidden className="absolute inset-y-0 left-0 w-full origin-left bg-black" style={{ transform: "scaleX(0)" }} />}
          </div>
        ))}
        {x.op === "DELETE_RECORD" && [0.9, 0.7, 0.8].map((w, i) => <div key={i} className="h-1.5 rounded bg-haunted/40" style={{ width: `${w * 100}%` }} />)}
        {x.op === "BLOCK_RESTORE" && <p className="mono pr-20 text-xs text-muted">restore path open · archive retained by policy</p>}
        {flow && <p className="mono text-xs text-flow">sync can recreate the subject's data</p>}
      </div>
      {x.op === "BLOCK_RESTORE" && (
        <div data-seal aria-hidden style={{ opacity: 0 }}
          className="absolute -bottom-6 -right-4 grid h-[84px] w-[84px] place-items-center rounded-full bg-[#8f1d1d] text-center shadow-[inset_0_-4px_8px_rgba(0,0,0,.45),0_6px_16px_rgba(0,0,0,.5)]">
          <span className="mono text-xs font-bold uppercase leading-tight tracking-widest text-[#ffd9c9]">sealed<br />no<br />restore</span>
        </div>
      )}
    </div>
  );
}
