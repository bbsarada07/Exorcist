"""SQLite-compatible SQL snapshots: typed inventories and primary/replica topology dumps."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from ..model import Coverage, Fact
from ..util import parse_ts
from .records import record_to_fact

# Table-name stem -> system it lists (used when a table is empty, so coverage still knows its system).
TABLE_SYSTEM = {
    "customer_profiles": "account_service",
    "customer_search_documents": "search_service",
    "search_documents": "search_service",
    "customer_analytics_profiles": "analytics_platform",
    "support_records": "support_platform",
    "customer_exports": "export_service",
    "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service",
}
LOCATION_SUFFIX = re.compile(r"_(primary|failover_replica|read_replica|reporting_replica|replica_[a-z_]+)$")


def _split_table(name: str) -> tuple[str, str]:
    """'customer_profiles_failover_replica' -> ('customer_profiles', 'failover_replica')."""
    m = LOCATION_SUFFIX.search(name)
    if m:
        return name[: m.start()], m.group(1)
    return name, "primary"


def parse_sql(text: str, evidence_id: str, cite_at: datetime) -> tuple[list[Fact], list[Coverage]]:
    m = re.search(r"Captured at:\s*(\S+)", text)
    snap_at = parse_ts(m.group(1)) if m else cite_at
    con = sqlite3.connect(":memory:")
    con.executescript(text)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
    facts: list[Fact] = []
    coverage: list[Coverage] = []

    scope = {}
    if "snapshot_scope" in tables:
        scope = {r["origin_system"]: parse_ts(r["captured_at"]) for r in con.execute("select * from snapshot_scope")}

    generic = [t for t in tables if "record_json" in [c[1] for c in con.execute(f'pragma table_info("{t}")')]]
    if generic:
        systems = set()
        per_table = {}
        for t in generic:
            _, loc = _split_table(t)
            ids_by_sys: dict[str, set] = {}
            for row in con.execute(f'select * from "{t}" order by resource_id'):
                rec = json.loads(row["record_json"])
                rec.setdefault("resource_id", row["resource_id"])
                f = record_to_fact(rec, evidence_id=evidence_id, observed_at=snap_at, cite_at=cite_at,
                                   location=loc, collection=row["collection_name"],
                                   system_hint=row["origin_system"], source="sql_topology")
                if f:
                    facts.append(f)
                    ids_by_sys.setdefault(row["origin_system"], set()).add(f.resource_id)
                    systems.add(row["origin_system"])
            per_table[loc] = ids_by_sys
        # every table of a topology dump lists the same set of systems -> absence in one copy is drift
        for loc, ids_by_sys in per_table.items():
            for system in sorted(systems):
                coverage.append(Coverage(evidence_id, snap_at, cite_at, system, loc,
                                         frozenset(ids_by_sys.get(system, ())), "sql_topology"))
        return facts, coverage

    for t in tables:
        if t == "snapshot_scope":
            continue
        stem, loc = _split_table(t)
        system = TABLE_SYSTEM.get(stem)
        if scope and system not in scope:
            continue  # inventory declares which systems it actually captured
        observed = scope.get(system, snap_at)
        ids = set()
        for row in con.execute(f'select * from "{t}"'):
            rec = dict(row)
            f = record_to_fact(rec, evidence_id=evidence_id, observed_at=observed, cite_at=cite_at,
                               location=loc, collection=stem, system_hint=system, source="sql_typed")
            if f:
                facts.append(f)
                ids.add(f.resource_id)
        if system:
            coverage.append(Coverage(evidence_id, observed, cite_at, system, loc, frozenset(ids), "sql_typed"))
    return facts, coverage
