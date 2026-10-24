# DEV_LOG

## 2026-10-24 — Phase 0 recon
* Cloned starter repo; `code/main.py` and `code/evaluation/main.py` are empty stubs.
* Profiled every CSV and evidence family (SQL via sqlite3, PDFs via pdftotext, PNGs viewed, logs/JSON parsed).
  Findings in `DATA_NOTES.md`, inferred rules in `CONVENTIONS.md`.
* Key decisions so far:
  - Deterministic-first: every sample row is explainable from structured evidence + activity; no LLM needed for verdicts.
  - Facts carry their own observation time; citations limited to files captured ≤ audit_at.
  - Linking identifier-free resources needs a global one-to-one assignment over the worker chain, not nearest-time.
* Known ceiling: 2 sample gold steps reference resources absent from all participant data (case_18, case_20).
