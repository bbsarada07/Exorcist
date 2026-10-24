"""LinkerAgent: which resources and worker events belong to which case.

1. Evidence links (hard): a fact carrying one of the subject's identifiers, observed inside the
   case's scope window, links its resource to the case. Content beats catalog claims: a resource
   whose own content names someone else is not linked through a catalog row (conflict ledger).
2. Account chain (global min-cost assignment): each deletion case owns at most one deletion-worker
   account delete. Evidence-linked accounts pin their event; the rest are assigned jointly with
   scipy's Hungarian solver using the measured timing (delete ~1 h before reported_at) and
   result-vs-claim agreement. A dummy column lets a case stay unlinked.
3. Policy-action chain: identifier-free resources touched by the deletion worker (e.g. anonymised
   analytics) are assigned per (event type, system) class, at most one per case, with a convex
   timing cost that keeps cases that share a reported_at in the same order as their account deletes.
Every link records how it was made and a margin (cost gap to the runner-up in that row).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import CLAIM_RESULT
from .identity import IdentityAgent, _edit_distance, near_miss
from .model import Activity
from .parsers import EvidenceStore

try:
    from scipy.optimize import linear_sum_assignment
except ImportError:  # pragma: no cover - pure-python fallback keeps the engine dependency-light
    linear_sum_assignment = None

INF = 1e6
H = 3600.0
ACCOUNT_WINDOW_AFTER_H = 3.0     # handcrafted chains put the delete up to ~0.1 h after reported_at
ACCOUNT_EXPECTED_OFFSET_H = -1.0
ACTION_WINDOW_H = (-0.75, 2.5)   # compliant actions -0.5..-0.1 h, failed/claimed attempts +0.6..+2 h
DUMMY_COST = 4.0
CONTESTED_SOLE_EVIDENCE_FAILSAFE = True  # see CONVENTIONS.md #15
OCR_TOLERANCE = 2               # max edit distance treated as an OCR misread (decoys differ by >= 3)
COOCCURRENCE_BONUS = 0.5        # candidate appears in the same evidence file as the case's linked records


@dataclass
class Link:
    resource_id: str
    mode: str                    # evidence | chain_pinned | chain_elimination | chain_soft
    margin: float | None = None
    evidence: tuple = ()         # fact evidence ids (evidence links) or activity ids (chain links)


@dataclass
class CaseLinks:
    resources: dict[str, Link] = field(default_factory=dict)
    account_event: Activity | None = None
    account_mode: str = "none"
    account_margin: float | None = None
    worker_events: list[Activity] = field(default_factory=list)
    decoys: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)


def _solve(cost):
    if linear_sum_assignment is not None:
        import numpy as np
        r, c = linear_sum_assignment(np.asarray(cost))
        return list(zip(r.tolist(), c.tolist()))
    return _hungarian(cost)


def _hungarian(cost):
    """O(n^3) Hungarian for rectangular matrices (rows <= cols)."""
    n, m = len(cost), len(cost[0])
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    return [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]


class LinkerAgent:
    def __init__(self, evidence: EvidenceStore, identity: IdentityAgent):
        self.ev = evidence
        self.id = identity

    # ---------- 1. evidence links ----------
    def _in_scope(self, case, t) -> bool:
        return t <= case.audit_at and (case.scope_start is None or t > case.scope_start)

    def _foreign_content(self, rid: str, subject_keys: set, case) -> list:
        """Content facts on this resource that identify a different person (not via catalog rows)."""
        out = []
        for f in self.ev.by_resource.get(rid, []):
            if f.kind == "link" or not self._in_scope(case, f.observed_at):
                continue
            direct = {k for k in f.keys if k[0] in ("email", "hash", "phone", "user")}
            if f.source == "ocr":  # tolerate OCR misreads ("outiook.com") of the subject's own identifiers
                direct = {k for k in direct if not any(
                    s[0] == k[0] == "email" and _edit_distance(s[1], k[1]) <= OCR_TOLERANCE for s in subject_keys)}
                if not direct:
                    continue
            if direct and not (direct & subject_keys):
                out.append((f.evidence_id, sorted(direct)))
        return out

    def evidence_links(self, case) -> CaseLinks:
        links = CaseLinks()
        subject = self.id.subjects[case.user_id]
        keys = subject.keys()
        hits: dict[str, list] = defaultdict(list)
        via_catalog_only: dict[str, bool] = {}
        for k in keys:
            for rid in self.ev.by_key.get(k, ()):
                for f in self.ev.by_resource[rid]:
                    if k in f.keys and self._in_scope(case, f.observed_at) and \
                            self.id.belongs_to(k, case.user_id, f.observed_at):
                        hits[rid].append(f)
        contested = {}
        for rid, fs in hits.items():
            content = [f for f in fs if f.kind != "link"]
            if not content:
                foreign = self._foreign_content(rid, keys, case)
                if foreign:  # catalog says ours, record content says someone else -> trust content
                    contested[rid] = fs
                    links.conflicts.append({
                        "type": "catalog_vs_content", "resource_id": rid,
                        "claim": {"evidence": sorted({f.evidence_id for f in fs}), "says": "linked to subject"},
                        "content": {"evidence": [e for e, _ in foreign], "identifiers": foreign[0][1]},
                        "trusted": "content", "why": "record content identifies a different person"})
                    continue
            links.resources[rid] = Link(rid, "evidence", None, tuple(sorted({f.evidence_id for f in fs})))
        if contested and not links.resources and CONTESTED_SOLE_EVIDENCE_FAILSAFE:
            # fail-safe: never certify a deletion from zero evidence; keep the contested record in scope
            for rid, fs in contested.items():
                links.resources[rid] = Link(rid, "evidence_contested", None, tuple(sorted({f.evidence_id for f in fs})))
            for c in links.conflicts:
                if c["resource_id"] in contested:
                    c["trusted"] = "catalog (fail-safe: contested record is the subject's only evidence)"
        # near-miss decoys seen while searching (kept as explicit rejections)
        emails = subject.emails()
        for key, rids in self.ev.by_key.items():
            if key[0] != "email" or key in keys:
                continue
            imitated = near_miss(key[1], emails)
            if not imitated:
                continue
            for rid in sorted(rids):
                seen = [f for f in self.ev.by_resource[rid] if key in f.keys and self._in_scope(case, f.observed_at)]
                if seen and rid not in links.resources:
                    links.decoys.append({"resource_id": rid, "decoy_identifier": key[1], "imitates": imitated,
                                         "evidence": sorted({f.evidence_id for f in seen})})
        return links

    # ---------- 2 + 3. worker chains ----------
    def link_all(self, cases) -> dict[str, CaseLinks]:
        deletion_cases = [c for c in cases if c.is_deletion]
        result = {c.case_id: self.evidence_links(c) for c in deletion_cases}
        owner_of: dict[str, set] = defaultdict(set)   # resource -> cases linked by evidence
        for cid, cl in result.items():
            for rid in cl.resources:
                owner_of[rid].add(cid)

        # who a resource's own content names (any time): a chain link may never contradict it
        self.content_owners: dict[str, set] = defaultdict(set)
        for rid, fs in self.ev.by_resource.items():
            for f in fs:
                if f.kind == "link":
                    continue
                for k in f.keys:
                    if k[0] in ("email", "hash", "phone", "user"):
                        self.content_owners[rid] |= (self.id.owners_of(k) or {"unknown:" + k[1]})
        cmap = {c.case_id: c for c in deletion_cases}
        self.case_files = {cid: {f.evidence_id for rid in cl.resources for f in self.ev.by_resource.get(rid, [])
                                 if f.kind != "link" and f.evidence_id.startswith("evidence_")
                                 and self._in_scope(cmap[cid], f.observed_at)}
                           for cid, cl in result.items()}
        worker = [a for a in self.ev.activities if a.is_worker]
        self._link_accounts(deletion_cases, result, owner_of,
                            [a for a in worker if a.event_type == "DELETE_RECORD" and a.target_system == "account_service"])
        self._link_actions(deletion_cases, result, owner_of,
                           [a for a in worker if a.target_system != "account_service"])
        return result

    def _cooccurs(self, rid: str, c, result) -> bool:
        """Does `rid` appear in an in-scope evidence file that also holds this case's identifier-linked records?"""
        files = {f.evidence_id for f in self.ev.by_resource.get(rid, []) if f.kind != "link" and self._in_scope(c, f.observed_at)}
        return bool(files & self.case_files[c.case_id])

    def _foreign(self, rid: str, c) -> bool:
        owners = self.content_owners.get(rid)
        return bool(owners) and c.user_id not in owners

    def _account_cost(self, a: Activity, c, result) -> float:
        if a.event_time < c.requested_at or (a.event_time - c.reported_at).total_seconds() > ACCOUNT_WINDOW_AFTER_H * H:
            return INF
        if self._foreign(a.resource_id, c):
            return INF
        off = (a.event_time - c.reported_at).total_seconds() / H
        cost = abs(off - ACCOUNT_EXPECTED_OFFSET_H)
        if a.reported_result != CLAIM_RESULT.get(c.reported_status):
            cost += 1.0
        if self._cooccurs(a.resource_id, c, result):
            cost -= COOCCURRENCE_BONUS
        return cost

    def _link_accounts(self, cases, result, owner_of, events):
        by_rid = {a.resource_id: a for a in events}
        taken = set()
        free_cases = []
        for c in cases:
            cl = result[c.case_id]
            ev_accounts = [rid for rid in cl.resources if rid.startswith("account_")]
            pinned = [by_rid[r] for r in ev_accounts if r in by_rid]
            if pinned:
                cl.account_event, cl.account_mode = pinned[0], "chain_pinned"
                taken.add(pinned[0].activity_id)
            elif ev_accounts:
                cl.account_mode = "evidence"
            else:
                free_cases.append(c)
        # an account that evidence ties to another subject can never be assigned here
        free_events = [a for a in events if a.activity_id not in taken and not owner_of.get(a.resource_id)]
        if not free_cases:
            return
        n, m = len(free_cases), len(free_events)
        cost = [[self._account_cost(a, c, result) for a in free_events] + [DUMMY_COST if i == j else INF for j in range(n)]
                for i, c in enumerate(free_cases)]
        for i, j in _solve(cost):
            c, cl = free_cases[i], result[free_cases[i].case_id]
            if j >= m or cost[i][j] >= INF:
                continue
            a = free_events[j]
            row = sorted(x for k, x in enumerate(cost[i]) if k != j and x < INF)
            feasible = sum(1 for x in cost[i][:m] if x < INF)
            cl.account_event = a
            cl.account_margin = round((row[0] if row else DUMMY_COST) - cost[i][j], 3)
            cl.account_mode = "chain_elimination" if feasible == 1 else "chain_soft"
            cl.resources[a.resource_id] = Link(a.resource_id, cl.account_mode, cl.account_margin, (a.activity_id,))
        for c in cases:
            cl = result[c.case_id]
            if cl.account_mode == "chain_pinned":
                rid = cl.account_event.resource_id
                cl.resources[rid].evidence = tuple(sorted(set(cl.resources[rid].evidence) | {cl.account_event.activity_id}))

    def _action_cost(self, a: Activity, c, result) -> float:
        off = (a.event_time - c.reported_at).total_seconds() / H
        if not (ACTION_WINDOW_H[0] <= off <= ACTION_WINDOW_H[1]) or a.event_time < c.requested_at:
            return INF
        if self._foreign(a.resource_id, c):
            return INF
        band = -0.3 if off <= 0 else 1.2
        cost = (off - band) ** 2
        if self._cooccurs(a.resource_id, c, result):
            cost -= COOCCURRENCE_BONUS
        return cost

    def _link_actions(self, cases, result, owner_of, events):
        by_class: dict[tuple, list] = defaultdict(list)
        for a in events:
            by_class[(a.event_type, a.target_system)].append(a)
        for cls, evs in sorted(by_class.items()):
            # events on resources that evidence already places somewhere: attach, don't reassign
            free = []
            for a in evs:
                owners = owner_of.get(a.resource_id)
                if owners:
                    for cid in owners:
                        result[cid].worker_events.append(a)
                else:
                    free.append(a)
            if not free:
                continue
            busy = {cid for cid, cl in result.items() if any((w.event_type, w.target_system) == cls for w in cl.worker_events)}
            cands = [c for c in cases if c.case_id not in busy]
            if not cands:
                continue
            m, n = len(free), len(cands)
            # rows = events (each event needs a home or the dummy), cols = cases + dummies
            cost = [[self._action_cost(a, c, result) for c in cands] + [DUMMY_COST if i == j else INF for j in range(m)]
                    for i, a in enumerate(free)]
            for i, j in _solve(cost):
                if j >= n or cost[i][j] >= INF:
                    continue
                a, c = free[i], cands[j]
                col = sorted(x for k, x in enumerate(cost[i][:n]) if k != j and x < INF)
                feasible = 1 + len(col)
                margin = round((col[0] if col else DUMMY_COST) - cost[i][j], 4)
                cl = result[c.case_id]
                mode = "chain_elimination" if feasible == 1 else "chain_soft"
                cl.resources.setdefault(a.resource_id, Link(a.resource_id, mode, margin, (a.activity_id,)))
                cl.worker_events.append(a)
