# CONVENTIONS — inferred from samples where the spec is silent

Each convention lists the evidence it was inferred from. "Open" items are decided provisionally and will be
re-checked against the evaluation harness.

## Output format
1. Header `case_id,deletion_status,steps_json`; JSON serialised compactly with a fixed key order
   (`step_no, phase, system_id, resource_id, operation, state, evidence_id`) — grader ignores key order anyway.
2. **Row order = numeric case order** (case_33, case_34, … case_550), implemented once in
   `audit.util.case_sort_key` (swappable). Evidence checked (Decision 1):
   - `dataset/output.csv` template: header only, 0 data rows → no ordering information;
   - `sample_output.csv`: case_01 … case_32, zero-padded, so numeric and lexicographic orders coincide → no information;
   - `deletion_requests.csv` (the only file with unpadded ids) is in numeric order case_33 … case_550.
   → We follow the input file's numeric order. The validator asserts whichever order `case_sort_key` defines.
3. NOT_APPLICABLE → `[]` exactly.

## Step semantics
4. Within a phase: operation table order → `system_id` → `resource_id`, plain string comparison
   (`analytics_platform` < `support_platform`; `account_410` sorts as a string).
5. COMPLETE: verification only; cite per resource the latest file with manifest `captured_at ≤ audit_at`
   that observes the resource's compliant state.
6. INCOMPLETE verification = account ABSENT + all retained records PRESENT + end state of each remediated item.
   Already-compliant non-retained resources are not re-verified (samples 05–32).
7. A finding cites the latest pre-audit file showing the violation.
8. The account always appears (VERIFY_RECORD_ABSENT) for a deletion case, even with no account finding.
9. Remediation order is the spec order (disable flows → block restores → delete → redact → anonymize), which
   already satisfies "disable/block before changing dependent records".

## Evidence and time
10. A fact's time is its own observation time (log line timestamp, inner snapshot `captured_at`, `observed_at`),
    not the file's manifest time. Facts after `audit_at` are ignored.
11. Citations only use files whose manifest `captured_at ≤ audit_at`.
12. **Citation rule = latest pre-audit proof, explicit observations before snapshot omissions, files before
    activity rows** (`planner.cite_latest_pre_audit`). Chosen empirically by `evaluation/citation_study.py`
    (Decision 2), scoring every candidate rule on all 75 cited gold steps:
    latest_pre_audit_explicit_first 72/75 (= every reachable step) · latest_pre_audit 67 ·
    latest_file_manifest_time 67 · prefer_snapshot_types 66 · earliest_pre_audit 54 · nearest_reported_at 54 ·
    first_after_delete_activity 54. No tie. The 3 misses are resources absent from all participant data.
    The case_04 evidence_54-vs-evidence_90 question is moot: `account_004` occurs in no participant file.
13. **No id-derivation convention** (Decision 3). Only the 8 handcrafted sample accounts follow
    `account_00N ↔ user_0N`; the other 24 sample accounts and all 25 sample audit records have no arithmetic
    relation to user or case number. Therefore `account_004`, `audit_record_6645`, `audit_record_5569`
    stay unreachable (honest ceiling), nothing is hardcoded.

## Identity
13. Normalise emails with `strip().lower()`; hash = sha256 of the normalised email.
14. A user's identifiers = current email/phone/hash/name + every historical value from the audit log.
    Exact matching only (decoys are near-misses). Names alone never link a record.
15. Catalog/link rows are claims; if record content shows a different person, the content wins.

## Intent
16. Deletion is authorised only if the text asks to delete/erase/close the account or personal data and does
    not negate it ("not asking for deletion", "don't delete", "without removing", "… only").
