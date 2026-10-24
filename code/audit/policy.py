"""PolicyAgent: deletion_rules.csv compiled into executable checks.

Category resolution (strongest first):
  1. a category the evidence states (flat RECORD_TYPE, collection name, attachment scan);
  2. the treatment the deletion worker attempted on that resource (its *operation* reveals the
     category the workflow assigned; its *result* is only a claim);
  3. the owning system's default category.
Then the resource's reconstructed state is compared with the rule's required end state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import DELETE_OVERRIDE_CATEGORY, SYSTEM_DEFAULT_CATEGORY, WORKER_OP_TREATMENT
from .model import DIRECT, Activity
from .timeline import Observation, ResourceState
from .util import parse_ts, read_csv

ACTION_OF = {  # rule action -> (finding when violated, remediation, verification of the end state)
    "DELETE": ("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "REDACT": ("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    "ANONYMIZE": ("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"),
    "RETAIN": (None, None, "VERIFY_RECORD_PRESENT"),
    "BLOCK": ("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED"),
    "DISABLE": ("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED"),
}
# completion criteria from the problem statement that are not rows of deletion_rules.csv
FLOW_RULE = ("criterion_no_active_path", "DATA_FLOW", "DISABLE")


@dataclass
class Rule:
    rule_id: str
    category: str
    condition: str
    action: str


@dataclass
class Assessment:
    resource_id: str
    system_id: str
    category: str
    rule_id: str
    action: str                  # DELETE | REDACT | ANONYMIZE | RETAIN | BLOCK | DISABLE
    status: str                  # violation | compliant | unknown
    finding: str | None
    remediation: str | None
    verification: str | None
    proof: list[Observation] = field(default_factory=list)   # observations supporting the verdict
    category_source: str = ""
    reason: str = ""
    resurrected_by: list = field(default_factory=list)
    drift: list = field(default_factory=list)


class PolicyAgent:
    def __init__(self, dataset_dir: Path):
        self.rules = {r["data_category"]: Rule(r["rule_id"], r["data_category"], r["condition"], r["required_action"])
                      for r in read_csv(dataset_dir / "deletion_rules.csv")}

    def category(self, state: ResourceState, worker_events: list[Activity], exclusive_link: bool) -> tuple[str, str]:
        if state.explicit_category and (state.explicit_category in self.rules or state.explicit_category == "DATA_FLOW"):
            return state.explicit_category, "evidence"
        treatments = {WORKER_OP_TREATMENT.get(a.event_type) for a in worker_events if a.resource_id == state.resource_id}
        default = SYSTEM_DEFAULT_CATEGORY.get(state.system_id, "USER_PROFILE")
        if "DELETE" in treatments and state.system_id in DELETE_OVERRIDE_CATEGORY:
            return DELETE_OVERRIDE_CATEGORY[state.system_id], "worker_operation"
        if exclusive_link and state.system_id in ("support_platform", "object_storage"):
            return "SUPPORT_ATTACHMENT", "catalog_exclusive"
        return default, "system_default"

    def _action(self, category: str, audit_at: datetime, attrs: dict) -> tuple[str, str]:
        if category == "DATA_FLOW":
            return FLOW_RULE[0], "DISABLE"
        rule = self.rules.get(category)
        if rule is None:
            return "unmapped", "DELETE"
        if category == "BACKUP_ARCHIVE":
            return rule.rule_id, "BLOCK"
        if rule.action == "RETAIN":
            until = attrs.get("retention_until") or attrs.get("retained_until")
            if until and parse_ts(until) < audit_at:   # retention lapsed: no longer a required-retention record
                return rule.rule_id + ":expired", "DELETE"
        return rule.rule_id, rule.action

    def assess(self, state: ResourceState, audit_at: datetime, worker_events: list[Activity],
               exclusive_link: bool = False, name_exposed: bool = False) -> Assessment:
        category, source = self.category(state, worker_events, exclusive_link)
        rule_id, action = self._action(category, audit_at, state.attrs)
        finding, remediation, verification = ACTION_OF[action]
        exposed = set(state.exposed) | ({"name"} if name_exposed and state.exists else set())
        status, reason = "unknown", ""
        if action == "DELETE":
            status, reason = ("violation", "record still exists") if state.exists else \
                (("compliant", "record absent") if state.exists is False else ("unknown", "never observed"))
        elif action in ("REDACT", "ANONYMIZE"):
            leaking = exposed & set(DIRECT) if action == "REDACT" else exposed & (set(DIRECT) | {"user_ref"})
            if state.exists:
                status, reason = ("violation", f"exposes {sorted(leaking)}") if leaking else ("compliant", "no prohibited identifiers")
            elif state.exists is False:
                status, reason = "compliant", "record absent"
                verification = "VERIFY_RECORD_ABSENT"
        elif action == "RETAIN":
            status, reason = ("compliant", "retained record present") if state.exists else ("unknown", "retained record not observed")
        elif action == "BLOCK":
            allowed = state.attrs.get("restore_allowed")
            if allowed is True or state.resurrected_by:
                status, reason = "violation", "restore path open"
            elif allowed is False:
                status, reason = "compliant", "restore blocked"
        elif action == "DISABLE":
            enabled = state.attrs.get("enabled")
            if enabled is True:
                status, reason = "violation", "connector enabled"
            elif enabled is False:
                status, reason = "compliant", "connector disabled"
        proof = self._proof(state, status, action, exposed)
        return Assessment(state.resource_id, state.system_id, category, rule_id, action, status,
                          finding if status == "violation" else None,
                          remediation if status == "violation" else None,
                          verification, proof, source, reason, state.resurrected_by, state.drift)

    @staticmethod
    def _proof(state: ResourceState, status: str, action: str, exposed: set) -> list[Observation]:
        """Observations that show the verdict (citation candidates), oldest first."""
        out = []
        for o in state.observations:
            if o.source == "resurrection" and status != "violation":
                continue
            if action == "DELETE" or (action in ("REDACT", "ANONYMIZE") and state.exists is False):
                ok = (o.exists is True) if status == "violation" else (o.exists is False)
            elif action == "RETAIN":
                ok = o.exists is True
            elif action == "BLOCK":
                ok = o.attrs.get("restore_allowed") is (status == "violation")
            elif action == "DISABLE":
                ok = o.attrs.get("enabled") is (status == "violation")
            else:
                leaking = o.exposed & (set(DIRECT) | ({"user_ref"} if action == "ANONYMIZE" else set()))
                ok = o.exists is True and (bool(leaking) if status == "violation" else not leaking)
            if ok:
                out.append(o)
        return out
