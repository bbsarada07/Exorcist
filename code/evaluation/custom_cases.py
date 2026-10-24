"""Custom evaluation cases (>= 10). Each scenario is injected into an overlay copy of the dataset and
scored against a hand-derived expected answer. Scenarios are dated after all real data so they never
interact with real cases.

    python code/evaluation/custom_cases.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.pipeline import AuditEngine  # noqa: E402
from audit.util import email_hash, iso  # noqa: E402
from evaluation.metrics import score  # noqa: E402
from evaluation.overlay import build_overlay, bundle, cleanup  # noqa: E402

BASE = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
DELETE_TEXT = "Please permanently delete the account associated with this email address."
CLAIM_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


def lookup_log(lines: list[tuple]) -> str:
    """resource_lookup_trace style: (ts, service, event_prefix, resource, key, completed_fields)."""
    out = []
    for i, (ts, svc, prefix, rid, key, fields) in enumerate(lines, 1):
        tr = f"rb-c-{i:03d}"
        out.append(f"{ts} level=DEBUG service={svc} trace_id={tr} event={prefix}_started resource_id={rid} lookup_key={key}")
        out.append(f"{ts} level=INFO service={svc} trace_id={tr} event={prefix}_completed resource_id={rid} {fields}")
    return "\n".join(out) + "\n"


class Scenario:
    def __init__(self, n: int, name: str, purpose: str, claim: str = "COMPLETE", text: str = DELETE_TEXT):
        self.n, self.name, self.purpose, self.claim, self.text = n, name, purpose, claim, text
        day = BASE + timedelta(days=3 * n)
        self.requested, self.reported, self.audit = day - timedelta(days=2), day, day + timedelta(days=2)
        self.uid, self.email = f"user_9{n:03d}", f"subject.c{n}@example.org"
        self.case_id = f"custom_{n:02d}"
        self.identities, self.audit_log, self.activities, self.evidence = [], [], [], []
        self.expected_status, self.expected_steps = None, []
        self.identities.append({"user_id": self.uid, "name": f"Custom Subject {n}", "email": self.email,
                                "phone": f"+1 555 01{n:02d} 0000", "email_hash": email_hash(self.email),
                                "updated_at": "2026-01-01T00:00:00Z"})
        self._act = 0
        self._ev = 0

    def rid(self, kind: str, k: int = 1) -> str:
        return f"{kind}_9{self.n:03d}{k}"

    def t(self, hours: float, ref=None) -> str:
        return iso((ref or self.audit) + timedelta(hours=hours))

    def activity(self, event_type, target, resource, result, details, source="deletion_worker", at=None):
        self._act += 1
        aid = f"activity_c{self.n:02d}{self._act}"
        self.activities.append({"activity_id": aid, "event_time": at, "event_type": event_type, "source_system": source,
                                "target_system": target, "resource_id": resource, "reported_result": result,
                                "details": details})
        return aid

    def account_chain(self, account: str):
        return self.activity("DELETE_RECORD", "account_service", account, CLAIM_RESULT[self.claim],
                             f"Deletion worker submitted primary profile {account} to account_service.",
                             at=self.t(-1.0, self.reported))

    def file(self, content, kind="records", ext="json", hours=-2.0) -> str:
        self._ev += 1
        fid = f"evidence_c{self.n:02d}{self._ev}"
        self.evidence.append({"file_id": fid, "file_path": f"evidence/{kind}/custom_{self.n:02d}_{self._ev}.{ext}",
                              "captured_at": self.t(hours), "content": content})
        return fid

    def expect(self, status, *steps):
        self.expected_status = status
        self.expected_steps = [{"step_no": i, "phase": p, "system_id": s, "resource_id": r, "operation": o,
                                "state": st, "evidence_id": e} for i, (p, s, r, o, st, e) in enumerate(steps, 1)]

    def request(self):
        return {"case_id": self.case_id, "email": self.email, "requested_at": iso(self.requested),
                "reported_status": self.claim, "reported_at": iso(self.reported), "audit_at": iso(self.audit),
                "request_text": self.text}


F, R, V = "FINDING", "REMEDIATION", "VERIFICATION"


def scenarios() -> list[Scenario]:
    out = []

    s = Scenario(1, "identity_change_before_deletion", "Request uses the OLD email; remaining copy uses the NEW one.", "NOT_STARTED")
    old = s.email
    s.email_new = f"renamed.c1@example.org"
    s.identities[0].update(email=s.email_new, email_hash=email_hash(s.email_new))
    s.audit_log += [{"audit_id": "audit_c011", "user_id": s.uid, "event_time": "2026-06-01T00:00:00Z", "field_name": "email",
                     "old_value": old, "new_value": s.email_new},
                    {"audit_id": "audit_c012", "user_id": s.uid, "event_time": "2026-06-01T00:00:00Z", "field_name": "email_hash",
                     "old_value": email_hash(old), "new_value": email_hash(s.email_new)}]
    acc, srch, aud = s.rid("account"), s.rid("search"), s.rid("audit_record")
    s.account_chain(acc)
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("search_service", "customer_search_documents",
                       [{"resource_id": srch, "index_name": "customer_directory_v3",
                         "document": {"display_name": None, "email": s.email_new, "customer_reference": None}}]),
                      ("security_service", "security_audit_events", [{"resource_id": aud, "subject_reference": s.uid}])))
    s.expect("INCOMPLETE", (F, "search_service", srch, "REPORT_REMAINING_RECORD", "PRESENT", f),
             (R, "search_service", srch, "DELETE_RECORD", "ABSENT", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "search_service", srch, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "security_service", aud, "VERIFY_RECORD_PRESENT", "PRESENT", ""))
    out.append(s)

    s = Scenario(2, "deletion_after_audit_at", "Account still live at audit_at; the 404 arrives a day later and must be ignored.")
    acc = s.rid("account")
    s.account_chain(acc)
    f1 = s.file(lookup_log([(s.t(-2), "account_service", "profile_lookup", acc, s.email,
                             f"rows=1 http_status=200 customer_reference=null email={s.email} phone=null")]), "logs", "log")
    s.file(lookup_log([(s.t(24), "account_service", "profile_lookup", acc, s.email, "rows=0 http_status=404")]), "logs", "log", hours=24)
    s.expect("INCOMPLETE", (F, "account_service", acc, "REPORT_REMAINING_RECORD", "PRESENT", f1),
             (R, "account_service", acc, "DELETE_RECORD", "ABSENT", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""))
    out.append(s)

    s = Scenario(3, "restore_recreating_data", "Search entry deleted, then a restore job repopulated it; backup still restorable.")
    acc, srch, bk = s.rid("account"), s.rid("search"), s.rid("backup")
    s.account_chain(acc)
    s.file(lookup_log([(s.t(-72), "search_service", "index_query", srch, s.email, "result=miss total_hits=0 email=null")]), "logs", "log", hours=-72)
    ra = s.activity("RESTORE_BACKUP", "search_service", bk, "SUCCESS", f"Restore job repopulated downstream resource {srch}.",
                    source="backup_service", at=s.t(-24))
    f = s.file(lookup_log([(s.t(-2), "account_service", "profile_lookup", acc, s.email, "rows=0 http_status=404"),
                           (s.t(-2), "backup_service", "restore_policy_read", bk, s.uid,
                            f"archive_present=true restore_allowed=true customer_email=null customer_reference={s.uid}")]), "logs", "log")
    s.expect("INCOMPLETE", (F, "search_service", srch, "REPORT_REMAINING_RECORD", "PRESENT", ra),
             (F, "backup_service", bk, "REPORT_RESTORE_RISK", "ACTIVE", f),
             (R, "backup_service", bk, "BLOCK_RESTORE", "BLOCKED", ""),
             (R, "search_service", srch, "DELETE_RECORD", "ABSENT", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "search_service", srch, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "backup_service", bk, "VERIFY_RESTORE_BLOCKED", "BLOCKED", ""))
    out.append(s)

    s = Scenario(4, "active_sync_recreating_data", "An enabled connector repopulated the search entry after deletion.")
    acc, srch, fl = s.rid("account"), s.rid("search"), s.rid("data_flow")
    s.account_chain(acc)
    s.activity("SYNC_RECORD", "search_service", fl, "SUCCESS", f"Active connector repopulated downstream resource {srch}.",
               source="integration_service", at=s.t(-30))
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("search_service", "customer_search_documents",
                       [{"resource_id": srch, "index_name": "customer_directory_v3",
                         "document": {"display_name": None, "email": s.email, "customer_reference": None}}]),
                      ("integration_service", "connector_configurations",
                       [{"resource_id": fl, "connector_name": "search_profile_indexer", "subject_selector": s.email,
                         "enabled": True, "mode": "continuous_sync"}])))
    s.expect("INCOMPLETE", (F, "search_service", srch, "REPORT_REMAINING_RECORD", "PRESENT", f),
             (F, "integration_service", fl, "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", f),
             (R, "integration_service", fl, "DISABLE_DATA_FLOW", "DISABLED", ""),
             (R, "search_service", srch, "DELETE_RECORD", "ABSENT", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "search_service", srch, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "integration_service", fl, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", ""))
    out.append(s)

    s = Scenario(5, "tombstone_leaking_email_hash", "Tombstone keeps user_id (allowed) but also the email hash (prohibited).", "PARTIALLY_COMPLETE")
    acc, tb, aud = s.rid("account"), s.rid("tombstone"), s.rid("audit_record")
    s.account_chain(acc)
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("identity_service", "deleted_customer_references",
                       [{"resource_id": tb, "subject_reference": s.uid, "name": None, "email": None, "phone": None,
                         "email_hash": email_hash(s.email), "account_status": "DELETED"}]),
                      ("security_service", "security_audit_events", [{"resource_id": aud, "subject_reference": s.uid}])))
    s.expect("INCOMPLETE", (F, "identity_service", tb, "REPORT_EXPOSED_PII", "PRESENT", f),
             (R, "identity_service", tb, "REDACT_RECORD", "REDACTED", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "security_service", aud, "VERIFY_RECORD_PRESENT", "PRESENT", ""),
             (V, "identity_service", tb, "VERIFY_RECORD_REDACTED", "REDACTED", ""))
    out.append(s)

    s = Scenario(6, "retention_required_record", "Account gone; security audit record must be retained and proven present.")
    acc, aud = s.rid("account"), s.rid("audit_record")
    s.account_chain(acc)
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("security_service", "security_audit_events",
                       [{"resource_id": aud, "subject_reference": s.uid, "event_name": "account_deletion_reviewed"}])))
    s.expect("COMPLETE", (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", f),
             (V, "security_service", aud, "VERIFY_RECORD_PRESENT", "PRESENT", f))
    out.append(s)

    s = Scenario(7, "non_deletion_request", "Address change, explicitly not a deletion.", "NOT_STARTED",
                 "Please update my shipping address. I want to keep the account active, so please do not delete anything.")
    s.expect("NOT_APPLICABLE")
    out.append(s)

    s = Scenario(8, "reused_email_across_users", "Address belonged to another user until March; that user's old record must not leak in.")
    shared = s.email
    prev_uid = f"user_9{s.n:03d}9"
    s.identities[0].update(email=shared)
    s.identities.append({"user_id": prev_uid, "name": "Previous Owner", "email": "previous.owner.c8@example.org",
                         "phone": "+1 555 0999 0000", "email_hash": email_hash("previous.owner.c8@example.org"),
                         "updated_at": "2026-03-01T00:00:00Z"})
    s.audit_log += [{"audit_id": "audit_c081", "user_id": prev_uid, "event_time": "2026-03-01T00:00:00Z", "field_name": "email",
                     "old_value": shared, "new_value": "previous.owner.c8@example.org"},
                    {"audit_id": "audit_c082", "user_id": s.uid, "event_time": "2026-03-01T00:00:00Z", "field_name": "email",
                     "old_value": "first.address.c8@example.org", "new_value": shared}]
    acc, old_srch = s.rid("account"), s.rid("search")
    s.account_chain(acc)
    s.file(bundle("2026-02-10T00:00:00Z", ("search_service", "customer_search_documents",
                                           [{"resource_id": old_srch, "index_name": "customer_directory_v3",
                                             "document": {"display_name": "Previous Owner", "email": shared, "customer_reference": None}}])),
           hours=-(s.audit - datetime(2026, 2, 10, tzinfo=timezone.utc)).total_seconds() / 3600)
    f = s.file(lookup_log([(s.t(-2), "account_service", "profile_lookup", acc, shared, "rows=0 http_status=404")]), "logs", "log")
    s.expect("COMPLETE", (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", f))
    out.append(s)

    s = Scenario(9, "false_complete_claim", "Workflow says COMPLETE but analytics still carries the email.")
    acc, an = s.rid("account"), s.rid("analytics")
    s.account_chain(acc)
    s.activity("ANONYMIZE_RECORD", "analytics_platform", an, "SUCCESS", f"Policy action completed for {an}.", at=s.t(1.0, s.reported))
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("analytics_platform", "customer_analytics_reports",
                       [{"resource_id": an, "user_id": None, "email": s.email, "phone": None, "email_hash": None}])))
    s.expect("INCOMPLETE", (F, "analytics_platform", an, "REPORT_EXPOSED_PII", "PRESENT", f),
             (R, "analytics_platform", an, "ANONYMIZE_RECORD", "ANONYMIZED", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "analytics_platform", an, "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", ""))
    out.append(s)

    s = Scenario(10, "false_not_started_claim", "Workflow says NOT_STARTED but every copy is already compliant.", "NOT_STARTED")
    acc, aud, sup, fl, bk = s.rid("account"), s.rid("audit_record"), s.rid("support"), s.rid("data_flow"), s.rid("backup")
    s.account_chain(acc)
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("security_service", "security_audit_events", [{"resource_id": aud, "subject_reference": s.uid}]),
                      ("support_platform", "support_conversations",
                       [{"resource_id": sup, "subject_reference": s.uid, "message_text": "[REDACTED]"}]),
                      ("integration_service", "connector_configurations",
                       [{"resource_id": fl, "subject_selector": s.uid, "enabled": False}]),
                      ("backup_service", "backup_catalog", [{"resource_id": bk, "subject_reference": s.uid, "restore_allowed": False}])))
    s.expect("COMPLETE", (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", f),
             (V, "security_service", aud, "VERIFY_RECORD_PRESENT", "PRESENT", f),
             (V, "support_platform", sup, "VERIFY_RECORD_REDACTED", "REDACTED", f),
             (V, "integration_service", fl, "VERIFY_DATA_FLOW_DISABLED", "DISABLED", f),
             (V, "backup_service", bk, "VERIFY_RESTORE_BLOCKED", "BLOCKED", f))
    out.append(s)

    s = Scenario(11, "near_miss_decoy", "A '.jr' look-alike address holds a live search entry; it is not the subject.")
    acc, decoy = s.rid("account"), s.rid("search")
    s.account_chain(acc)
    local, dom = s.email.split("@")
    f = s.file(bundle(s.t(-2), ("account_service", "customer_profiles", []),
                      ("search_service", "customer_search_documents",
                       [{"resource_id": decoy, "index_name": "customer_directory_v3",
                         "document": {"display_name": None, "email": f"{local}.jr@{dom}", "customer_reference": None}}])))
    f2 = s.file(lookup_log([(s.t(-1), "account_service", "profile_lookup", acc, s.email, "rows=0 http_status=404")]), "logs", "log", hours=-1)
    s.expect("COMPLETE", (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", f2))
    out.append(s)

    s = Scenario(12, "replica_drift", "Primary deleted the account; the read replica still serves it.")
    acc = s.rid("account")
    s.account_chain(acc)
    rec = json.dumps({"resource_id": acc, "customer_reference": s.uid, "full_name": "Custom Subject 12", "email": s.email,
                      "phone": "+1 555 0112 0000", "account_status": "ACTIVE"})
    sql = (f"-- Captured at: {s.t(-2)}\n-- Database topology: read_replica\nBEGIN TRANSACTION;\n"
           "CREATE TABLE customer_data_primary (resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);\n"
           "CREATE TABLE customer_data_read_replica (resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT);\n"
           f"INSERT INTO customer_data_primary VALUES('audit_record_9{s.n:03d}1','security_service','security_audit_events',"
           f"'{json.dumps({'resource_id': f'audit_record_9{s.n:03d}1', 'subject_reference': s.uid})}','{s.t(-2)}');\n"
           f"INSERT INTO customer_data_read_replica VALUES('{acc}','account_service','customer_profiles','{rec}','{s.t(-2)}');\n"
           f"INSERT INTO customer_data_read_replica VALUES('audit_record_9{s.n:03d}1','security_service','security_audit_events',"
           f"'{json.dumps({'resource_id': f'audit_record_9{s.n:03d}1', 'subject_reference': s.uid})}','{s.t(-2)}');\nCOMMIT;\n")
    f = s.file(sql, "databases", "sql")
    aud = f"audit_record_9{s.n:03d}1"
    s.expect("INCOMPLETE", (F, "account_service", acc, "REPORT_REMAINING_RECORD", "PRESENT", f),
             (R, "account_service", acc, "DELETE_RECORD", "ABSENT", ""),
             (V, "account_service", acc, "VERIFY_RECORD_ABSENT", "ABSENT", ""),
             (V, "security_service", aud, "VERIFY_RECORD_PRESENT", "PRESENT", ""))
    out.append(s)
    return out


def run(verbose: bool = True) -> dict:
    scs = scenarios()
    root = build_overlay(identities=[r for s in scs for r in s.identities], audit_log=[r for s in scs for r in s.audit_log],
                         activities=[r for s in scs for r in s.activities], evidence=[e for s in scs for e in s.evidence],
                         requests=[s.request() for s in scs])
    try:
        results = AuditEngine(root).run()
    finally:
        cleanup(root)
    gold = {s.case_id: (s.expected_status, s.expected_steps) for s in scs}
    pred = {s.case_id: (results[s.case_id].status, [x.as_json() for x in results[s.case_id].steps]) for s in scs}
    m = score(pred, gold)
    rows = []
    for s in scs:
        ok = pred[s.case_id] == gold[s.case_id] or (
            pred[s.case_id][0] == gold[s.case_id][0] and
            [{k: v for k, v in x.items()} for x in pred[s.case_id][1]] == gold[s.case_id][1])
        rows.append({"case": s.case_id, "scenario": s.name, "purpose": s.purpose, "claim": s.claim,
                     "expected": s.expected_status, "predicted": pred[s.case_id][0], "exact_match": ok,
                     "steps_expected": len(s.expected_steps), "steps_predicted": len(pred[s.case_id][1])})
    if verbose:
        for r in rows:
            print(f"{r['case']} {r['scenario']:32s} expected={r['expected']:14s} got={r['predicted']:14s} exact={r['exact_match']}")
        print("status_accuracy", m["status_accuracy"], "step F1", m["step_strict"]["f1"])
        for d in m["diffs"]:
            print(d)
    return {"rows": rows, "metrics": {k: v for k, v in m.items() if k != "diffs"}, "diffs": m["diffs"]}


if __name__ == "__main__":
    run()
