"""Case loading: request row + resolved subject + intent + the evidence scope window."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .identity import IdentityAgent, Resolution
from .intent import IntentResult, classify_with_fallback
from .util import case_sort_key, parse_ts, read_csv


@dataclass
class Case:
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str
    resolution: Resolution
    intent: IntentResult
    scope_start: datetime | None = None   # previous case of the same subject (its evidence is not ours)
    notes: list = field(default_factory=list)

    @property
    def user_id(self):
        return self.resolution.user_id

    @property
    def is_deletion(self) -> bool:
        return self.intent.authorises_deletion and self.user_id is not None


def load_cases(path: Path, identity: IdentityAgent, llm=None) -> list[Case]:
    return cases_from_rows(read_csv(path), identity, llm)


def cases_from_rows(rows: list[dict], identity: IdentityAgent, llm=None) -> list[Case]:
    cases = [Case(r["case_id"], r["email"], parse_ts(r["requested_at"]), r["reported_status"],
                  parse_ts(r["reported_at"]), parse_ts(r["audit_at"]), r["request_text"],
                  identity.resolve(r["email"], parse_ts(r["requested_at"])),
                  classify_with_fallback(r["request_text"], llm)) for r in rows]
    return sorted(cases, key=lambda c: case_sort_key(c.case_id))


def assign_scopes(cases: list[Case]) -> None:
    """A subject with several cases: each case only sees evidence after the previous case's audit."""
    by_user: dict[str, list[Case]] = {}
    for c in cases:
        if c.user_id:
            by_user.setdefault(c.user_id, []).append(c)
    for group in by_user.values():
        group.sort(key=lambda c: c.audit_at)
        for prev, cur in zip(group, group[1:]):
            cur.scope_start = prev.audit_at
