"""AuditEngine: wires the agents together for every case (deterministic, no network)."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .cases import Case, assign_scopes, cases_from_rows
from .util import read_csv
from .identity import IdentityAgent
from .linker import CaseLinks, LinkerAgent
from .model import system_of
from .parsers import EvidenceStore, load_evidence
from .planner import PlannerAgent, Step
from .policy import Assessment, PolicyAgent
from .simulator import SimResult, simulate
from .timeline import TimelineAgent


@dataclass
class CaseResult:
    case: Case
    status: str
    steps: list[Step]
    assessments: list[Assessment] = field(default_factory=list)
    links: CaseLinks | None = None
    sim: SimResult | None = None

    def steps_json(self) -> str:
        return json.dumps([s.as_json() for s in self.steps], ensure_ascii=False, separators=(",", ":"))


class AuditEngine:
    def __init__(self, dataset_dir: Path, llm=None, evidence: EvidenceStore | None = None):
        self.dataset_dir = dataset_dir
        self.llm = llm
        self.ev = evidence or load_evidence(dataset_dir)
        self.identity = IdentityAgent(dataset_dir)
        self.policy = PolicyAgent(dataset_dir)
        self.timeline = TimelineAgent(self.ev)
        self.linker = LinkerAgent(self.ev, self.identity)
        self.planner = PlannerAgent()
        self.worker_by_resource = defaultdict(list)
        for a in self.ev.activities:
            if a.is_worker:
                self.worker_by_resource[a.resource_id].append(a)

    def load_all_cases(self, extra_rows: list[dict] | None = None, transform=None) -> list[Case]:
        """Sample and evaluation requests are linked together: they share subjects and worker chains.

        `transform(row) -> row` lets metamorphic tests mutate requests without touching dataset/.
        """
        cases = []
        for name in ("sample_deletion_requests.csv", "deletion_requests.csv"):
            path = self.dataset_dir / name
            if path.exists():
                rows = read_csv(path)
                cases += cases_from_rows([transform(dict(r)) for r in rows] if transform else rows, self.identity, self.llm)
        if extra_rows:  # custom evaluation cases / mutations
            cases += cases_from_rows(extra_rows, self.identity, self.llm)
        assign_scopes(cases)
        return cases

    def _exclusive(self, rid: str, case: Case) -> bool:
        return any(f.kind == "link" and f.attrs.get("exclusive") and f.observed_at <= case.audit_at
                   for f in self.ev.by_resource.get(rid, []))

    def assess_case(self, case: Case, links: CaseLinks) -> list[Assessment]:
        out = []
        names = frozenset(self.identity.subjects[case.user_id].names())
        case_files = frozenset(self.linker.case_files.get(case.case_id, ()))
        for rid in sorted(links.resources):
            system = system_of(rid)
            if system is None:
                continue
            state = self.timeline.state(rid, system, case.audit_at, names, case_files)
            workers = [a for a in self.worker_by_resource.get(rid, []) if a.event_time <= case.audit_at]
            out.append(self.policy.assess(state, case.audit_at, workers, self._exclusive(rid, case)))
        return out

    def run(self, extra_rows: list[dict] | None = None, transform=None) -> dict[str, CaseResult]:
        cases = self.load_all_cases(extra_rows, transform)
        links = self.linker.link_all(cases)
        results = {}
        for case in cases:
            if not case.is_deletion:
                results[case.case_id] = CaseResult(case, "NOT_APPLICABLE", [])
                continue
            cl = links[case.case_id]
            assessments = self.assess_case(case, cl)
            status, steps = self.planner.plan(assessments, case.audit_at, case.reported_at)
            results[case.case_id] = CaseResult(case, status, steps, assessments, cl, simulate(assessments, steps))
        return results
