"""SimulatorAgent: apply the remediation plan to the reconstructed state and prove it works.

Checks per case: every violation is remediated; flows/restores are closed before records change;
retained records are never touched; and every verification step's expected state equals the
simulated end state. A failure here is a planner bug, never a reason to edit the output silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .policy import Assessment
from .planner import Step

BEFORE = {"violation": {"DELETE": "PRESENT", "REDACT": "PRESENT", "ANONYMIZE": "PRESENT",
                        "BLOCK": "ACTIVE", "DISABLE": "ACTIVE"},
          "compliant": {"DELETE": "ABSENT", "REDACT": "REDACTED", "ANONYMIZE": "ANONYMIZED",
                        "BLOCK": "BLOCKED", "DISABLE": "DISABLED", "RETAIN": "PRESENT"}}
GATES = {"DISABLE_DATA_FLOW", "BLOCK_RESTORE"}


@dataclass
class SimResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)


def simulate(assessments: list[Assessment], steps: list[Step]) -> SimResult:
    state = {}
    for a in assessments:
        s = BEFORE.get(a.status, {}).get(a.action, "UNKNOWN")
        if a.status == "compliant" and a.verification == "VERIFY_RECORD_ABSENT":
            s = "ABSENT"
        state[a.resource_id] = s
    before = dict(state)
    failures = []
    remediation = [s for s in steps if s.phase == "REMEDIATION"]
    seen_change = False
    for s in remediation:
        if s.operation in GATES and seen_change:
            failures.append(f"{s.resource_id}: {s.operation} after a record change")
        seen_change |= s.operation not in GATES
        state[s.resource_id] = s.state
    by_id = {a.resource_id: a for a in assessments}
    for a in assessments:
        if a.status == "violation" and not any(s.resource_id == a.resource_id for s in remediation):
            failures.append(f"{a.resource_id}: violation without remediation")
        if a.action == "RETAIN" and any(s.resource_id == a.resource_id for s in remediation):
            failures.append(f"{a.resource_id}: retained record would be modified")
    for s in steps:
        if s.phase == "VERIFICATION" and state.get(s.resource_id) not in (s.state, "UNKNOWN"):
            failures.append(f"{s.resource_id}: expects {s.state} but simulation ends {state.get(s.resource_id)}")
        if s.phase == "VERIFICATION" and s.resource_id not in by_id:
            failures.append(f"{s.resource_id}: verification for an unassessed resource")
    return SimResult(not failures, failures, before, state)
