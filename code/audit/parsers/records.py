"""Normalise one structured record (SQL row / JSON object) into a Fact."""
from __future__ import annotations

from datetime import datetime

from ..config import COLLECTION_CATEGORY
from ..model import Fact, system_of
from ..util import identifier_of, identifiers_in_text, is_null

# field name -> kind of direct identifier it carries
EMAIL_FIELDS = {"email", "owner_email", "requester_email", "customer_email", "uploaded_by"}
NAME_FIELDS = {"full_name", "name", "display_name", "requester_name"}
PHONE_FIELDS = {"phone", "owner_phone", "requester_phone"}
HASH_FIELDS = {"email_hash"}
REF_FIELDS = {"user_id", "customer_reference", "subject_reference", "subject_selector"}
TEXT_FIELDS = {"message_text"}
BOOL_ATTRS = {"enabled", "restore_allowed", "download_available", "archive_present"}
KEEP_ATTRS = {"account_status", "retention_until", "retained_until", "file_name", "connector_name",
              "destination", "mode", "event_code", "event_name", "index_name", "object_key", "archive_key"}


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in {"1", "true", "yes"}


def flatten(rec: dict) -> dict:
    out = {}
    for k, v in rec.items():
        if isinstance(v, dict) and k in ("document", "profile"):
            out.update(flatten(v))
        else:
            out[k] = v
    return out


def record_to_fact(rec: dict, *, evidence_id: str, observed_at: datetime, cite_at: datetime,
                   location: str, collection: str = "", system_hint: str | None = None,
                   source: str = "") -> Fact | None:
    rec = flatten(rec)
    rid = rec.get("resource_id")
    if is_null(rid):
        return None
    system = system_of(rid) or system_hint
    if system is None:
        return None
    exposed, keys, attrs = set(), set(), {}
    for k, v in rec.items():
        if is_null(v):
            continue
        if k in EMAIL_FIELDS:
            exposed.add("email")
        elif k in NAME_FIELDS:
            exposed.add("name")
        elif k in PHONE_FIELDS:
            exposed.add("phone")
        elif k in HASH_FIELDS:
            exposed.add("hash")
        elif k in REF_FIELDS:
            ident = identifier_of(v)
            if ident and ident[0] == "user":
                exposed.add("user_ref")
            elif ident:  # a selector that is an email: direct identifier
                exposed.add(ident[0])
        elif k in TEXT_FIELDS:
            found = identifiers_in_text(str(v))
            exposed |= {kind for kind, _ in found}
            keys |= found
        if k in BOOL_ATTRS:
            attrs[k] = _bool(v)
        elif k in KEEP_ATTRS:
            attrs[k] = v
        ident = identifier_of(v) if isinstance(v, str) else None
        if ident and k not in NAME_FIELDS:
            keys.add(ident)
    for k in NAME_FIELDS:
        if not is_null(rec.get(k)):
            keys.add(("name", str(rec[k]).strip()))
    category = COLLECTION_CATEGORY.get(collection)
    status = str(attrs.get("account_status", "")).upper()
    exists = True
    if status == "DELETED" and system == "account_service":
        exists = False
    return Fact(evidence_id=evidence_id, observed_at=observed_at, cite_at=cite_at, resource_id=rid,
                system_id=system, location=location, exists=exists, category=category,
                exposed=frozenset(exposed), keys=frozenset(keys), attrs=attrs, kind="record",
                source=source, note=collection)
