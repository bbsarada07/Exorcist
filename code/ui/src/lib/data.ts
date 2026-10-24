// Typed access to the static export in public/data (see docs/UI_DATA_NOTES.md). Nothing here computes verdicts.
export type Status = "COMPLETE" | "INCOMPLETE" | "NOT_APPLICABLE";
export type Phase = "FINDING" | "REMEDIATION" | "VERIFICATION";

export interface CaseSummary {
  id: string;
  s: Status;            // reconstructed status (output.csv)
  r: string;            // legacy reported_status
  f: number;            // FINDING steps
  n: number;            // total steps
  q: 0 | 1;             // in review_queue.json
  c: number | null;     // confidence
  v: string | null;     // lie_report verdict
  sys: string[];        // systems touched by the steps
}

export interface Summary {
  totals: { cases: number; status: Record<Status, number> };
  lie: {
    headline: { reported_COMPLETE_but_incomplete_pct: number; reported_COMPLETE_cases: number; status_claim_wrong_pct: number };
    claim_vs_truth: Record<string, Record<string, number>>;
    failure_modes: Record<string, { cases: number; pct_of_incomplete: number }>;
    deletion_cases: number;
  };
  review: { count: number; threshold: number; rule: string; ambiguous_account_links: number;
            ambiguous_identifier_free_ties: number; no_account_evidence_cases: string[] };
  risk_note: string;
  decoys: { encountered: number; emitted: number; avoided: number };
  cases: CaseSummary[];
}

export type StepRow = [Phase, string, string, string, string, string]; // phase, op, system, resource, state, evidence
export type Why = [string, string, string, string, string, string | null, string[]] | null;

export interface CaseDetail {
  id: string;
  status: Status;
  reported: string;
  requested_at: string;
  reported_at: string;
  audit_at: string;
  email: string | null;
  user_id: string | null;
  identity_match: string;
  intent: string;
  request_text: string;
  confidence: number | null;
  confidence_reasons: string[];
  review: { reasons: string[]; links: { resource_id: string; kind: string; margin: number | null }[] } | null;
  verdict: string | null;
  failure_modes: string[];
  steps: StepRow[];
  why: Why[];
  assessed: number;
  lineage: { from: string; via: string; kind: string; to: string; at: string | null }[];
  risk: { score: number; systems: string[]; flows: number; restore: boolean } | null;
  conflicts: { type: string; r: string; trusted: string; why: string }[];
}

const base = `${import.meta.env.BASE_URL}data/`;
let summaryP: Promise<Summary> | null = null;
let detailsP: Promise<Record<string, CaseDetail>> | null = null;

export function loadSummary(): Promise<Summary> {
  return (summaryP ??= fetch(`${base}summary.json`).then((r) => r.json()));
}

export function loadDetails(): Promise<Record<string, CaseDetail>> {
  return (detailsP ??= fetch(`${base}details.json`).then((r) => r.json()));
}
