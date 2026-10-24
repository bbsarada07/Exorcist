# DEV_LOG

## 2026-10-24 — Phase 0 recon
* Cloned starter repo; `code/main.py` and `code/evaluation/main.py` were empty stubs.
* Profiled every CSV and evidence family; findings in `DATA_NOTES.md`, rules in `CONVENTIONS.md`.

## 2026-10-24 — Phase 1 build (commits in order)
1. **Parsers → fact table** (3,047 facts / 369 coverage snapshots / 4,011 activities, 5.7 s cold, ~2.5 s warm).
   Fix: an alias equal to a person key (`user_<n>`) matched a table row in a PDF → only title lines count.
2. **IdentityAgent**: 550/550 requests resolve (447 current, 103 historical); hashes derived for every email.
3. **IntentAgent**: first version missed 5 free-form sample follow-ups and read "download your data" as an export
   request → broadened cues; 540 deletion / 10 non-deletion, all high confidence.
4. **LinkerAgent**: direct identifier links alone gave 3 FP (all multi-case subjects) / 28 FN on samples → scope
   window per subject + worker-chain Hungarian assignment.
   - Account-order tie-break term: label-free test showed ~50% consistency → removed; co-occurrence bonus added
     (TP 100 → 104, FP 7 → 5).
   - OCR misread `outiook.com` produced a false conflict → OCR tolerance (edit distance ≤ 2).
   - Global "identifier anywhere" exclusion blocked `account_3866` (only post-audit identifying snapshot) →
     per-case foreign-owner check (TP 105).
5. **Timeline / Policy / Planner / Simulator / Validator / pipeline**: samples status 1.0, step F1 0.979,
   evidence_id 1.0 on aligned steps.
6. **Citation study (Decision 2)**: latest-pre-audit-explicit-first reproduces 72/72 reachable citations.
7. **First full run**: validator rejected 4 rows → name exposure in observations, open restore paths for archives
   without a blocked flag, case-file omissions count as explicit, contested-sole-evidence fail-safe. Validation passes.
8. **Custom cases**: 11/12 first run; reused-email contamination → `IdentityAgent.belongs_to` (validity windows) → 12/12.
9. **Metamorphic**: R1–R4 100% first run; R5 39/40 due to a fixture id colliding with a real decoy `user_id` →
   disjoint synthetic id space → 40/40. Also: sync/restore jobs that ran now evidence an active path.
10. **Tests**: hardcode lint caught a dataset id in a comment → fixed; determinism across hash seeds passes.

## 2026-10-24 — Phase 1 review
* Mismatch audit: 3 ceiling (no participant evidence), 3 linker errors on identifier-free records.
* Found the worker clock (period 30 s, residues 10/21 s relative to the case's account delete; learned from 361
  unlabeled pinned pairs, 100% coverage). Replaces the 390/449 s block-gap observation (13 and 15 ticks).
  Samples: TP 187 → 190, FP 2 → 0, FN 6 → 3 (= ceiling), F1 0.979 → 0.992; 90 eval rows changed, 0 status changes.
* Holdout (tune on 16 / test on 16, 5 seeds × 2 directions, 567 configs): mean gap 0.000, max 0.0095; tuned
  configs always equal the shipped defaults (13–39 configs tie for best).
* Lowest-confidence review: all 41 low-margin account links have 2–7 candidates that fit claim and clock equally
  (genuine ambiguity); 16 identifier-free analytics links remain clock-ambiguous at ±1 s tolerance. A slot-aware
  mod-60 phase would separate some, but only 4 unlabeled first-slot points exist → not implemented (documented).
* Distribution: COMPLETE 29.5% / INCOMPLETE 68.5% / NOT_APPLICABLE 10 (= 10 CLASSIFY_REQUEST events); mean steps
  3.44 / 7.69 vs samples 3.40 / 7.23. Flag: 10 handcrafted multimodal cases have no account evidence at all.

## Known ceiling
`account_004` (case_04), `audit_record_6645` (case_18), `audit_record_5569` (case_20) occur in no participant
file; no id-derivation convention exists (Decision 3). Identifier-free records shared by several cases with the
same `reported_at` and claim remain coin flips; flagged in `review_queue.json`.
