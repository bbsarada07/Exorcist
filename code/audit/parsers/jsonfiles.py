"""JSON evidence: snapshot bundles, service resource exports, flat manifests, single collections."""
from __future__ import annotations

import json
from datetime import datetime

from ..config import PREFIX_SYSTEM
from ..model import Coverage, Fact
from ..util import identifier_of, parse_ts
from .flat import flat_record
from .records import record_to_fact

KNOWN_SYSTEMS = set(PREFIX_SYSTEM.values())


def _collection(records, *, evidence_id, observed_at, cite_at, collection, store, location, source):
    facts = []
    for rec in records:
        if "record_type" in rec and "recorded_at" in rec:
            f = flat_record(rec, evidence_id, cite_at, source + "_flat")
        else:
            f = record_to_fact(rec, evidence_id=evidence_id, observed_at=observed_at, cite_at=cite_at,
                               location=location, collection=collection,
                               system_hint=store if store in KNOWN_SYSTEMS else None, source=source)
        if f:
            facts.append(f)
    return facts


def _service_export(d: dict, evidence_id: str, cite_at: datetime) -> list[Fact]:
    facts = []
    for system, sections in d["service_exports"].items():
        for kind, rows in sections.items():
            for row in rows:
                observed = parse_ts(row["observed_at"]) if row.get("observed_at") else cite_at
                rec = {k: v for k, v in row.items() if k not in ("observed_at", "hits", "query", "status_code")}
                if kind == "index_queries":
                    docs = (row.get("hits") or {}).get("documents") or []
                    doc = next((x for x in docs if x.get("resource_id") == row["resource_id"]), None)
                    rec.update(doc or {})
                f = record_to_fact(rec, evidence_id=evidence_id, observed_at=observed, cite_at=cite_at,
                                   location="primary", collection=kind, system_hint=system, source="service_export")
                if not f:
                    continue
                if kind == "profile_lookups":
                    f.exists = row.get("status_code") == 200 and row.get("profile") is not None
                    f.kind = "lookup"
                elif kind == "index_queries":
                    f.exists = bool((row.get("hits") or {}).get("total"))
                    f.kind = "lookup"
                    if row.get("query"):
                        ident = identifier_of(row["query"])
                        if ident:
                            f.keys = f.keys | {ident}
                facts.append(f)
    return facts


def parse_json(text: str, evidence_id: str, cite_at: datetime) -> tuple[list[Fact], list[Coverage]]:
    d = json.loads(text)
    facts: list[Fact] = []
    coverage: list[Coverage] = []
    if "snapshots" in d:
        for snap in d["snapshots"]:
            observed = parse_ts(snap["captured_at"])
            store, coll = snap["data_store"], snap["collection"]
            fs = _collection(snap["records"], evidence_id=evidence_id, observed_at=observed, cite_at=cite_at,
                             collection=coll, store=store, location="primary", source="snapshot_bundle")
            facts += fs
            if coll != "operational_record_history":
                system = store if store in KNOWN_SYSTEMS else None
                systems = {f.system_id for f in fs} or ({system} if system else set())
                for s in systems:
                    coverage.append(Coverage(evidence_id, observed, cite_at, s, coll,
                                             frozenset(f.resource_id for f in fs if f.system_id == s),
                                             "snapshot_bundle"))
    elif "service_exports" in d:
        facts += _service_export(d, evidence_id, cite_at)
    elif "records" in d:
        observed = parse_ts(d.get("captured_at") or d.get("exported_at")) if (d.get("captured_at") or d.get("exported_at")) else cite_at
        facts += _collection(d["records"], evidence_id=evidence_id, observed_at=observed, cite_at=cite_at,
                             collection=d.get("collection", ""), store=d.get("source", ""), location="primary",
                             source="json_collection")
    return facts, coverage
