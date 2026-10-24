# DATA_NOTES — Phase 0 reconnaissance

Everything below was measured from `dataset/` with throwaway scripts (no engine code yet).
Numbers are real counts. Where a statement is an inference, it is marked **(inference)**.

---

## 1. Inputs at a glance

| File | Rows | Notes |
|---|---:|---|
| `deletion_requests.csv` | 518 | case_33 … case_550, file is in **numeric** case order |
| `sample_deletion_requests.csv` / `sample_output.csv` | 32 | case_01 … case_32 — **no NOT_APPLICABLE example** |
| `user_identities.csv` | 850 | `user_id,name,email,phone,email_hash,updated_at` |
| `user_audit_log.csv` | 306 | field_name ∈ {email:107, email_hash:107, phone:92}; email+hash changes are paired by `(user_id, event_time)` |
| `system_activity.csv` | 4011 | global stream, mostly unrelated people |
| `deletion_rules.csv` | 15 | see §4 |
| `evidence_files.csv` | 94 | 28 json, 26 log, 24 sql, 11 png, 4 pdf, 1 txt |

Reported status split (eval): COMPLETE 254 · PARTIALLY_COMPLETE 152 · NOT_STARTED 112.
Audit window (eval): 2026-01-29 → 2026-10-01. Samples: 2026-09-03 → 2026-10-01.

## 2. Identity

* **email_hash = sha256(lower(strip(email)))** — verified on 850/850 current identities and 107/107
  historical (old email → old hash) pairs from the audit log.
* All 518 eval request emails resolve to exactly one user after `strip().lower()`:
  403 current, 95 historical, 20 needed case/space normalisation (5 of those historical).
* No email is owned by two users (current or historical). 3 duplicate *names* exist → names are weak evidence only.
* 3 users have more than one case at different audit times (user_07: case_07/case_61, user_17: case_17/case_46,
  user_18: case_33/case_52). The audit cutoff decides which resources belong to which case.
* Decoys use **near-miss identifiers**: `jonas.berglund@…` vs `jonas.berg@…`, `g.silva76.jr@…` vs `g.silva76@…`,
  `smartinez6461.jr@…`, "Karim El-Masri" vs "Amina El-Masri", "Mateo Rios Gil" vs "Mateo Ríos". → exact
  normalised matching only, never fuzzy.

Identifiers seen inside evidence: current email, historical email, UPPER-CASED email, email_hash (current or
historical), `user_id` (as `customer_reference` / `subject_reference` / `subject_selector` / `correlation_key` /
`lookup_key`), name, phone.

## 3. Evidence formats (all parsed into one fact shape: system, resource, state, identifiers, observed_at, evidence_id)

| Family | Files | How a fact is expressed |
|---|---|---|
| Typed inventory SQL (`customer_data_inventory_*`) | 11 | tables per system (`customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `support_records`, `customer_exports`, `connector_subscriptions`, `backup_restore_entries`, `security_audit_records`) + `snapshot_scope(origin_system, captured_at)` = which systems the snapshot fully covers |
| Generic topology SQL (`customer_data_{read_replica,regional_replicas,reporting_replica,failover_replica}_*`) | 11 | `customer_data_<topology>(resource_id, origin_system, collection_name, record_json, updated_at)`; primary + replica tables → **replication drift** (e.g. `account_994` only in read replica) |
| Special SQL | 2 | `customer_profiles_{primary,failover_replica}` (evidence_54), `search_documents_primary` (evidence_57) |
| Snapshot bundles JSON | 13 | `snapshots[]` each with its **own** `captured_at`, `data_store`, `collection`, `records[]`; collections also include `deleted_customer_references` (tombstones), `ticket_attachments`, `retained_order_records` (legal holds), `operational_record_history` (flat lookups) |
| Service resource exports JSON | 11 | `service_exports.<system>.<kind>[]` with `observed_at`, 404/200 lookups, `restore_allowed`, `enabled` |
| Flat record_lookup | txt + 3 json + 2 logs | `system | resource | RECORD_TYPE | RESULT | identifier` — RECORD_TYPE is the policy **data category** and RESULT the state (FOUND/NOT_FOUND/IDENTIFIABLE/ANONYMIZED/REDACTED/ACTIVE/DISABLED/BLOCKED) |
| Logs (6 syntaxes) | 24 | logfmt, `[LEVEL] [svc] [trace]`, cloud-runtime nested `message="…"`, pipe-delimited, RFC5424 syslog, JSON lines. Facts span two lines joined by **trace_id**: `*_started` carries `lookup_key/match_key/subject_ref/owner_key`, `*_completed`/`*_scan` carries `resource_id` + state. Some lines carry `correlation_key` (email, user_id, or hash) directly |
| PDFs | 4 | `pdftotext -layout` extracts all text (support attachment `support_001`, statement `NST-2026-0718-1842` for user_18, legal register, signed audit extract `audit_record_003`/user_03) |
| PNG screenshots | 11 | admin consoles; each has a **parallel `LINK_RESOURCE_IDENTITY` row** in system_activity timestamped capture+7 min (e.g. evidence_09 06:00 ↔ activity_4001 06:07). Tesseract is installed for OCR corroboration |

**Fact time ≠ file time.** evidence_06 is manifested 09-18 but its lines are dated 09-16 08:5x and gold uses
them for a 09-16 09:00 audit; evidence_02 is manifested 09-17 but its inner snapshots are dated 09-09/09-15.
→ every fact keeps its own `observed_at`; *citations* are restricted to files whose manifest `captured_at ≤ audit_at`
(gold never cites a later file).

## 4. Policy (deletion_rules.csv) → required end state

| Category | Condition | Action | End state verified by |
|---|---|---|---|
| USER_PROFILE (account) | Always | DELETE | VERIFY_RECORD_ABSENT |
| SECONDARY_IDENTIFIER | Always | DELETE | VERIFY_RECORD_ABSENT |
| SEARCH_INDEX_ENTRY | Always | DELETE | VERIFY_RECORD_ABSENT |
| CACHE_ENTRY | Always | DELETE | VERIFY_RECORD_ABSENT |
| SUPPORT_MESSAGE | shared customer/agent/order context | REDACT | VERIFY_RECORD_REDACTED |
| SUPPORT_ATTACHMENT | belongs only to subject | DELETE | VERIFY_RECORD_ABSENT |
| ANALYTICS_PROFILE | still attributable | ANONYMIZE | VERIFY_RECORD_ANONYMIZED |
| PRODUCT_TELEMETRY | still attributable | ANONYMIZE | VERIFY_RECORD_ANONYMIZED |
| USER_EXPORT | Always | DELETE | VERIFY_RECORD_ABSENT |
| MARKETING_PROFILE | Always | DELETE | VERIFY_RECORD_ABSENT |
| EMAIL_DELIVERY_LOG | contains user email | REDACT | VERIFY_RECORD_REDACTED |
| SECURITY_AUDIT_LOG | within retention | RETAIN | VERIFY_RECORD_PRESENT |
| LEGAL_HOLD_RECORD | hold active | RETAIN | VERIFY_RECORD_PRESENT |
| BACKUP_ARCHIVE | restore can be blocked | RETAIN (+ block restore) | VERIFY_RESTORE_BLOCKED |
| ACCOUNT_TOMBSTONE | only stable user_id needed | REDACT (keep user_id only) | VERIFY_RECORD_REDACTED |
| (data flow, not a rule row) | active sync/connector | disable | VERIFY_DATA_FLOW_DISABLED |

Category signals, strongest first: explicit RECORD_TYPE in flat lookups → collection/table name
(`ticket_attachments` = SUPPORT_ATTACHMENT, `deleted_customer_references` = ACCOUNT_TOMBSTONE …) →
**the operation the deletion worker attempted on that resource**. Measured on samples: worker op type matches the
gold treatment for every resource that has a worker event (DELETE_RECORD→DELETE 47, ANONYMIZE_RECORD→ANONYMIZE 17,
REDACT_RECORD→REDACT 16, CHECK_DATA_FLOW→disable 6, CHECK_RESTORE_ACCESS→block 3). The *result* is a claim; the
*operation type* reveals the category the workflow assigned. Example: case_12 `analytics_9914` is a hash-keyed
contact record the worker tried to DELETE → gold is DELETE, not ANONYMIZE.

## 5. system_activity anatomy

| event_type | meaning for us |
|---|---|
| DELETE/REDACT/ANONYMIZE_RECORD, DISABLE_DATA_FLOW, BLOCK_RESTORE (source deletion_worker) | claims + category signal + case-chain timing |
| CHECK_DATA_FLOW "remains enabled", CHECK_RESTORE_ACCESS "can still be restored" | positive evidence of an active path |
| SYNC_RECORD "Active connector repopulated downstream resource search_N" (source integration_service, resource = data_flow_N) | data flow that recreates a search record |
| RESTORE_BACKUP "Restore job repopulated downstream resource search_N" | restore path that recreated data |
| SYNC_RECORD "Replication worker reported its final checkpoint … account_N" | replica rewrite after deletion (case_05) |
| LINK_RESOURCE_IDENTITY (data_catalog) | resource ↔ email + user_id link (mirrors the screenshots) |
| CLASSIFY_REQUEST (privacy_intake) | 10 events "classified … as non-deletion" — matches the 10 non-deletion texts |
| INDEX/UPDATE/SYNC/REFRESH/SEND_EMAIL/CREATE_EXPORT/RETAIN (non-worker) | background noise; no user identifiers |

**Per-case worker chain (measured on all 32 samples):** account DELETE at `reported_at − 0.8…1.2 h` with
`reported_result` mirroring the claim (COMPLETE→SUCCESS, PARTIALLY_COMPLETE→PARTIAL, NOT_STARTED→FAILED);
actions on already-compliant resources at `reported_at − 0.1…0.5 h` (SUCCESS); attempts on non-compliant resources
at `reported_at + 0.6…2 h` (FAILED, or SUCCESS that the evidence contradicts).
There are 539 account-delete events for ~540 deletion cases, but a time window alone is ambiguous
(only 118/550 cases have a single matching candidate) → linking must be **evidence first, then a global one-to-one
assignment** (elimination + order), never a per-case nearest-timestamp guess.

## 6. How the canonical answers are formed (all 32 samples walked)

General shape:
* **COMPLETE** → verification only, each step cites the latest pre-audit evidence observing that resource's state:
  account `VERIFY_RECORD_ABSENT` (absence proof = a pre-audit snapshot covering the account store that lacks it,
  or a 404 lookup), every retained security record `VERIFY_RECORD_PRESENT`, already-redacted support/tombstone
  `VERIFY_RECORD_REDACTED`, null-identifier analytics `VERIFY_RECORD_ANONYMIZED`, disabled flows, blocked backups.
  Deleted non-account records are *not* listed (nothing observes them any more).
* **INCOMPLETE** → findings (cite evidence) for every violation; remediation for each; verification =
  account ABSENT (always, even with no account finding) + every retained record PRESENT + the post-state of every
  remediated item; all remediation/verification `evidence_id = ""`. Already-compliant resources other than
  account/retained are **not** re-verified in INCOMPLETE cases (case_07 omits user_07's long-gone `object_19`).
* Finding choice: DELETE-category record still present → `REPORT_REMAINING_RECORD`; REDACT/ANONYMIZE-category
  record still carrying identifiers → `REPORT_EXPOSED_PII`; enabled connector → `REPORT_ACTIVE_DATA_FLOW`;
  restorable backup → `REPORT_RESTORE_RISK`.
* Ordering exactly as specified: phase → operation table order → system_id → resource_id (string compare).

| Case | Status | Why (resources, evidence, link) |
|---|---|---|
| 01 | COMPLETE | user_01; `account_001` missing from both tables of evidence_54 (failover snapshot); decoy "Karim El-Masri" |
| 02 | COMPLETE | ES text; claim PARTIALLY_COMPLETE but `account_002` absent in evidence_54; decoy "Mateo Rios Gil" |
| 03 | COMPLETE | FR text; evidence_94: `account_7566` 404 via `lookup_key=l.fontaine46…`; `audit_record_2016` subject user_43 retained to 2034; `analytics_9406` all-null, linked only by worker chain (ANONYMIZE at −0.5 h) |
| 04 | COMPLETE | `account_004` absent (evidence_54); `analytics_901` all-null in evidence_56 |
| 05 | INCOMPLETE | `account_005` gone from primary but alive in **failover replica** (evidence_54); replication checkpoint activity re-wrote it |
| 06 | INCOMPLETE | `search_001` still holds name+email (evidence_57); decoys Berglund/Joana; account verified absent with no finding |
| 07 | INCOMPLETE | `support_001` = identity attachment PDF (evidence_58), subject-only → DELETE |
| 08 | INCOMPLETE | `export_001` download still available (evidence_59) → DELETE |
| 09 | INCOMPLETE | `backup_4978` `restore_allowed=1` (evidence_93) → restore risk + block; `account_3960`/`audit_record_4902` linked via evidence_06 trace lines |
| 10 | INCOMPLETE | request email is historical; `support_002` found via old email in legacy contact index, `marker_found=false` (evidence_61) despite a "completed" worker claim |
| 11 | INCOMPLETE | handover evidence_03: search FOUND, analytics IDENTIFIABLE, support message IDENTIFIABLE, data flow ACTIVE; account NOT_FOUND; audit record user_32 |
| 12 | INCOMPLETE | `analytics_9914` matched by **historical email hash** (evidence_01); worker DELETE → REMAINING_RECORD/DELETE |
| 13 | INCOMPLETE | handover: search FOUND + `SUPPORT_ATTACHMENT` FOUND → both DELETE |
| 14 | INCOMPLETE | JA text; handover: `backup_3870` ACTIVE → restore risk |
| 15 | INCOMPLETE | `data_flow_9846` active (evidence_01) |
| 16 | INCOMPLETE | evidence_05: `account_994` only in read replica (drift) + `search_1007` |
| 17 | INCOMPLETE | `backup_3245` restorable (evidence_01) |
| 18 | INCOMPLETE | evidence_94: search hit, analytics email, support requester_email, connector enabled |
| 19 | INCOMPLETE | search + support message PII scan (conversation shared → REDACT) |
| 20 | INCOMPLETE | evidence_94: search hit + connector enabled |
| 21 | COMPLETE | evidence_92: account 404, audit retained, analytics all-null |
| 22 | INCOMPLETE | evidence_05: search + identifiable analytics |
| 23 | INCOMPLETE | evidence_92: export + search still present |
| 24 | INCOMPLETE | evidence_92: account lookup **200 with email** (false COMPLETE claim) + search |
| 25 | COMPLETE | claim NOT_STARTED but evidence_92 shows everything compliant (false NOT_STARTED claim) |
| 26–28 | COMPLETE | full compliant set: account 404, audit retained, support with only customer_reference (REDACTED), analytics null, connector disabled, backup `restore_allowed=false`; case_28 ignores decoy `search_8168` (`smartinez6461.jr`) |
| 29 | INCOMPLETE | historical email `noah.f4380`; current-email copies in search/analytics/support/connector |
| 30 | INCOMPLETE | same pattern as 29 with current email |
| 31 | COMPLETE | `tombstone_440` keeps only `subject_reference` → REDACTED; account absent (evidence_51 empty `customer_profiles`, linked via worker chain) |
| 32 | INCOMPLETE | `tombstone_9178` still holds name/email/phone/hash → EXPOSED_PII → REDACT |

## 7. Things that cannot be (or should not be) reproduced

* **Unreachable gold steps:** `security_service/audit_record_6645` (case_18) and `audit_record_5569` (case_20)
  appear in no participant file. A non-hardcoded solution cannot emit them → max achievable sample step recall < 100%.
* **Citation tie for absence proofs:** evidence_90 (09-05, inventory scoped to account_service, 0 rows) is a valid
  later absence proof for case_04, yet gold cites evidence_54. Exact citation rule for absence proofs is open (see CONVENTIONS).
* **Conflicting catalog row:** activity_4008 links `marketing_001` to user_09, but the screenshot (evidence_60)
  shows a different person (Soo-jin Park, `sj.park@naver.com`, not a known user). Treated as a trap: content wins over catalog claims.
* **Legal retention register PDF** lists users/orders but no resource ids; samples for those users (12, 21, 24, 29)
  verify nothing from it → used as context only.

## 8. Intent

27 distinct first sentences in eval: 17 deletion templates (EN ×12, PT, KO, ES, JA, FR) + 10 one-off
non-deletion requests (phone update, stop promos, portable export, login reset, surname fix, marketing-only
opt-out, access request, invoices, email change, copy of data). Non-deletion texts contain explicit negations
("I am not asking for deletion", "please don't delete or change anything", "without removing", "only").
These 10 coincide with the 10 `CLASSIFY_REQUEST … non-deletion` activity rows (used as corroboration, not proof).
