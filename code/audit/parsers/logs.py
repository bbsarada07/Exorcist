"""Operational logs in six syntaxes, normalised to (time, service, trace, event, key/values).

A lookup is usually split over two lines sharing a trace id: the `*_started` line carries the
lookup key (email / user id / hash) and the `*_completed` / `*_scan` line carries the resource
and its state. We join them per trace so the resource inherits the key.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime

from ..model import Fact, system_of
from ..util import RESOURCE_RE, identifier_of, parse_ts
from .flat import flat_fact
from .records import record_to_fact

KV = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$")
KEY_FIELDS = ("lookup_key", "match_key", "subject_ref", "subject_key", "owner_key", "scan_key", "correlation_key")
RECORD_FIELDS = {"email", "phone", "email_hash", "customer_reference", "customer_email", "owner_email",
                 "requester_name", "requester_email", "requester_phone", "message_text", "enabled",
                 "restore_allowed", "archive_key", "archive_present", "connector_name", "file",
                 "subject_reference", "object_key"}


def _kv(text: str) -> dict:
    return {k: v[1:-1] if v.startswith('"') else v for k, v in KV.findall(text)}


def parse_line(line: str) -> dict | None:
    m = TS.match(line.strip())
    if not m:
        return None
    ts, body = m.groups()
    ev: dict = {}
    if body.startswith("{"):
        ev = json.loads(body)
        ev.setdefault("service", ev.get("logger"))
    elif body.startswith("["):  # [LEVEL] [svc] [trace] event: k="v" ...
        mm = re.match(r"\[(\w+)\] \[([\w.-]+)\] \[([\w-]+)\] (\w+):\s*(.*)$", body)
        if not mm:
            return None
        ev = _kv(mm.group(5))
        ev.update(level=mm.group(1), service=mm.group(2), trace_id=mm.group(3), event=mm.group(4))
    elif body.startswith("<"):  # <pri>1 host svc trace - - k="v" ...
        mm = re.match(r"<\d+>1 \S+ ([\w.-]+) ([\w-]+) - - (.*)$", body)
        if not mm:
            return None
        ev = _kv(mm.group(3))
        ev.update(service=mm.group(1), trace_id=mm.group(2))
    elif " | " in body:  # LEVEL | svc | trace | event | k="v" ...
        parts = body.split(" | ", 4)
        if len(parts) < 4:
            return None
        ev = _kv(parts[4]) if len(parts) == 5 else {}
        ev.update(level=parts[0], service=parts[1], trace_id=parts[2], event=parts[3])
    else:
        ev = _kv(body)
        inner = re.search(r'message="(.*)"$', body)
        if inner:  # cloud runtime: requestId=… function=svc message="k=\"v\" …"
            ev.pop("message", None)
            ev.update(_kv(inner.group(1).replace('\\"', '"')))
            ev.setdefault("service", ev.get("function"))
            ev.setdefault("trace_id", ev.get("requestId"))
    ev["ts"] = ts
    return ev if ev.get("event") else None


def _keys_of(ev: dict) -> set:
    keys = set()
    for k in KEY_FIELDS + ("matched_value",):
        v = ev.get(k)
        if isinstance(v, str) and not RESOURCE_RE.fullmatch(v):
            ident = identifier_of(v)
            if ident:
                keys.add(ident)
    return keys


def _exists(ev: dict) -> bool | None:
    e = ev["event"]
    if "rows" in ev and str(ev["rows"]) == "0":
        return False
    if str(ev.get("http_status")) == "404":
        return False
    if e == "index_query_completed":
        return ev.get("result") == "hit" or str(ev.get("total_hits", "0")) != "0"
    if e in ("export_download_check_completed", "export_metadata_read_completed"):
        return str(ev.get("available", "true")).lower() != "false"
    if e == "deletion_marker_check":
        return str(ev.get("marker_found")).lower() != "true"
    return True


STATE_EVENTS = {
    "profile_lookup_completed", "index_query_completed", "analytics_profile_read_completed",
    "analytics_profile_read", "analytics_identity_scan", "contact_lookup_completed", "message_pii_scan",
    "attachment_pii_scan", "message_read", "support_ticket_read_completed", "audit_record_read_completed",
    "connector_config_read_completed", "connector_config_loaded", "connector_heartbeat",
    "restore_policy_read_completed", "restore_candidate_evaluated", "restore_authorization_completed",
    "export_download_check_completed", "export_metadata_read_completed", "retained_order_loaded",
    "contact_query_completed", "deletion_marker_check",
}


def parse_log(text: str, evidence_id: str, cite_at: datetime) -> list[Fact]:
    events = [ev for ev in (parse_line(l) for l in text.splitlines()) if ev]
    trace_keys: dict[str, set] = defaultdict(set)
    for ev in events:
        if ev.get("trace_id") and ev["event"].endswith("_started"):
            trace_keys[ev["trace_id"]] |= _keys_of(ev)
    facts = []
    for ev in events:
        e, rid, ts = ev["event"], ev.get("resource_id"), parse_ts(ev["ts"])
        if e == "record_lookup":
            f = flat_fact(evidence_id=evidence_id, observed_at=ts, cite_at=cite_at, system=ev.get("system", ""),
                          resource_id=ev.get("resource_id", ""), record_type=ev.get("record_type", ""),
                          result=ev.get("result", ""), identifier=ev.get("subject_reference", ""),
                          source="log_record_lookup")
            if f:
                facts.append(f)
            continue
        if e not in STATE_EVENTS or not rid or not system_of(rid):
            continue
        rec = {k: v for k, v in ev.items() if k in RECORD_FIELDS}
        if e == "message_read" and ev.get("subject_ref"):
            rec["subject_reference"] = ev["subject_ref"]
        if e == "restore_candidate_evaluated":
            rec["restore_allowed"] = str(ev.get("eligible")).lower() == "true" and \
                str(ev.get("deletion_block")).lower() != "true"
        if e == "restore_authorization_completed":
            rec["restore_allowed"] = str(ev.get("decision")).lower() != "deny"
        if e == "export_download_check_completed":
            rec["download_available"] = str(ev.get("available")).lower() == "true"
        rec["resource_id"] = rid
        f = record_to_fact(rec, evidence_id=evidence_id, observed_at=ts, cite_at=cite_at,
                           location=str(ev.get("service") or "log"), system_hint=None, source="log")
        if not f:
            continue
        f.exists = _exists(ev)
        f.kind = "scan" if e.endswith("_scan") else "lookup"
        keys = set(f.keys) | _keys_of(ev) | trace_keys.get(ev.get("trace_id", ""), set())
        if e.endswith("_scan") and ev.get("matched_value"):
            ident = identifier_of(ev["matched_value"])
            f.exposed = f.exposed | ({ident[0]} if ident else {"email"})
        if e == "contact_lookup_completed":
            f.exposed = f.exposed | {k for k, _ in _keys_of(ev) if k != "user"}
        if e == "attachment_pii_scan":
            f.category = "SUPPORT_ATTACHMENT"
        if e == "retained_order_loaded":
            f.category = "LEGAL_HOLD_RECORD"
        f.keys = frozenset(keys)
        f.note = f"{ev.get('service')}:{e}"
        facts.append(f)
    return facts
