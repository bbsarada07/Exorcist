# Interview notes

## The one-paragraph pitch
Deletion workflows report "Complete" while copies survive. The agent rebuilds the truth at `audit_at` from
evidence only: who the subject is (including old addresses and hashes), which records belong to them, what each
record looked like at the cut-off, what the policy requires, and what must happen next. Every verdict is backed by a
cited observation, every plan is proven by simulation, and every output row passes a strict validator.

## Key design decisions (and why)
1. **Deterministic first.** Verdicts must be reproducible and defensible to an auditor; the data is structured enough
   that rules + evidence explain all 32 samples. An LLM would add cost and non-determinism without accuracy. The LLM
   hook exists only for low-confidence intent and is never consulted on this dataset (0 tokens).
2. **One fact model for ten formats.** SQL, JSON bundles, service exports, flat lookups, six log syntaxes, PDFs,
   screenshots all become `Fact(evidence_id, observed_at, cite_at, resource, location, exists, exposed, keys)`.
   Downstream agents never care about formats.
3. **Fact time ≠ file time.** A file manifested after the audit can contain observations from before it (gold uses
   them). State uses observation time; citations only use files captured ≤ `audit_at`.
4. **Claims vs evidence.** Workflow statuses and operation *results* are claims and never prove state. But the
   *operation type* the worker attempted is a reliable signal of the policy category (it matched gold on every sample
   resource), e.g. an analytics record the worker tried to DELETE is a secondary identifier, not an analytics profile.
5. **Evidence links first, then a global assignment.** Identifier matches are exact (decoys are near-misses; names
   never link). Identifier-free records (deleted accounts, anonymised analytics) are linked through the deletion
   worker's chain with a Hungarian assignment over all cases jointly, using measured timing (account delete ≈ 1 h
   before `reported_at`), claim/result agreement and evidence-file co-occurrence. Each link records mode and margin.
6. **Citation rule chosen by experiment**, not intuition: 7 candidate rules scored on all 75 cited gold steps; the
   winner reproduces all 72 reachable ones.
7. **Content beats catalog**, with a fail-safe: a catalog row is a claim, so a record whose content names someone
   else is not attributed — unless it is the subject's only evidence, in which case we refuse to certify completion
   and flag the case (conflict ledger + review queue).
8. **Proof by simulation + strict validator.** The plan is applied to the reconstructed state; any verification that
   would not pass, any retained record that would be touched, or any record change before a flow is disabled is a bug.

## Trade-offs / known limits
- 3 sample gold steps reference resources that appear in no participant file → honest recall ceiling 0.9845.
- When several cases share `reported_at` and claimed result, identifier-free records are inherently ambiguous
  (measured ~50% order consistency). We do not invent a tie-breaker; we flag low margin in the review queue.
- Snapshot omissions are weak evidence of absence (inventories list only relevant rows); they decide existence only
  when nothing explicit exists or when the snapshot is one of the case's own files.
- OCR depends on Tesseract; misreads within edit distance 2 are tolerated for linking, never for decoys.

## Failures found during development (see evaluation_report.md §12)
Account-order tie-break was noise (removed after a label-free test); an OCR misread caused a false conflict;
an over-broad exclusion blocked a correct account; the validator caught 4 contract violations on the first full run;
a custom case exposed reused-email contamination (fixed with validity windows); a test fixture collided with a real
id; the lint caught an id in a comment.

## Likely questions
- *How do you know a record belongs to the user?* Exact current/historical email, hash, phone or user_id in the
  record or in the lookup that produced it (trace-id joined), inside the case's scope window; reused addresses use
  the owner at observation time. Otherwise only through the worker chain, with a recorded margin.
- *Why not trust "SUCCESS"?* Because 64% of COMPLETE claims in the evaluation set are contradicted by evidence.
- *What if the grader's convention differs?* Conventions are isolated (`case_sort_key`, citation rule, planner
  rules) and each is documented with the evidence that chose it.
- *How is hardcoding prevented?* A unit test scans engine code for id literals, dataset emails and evidence file
  names, and checks the engine never reads `sample_output.csv`.
