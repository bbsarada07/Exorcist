import type { Status } from "../lib/data";
import { REPORTED_LABEL, STATUS_LABEL, STATUS_TONE } from "../lib/labels";

export function StatusChip({ status, className = "" }: { status: Status; className?: string }) {
  return <span className={`chip tone-${STATUS_TONE[status]} ${className}`}>{STATUS_LABEL[status]} · {status}</span>;
}

export function ReportedChip({ reported }: { reported: string }) {
  return <span className="chip tone-bone">claimed · {REPORTED_LABEL[reported] ?? reported}</span>;
}

export function Chip({ tone = "bone", children, title }: { tone?: "haunted" | "proven" | "na" | "flow" | "bone"; children: React.ReactNode; title?: string }) {
  return <span className={`chip tone-${tone}`} title={title}>{children}</span>;
}

export function ReviewBadge({ reasons }: { reasons: string[] }) {
  return (
    <span className="chip tone-flow" title={reasons.join("\n")}>
      needs review · {reasons[0] ?? "flagged"}
    </span>
  );
}

export function ConfidenceMeter({ value }: { value: number | null }) {
  if (value === null) return null;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2" aria-label={`confidence ${pct}%`}>
      <span className="mono text-xs uppercase tracking-widest text-muted">confidence</span>
      <div className="relative h-1.5 w-28 overflow-hidden rounded-full bg-line">
        <div className="absolute inset-y-0 left-0 origin-left rounded-full bg-bone" style={{ width: "100%", transform: `scaleX(${value})` }} />
      </div>
      <span className="mono text-xs text-bone">{value.toFixed(2)}</span>
    </div>
  );
}
