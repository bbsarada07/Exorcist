"""system_activity.csv -> Activity rows (+ the few rows that are evidence rather than claims)."""
from __future__ import annotations

import re
from pathlib import Path

from ..model import Activity, Fact, resources_in, system_of
from ..util import identifiers_in_text, parse_ts, read_csv

LINK_ALIAS = re.compile(r"linked (\S+) \(([^)]+)\)|confirmed (\S+) \(([^)]+)\)")


def load_activities(path: Path) -> list[Activity]:
    out = []
    for r in read_csv(path):
        mentions = tuple(x for x in resources_in(r["details"]) if x != r["resource_id"])
        out.append(Activity(r["activity_id"], parse_ts(r["event_time"]), r["event_type"], r["source_system"],
                            r["target_system"], r["resource_id"], r["reported_result"], r["details"], mentions))
    return out


def catalog_aliases(activities: list[Activity]) -> dict[str, str]:
    """Alias text -> resource id, from data-catalog link rows (statement numbers, file names, user keys)."""
    aliases = {}
    for a in activities:
        if a.event_type == "LINK_RESOURCE_IDENTITY":
            m = LINK_ALIAS.search(a.details)
            if m:
                rid, alias = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                aliases[alias] = rid
    return aliases


def activity_facts(activities: list[Activity]) -> list[Fact]:
    """Activity rows that carry positive state/link information (still weaker than file evidence)."""
    facts = []
    for a in activities:
        system = system_of(a.resource_id) or a.target_system
        if a.event_type == "LINK_RESOURCE_IDENTITY":
            attrs = {"exclusive": "belongs only" in a.details}
            facts.append(Fact(a.activity_id, a.event_time, a.event_time, a.resource_id, system, "catalog",
                              None, None, frozenset(), frozenset(identifiers_in_text(a.details)), attrs,
                              "link", "activity_link", a.details[:160]))
        elif a.event_type == "CHECK_DATA_FLOW" and "remains enabled" in a.details:
            facts.append(Fact(a.activity_id, a.event_time, a.event_time, a.resource_id, system, "check", True,
                              None, frozenset(), frozenset(), {"enabled": True}, "check", "activity_check",
                              a.details[:160]))
        elif a.event_type == "CHECK_RESTORE_ACCESS" and "can still be restored" in a.details:
            facts.append(Fact(a.activity_id, a.event_time, a.event_time, a.resource_id, system, "check", True,
                              None, frozenset(), frozenset(), {"restore_allowed": True}, "check",
                              "activity_check", a.details[:160]))
    return facts
