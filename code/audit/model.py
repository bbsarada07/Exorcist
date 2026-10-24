"""Shared data shapes. Every evidence format is normalised into `Fact` and `Coverage`."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .config import PREFIX_SYSTEM
from .util import RESOURCE_RE

DIRECT = ("email", "name", "phone", "hash")  # identifiers a tombstone/redacted record must not hold


def system_of(resource_id: str) -> str | None:
    best = None
    for prefix, system in PREFIX_SYSTEM.items():
        if resource_id.startswith(prefix + "_") and (best is None or len(prefix) > len(best[0])):
            best = (prefix, system)
    return best[1] if best else None


@dataclass
class Fact:
    """One observation of one resource in one place at one time."""

    evidence_id: str                  # file_id, or activity_id for activity-derived facts
    observed_at: datetime             # time the observation refers to (line / inner snapshot time)
    cite_at: datetime                 # earliest time the evidence item existed (manifest captured_at)
    resource_id: str
    system_id: str
    location: str = "primary"         # table / replica / collection the copy lives in
    exists: bool | None = True        # False = explicit "not found"; None = no existence claim
    category: str | None = None       # explicit policy category stated by the source
    exposed: frozenset = frozenset()  # direct identifier kinds present in content (+ "user_ref")
    keys: frozenset = frozenset()     # (kind, value) identifiers linking this record to a person
    attrs: dict = field(default_factory=dict)  # enabled, restore_allowed, download_available, ...
    kind: str = "record"              # record | lookup | scan | link | check
    source: str = ""                  # parser name, for traceability
    note: str = ""                    # short human-readable excerpt


@dataclass
class Coverage:
    """A snapshot that lists *all* records of a system at a point in time (enables absence proofs)."""

    evidence_id: str
    observed_at: datetime
    cite_at: datetime
    system_id: str
    location: str
    present: frozenset                # resource ids listed in that snapshot
    source: str = ""


@dataclass
class Activity:
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str
    mentions: tuple = ()              # resource ids mentioned in details (e.g. downstream resource)

    @property
    def is_worker(self) -> bool:
        return self.source_system == "deletion_worker"


def resources_in(text: str) -> list[str]:
    return RESOURCE_RE.findall(text)
