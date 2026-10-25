"""Investigator loop: a deterministic controller that chooses the next lookup from what the last lookups found.

State   known identifiers, hypotheses, resources tied to the subject (with how and at which hop), and a frontier of
        lookups still to do. Each frontier entry records the finding that put it there.
Policy  pop the highest-priority open lead (identity expansion > identifier sweeps > following a lead > context),
        ties broken by the order the leads were found. Stop when the frontier is empty.
Leads   identity found -> sweep every investigated store and the logs with the identifiers
        a log line prints an identifier -> follow its trace to the lines that name the resource
        a record is found -> read its file for more of the subject's identifiers; pull its activity chain
        a new identifier appears -> re-sweep every store with it
        a sync job / connector is found -> check it, inspect each destination record it recreated
        a backup is found -> check its restore path and what it restored
        a record was recreated by a job -> check the connector / backup that did it
State and policy at audit_at reuse the engine's TimelineAgent and PolicyAgent, so any disagreement with the main
engine comes from *which resources were discovered*, not from a second copy of the rules.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from audit.config import STORE_TYPE
from audit.model import system_of

from .tools import STORES, Tools

P_IDENTITY, P_EXPAND, P_SWEEP, P_LEAD, P_CONTEXT = 0, 1, 2, 3, 4
PRIORITY_NAME = {P_IDENTITY: "identity", P_EXPAND: "identity expansion", P_SWEEP: "identifier sweep",
                 P_LEAD: "follow a lead", P_CONTEXT: "context"}
MAX_STEPS = 800


@dataclass(order=True)
class Action:
    priority: int
    seq: int
    tool: str = field(compare=False)
    args: dict = field(compare=False)
    hypothesis: str = field(compare=False)
    because: str = field(compare=False)


@dataclass
class Found:
    resource_id: str
    how: str          # identifier-on-record | identifier-on-log-line | trace-sibling | catalog | sync-destination |
                      # restore-target | recreator
    hop: int          # 1 = an identifier query returned it; 2 = reached only by following a lead
    lead: str         # the finding that led here
    evidence: set = field(default_factory=set)


@dataclass
class InvestigationResult:
    case_id: str
    status: str
    findings: set
    resources: dict
    assessments: list
    trace: list
    steps: int
    exhausted: bool
    identifiers_discovered: list


class Investigation:
    def __init__(self, tools: Tools, engine, case):
        self.t, self.engine, self.case = tools, engine, case
        self.known: dict[tuple, str] = {}
        self.labels: dict[tuple, str] = {}
        self.hypotheses: list[str] = []
        self.found: dict[str, Found] = {}
        self.workers: dict[str, list] = {}
        self.frontier: list[Action] = []
        self.done: set = set()
        self.seq = 0
        self.trace: list[dict] = []
        self.discovered: list[str] = []

    # ---------- helpers ----------
    def in_scope(self, t) -> bool:
        c = self.case
        return t <= c.audit_at and (c.scope_start is None or t > c.scope_start)

    def owns(self, key, t) -> bool:
        return self.case.user_id is not None and self.engine.identity.belongs_to(key, self.case.user_id, t)

    def label(self, key) -> str:   # identifiers are never written to the trace, only their kind and provenance
        if key not in self.labels:
            self.labels[key] = f"{key[0]}#{sum(1 for k in self.labels if k[0] == key[0]) + 1}({self.known.get(key, '?')})"
        return self.labels[key]

    def push(self, priority, tool, args, hypothesis, because):
        sig = (tool, tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple, set, frozenset)) else v) for k, v in args.items())))
        if sig in self.done:
            return
        self.done.add(sig)
        self.seq += 1
        heapq.heappush(self.frontier, Action(priority, self.seq, tool, args, hypothesis, because))

    def add(self, rid, how, hop, lead, evidence=()) -> bool:
        if system_of(rid) not in STORES:
            return False
        if rid in self.found:
            self.found[rid].evidence |= set(evidence)
            return False
        self.found[rid] = Found(rid, how, hop, lead, set(evidence))
        self.hypotheses.append(f"{rid} holds the subject's data ({how}, hop {hop})")
        system = system_of(rid)
        self.push(P_CONTEXT, "get_activity_chain", {"resource_id": rid}, f"who touched {rid} and what it recreated",
                  f"{rid} was tied to the subject ({how})")
        if system == "integration_service":
            self.push(P_LEAD, "check_flow", {"resource_id": rid}, f"{rid} still syncs the subject's data",
                      f"a sync connector {rid} was found")
        if system == "backup_service":
            self.push(P_LEAD, "check_restore", {"resource_id": rid}, f"{rid} can restore the subject's data",
                      f"a backup {rid} was found")
        for e in sorted(evidence):
            if e.startswith("evidence_"):
                self.push(P_EXPAND, "read_evidence", {"file_id": e}, f"{e} holds more identifiers of the subject",
                          f"{rid} was found in {e}")
        return True

    def sweep(self, keys: set, why: str):
        ks = sorted(keys)
        for system in STORES:
            self.push(P_SWEEP, "query_snapshot", {"system": system, "identifiers": ks},
                      f"{STORE_TYPE[system]} holds records with these identifiers", why)
        self.push(P_SWEEP, "search_logs", {"identifiers": ks}, "operational logs print these identifiers", why)

    # ---------- the loop ----------
    def run(self) -> InvestigationResult:
        c = self.case
        self.push(P_IDENTITY, "lookup_identity", {"email": "request email"}, "the request email identifies one subject",
                  "start: the request names only an email")
        steps = 0
        while self.frontier and steps < MAX_STEPS:
            a = heapq.heappop(self.frontier)
            steps += 1
            before = set(self.found)
            summary = self.execute(a)
            new = sorted(set(self.found) - before)
            self.trace.append({
                "case_id": c.case_id, "step": steps, "hypothesis": a.hypothesis, "tool": a.tool,
                "args": self.public_args(a.args), "result": summary,
                "new_findings": [{"resource_id": r, "how": self.found[r].how, "hop": self.found[r].hop} for r in new],
                "chosen_because": f"{PRIORITY_NAME[a.priority]}: {a.because}",
                "frontier_after": len(self.frontier)})
        return self.finish(steps, exhausted=not self.frontier)

    def public_args(self, args: dict) -> dict:
        out = {}
        for k, v in args.items():
            if k == "identifiers":
                out[k] = [self.label(x) for x in v]
            elif k == "trace":
                out[k] = {"file_id": v[0], "trace_id": v[1]}
            else:
                out[k] = v
        return out

    def execute(self, a: Action) -> str:
        c, t = self.case, self.t
        if a.tool == "lookup_identity":
            r = t.lookup_identity(c.email, c.requested_at)
            if not r.items:
                return r.summary
            uid, ids = r.items
            for kind, value, origin in ids:
                self.known[(kind, value)] = origin
            self.hypotheses.append(f"subject is {uid}")
            self.sweep(set(self.known), f"identity registry lists {len(ids)} identifiers for {uid}")
            return r.summary

        if a.tool == "query_snapshot":
            keys = set(a.args.get("identifiers", ()))
            res = t.query_snapshot(a.args["system"], keys, self.in_scope, tuple(a.args.get("resources", ())))
            for rid, hits in res.items:
                if a.args.get("resources"):
                    self.add(rid, a.args["how"], 2, a.args["lead"], hits)
                    continue
                files = {e for e, k in hits if self.owns(k, self._fact_time(rid, e, k))}
                if files:
                    self.add(rid, "identifier-on-record", 1, f"identifier in {', '.join(sorted(files))}", files)
            return res.summary

        if a.tool == "search_logs":
            if "trace" in a.args:
                res = t.search_logs(self.in_scope, trace=a.args["trace"])
                for e in res.items:
                    if e.resource_id:
                        self.add(e.resource_id, "trace-sibling", 2, a.args["lead"], {e.file_id})
                return res.summary
            keys = set(a.args["identifiers"])
            res = t.search_logs(self.in_scope, identifiers=keys)
            lines, acts = res.items
            for e in lines:
                own = {k for k in e.keys & keys if self.owns(k, e.ts)}
                if not own:
                    continue
                if e.resource_id:
                    self.add(e.resource_id, "identifier-on-log-line", 1, f"{e.file_id} line {e.line}", {e.file_id})
                if e.trace_id:
                    self.push(P_LEAD, "search_logs", {"trace": (e.file_id, e.trace_id),
                                                      "lead": f"{e.file_id} line {e.line} printed {self.label(sorted(own)[0])}"},
                              "the lookup trace resolves to the resource it read",
                              f"{e.file_id} line {e.line} printed a subject identifier in trace {e.trace_id}")
            for act in acts:
                if act.event_type == "LINK_RESOURCE_IDENTITY":
                    self.add(act.resource_id, "catalog", 1, f"catalog row {act.activity_id}", {act.activity_id})
            return res.summary

        if a.tool == "get_activity_chain":
            rid = a.args["resource_id"]
            res = t.get_activity_chain(rid, c.audit_at)
            self.workers[rid] = [x for x in res.items if x.is_worker and x.resource_id == rid]
            for job in res.items:
                if "repopulated downstream resource" not in job.details:
                    continue
                if job.resource_id == rid:   # rid is the connector / backup: inspect every destination it recreated
                    for m in job.mentions:
                        self._inspect(m, "sync-destination" if system_of(rid) == "integration_service" else "restore-target",
                                      f"{job.activity_id} ({job.event_type}) on {rid} recreated {m}")
                elif rid in job.mentions:    # rid was recreated: the job's connector / backup is a live path
                    self.add(job.resource_id, "recreator", 2, f"{job.activity_id} recreated {rid}", {job.activity_id})
            return res.summary

        if a.tool in ("check_flow", "check_restore"):
            rid = a.args["resource_id"]
            res = (t.check_flow if a.tool == "check_flow" else t.check_restore)(rid, c.audit_at)
            for m in res.items[1]:
                self._inspect(m, "sync-destination" if a.tool == "check_flow" else "restore-target",
                              f"{rid} recreated {m}")
            return res.summary

        if a.tool == "read_evidence":
            res = t.read_evidence(a.args["file_id"], set(self.known), c.user_id, self.in_scope)
            fresh = [k for k in res.items if k not in self.known]
            for k in fresh:
                self.known[k] = f"discovered in {a.args['file_id']}"
                self.discovered.append(f"{k[0]} found in {a.args['file_id']}")
            if fresh:
                self.sweep(set(fresh), f"{len(fresh)} new identifier(s) found in {a.args['file_id']}")
            return res.summary
        raise ValueError(a.tool)

    def _inspect(self, rid, how, lead):
        system = system_of(rid)
        if system in STORES:
            self.push(P_LEAD, "query_snapshot", {"system": system, "resources": [rid], "how": how, "lead": lead},
                      f"{rid} is a copy of the subject's data", lead)

    def _fact_time(self, rid, evidence_id, key):
        return min(f.observed_at for f in self.engine.ev.by_resource[rid] if f.evidence_id == evidence_id and key in f.keys)

    # ---------- verdict from what was found ----------
    def finish(self, steps, exhausted) -> InvestigationResult:
        c, eng = self.case, self.engine
        found = dict(self.found)
        # content beats a catalog claim (same principle as the engine; fail-safe if it is the only evidence)
        rejected = [rid for rid, f in found.items() if f.how == "catalog" and self._foreign_content(rid)]
        if len(rejected) < len(found):
            for rid in rejected:
                found.pop(rid)
        names = frozenset(eng.identity.subjects[c.user_id].names()) if c.user_id else frozenset()
        files = frozenset(f.evidence_id for rid in found for f in eng.ev.by_resource.get(rid, [])
                          if f.kind != "link" and f.evidence_id.startswith("evidence_") and self.in_scope(f.observed_at))
        assessments = []
        for rid in sorted(found):
            system = system_of(rid)
            state = eng.timeline.state(rid, system, c.audit_at, names, files)
            assessments.append(eng.policy.assess(state, c.audit_at, self.workers.get(rid, []), eng._exclusive(rid, c)))
        findings = {(a.finding, a.system_id, a.resource_id) for a in assessments if a.status == "violation"}
        return InvestigationResult(c.case_id, "INCOMPLETE" if findings else "COMPLETE", findings, found, assessments,
                                   self.trace, steps, exhausted, self.discovered)

    def _foreign_content(self, rid) -> bool:
        keys = set(self.known)
        for f in self.engine.ev.by_resource.get(rid, []):
            if f.kind == "link" or not self.in_scope(f.observed_at):
                continue
            direct = {k for k in f.keys if k[0] in ("email", "hash", "phone", "user")}
            if direct and not direct & keys:
                return True
        return False
