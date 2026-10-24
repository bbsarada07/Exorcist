# UI data notes — every field the UI shows and where it comes from

The UI never computes verdicts. `npm run export-data` (code/ui/scripts/export-data.mjs) reads the engine outputs
read-only and writes `code/ui/public/data/summary.json` (94 KB, 5 KB gz) and `details.json` (1.2 MB, 88 KB gz).

## Sources inspected (real schemas)

| Source | Shape (real) | Used for |
|---|---|---|
| `output.csv` (repo root) | `case_id, deletion_status, steps_json[step_no, phase, system_id, resource_id, operation, state, evidence_id]` | **status of every tombstone / case**, the runbook steps (source of truth) |
| `code/out/decision_trace.jsonl` | per emitted step: `case_id, step_no, operation, resource_id, evidence_id, link_mode, rule_id, category, category_source, verdict, reason, agent, evidence_chain[]` | "why this step exists" panel |
| `code/out/lie_report.json` | `deletion_cases, headline{reported_COMPLETE_but_incomplete_pct, reported_COMPLETE_cases, status_claim_wrong_pct}, claim_vs_truth, failure_modes{mode:{cases,pct_of_incomplete}}, cases[{case_id, reported_status, reconstructed, verdict, failure_modes[]}]` | hero counter "legacy claims wrong %", Reported-vs-Reality verdict + failure modes |
| `code/out/lineage.json` | `{case_id: {nodes[{id}], edges[{from, via, kind, to, at}]}}` (INCOMPLETE cases) | exorcism tendrils (which flow / restore feeds which record) |
| `code/out/review_queue.json` | `threshold, rule, no_account_evidence_cases[], ambiguous_account_links, ambiguous_identifier_free_ties, cases[{case_id, confidence, status, reasons[], ambiguous_links[{resource_id, kind, margin}]}]` (64 cases) | "needs review" badge + reason |
| `code/out/risk_scores.json` | `note, ranking[{case_id, score, exposed_systems[], active_flows, restore_path, sensitivity_sum}]` | risk chip, always labelled **heuristic** |
| `code/out/conflicts.jsonl` | `{case_id, type, resource_id, trusted, why, ...}` (205 rows) | conflict notes in the case view |
| `code/out/confidence.json` | `{case_id: {confidence, reasons[], ambiguous_links[]}}` | confidence meter |
| `code/out/cases.json` | per case: `email, user_id, identity_match, requested_at, reported_at, audit_at, reported_status, intent, request_text, assessments[]...` | request metadata; email is **masked** on export |
| `code/out/decoys.json` | `near_miss_decoys_encountered, decoys_emitted_as_subject_records, false_exposures_avoided` | hero footnote |
| `evaluation/evaluation_report.md`, `usage_report.md` | Markdown | not loaded at runtime; figures quoted in docs only (0 LLM tokens) |

## Exported fields

`summary.json`
- `totals.cases`, `totals.status{INCOMPLETE, COMPLETE, NOT_APPLICABLE}` ← counted from output.csv (hero counters)
- `lie.headline.*`, `lie.failure_modes`, `lie.claim_vs_truth` ← lie_report.json
- `review.*` ← review_queue.json (count, rule, ambiguous_account_links, ambiguous_identifier_free_ties, no-account list)
- `decoys.{encountered, emitted, avoided}` ← decoys.json; `risk_note` ← risk_scores.json
- `cases[]`: `id`, `s` status (output.csv), `r` reported_status (cases.json), `f` # FINDING steps, `n` # steps,
  `q` in review queue (0/1), `c` confidence, `v` lie verdict, `sys` systems touched by its steps

`details.json` (`{case_id: …}`)
- `status`, `steps[[phase, operation, system_id, resource_id, state, evidence_id]]` ← output.csv
- `reported, requested_at, reported_at, audit_at, user_id, identity_match, intent, request_text` ← cases.json
- `email` ← cases.json, masked to `abc••@••••.tld`
- `confidence, confidence_reasons` ← confidence.json; `review{reasons, links}` ← review_queue.json
- `verdict, failure_modes` ← lie_report.json
- `why[i] = [rule_id, category, category_source, reason, agent, link_mode, last 4 unique evidence ids]` ← decision_trace.jsonl (aligned to step i)
- `lineage` ← lineage.json edges; `risk{score, systems, flows, restore}` ← risk_scores.json; `conflicts[{type, r, trusted, why}]` ← conflicts.jsonl
- `assessed` (count of assessed resources) ← cases.json

## Design features adapted to the data (nothing invented)
- **Hero PII fragments**: generic masked patterns only (e.g. `k.r••@••••.com`, `••• •• 4417`); never dataset values.
- **Tombstone glow** = number of FINDING steps (`f`); **ring** = `q` (review queue). No per-case "severity" invented.
- **Exorcism animation** is driven only by the case's own REMEDIATION / VERIFICATION operations; tendrils are drawn
  for `DISABLE_DATA_FLOW` steps and labelled with lineage edges when they exist.
- **Retained shield** = `VERIFY_RECORD_PRESENT` steps (the policy RETAIN records).
- **Reported vs Reality** uses `reported` vs `status` and lie_report `verdict` / `failure_modes` verbatim (humanised labels only).
- **Risk** is shown only for INCOMPLETE cases (that is where risk_scores.json has rows) and always labelled "heuristic".
- Sample cases (case_01–32) are not in output.csv, so the graveyard shows exactly the 518 evaluation cases.
