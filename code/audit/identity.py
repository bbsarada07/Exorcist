"""IdentityAgent: every identifier a subject has ever had, with validity windows.

Identifier kinds: email, hash (sha256 of normalised email), phone, user (stable user_id), name.
Names are kept for *exposure* detection only; they never link a record to a person because the
dataset contains duplicate names and near-miss decoys.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .util import email_hash, norm_email, norm_phone, parse_ts, read_csv

LINKING_KINDS = ("email", "hash", "phone", "user")


@dataclass
class Identifier:
    kind: str
    value: str
    valid_from: datetime | None   # None = since before the dataset begins
    valid_to: datetime | None     # None = still current
    origin: str                   # current | historical | derived

    def valid_at(self, t: datetime) -> bool:
        return (self.valid_from is None or self.valid_from <= t) and (self.valid_to is None or t < self.valid_to)


@dataclass
class Subject:
    user_id: str
    name: str
    identifiers: list[Identifier] = field(default_factory=list)

    def keys(self, kinds=LINKING_KINDS) -> set[tuple[str, str]]:
        return {(i.kind, i.value) for i in self.identifiers if i.kind in kinds}

    def names(self) -> set[str]:
        return {i.value for i in self.identifiers if i.kind == "name"}

    def emails(self) -> set[str]:
        return {i.value for i in self.identifiers if i.kind == "email"}


@dataclass
class Resolution:
    user_id: str | None
    match: str                    # current | historical | unresolved | ambiguous
    candidates: tuple = ()


class IdentityAgent:
    def __init__(self, dataset_dir: Path):
        self.subjects: dict[str, Subject] = {}
        self.owners: dict[tuple, set[str]] = defaultdict(set)
        users = read_csv(dataset_dir / "user_identities.csv")
        history = defaultdict(list)
        for a in read_csv(dataset_dir / "user_audit_log.csv"):
            history[a["user_id"]].append(a)
        for u in users:
            self.subjects[u["user_id"]] = self._build(u, sorted(history[u["user_id"]], key=lambda a: a["event_time"]))
        for s in self.subjects.values():
            for i in s.identifiers:
                self.owners[(i.kind, i.value)].add(s.user_id)

    @staticmethod
    def _norm(kind: str, value: str) -> str:
        return {"email": norm_email, "phone": norm_phone, "hash": str.lower}.get(kind, str.strip)(value)

    def _build(self, u: dict, changes: list[dict]) -> Subject:
        s = Subject(u["user_id"], u["name"])
        current_since = {}
        prev_change: dict[str, datetime | None] = defaultdict(lambda: None)
        for c in changes:
            kind = {"email": "email", "email_hash": "hash", "phone": "phone", "name": "name"}.get(c["field_name"])
            if not kind:
                continue
            t = parse_ts(c["event_time"])
            s.identifiers.append(Identifier(kind, self._norm(kind, c["old_value"]), prev_change[kind], t, "historical"))
            prev_change[kind] = t
            current_since[kind] = t
        for kind, col in (("email", "email"), ("hash", "email_hash"), ("phone", "phone"), ("name", "name")):
            if u.get(col):
                s.identifiers.append(Identifier(kind, self._norm(kind, u[col]), current_since.get(kind), None, "current"))
        s.identifiers.append(Identifier("user", u["user_id"], None, None, "current"))
        # every email (current or historical) also exposes the subject through its hash
        known_hashes = {i.value for i in s.identifiers if i.kind == "hash"}
        for i in list(s.identifiers):
            if i.kind == "email" and email_hash(i.value) not in known_hashes:
                s.identifiers.append(Identifier("hash", email_hash(i.value), i.valid_from, i.valid_to, "derived"))
        return s

    def resolve(self, email: str, at: datetime | None = None) -> Resolution:
        key = ("email", norm_email(email))
        owners = sorted(self.owners.get(key, ()))
        if not owners:
            return Resolution(None, "unresolved")
        if len(owners) > 1 and at is not None:  # reused address: keep the owner whose window covers `at`
            live = [o for o in owners if any(i.kind == "email" and i.value == key[1] and i.valid_at(at)
                                             for i in self.subjects[o].identifiers)]
            owners = live or owners
        if len(owners) > 1:
            return Resolution(None, "ambiguous", tuple(owners))
        uid = owners[0]
        origin = next(i.origin for i in self.subjects[uid].identifiers if (i.kind, i.value) == key)
        return Resolution(uid, origin)

    def owners_of(self, key: tuple) -> set[str]:
        return self.owners.get(key, set())

    def belongs_to(self, key: tuple, user_id: str, at: datetime) -> bool:
        """Does an observation of `key` at time `at` identify `user_id`?

        A key with a single owner always does (stale copies of an old address are still that person's).
        A key that several people held over time (reused address) identifies whoever held it at `at`.
        """
        owners = self.owners.get(key, set())
        if user_id not in owners:
            return False
        if len(owners) == 1:
            return True
        live = {o for o in owners if any((i.kind, i.value) == key and i.valid_at(at) for i in self.subjects[o].identifiers)}
        return user_id in live if live else False


def _edit_distance(a: str, b: str, cap: int = 4) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near_miss(candidate: str, subject_emails: set[str]) -> str | None:
    """Return the subject email that `candidate` imitates, if it is a near-miss (decoy) rather than a match."""
    c_local, _, c_dom = candidate.partition("@")
    for e in subject_emails:
        if e == candidate:
            return None
        local, _, dom = e.partition("@")
        if c_local.startswith(local) or local.startswith(c_local) or \
                (dom == c_dom and _edit_distance(local, c_local) <= 3):
            return e
    return None
