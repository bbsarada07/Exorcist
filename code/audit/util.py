"""Small shared helpers: time parsing, identifier normalisation, CSV IO, ordering."""
from __future__ import annotations

import csv
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")
PHONE_RE = re.compile(r"\+\d[\d ()\-]{6,}\d")
RESOURCE_RE = re.compile(
    r"\b(?:account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|"
    r"legal_hold|marketing|object|cache|email_delivery)_\d+\b"
)
NULLS = {None, "", "null", "none", "None", "NULL"}


def parse_ts(value: str) -> datetime:
    """Parse the ISO-8601 timestamps used across the dataset (always UTC)."""
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_email(value: str) -> str:
    return value.strip().lower()


def norm_phone(value: str) -> str:
    return "+" + re.sub(r"\D", "", value)


def email_hash(email: str) -> str:
    """Hash convention inferred in Phase 0: sha256 of the normalised email (850/850 + 107/107 pairs)."""
    return hashlib.sha256(norm_email(email).encode("utf-8")).hexdigest()


def is_null(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in NULLS)


def identifier_of(value) -> tuple[str, str] | None:
    """Classify a single scalar as a person identifier: (kind, normalised value)."""
    if is_null(value) or not isinstance(value, str):
        return None
    v = value.strip()
    if EMAIL_RE.fullmatch(v):
        return ("email", norm_email(v))
    if HASH_RE.fullmatch(v.lower()):
        return ("hash", v.lower())
    if USER_RE.fullmatch(v):
        return ("user", v)
    if PHONE_RE.fullmatch(v):
        return ("phone", norm_phone(v))
    return None


def identifiers_in_text(text: str) -> set[tuple[str, str]]:
    """All identifiers embedded in free text (support messages, OCR, PDF text)."""
    found = {("email", norm_email(m)) for m in EMAIL_RE.findall(text)}
    found |= {("hash", m.lower()) for m in HASH_RE.findall(text.lower())}
    found |= {("user", m) for m in USER_RE.findall(text)}
    found |= {("phone", norm_phone(m)) for m in PHONE_RE.findall(text)}
    return found


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def case_sort_key(case_id: str):
    """Row order for output.csv. Swappable in one place (see CONVENTIONS.md #2).

    deletion_requests.csv is ordered by the numeric suffix; the template and the zero-padded
    samples cannot distinguish numeric from lexicographic, so we follow the input file.
    """
    m = re.search(r"(\d+)$", case_id)
    return (case_id[: m.start()], int(m.group(1))) if m else (case_id, -1)
