"""The investigator's tools. Each one answers one narrow question against the participant evidence and returns a
short summary plus structured items. They read the parsed fact table, the raw log lines and system_activity.csv;
they never consult the main engine's linker, so the investigator discovers resources on its own.

Only the store types listed in docs/DATA_NOTES.md §9 are queried (audit.config.STORE_TYPE).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from audit.config import STORE_TYPE
from audit.model import system_of
from audit.parsers.logs import parse_line
from audit.util import RESOURCE_RE, identifier_of, identifiers_in_text, parse_ts

LOG_SOURCES = ("log", "log_record_lookup")
ACTIVITY_SOURCES = ("activity_link", "activity_check")
STORES = tuple(STORE_TYPE)          # the investigated store types, nothing else


@dataclass
class LogEvent:
    file_id: str
    line: int
    ts: datetime
    cite_at: datetime
    trace_id: str
    event: str
    resource_id: str | None
    keys: frozenset              # identifiers printed on this very line (no trace join)


@dataclass
class ToolResult:
    summary: str
    items: list = field(default_factory=list)


class Tools:
    def __init__(self, engine):
        self.engine = engine
        self.ev = engine.ev
        self.identity = engine.identity
        self.timeline = engine.timeline
        self.logs: list[LogEvent] = []
        self.log_by_key: dict[tuple, list[int]] = defaultdict(list)
        self.log_by_trace: dict[tuple, list[int]] = defaultdict(list)
        for fid, row in sorted(self.ev.manifest.items()):
            if not row["file_path"].lower().endswith(".log"):
                continue
            text = (engine.dataset_dir / row["file_path"]).read_text(encoding="utf-8")
            for n, raw in enumerate(text.splitlines(), 1):
                ev = parse_line(raw)
                if not ev:
                    continue
                rid = ev.get("resource_id") if isinstance(ev.get("resource_id"), str) and system_of(ev["resource_id"]) else None
                keys = set()
                for k, v in ev.items():
                    if k in ("resource_id", "ts") or not isinstance(v, str) or RESOURCE_RE.fullmatch(v):
                        continue
                    ident = identifier_of(v)
                    if ident:
                        keys.add(ident)
                e = LogEvent(fid, n, parse_ts(ev["ts"]), row["captured"], str(ev.get("trace_id") or ""), ev["event"], rid,
                             frozenset(keys))
                i = len(self.logs)
                self.logs.append(e)
                for k in keys:
                    self.log_by_key[k].append(i)
                if e.trace_id:
                    self.log_by_trace[(fid, e.trace_id)].append(i)
        self.activity_ids = {a.activity_id: a for a in self.ev.activities}
        self.act_by_key: dict[tuple, list] = defaultdict(list)
        self.act_by_resource: dict[str, list] = defaultdict(list)
        for a in self.ev.activities:
            for k in identifiers_in_text(a.details):
                self.act_by_key[k].append(a)
            self.act_by_resource[a.resource_id].append(a)
            for m in a.mentions:
                self.act_by_resource[m].append(a)
        self.facts_by_file: dict[str, list] = defaultdict(list)
        for f in self.ev.facts:
            self.facts_by_file[f.evidence_id].append(f)

    # ------------------------------------------------------------ identity
    def lookup_identity(self, email: str, at: datetime) -> ToolResult:
        res = self.identity.resolve(email, at)
        if res.user_id is None:
            return ToolResult(f"email resolves to no subject ({res.match})", [])
        subject = self.identity.subjects[res.user_id]
        # what the identity snapshot + audit log state; derived hashes of old emails are NOT listed by the registry
        ids = sorted({(i.kind, i.value, i.origin) for i in subject.identifiers if i.kind != "name" and i.origin != "derived"})
        return ToolResult(f"{res.user_id} ({res.match} address); {len(ids)} registry identifiers", [res.user_id, ids])

    # ------------------------------------------------------------ stores
    def query_snapshot(self, system: str, identifiers: set, in_scope, resources: tuple = ()) -> ToolResult:
        """Record-level evidence (SQL, JSON, flat lookups, documents) for a store: rows carrying any of the
        identifiers, or every row of the given resource ids (inspecting a store a lead pointed to)."""
        hits = defaultdict(set)
        if resources:
            for rid in resources:
                for f in self.ev.by_resource.get(rid, []):
                    if f.source not in LOG_SOURCES + ACTIVITY_SOURCES and in_scope(f.observed_at):
                        hits[rid].add(f.evidence_id)
        else:
            for k in sorted(identifiers):
                for rid in sorted(self.ev.by_key.get(k, ())):
                    if system_of(rid) != system:
                        continue
                    for f in self.ev.by_resource[rid]:
                        if k in f.keys and f.kind != "link" and f.source not in LOG_SOURCES + ACTIVITY_SOURCES \
                                and in_scope(f.observed_at):
                            hits[rid].add((f.evidence_id, k))
        items = sorted(hits.items())
        what = f"resource(s) {', '.join(resources)}" if resources else f"{len(identifiers)} identifier(s)"
        return ToolResult(f"{STORE_TYPE.get(system, system)}: {len(items)} record(s) for {what}", items)

    # ------------------------------------------------------------ logs + activity stream
    def search_logs(self, in_scope, identifiers: set = frozenset(), trace: tuple | None = None) -> ToolResult:
        """Operational log lines (and activity rows) that print an identifier, or every line of one trace."""
        if trace is not None:
            evs = [self.logs[i] for i in self.log_by_trace.get(trace, ()) if in_scope(self.logs[i].ts)]
            return ToolResult(f"trace {trace[1]} in {trace[0]}: {len(evs)} line(s), "
                              f"{len({e.resource_id for e in evs if e.resource_id})} resource(s)", evs)
        evs = sorted({i for k in identifiers for i in self.log_by_key.get(k, ()) if in_scope(self.logs[i].ts)})
        lines = [self.logs[i] for i in evs]
        acts = sorted({a.activity_id: a for k in identifiers for a in self.act_by_key.get(k, ()) if in_scope(a.event_time)}.values(),
                      key=lambda a: a.activity_id)
        return ToolResult(f"{len(lines)} log line(s) and {len(acts)} activity row(s) print the identifiers", [lines, acts])

    def get_activity_chain(self, rid: str, until: datetime) -> ToolResult:
        acts = sorted((a for a in self.act_by_resource.get(rid, []) if a.event_time <= until),
                      key=lambda a: (a.event_time, a.activity_id))
        worker = [a for a in acts if a.is_worker and a.resource_id == rid]
        jobs = [a for a in acts if "repopulated downstream resource" in a.details]
        return ToolResult(f"{len(acts)} activity row(s): {len(worker)} deletion-worker, {len(jobs)} recreation job(s)", acts)

    def check_flow(self, rid: str, until: datetime) -> ToolResult:
        st = self.timeline.state(rid, "integration_service", until)
        targets = sorted({m for o in st.observations for m in o.attrs.get("recreated", [])})
        return ToolResult(f"connector enabled={st.attrs.get('enabled')}; recreated {len(targets)} downstream record(s)",
                          [st.attrs.get("enabled"), targets])

    def check_restore(self, rid: str, until: datetime) -> ToolResult:
        st = self.timeline.state(rid, "backup_service", until)
        targets = sorted({m for o in st.observations for m in o.attrs.get("recreated", [])})
        return ToolResult(f"restore_allowed={st.attrs.get('restore_allowed')}; restored {len(targets)} record(s)",
                          [st.attrs.get("restore_allowed"), targets])

    def read_evidence(self, file_id: str, known: set, user_id: str, in_scope) -> ToolResult:
        """Read one file: identifiers that sit next to a known identifier and belong only to this subject."""
        new = set()
        for f in self.facts_by_file.get(file_id, []):
            if not in_scope(f.observed_at) or not (f.keys & known):
                continue
            for k in f.keys - known:
                if k[0] in ("email", "hash", "phone", "user") and self.identity.owners_of(k) == {user_id}:
                    new.add(k)
        return ToolResult(f"{file_id}: {len(new)} new identifier(s) of the subject", sorted(new))
