// Human-readable labels for engine vocabulary. Labels only; values always come from the data.
import type { Status } from "./data";

export const STATUS_LABEL: Record<Status, string> = {
  INCOMPLETE: "Haunted",
  COMPLETE: "Proven",
  NOT_APPLICABLE: "Not applicable",
};

export const STATUS_TONE: Record<Status, "haunted" | "proven" | "na"> = {
  INCOMPLETE: "haunted",
  COMPLETE: "proven",
  NOT_APPLICABLE: "na",
};

export const REPORTED_LABEL: Record<string, string> = {
  COMPLETE: "Complete",
  PARTIALLY_COMPLETE: "Partially complete",
  NOT_STARTED: "Not started",
};

const VERDICTS: Record<string, string> = {
  false_COMPLETE: "False “complete”: data still exists",
  false_NOT_STARTED_actually_complete: "Said “not started”, but already complete",
  understated_PARTIAL_actually_complete: "Said “partial”, but already complete",
  accurate_COMPLETE: "Claim confirmed by evidence",
  PARTIALLY_COMPLETE_and_INCOMPLETE: "Partial claim confirmed: still incomplete",
  NOT_STARTED_and_INCOMPLETE: "Not started claim confirmed: still incomplete",
};
export const verdictLabel = (v: string | null) => (v ? VERDICTS[v] ?? v.replace(/_/g, " ") : "No deletion requested");

const MODES: Record<string, string> = {
  hidden_replica_drift: "Hidden replica drift",
  sync_or_restore_resurrection: "Resurrected by sync / restore",
  restore_risk: "Restore path still open",
  active_data_flow: "Active data flow",
  primary_record_remaining: "Primary record remaining",
  tombstone_leaking_identifiers: "Tombstone leaking identifiers",
  tombstone_leaking_hash: "Tombstone leaking email hash",
  over_deletion_risk: "Retained record not observed",
};
export const modeLabel = (m: string) =>
  MODES[m] ?? (m.startsWith("identifier_leakage_") ? `Identifier leak · ${m.slice(19).replace(/_/g, " ")}` : m.replace(/_/g, " "));

export const OP_VERB: Record<string, string> = {
  REPORT_REMAINING_RECORD: "Remaining record",
  REPORT_EXPOSED_PII: "Exposed PII",
  REPORT_ACTIVE_DATA_FLOW: "Active data flow",
  REPORT_RESTORE_RISK: "Restore risk",
  DISABLE_DATA_FLOW: "Cut the flow",
  BLOCK_RESTORE: "Seal the restore",
  DELETE_RECORD: "Destroy the record",
  REDACT_RECORD: "Redact identifiers",
  ANONYMIZE_RECORD: "Anonymise",
  VERIFY_RECORD_ABSENT: "Verify absent",
  VERIFY_RECORD_PRESENT: "Verify retained",
  VERIFY_RECORD_REDACTED: "Verify redacted",
  VERIFY_RECORD_ANONYMIZED: "Verify anonymised",
  VERIFY_DATA_FLOW_DISABLED: "Verify flow disabled",
  VERIFY_RESTORE_BLOCKED: "Verify restore blocked",
};

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
