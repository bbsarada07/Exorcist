# Interview notes

## The one-paragraph pitch
Deletion workflows report "Complete" while copies survive. The agent rebuilds the truth at `audit_at` from
evidence only: who the subject is (including old addresses and hashes), which records belong to them, what each
record looked like at the cut-off, what the policy requires, and what must happen next. Every verdict is backed by a
cited observation, every plan is proven by simulation, and every output row passes a strict validator.

## Read this first: three plain statements
1. **The 30-second-tick linking rule is a regularity learned from unlabeled worker logs.** The deletion worker's
   actions for one case sit at fixed residues (10 s / 21 s modulo 30 s) after that case's account delete. The engine
   re-learns this on every run from pairs whose account link is already proven by identifiers (361 pairs, 100% fit),
   and uses it **only** to link cases to identifier-free resources (accounts deleted without a trace, anonymised
   analytics). It never decides a status and never overrides evidence. Every guessed link is flagged in
   `code/out/review_queue.json` — **41 ambiguous account links and 16 analytics ties** on the final run — with its
   margin, and the case confidence score is lowered for each.
2. **The held-out check covered tunable parameters only** (cost constants and the citation rule: 567 configurations,
   tune on 16 samples / test on 16, 5 splits × 2 directions, gap 0.000). The structural rules (step conventions,
   category signals, linking design) were derived while inspecting the samples, so the **sample score
   (F1 0.992, status 100%) is an upper bound, not a generalisation estimate**.
3. **Known risk: 10 hand-built multimodal cases have no account step** — case_33, case_35, case_39, case_45, case_50,
   case_52, case_53, case_55, case_61, case_63. No participant file or worker event names an account for these
   subjects; the hand-built sample cases did have one, so the hidden answers may expect a step our evidence cannot
   support. All ten are in the review queue.

## Key design decisions (and why)
1. **Deterministic first.** Verdicts must be reproducible and defensible to an auditor; rules + evidence explain all
   reachable sample steps. The optional LLM hook is only a fallback for low-confidence intent and was never consulted
   (0 tokens).
2. **One fact model for ten formats.** SQL (typed inventories, primary/replica dumps), JSON bundles, service exports,
   flat lookups, six log syntaxes (trace-id joins), PDFs, screenshots → `Fact(evidence_id, observed_at, cite_at,
   resource, location, exists, exposed, keys)`.
3. **Fact time ≠ file time.** State uses each observation's own time; citations only use files captured ≤ `audit_at`.
4. **Claims vs evidence.** Workflow statuses and operation *results* never prove state; the *operation type* the
   worker attempted is used as a category signal (matched gold on every sample resource that had one).
5. **Evidence links first, then a global assignment.** Exact identifier matches (never names, never fuzzy; decoys
   logged). Identifier-free records: Hungarian assignment over all cases using timing, claim/result agreement,
   evidence-file co-occurrence and the learned worker clock; each link stores mode and margin.
6. **Citation rule chosen by experiment:** 7 rules scored on 75 cited gold steps; the winner reproduces all 72
   reachable ones.
7. **Content beats catalog**, with a fail-safe when the contested record is the subject's only evidence (1 case,
   case_63: we refuse to certify completion and flag it).
8. **Proof by simulation + strict validator** — failures are bugs, never silently patched outputs.

## Trade-offs and limits
- Honest ceiling: 3 sample gold steps reference resources that occur in no participant file → max recall 0.9845
  (reached). No id-derivation convention exists, so nothing is hardcoded.
- Genuine ambiguity remains where several cases share `reported_at`, claim and clock phase (41 account / 16 analytics
  links); a slot-aware mod-60 phase could split some ties but only 4 unlabeled examples support it, so not built.
- Snapshot omissions are weak evidence of absence; they decide existence only when nothing explicit exists or the
  snapshot is one of the case's own files.
- OCR depends on local Tesseract (misreads within edit distance 2 tolerated for linking, never for decoys).
- Sample score is an upper bound (statement 2).

## Failures found during development (full table in evaluation_report.md §12)
Account-order tie-break was noise (removed after a label-free test); an OCR misread caused a false conflict; an
over-broad exclusion blocked a correct account; the validator caught 4 contract violations on the first full run; a
custom case exposed reused-email contamination (validity windows); a test fixture collided with a real id; the lint
caught an id in a comment; identifier-free coin flips were resolved by the learned worker clock.

## Likely judge questions — with answers
- **How do you know a record belongs to the user?** An exact current/historical email, hash, phone or user_id in the
  record or in the lookup that produced it (trace-id joined), inside the case's scope window; reused addresses go to
  whoever held them at observation time. Otherwise only via the worker chain, flagged with a margin.
- **Isn't the 30-second clock overfitting to the generator?** It is learned from unlabeled logs each run (no gold),
  only links identifier-free resources, is disabled automatically if no period shows structure, and every guessed
  link is in the review queue. It fixed the reachable sample errors without changing any case status.
- **Why trust your 0.992 F1?** Don't treat it as a forecast: it is an upper bound because structural rules came from
  the samples. Independent signals: 12/12 custom scenarios, metamorphic relations at 100% on all 550 requests, 0
  simulation failures, validator clean.
- **Why not trust "SUCCESS"?** 64% of COMPLETE claims in the evaluation set are contradicted by evidence.
- **What happens with no account evidence?** We do not invent an account id; the 10 affected cases are listed as a
  known risk and queued for review.
- **Why no LLM?** Nothing in the data needed one; an LLM would add cost and non-determinism. The hook exists, is
  cached, temperature 0, and can never override evidence.
- **How is hardcoding prevented?** A unit test scans engine code for id literals, dataset emails and evidence file
  names, and asserts the engine never reads `sample_output.csv`.
- **What would you do with more time?** Slot-aware worker clock for the remaining ties, a VLM cross-check of OCR on
  screenshots, and the forensic UI on top of the sidecars.

## Evidence pass: the strongest 5 findings
Each finding below has a full card in `code/out/findings_evidence.jsonl`, and each case can be replayed live with
`python code/main.py investigate --case <id>`. How they were chosen:
- the case was falsely claimed COMPLETE;
- the deletion worker itself reported SUCCESS on the very resource the evidence still shows;
- the card confidence is the highest available;
- there is one per ghost type. Replica drift has no such worker contradiction, so its slot goes to the
  highest-confidence drift ghost whose drift file was captured before the audit cut.

| Case | Ghost | Resource | The claim | The evidence at audit_at | Card confidence |
|---|---|---|---|---|---|
| case_115 | leftover record | `search_service/search_4417` | activity_3073 DELETE_RECORD SUCCESS (08-02) | evidence_88 (fact 08-22): record still exists, current email exact | 0.99 |
| case_116 | active sync | `integration_service/data_flow_6699` | activity_3029 CHECK_DATA_FLOW SUCCESS (07-30) | evidence_88 (fact 08-22): connector enabled, carries current email | 0.99 |
| case_123 | restore risk | `backup_service/backup_8742` | activity_3170 CHECK_RESTORE_ACCESS SUCCESS (08-08) | evidence_87 (fact 08-17): restore path open | 0.99 |
| case_487 | exposed PII in a retained record | `analytics_platform/analytics_7818` | activity_452 ANONYMIZE_RECORD SUCCESS (02-06) | evidence_64 (fact 02-18): analytics profile still holds the current email | 0.99 |
| case_307 | replica drift | `account_service/account_585` | workflow reported COMPLETE (05-07) | evidence_29 (fact 05-19): gone from primary and replica_eu_west, alive in replica_ap_south with email, name, phone and user_id | 0.98 |

## Error analysis summary (full text: docs/ERROR_ANALYSIS.md)
- **Samples:** 32/32 statuses, 190/193 steps, 0 false-positive steps. The 3 misses are resources that occur in no
  participant file, so we refuse to derive ids from case numbers.
- **Where evaluation answers can be wrong:** 41 ambiguous account links (20 with negative margin, i.e. close to coin
  flips), 16 identifier-free analytics ties and 10 cases with no account evidence. These are 64 queued cases in all.
- **Why that cannot flip a status:** all 722 evaluation findings rest on identifier evidence (721 direct, 1
  contested). Chain links only produce verifications: 380 of 3,257 steps, 57 of them flagged. A wrong guess costs a
  step, not a status. A link we never made could still hide a violation, and that we cannot measure.
- **Calibration:** on the samples the finding confidences are slightly under-confident (mean 0.98, accuracy 1.0),
  but with zero wrong samples to learn from, "0.6 means 60 %" is unproven. The weights are documented heuristics.
- **What we would do next:** label the 57 ambiguous links (the cheapest way to get negative examples), then fit
  the confidence model on them.
