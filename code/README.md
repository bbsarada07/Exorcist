# Exorcist — deletion audit agent for "Ghost Data Still Exists"

Deterministic, evidence-first audit of 518 deletion requests. For every request it decides
`COMPLETE | INCOMPLETE | NOT_APPLICABLE` and emits the ordered FINDING → REMEDIATION → VERIFICATION
plan, citing only participant-visible evidence (`file_id`, `activity_id`, `audit_id`).

## Quick start (one command)

```bash
pip install -r code/requirements.txt        # numpy + scipy (Hungarian solver; a pure-python fallback exists)
python code/main.py                          # -> ./output.csv, code/out/*.json(l), validation report
```

Runs offline in ~3 s after the first run. External tools used for document evidence (both local, no network):
`pdftotext` (poppler) for PDFs and `tesseract` for screenshots; extracted text is cached by content hash in
`code/cache/`. Without them, PDF/screenshot facts are skipped (catalog rows still link those resources).

| Command | What it does |
|---|---|
| `python code/main.py` | full run, writes `output.csv` at the repo root, sidecars in `code/out/`, validates (exit 1 on any contract error) |
| `python code/evaluation/main.py` | scores the 32 public samples, prints every diff |
| `python code/evaluation/custom_cases.py` | 12 custom scenarios injected into a temp copy of `dataset/` |
| `python code/evaluation/metamorphic.py` | metamorphic relations R1–R5 incl. the seeded mutation generator |
| `python code/evaluation/citation_study.py` | empirical choice of the citation rule |
| `python code/evaluation/holdout.py` | overfitting check: tune knobs on half the samples, score the other half |
| `python code/evaluation/report.py` | regenerates `evaluation/evaluation_report.md` and `evaluation/usage_report.md` |
| `python -m unittest discover -s code/tests` | no-hardcode lint, determinism (two hash seeds), validator negative tests |
| `python code/tools/inspect_case.py case_123` | debug view: links, observations, assessments, steps |

Optional LLM: `cp code/.env.example .env`, set `AUDIT_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`. It is
only a cached fallback for low-confidence intent (never needed on this dataset; see `usage_report.md`).

## Architecture

```
dataset/ ──► parsers/ ──► Fact table (3,047 facts, 369 coverage snapshots, 4,011 activities)
              sql · json · logs(6 syntaxes, trace-id joins) · flat lookups · pdf · ocr · activity
                         │
 IdentityAgent ──────────┤ current + historical emails/phones/hashes (sha256(lower(email))), validity windows
 IntentAgent  ───────────┤ multilingual deletion cues + explicit negations  -> NOT_APPLICABLE = []
                         ▼
 LinkerAgent   evidence links (exact identifiers, content beats catalog, OCR-misread tolerance, decoys logged)
               + global min-cost assignment (Hungarian) of deletion-worker chains for identifier-free records
                         ▼
 TimelineAgent per resource: observations ≤ audit_at (replica copies, snapshot omissions, resurrection jobs)
 PolicyAgent   deletion_rules.csv compiled: category (stated > worker operation > system default) → required end state
 PlannerAgent  spec ordering; COMPLETE = cited verifications; INCOMPLETE = findings + remediation + checks
 SimulatorAgent applies the plan to the reconstructed state, proves every verification passes
 ValidatorAgent output contract (518 rows, order, enums, step_no, phase/op order, evidence rules) — fails loudly
                         ▼
 output.csv  +  code/out/ sidecars (never influence output.csv)
```

| Module | Responsibility |
|---|---|
| `audit/parsers/*` | every evidence format → `Fact(evidence_id, observed_at, cite_at, resource, system, location, exists, category, exposed, keys, attrs)` |
| `audit/identity.py` | identity graph, `resolve()`, `belongs_to()` (reused addresses by validity window), near-miss detector |
| `audit/intent.py` | deletion intent (rules; optional LLM only for low confidence) |
| `audit/linker.py` | which resources / worker events belong to which case, link mode + margin |
| `audit/timeline.py` | state of a resource at `audit_at` |
| `audit/policy.py` | rule compilation, category resolution, violation / compliant verdict, proof observations |
| `audit/planner.py` | steps + citation rule |
| `audit/simulator.py`, `audit/validator.py` | proof-by-simulation, strict contract checks |
| `audit/sidecars.py` | USP outputs (below) |

## Sidecars (`code/out/`, explainability only)

| File | Content |
|---|---|
| `decision_trace.jsonl` | per emitted step: rule_id, category + where it came from, evidence chain, producing agent, link mode |
| `lie_report.json` | reported status vs reconstructed truth; failure modes (false COMPLETE, replica drift, resurrection, restore risk, leakage, tombstone hash) |
| `confidence.json`, `review_queue.json` | 0–1 confidence per case from link mode, assignment margin, drift, conflicts; the queue holds every case below 0.6, every ambiguous (guessed) chain link with its margin, and every deletion case with no account evidence |
| `lineage.json` | recreation paths (connector / restore job / replication → recreated record) |
| `conflicts.jsonl` | catalog vs content, primary vs replica, claimed result vs evidence, rejected decoys — with the side trusted and why |
| `risk_scores.json` | transparent exposure heuristic (weights in `audit/config.py`), "fix these first" ranking |
| `decoys.json` | near-miss identifiers met and rejected ("false exposures avoided") |
| `cases.json` | compact bundle for the UI |

## Results (measured, see `evaluation/evaluation_report.md`)

Samples: status accuracy **1.0**, strict step precision **1.0** / recall **0.9845** / F1 **0.992** — recall equals
the honest ceiling (3 gold steps reference resources that exist in no participant file), evidence_id accuracy
**1.0**, ordering **1.0**. Overfitting check (tune on 16 samples, test on 16, 5 splits × 2 directions): mean
held-out F1 = mean train F1 = 0.9918. Custom cases 12/12. Metamorphic R1–R5 all 100%. Evaluation set: 518 rows,
validation passed, 0 simulation failures, no LLM tokens used.

Read the sample score as an **upper bound**: the structural rules were derived while inspecting the samples and the
held-out check covers tunable parameters only. Identifier-free resources are linked with a worker-clock regularity
(30 s tick) learned from unlabeled logs on every run; each guessed link is flagged in `review_queue.json`
(final run: 41 ambiguous account links, 16 analytics ties). Known risk: 10 hand-built multimodal cases
(case_33, 35, 39, 45, 50, 52, 53, 55, 61, 63) have no account evidence and therefore no account step.

## UI — "Exorcist" (code/ui)

A cinematic, read-only front end over the engine's outputs (Vite + React + TypeScript + Tailwind, raw WebGL, Framer
Motion, GSAP, Lenis, Zustand). Fully offline: fonts are bundled, and the UI loads only the static JSON in
`code/ui/public/data/` (committed), so it runs without Python.
code/ui/public/data/ contains derived engine outputs (statuses, steps, evidence ids, scores, masked emails), not the dataset or its evidence files. `npm run test:privacy` enforces it.

```bash
cd code/ui
npm install
npm run dev            # http://localhost:5173
npm run build          # type-check + production build to code/ui/dist (not committed, not zipped)
npm run preview        # serve the production build
npm test               # privacy scan + 56 Playwright end-to-end tests (builds and serves dist itself)
npm run test:privacy   # scan public/data, src and dist/data for PII / dataset content
npm run test:e2e       # e2e only; uses a locally installed Chrome/Edge (set CHROME_PATH), no browser download
npm run export-data    # after re-running `python code/main.py`: code/out + output.csv -> public/data/*.json
npm run shots          # optional: screenshots to code/docs/ui
```

Screens (Tier 1): **The Summoning** (particle hero, flashlight reveals masked identifiers, odometer counters) ·
**The Graveyard** (518 frosted-glass tombstones, glow = findings, filters, `/` search over case ids, system names and
evidence ids with a pinned result strip, `j`/`k`/Enter, ledger view, `ctrl/cmd+K` palette) · **Case file**
(shared-element zoom, review reasons, confidence, heuristic risk, runbook with "why this step exists" from
`decision_trace.jsonl`) · **Reported vs Reality** (legacy claim vs reconstructed truth from `lie_report.json`) · **The
Exorcism** (GSAP sequence generated from the case's remediation steps, ending in the purge; proof view for COMPLETE
cases). Behind everything runs an "ink in water" WebGL fluid whose ember/green/violet shares are the real haunted,
proven and active-flow numbers. Top bar: **Perf** (Auto adapts resolution and falls back to a CSS gradient; High;
Low) and **Lite mode** (default on with `prefers-reduced-motion`: no canvas, every number kept).
Details: `docs/UI_DATA_NOTES.md` (every field and its source), `docs/DESIGN_NOTES.md` (decisions, data → fluid
mapping, performance), `docs/UI_TEST_REPORT.md` (test results and measured fps), `docs/DEMO_SCRIPT.md`,
`ui/src/effects/README.md`; screenshots in `docs/ui/` (before: `docs/ui/before/`).

## 60-second demo script

1. `python code/main.py` — "518 rows in ~3 seconds, validator green, zero simulation failures."
2. Open `code/out/lie_report.json` — "64% of the workflow's COMPLETE claims are false; top cause: search entries
   still holding the email; 34 cases of replica drift, 29 resurrections by sync/restore jobs."
3. `python code/tools/inspect_case.py case_16` — "primary deleted the account, the read replica still serves it:
   the finding cites the SQL snapshot that shows both copies."
4. `python code/tools/inspect_case.py case_34` — "a support attachment found through the customer's *previous*
   phone number, and the account still visible on an admin screenshot (OCR)."
5. `python code/evaluation/main.py` — "100% status on the samples; the only misses are 3 steps that no evidence
   supports and coin-flip identifier-free records, all flagged in the review queue."
6. `grep -c . code/out/decision_trace.jsonl` — "every step has a rule, a category source and an evidence chain."

## How AI was used

Built with Claude Code (model `claude-opus-5-5`) as a pair programmer: it read the repo contract, ran the
reconnaissance scripts, proposed hypotheses (e.g. "the worker's *operation* reveals the policy category"),
and wrote the code; every hypothesis was accepted only after a measurement on the data (scripts and numbers in
`docs/DATA_NOTES.md`, `docs/DEV_LOG.md`). Decisions the data could not settle were escalated to the human and
recorded in `docs/CONVENTIONS.md`. The shipped engine itself calls no model.
