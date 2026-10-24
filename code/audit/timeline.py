"""TimelineAgent: what did each resource look like at audit_at?

An *observation* = one evidence item's view of one resource at one time, merged over the copies
(locations) it shows: present in any copy beats absent (a replica copy is a remaining record).
Sources: content facts, explicit not-found lookups, coverage snapshots that do not list the
resource, positive activity checks, and resurrection events (sync/restore "repopulated").
Workflow results ("deleted SUCCESS") are never treated as observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .model import Activity, Coverage, Fact
from .parsers import EvidenceStore


@dataclass
class Observation:
    evidence_id: str
    observed_at: datetime
    cite_at: datetime
    exists: bool | None
    exposed: frozenset = frozenset()
    attrs: dict = field(default_factory=dict)
    locations: tuple = ()
    category: str | None = None
    source: str = ""
    absent_locations: tuple = ()   # copies this evidence shows the resource missing from (drift)


@dataclass
class ResourceState:
    resource_id: str
    system_id: str
    observations: list[Observation]
    exists: bool | None             # latest known existence at audit_at (None = never observed)
    exposed: frozenset              # identifiers in the latest present copy
    attrs: dict                     # latest value of each state attribute
    explicit_category: str | None
    resurrected_by: list[Activity] = field(default_factory=list)
    drift: list[Observation] = field(default_factory=list)

    @property
    def latest(self) -> Observation | None:
        return self.observations[-1] if self.observations else None


class TimelineAgent:
    def __init__(self, evidence: EvidenceStore):
        self.ev = evidence
        self.coverage_by_system: dict[str, list[Coverage]] = {}
        for c in evidence.coverage:
            self.coverage_by_system.setdefault(c.system_id, []).append(c)
        self.repopulated: dict[str, list[Activity]] = {}   # downstream resource -> jobs that recreated it
        self.recreators: dict[str, list[Activity]] = {}    # connector / backup -> jobs it ran
        for a in evidence.activities:
            if "repopulated downstream resource" in a.details:
                for rid in a.mentions:
                    self.repopulated.setdefault(rid, []).append(a)
                self.recreators.setdefault(a.resource_id, []).append(a)

    def observations(self, rid: str, system: str, until: datetime, names: frozenset = frozenset(),
                     case_files: frozenset = frozenset()) -> list[Observation]:
        grouped: dict[tuple, list[Fact]] = {}
        for f in self.ev.by_resource.get(rid, []):
            if f.kind == "link" or f.observed_at > until:
                continue
            grouped.setdefault((f.evidence_id, f.observed_at), []).append(f)
        obs = []
        covered_keys = set()
        for (eid, t), fs in grouped.items():
            present = [f for f in fs if f.exists]
            absent = [f for f in fs if f.exists is False]
            attrs = {}
            for f in fs:
                attrs.update({k: v for k, v in f.attrs.items() if k != "text"})
            exists = True if present else (False if absent else None)
            exposed = frozenset().union(*(f.exposed for f in present)) if present else frozenset()
            if names and any(n in f.attrs.get("text", "") for f in present for n in names):
                exposed |= {"name"}  # documents/screens that print the subject's name
            obs.append(Observation(eid, t, fs[0].cite_at, exists, exposed,
                                   attrs, tuple(sorted({f.location for f in present})),
                                   next((f.category for f in fs if f.category), None), fs[0].source,
                                   tuple(sorted({f.location for f in absent}))))
            covered_keys.add((eid, t))
        # coverage snapshots: listed nowhere in that snapshot -> absent; listed in some copies -> drift
        by_snapshot: dict[tuple, list[Coverage]] = {}
        for c in self.coverage_by_system.get(system, []):
            if c.observed_at <= until:
                by_snapshot.setdefault((c.evidence_id, c.observed_at), []).append(c)
        for key, covs in by_snapshot.items():
            missing = tuple(sorted(c.location for c in covs if rid not in c.present))
            if not missing:
                continue
            if key in covered_keys:  # resource present in other copies of this snapshot: record drift
                for o in obs:
                    if (o.evidence_id, o.observed_at) == key:
                        o.absent_locations = tuple(sorted(set(o.absent_locations) | set(missing)))
                continue
            if len(missing) == len(covs):
                # omission from a snapshot that holds this case's other records is a deliberate absence
                src = "coverage_case_file" if key[0] in case_files else "coverage"
                obs.append(Observation(key[0], key[1], covs[0].cite_at, False, source=src,
                                       absent_locations=missing))
        for a in self.repopulated.get(rid, []):
            if a.event_time <= until:
                obs.append(Observation(a.activity_id, a.event_time, a.event_time, True, source="resurrection",
                                       attrs={"repopulated_by": a.resource_id}))
        for a in self.recreators.get(rid, []):  # the path demonstrably ran: connector enabled / restore possible
            if a.event_time <= until:
                key = "enabled" if system == "integration_service" else "restore_allowed"
                obs.append(Observation(a.activity_id, a.event_time, a.event_time, True, source="recreation_job",
                                       attrs={key: True, "recreated": list(a.mentions)}))
        obs.sort(key=lambda o: (o.observed_at, o.exists is True, o.evidence_id))
        return obs

    def state(self, rid: str, system: str, until: datetime, names: frozenset = frozenset(),
              case_files: frozenset = frozenset()) -> ResourceState:
        obs = self.observations(rid, system, until, names, case_files)
        exists, exposed, attrs, category = None, frozenset(), {}, None
        explicit = [o for o in obs if o.source != "coverage"]
        # snapshots list only the records relevant to them, so omission is weak: it decides existence
        # only when no explicit observation exists (it always remains a citation candidate)
        for o in (explicit if any(o.exists is not None for o in explicit) else obs):
            if o.exists is not None:
                exists = o.exists
                if o.exists and o.source != "resurrection":
                    exposed = o.exposed
            attrs.update(o.attrs)
            category = o.category or category
        resurrected = [self._activity(o.evidence_id) for o in obs if o.source == "resurrection"]
        drift = [o for o in obs if o.exists and o.absent_locations]
        return ResourceState(rid, system, obs, exists, exposed, attrs, category, resurrected, drift)

    def _activity(self, aid: str) -> Activity:
        return next(a for a in self.ev.activities if a.activity_id == aid)
