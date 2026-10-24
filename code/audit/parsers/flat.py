"""Flat lookup lines: `system | resource | RECORD_TYPE | RESULT | identifier`.

Shared by the handover text file, record_lookup log lines, flat JSON manifests and
`operational_record_history` collections. RECORD_TYPE is the policy data category.
"""
from __future__ import annotations

import re
from datetime import datetime

from ..model import Fact, system_of
from ..util import identifier_of, parse_ts

RESULT_STATE = {
    "FOUND": dict(exists=True),
    "NOT_FOUND": dict(exists=False),
    "IDENTIFIABLE": dict(exists=True, exposed=True),
    "ANONYMIZED": dict(exists=True, exposed=False),
    "REDACTED": dict(exists=True, exposed=False),
    "ACTIVE": dict(exists=True, active=True),
    "DISABLED": dict(exists=True, active=False),
    "BLOCKED": dict(exists=True, active=False),
}


def flat_fact(*, evidence_id: str, observed_at: datetime, cite_at: datetime, system: str, resource_id: str,
              record_type: str, result: str, identifier: str, source: str) -> Fact | None:
    sem = RESULT_STATE.get(result.upper())
    system = system_of(resource_id) or system
    if sem is None or not system:
        return None
    ident = identifier_of(identifier)
    keys = {ident} if ident else set()
    exposed = set()
    if ident and ident[0] == "user":
        exposed.add("user_ref")
    direct_kind = ident[0] if ident and ident[0] != "user" else "email"
    if sem.get("exposed") is True:
        exposed.add(direct_kind)          # IDENTIFIABLE: content still carries a direct identifier
    elif sem.get("exposed") is None and ident and ident[0] != "user":
        exposed.add(direct_kind)          # FOUND/ACTIVE keyed by an email: the copy holds that email
    attrs = {}
    if "active" in sem:
        if system == "integration_service":
            attrs["enabled"] = sem["active"]
        elif system == "backup_service":
            attrs["restore_allowed"] = sem["active"]
    return Fact(evidence_id=evidence_id, observed_at=observed_at, cite_at=cite_at, resource_id=resource_id,
                system_id=system, exists=sem["exists"], category=record_type.upper() or None,
                exposed=frozenset(exposed), keys=frozenset(keys), attrs=attrs, kind="lookup", source=source,
                note=f"{record_type}:{result}")


def parse_flat_text(text: str, evidence_id: str, cite_at: datetime) -> list[Fact]:
    """Pipe-delimited handover style: `- ts | system | resource | TYPE | RESULT | identifier`."""
    facts = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.lstrip("- ").split("|")]
        if len(parts) != 6 or not re.match(r"\d{4}-\d\d-\d\dT", parts[0]):
            continue
        f = flat_fact(evidence_id=evidence_id, observed_at=parse_ts(parts[0]), cite_at=cite_at, system=parts[1],
                      resource_id=parts[2], record_type=parts[3], result=parts[4], identifier=parts[5],
                      source="flat_text")
        if f:
            facts.append(f)
    return facts


def flat_record(rec: dict, evidence_id: str, cite_at: datetime, source: str) -> Fact | None:
    ident = rec.get("subject_reference") or rec.get("lookup_value") or ""
    return flat_fact(evidence_id=evidence_id, observed_at=parse_ts(rec["recorded_at"]), cite_at=cite_at,
                     system=rec.get("system", ""), resource_id=rec["resource_id"],
                     record_type=rec.get("record_type", ""), result=rec.get("result", ""),
                     identifier=ident, source=source)
