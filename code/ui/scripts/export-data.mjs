// npm run export-data
// Converts engine outputs (code/out/*, <repo>/output.csv) into small static JSON under public/data/.
// Read-only with respect to the engine: it never writes outside code/ui/public/data.
// Privacy: subject emails are masked (k.r••@••••.com style) and raw identifier lists are dropped.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const UI = join(here, "..");
const OUT = join(UI, "..", "out");
const REPO = join(UI, "..", "..");
const DEST = join(UI, "public", "data");

const need = (p) => {
  if (!existsSync(p)) throw new Error(`missing ${p} — run "python code/main.py" first`);
  return readFileSync(p, "utf8");
};
const json = (f) => JSON.parse(need(join(OUT, f)));
const jsonl = (f) => need(join(OUT, f)).split("\n").filter(Boolean).map((l) => JSON.parse(l));

// RFC-4180 CSV parser (quoted fields, "" escapes)
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') q = false;
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.length > 1);
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

function maskEmail(e) {
  if (!e || !e.includes("@")) return null;
  const [local, domain] = e.trim().toLowerCase().split("@");
  const tld = domain.slice(domain.lastIndexOf("."));
  return `${local.slice(0, Math.min(3, local.length))}••@••••${tld}`;
}

const uniqTail = (arr, n) => {
  const seen = new Set(), out = [];
  for (let i = arr.length - 1; i >= 0 && out.length < n; i--) if (!seen.has(arr[i])) { seen.add(arr[i]); out.unshift(arr[i]); }
  return out;
};

const output = parseCsv(need(join(REPO, "output.csv")));
const cases = Object.fromEntries(json("cases.json").map((c) => [c.case_id, c]));
const lie = json("lie_report.json");
const lieBy = Object.fromEntries(lie.cases.map((c) => [c.case_id, c]));
const lineage = json("lineage.json");
const queue = json("review_queue.json");
const queueBy = Object.fromEntries(queue.cases.map((c) => [c.case_id, c]));
const risk = json("risk_scores.json");
const riskBy = Object.fromEntries(risk.ranking.map((r) => [r.case_id, r]));
const conf = json("confidence.json");
const decoys = json("decoys.json");
const conflicts = jsonl("conflicts.jsonl");
const trace = jsonl("decision_trace.jsonl");
const traceBy = {};
for (const t of trace) (traceBy[t.case_id] ??= {})[t.step_no] = t;
const confBy = {};
for (const c of conflicts) (confBy[c.case_id] ??= []).push(c);

const statusCount = {};
const summaryCases = [];
const details = {};
for (const row of output) {
  const id = row.case_id;
  const steps = JSON.parse(row.steps_json);
  const c = cases[id];
  const l = lieBy[id];
  const q = queueBy[id];
  statusCount[row.deletion_status] = (statusCount[row.deletion_status] ?? 0) + 1;
  summaryCases.push({
    id,
    s: row.deletion_status,
    r: c.reported_status,
    f: steps.filter((x) => x.phase === "FINDING").length,
    n: steps.length,
    q: q ? 1 : 0,
    c: conf[id]?.confidence ?? null,
    v: l?.verdict ?? null,
    sys: [...new Set(steps.map((x) => x.system_id))],
  });
  details[id] = {
    id,
    status: row.deletion_status,
    reported: c.reported_status,
    requested_at: c.requested_at,
    reported_at: c.reported_at,
    audit_at: c.audit_at,
    email: maskEmail(c.email),
    user_id: c.user_id,
    identity_match: c.identity_match,
    intent: c.intent,
    request_text: c.request_text,
    confidence: conf[id]?.confidence ?? null,
    confidence_reasons: conf[id]?.reasons ?? [],
    review: q ? { reasons: q.reasons, links: q.ambiguous_links } : null,
    verdict: l?.verdict ?? null,
    failure_modes: l?.failure_modes ?? [],
    steps: steps.map((x) => [x.phase, x.operation, x.system_id, x.resource_id, x.state, x.evidence_id]),
    // positional: [rule_id, category, category_source, reason, agent, link_mode, last evidence ids of the chain]
    why: steps.map((x) => {
      const t = traceBy[id]?.[x.step_no];
      return t ? [t.rule_id, t.category, t.category_source, t.reason, t.agent, t.link_mode,
                  uniqTail(t.evidence_chain ?? [], 4)] : null;
    }),
    assessed: (c.assessments ?? []).length,
    lineage: lineage[id]?.edges ?? [],
    risk: riskBy[id] ? { score: riskBy[id].score, systems: riskBy[id].exposed_systems, flows: riskBy[id].active_flows,
                         restore: riskBy[id].restore_path } : null,
    conflicts: (confBy[id] ?? []).map((x) => ({ type: x.type, r: x.resource_id, trusted: x.trusted, why: x.why })),
  };
}

const summary = {
  generated_from: ["output.csv", "code/out/*"],
  totals: { cases: output.length, status: statusCount },
  lie: { headline: lie.headline, claim_vs_truth: lie.claim_vs_truth, failure_modes: lie.failure_modes,
         deletion_cases: lie.deletion_cases },
  review: { count: queue.cases.length, threshold: queue.threshold, rule: queue.rule,
            ambiguous_account_links: queue.ambiguous_account_links,
            ambiguous_identifier_free_ties: queue.ambiguous_identifier_free_ties,
            no_account_evidence_cases: queue.no_account_evidence_cases },
  risk_note: risk.note,
  decoys: { encountered: decoys.near_miss_decoys_encountered, emitted: decoys.decoys_emitted_as_subject_records,
            avoided: decoys.false_exposures_avoided },
  cases: summaryCases,
};

mkdirSync(DEST, { recursive: true });
writeFileSync(join(DEST, "summary.json"), JSON.stringify(summary));
writeFileSync(join(DEST, "details.json"), JSON.stringify(details));
const kb = (s) => (Buffer.byteLength(s) / 1024).toFixed(0);
console.log(`summary.json ${kb(JSON.stringify(summary))} KB, details.json ${kb(JSON.stringify(details))} KB, ${output.length} cases`);
