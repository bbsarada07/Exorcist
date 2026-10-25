# Error analysis

Plain version first: on the 32 public samples the engine gets every case status right and misses 3 of 193 steps.
All 3 concern resources that appear in no participant file. That is a ceiling, not a bug we chose to leave. The
real uncertainty is elsewhere and the samples cannot measure it: about 1 in 9 evaluation steps rests on worker
timing rather than an identifier, and the confidence numbers have never been tested against a wrong answer,
because the samples contain none.

All numbers below come from the current code (`python code/main.py`, `python code/evaluation/main.py`,
`python code/evaluation/calibration.py`, `code/out/review_queue.json`).

## 1. Every sample miss, and why

| Case | Missing gold step | Why it is missed |
|---|---|---|
| case_04 | VERIFY_RECORD_ABSENT `account_service/account_004`, cites evidence_54 | `account_004` occurs in **no** participant file (0 matches in `dataset/` outside `sample_output.csv`), and no worker event names it. evidence_54 does not list it either: it proves absence only by omission. |
| case_18 | VERIFY_RECORD_PRESENT `security_service/audit_record_6645` | `audit_record_6645` occurs in no participant file. |
| case_20 | VERIFY_RECORD_PRESENT `security_service/audit_record_5569` | `audit_record_5569` occurs in no participant file. |

Only the 8 hand-built sample accounts follow an `account_00N ↔ user_0N` pattern; the other 24 sample accounts and
all 25 sample audit records have no arithmetic relation to the user or case number (CONVENTIONS.md #13). Emitting
these 3 steps would mean deriving ids from case numbers. That is a shortcut the rules forbid, and it would be
wrong for most of the data. So recall stays at 190 / 193 = 0.9845.

There are no false-positive steps on the samples (precision 1.0) and no status errors. Treat that as an
**upper bound**: the structural rules were derived while reading these same 32 cases (evaluation_report.md §1b).

## 2. Where the evaluation answers can actually be wrong

| Uncertainty | Count (518 evaluation cases) | What is guessed | What a wrong guess costs |
|---|---:|---|---|
| **Ambiguous account links** | 41 cases (26 COMPLETE, 15 INCOMPLETE) | Which deletion-worker account delete belongs to the case. No identifier ties any account to the subject, so the Hungarian assignment uses timing, claim/result agreement and the learned worker clock. "Ambiguous" means the runner-up in that row is within 0.3 cost. **20 of the 41 have a negative margin**: the global optimum gave this case a locally worse choice to make a neighbour fit. Those are close to coin flips. | One VERIFY_RECORD_ABSENT step with the wrong `resource_id`. |
| **Identifier-free analytics ties** | 16 cases (all COMPLETE) | Which anonymised analytics record (no identifier left, by design) the worker anonymised for this case. Several cases share a `reported_at` and claim, so the timing cost ties (margin < 0.05). | One VERIFY_RECORD_ANONYMIZED step on the wrong record, or a missing one. |
| **No account evidence** | 10 cases (9 INCOMPLETE, 1 COMPLETE) | Nothing is guessed: no file and no worker event names an account, so no account step is emitted. The hand-built samples always had one, so the hidden answers may expect a step the evidence cannot support. | Probably one missing VERIFY_RECORD_ABSENT step per case. |
| Contested catalog link | 1 case (case_63) | The catalog says a record is the subject's, but its content names someone else. It is kept only because it is the subject's only evidence (fail-safe: never certify a deletion from zero evidence). | One finding plus its plan could be wrong. Confidence 0.5, queued. |

**Why none of this flips a status.** Across all 518 cases, every one of the 722 evaluation findings rests on
identifier evidence (721 direct matches, 1 contested; see `code/out/findings_evidence.jsonl`). No finding rests on a
chain link alone. Chain links produce only verification steps: 380 of the 3,257 evaluation steps (11.7 %), of which
57 are the flagged ambiguous ones above. COMPLETE vs INCOMPLETE is decided by violations, and violations are all
identifier-backed. So a wrong guess costs steps, not a status.

The reverse risk remains: a link we failed to make can hide a violation. A record carrying none of the subject's
identifiers and touched by no worker event is invisible to us, and we cannot measure how often that happens.

## 3. What the system does when it is unsure

1. **Flags it.** Every ambiguous chain link, every no-account case and every case under 0.6 confidence goes to
   `code/out/review_queue.json` with the reason and the margin: 64 cases (40 COMPLETE, 24 INCOMPLETE).
2. **Lowers confidence.** Case confidence (`confidence.json`) and per-finding confidence (`findings_evidence.jsonl`)
   multiply in a factor for each weak link, with the factor written next to the number.
3. **Never invents.** No resource id is derived from a case number. A COMPLETE verification without a citable
   pre-audit file is dropped, not emitted with a made-up citation. Near-miss identifiers (decoys) are rejected by
   exact normalised matching (`decoys.json`), and content beats catalog claims (`conflicts.jsonl`).
4. **Never lets the review layer change the answer.** The queue, the confidence scores and the cards are sidecars.
   `output.csv` is byte-identical with or without them (the determinism test runs `--no-sidecars`).

## 4. Calibration: honest limits

`python code/evaluation/calibration.py`:

| Table | n | mean confidence | accuracy | ECE |
|---|---:|---:|---:|---:|
| A. finding cards (samples) | 41 | 0.980 | 1.000 | 0.020 |
| B. every emitted resource, match strength only | 108 | 0.954 | 1.000 | 0.046 |

Table B includes the 25 chain links (confidence 0.60–0.90), and all 25 are right on the samples. So the confidences
are, if anything, slightly **under**-confident on the samples. That proves less than it sounds: the samples
contain no wrong prediction, so the tables can show "not over-confident" but cannot show that 0.6 means 60 %.
The weights in `audit/evidence_cards.py` are documented heuristics, not fitted probabilities. With only these 32
labels, fitting them would be overfitting.

## 5. Other blunt weaknesses

- **The worker clock is a regularity of this dataset** (30 s period, 361/361 coverage on identifier-proven pairs).
  A real deletion worker would not tick so cleanly. The clock is learned per run and switches itself off when no
  period stands out, but a real system's identifier-free links would be much weaker than ours.
- **The citation rule was chosen on the samples** (latest pre-audit proof, explicit before omission). It reproduces
  every reachable sample citation. The held-out split (evaluation_report.md §7b) shows the tunable knobs are not
  overfit, but the rule's *shape* was picked after reading the gold answers.
- **Category inference leans on the worker's attempted operation** when the evidence states no category. If the
  worker attempted the wrong treatment, we inherit its view of the category.
- **Absence by omission is weak evidence.** A snapshot that simply doesn't list a record decides existence only
  when nothing explicit exists. When that is all we have, a COMPLETE verification can rest on it.
- **Intent is rule-based.** The 10 NOT_APPLICABLE requests are exactly the 10 cases the intake logged as
  CLASSIFY_REQUEST. An LLM fallback exists for low-confidence texts but was not needed. A broader multilingual
  phrasing set could break the rules.
- **The OCR and PDF paths are thin:** 11 screenshots and 4 PDFs. Each matters, but there are too few to say how
  robust the OCR tolerance (edit distance ≤ 2) is.

## 6. What we would change with more time

1. Get labels for the uncertain cases instead of reweighting guesses: the 57 ambiguous links are the obvious
   review sample. Each answer either confirms the timing model or gives it its first negative example.
2. Replace the multiplicative confidence heuristics with a model fitted on those reviewed links, and report a real
   reliability curve.
3. Treat "no account evidence" as its own status signal: surface it in the output narrative rather than silently
   emitting no account step.
4. Model replication explicitly (primary → replica lag) instead of treating any surviving copy as a leftover. The
   current rule is safe (it never hides a copy) but cannot tell a lagging replica from a forgotten one.
5. Add a second-opinion investigator that follows leads independently and compare findings case by case (Tier B
   of this pass). Disagreement is the cheapest error detector available without labels.
