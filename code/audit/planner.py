"""PlannerAgent: assessments -> ordered FINDING / REMEDIATION / VERIFICATION steps.

Conventions (CONVENTIONS.md):
  COMPLETE   -> only verification of the evidenced current state: account absent + every compliant
                retained / redacted / anonymised / disabled / blocked resource, each with a citation.
  INCOMPLETE -> findings (cited) for every violation, remediation for each, then verification of the
                account, every retained record, and the end state of every remediated resource
                (evidence_id "" for future work).
Order: phase -> operation table order -> system_id -> resource_id (spec). The spec's remediation order
already disables flows and blocks restores before any record is changed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .config import OPERATION_ORDER, OPERATION_STATE, PHASES
from .policy import Assessment
from .timeline import Observation

COMPLETE_VERIFY_ACTIONS = {"RETAIN", "REDACT", "ANONYMIZE", "BLOCK", "DISABLE"}


@dataclass
class Step:
    phase: str
    system_id: str
    resource_id: str
    operation: str
    evidence_id: str = ""
    step_no: int = 0
    trace: dict = field(default_factory=dict)

    @property
    def state(self) -> str:
        return OPERATION_STATE[self.operation]

    def as_json(self) -> dict:
        return {"step_no": self.step_no, "phase": self.phase, "system_id": self.system_id,
                "resource_id": self.resource_id, "operation": self.operation, "state": self.state,
                "evidence_id": self.evidence_id}


def cite_latest_pre_audit(proof: list[Observation], audit_at: datetime, **_) -> Observation | None:
    """Default citation rule (chosen empirically, see evaluation/citation_study.py)."""
    eligible = [o for o in proof if o.cite_at <= audit_at and o.observed_at <= audit_at]
    if not eligible:
        return None
    return max(eligible, key=lambda o: (o.source != "coverage", o.evidence_id.startswith("evidence_"),
                                        o.observed_at, o.cite_at))


def sort_steps(steps: list[Step]) -> list[Step]:
    steps = sorted(steps, key=lambda s: (PHASES.index(s.phase), OPERATION_ORDER[s.phase].index(s.operation),
                                         s.system_id, s.resource_id))
    for i, s in enumerate(steps, 1):
        s.step_no = i
    return steps


class PlannerAgent:
    def __init__(self, cite=cite_latest_pre_audit):
        self.cite = cite

    def _trace(self, a: Assessment, agent: str, evidence: list[str]) -> dict:
        return {"rule_id": a.rule_id, "category": a.category, "category_source": a.category_source,
                "verdict": a.status, "reason": a.reason, "agent": agent, "evidence_chain": evidence}

    def plan(self, assessments: list[Assessment], audit_at: datetime, reported_at: datetime | None = None):
        violations = [a for a in assessments if a.status == "violation"]
        steps: list[Step] = []
        if not violations:
            for a in assessments:
                if a.status != "compliant":
                    continue
                if not (a.system_id == "account_service" or a.action in COMPLETE_VERIFY_ACTIONS):
                    continue
                obs = self.cite(a.proof, audit_at, reported_at=reported_at)
                if obs is None:
                    continue  # never emit an uncited COMPLETE verification
                steps.append(Step("VERIFICATION", a.system_id, a.resource_id, a.verification, obs.evidence_id,
                                  trace=self._trace(a, "PlannerAgent", [o.evidence_id for o in a.proof])))
            return "COMPLETE", sort_steps(steps)

        for a in violations:
            obs = self.cite(a.proof, audit_at, reported_at=reported_at)
            chain = [o.evidence_id for o in a.proof]
            steps.append(Step("FINDING", a.system_id, a.resource_id, a.finding, obs.evidence_id if obs else "",
                              trace=self._trace(a, "PolicyAgent", chain)))
            steps.append(Step("REMEDIATION", a.system_id, a.resource_id, a.remediation,
                              trace=self._trace(a, "PlannerAgent", chain)))
            steps.append(Step("VERIFICATION", a.system_id, a.resource_id, ACTION_VERIFY[a.action],
                              trace=self._trace(a, "PlannerAgent", chain)))
        remediated = {a.resource_id for a in violations}
        for a in assessments:
            if a.resource_id in remediated:
                continue
            if a.system_id == "account_service" and a.status in ("compliant", "unknown"):
                steps.append(Step("VERIFICATION", a.system_id, a.resource_id, "VERIFY_RECORD_ABSENT",
                                  trace=self._trace(a, "PlannerAgent", [o.evidence_id for o in a.proof])))
            elif a.action == "RETAIN" and a.status == "compliant":
                steps.append(Step("VERIFICATION", a.system_id, a.resource_id, "VERIFY_RECORD_PRESENT",
                                  trace=self._trace(a, "PlannerAgent", [o.evidence_id for o in a.proof])))
        return "INCOMPLETE", sort_steps(steps)


ACTION_VERIFY = {"DELETE": "VERIFY_RECORD_ABSENT", "REDACT": "VERIFY_RECORD_REDACTED",
                 "ANONYMIZE": "VERIFY_RECORD_ANONYMIZED", "BLOCK": "VERIFY_RESTORE_BLOCKED",
                 "DISABLE": "VERIFY_DATA_FLOW_DISABLED", "RETAIN": "VERIFY_RECORD_PRESENT"}
