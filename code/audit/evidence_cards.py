"""Finding evidence cards (sidecar): one card per emitted FINDING step. Reads engine results, NEVER influences
output.csv.

A card answers four questions about a finding:
  where    store type, system_id, resource_id, the copies (locations) it was seen in
  why      which of the subject's identifiers matched (current / historical email, hash, phone, user_id) and how
           (exact, normalized, hash, catalog link, or chain-linked through the deletion worker with no identifier)
  state    the cited observation at audit_at, with the fact's own timestamp and the file's capture time
  recreate which sync / restore paths could bring it back (linked by a recreation job, or merely open in the case)
plus a 0-1 confidence whose factors are listed, so a reviewer can see what set it.
"""
from __future__ import annotations

from datetime import datetime

from .config import STORE_TYPE
from .model import DIRECT
from .util import iso

# Confidence factors (heuristic, documented in docs/ERROR_ANALYSIS.md; calibrated on the samples by
# evaluation/calibration.py). Match strength: how surely the record is this person's.
MATCH_BASE = {
    ("email", "current"): 0.98, ("email", "historical"): 0.96, ("user", "current"): 0.98,
    ("hash", "current"): 0.96, ("hash", "historical"): 0.95, ("hash", "derived"): 0.95,
    ("phone", "current"): 0.93, ("phone", "historical"): 0.92,
}
NORMALIZED_FACTOR = 0.98        # identifier matched only after case / punctuation normalisation
CATALOG_ONLY = 0.85             # only a data-catalog link row ties the record to the subject (no content match)
CONTESTED = 0.5                 # catalog says ours, content names someone else (kept in scope only as a fail-safe)
CHAIN_ELIMINATION = 0.85        # the only feasible owner of a deletion-worker event
CHAIN_SOFT_RANGE = (0.6, 0.9)   # global assignment; scaled by the margin to the runner-up
CHAIN_SOFT_FULL_MARGIN = 0.5
CORROBORATION_BONUS = 0.01      # each extra independent file showing the same match (capped)
RECREATION_ONLY = 0.9           # state shown only by a resurrection / recreation job, not by a record readback
INFERRED_RESTORE = 0.85         # restore risk inferred from the archive's presence (no explicit restore flag)
STALE_DAYS = 30
STALE_FACTOR = 0.9              # cited observation is older than STALE_DAYS before audit_at
UNCITED = 0.5                   # no citable pre-audit evidence for the finding

IDENTIFIER_LABEL = {
    ("email", "current"): "current email", ("email", "historical"): "historical email",
    ("hash", "current"): "hash of current email", ("hash", "historical"): "hash of historical email",
    ("hash", "derived"): "hash of an email", ("phone", "current"): "current phone",
    ("phone", "historical"): "historical phone", ("user", "current"): "user_id (stable reference)",
}
TEXT_SUFFIXES = (".sql", ".json", ".log", ".txt")


def store_of(system_id: str, locations=()) -> str:
    base = STORE_TYPE.get(system_id, system_id)
    replicas = sorted(l for l in locations if "replica" in l)
    return f"{base} (replica: {', '.join(replicas)})" if replicas else base


class CardBuilder:
    def __init__(self, engine):
        self.engine = engine
        self.ev = engine.ev
        self.id = engine.identity
        self._raw: dict[str, str] = {}
        self._acts = {a.activity_id: a for a in self.ev.activities}
        self._replication: dict[str, list] = {}
        for a in self.ev.activities:
            if "Replication worker" in a.details:
                self._replication.setdefault(a.resource_id, []).append(a)

    # ---------- raw text, to tell an exact match from a normalized one ----------
    def raw_text(self, evidence_id: str) -> str | None:
        if evidence_id in self._raw:
            return self._raw[evidence_id]
        text = None
        row = self.ev.manifest.get(evidence_id)
        if row is not None and row["file_path"].lower().endswith(TEXT_SUFFIXES):
            text = (self.engine.dataset_dir / row["file_path"]).read_text(encoding="utf-8")
        elif evidence_id in self._acts:
            text = self._acts[evidence_id].details
        self._raw[evidence_id] = text
        return text

    def match_mode(self, kind: str, value: str, fact) -> str:
        if fact.kind == "link":
            return "catalog-link"
        if kind == "hash":
            return "hash"
        if kind == "user":
            return "exact"
        text = fact.attrs.get("text") or self.raw_text(fact.evidence_id)
        if text is None:
            return "exact"
        return "exact" if value in text else "normalized"

    def identifier_origin(self, user_id: str, key: tuple) -> str:
        for i in self.id.subjects[user_id].identifiers:
            if (i.kind, i.value) == key:
                return i.origin
        return "derived"

    # ---------- why: identifier matches ----------
    def matches(self, case, rid: str) -> list[dict]:
        keys = self.id.subjects[case.user_id].keys()
        out = {}
        for f in self.ev.by_resource.get(rid, []):
            if not self.engine.linker._in_scope(case, f.observed_at):
                continue
            for k in sorted(f.keys & keys):
                if not self.id.belongs_to(k, case.user_id, f.observed_at):
                    continue
                origin = self.identifier_origin(case.user_id, k)
                mode = self.match_mode(k[0], k[1], f)
                key = (k[0], origin, mode)
                m = out.setdefault(key, {"identifier": IDENTIFIER_LABEL.get((k[0], origin), k[0]), "kind": k[0],
                                         "origin": origin, "mode": mode, "evidence": set(), "captured_after_audit": set()})
                # the fact itself predates audit_at; a file captured later may explain but is never a citation
                (m["evidence"] if f.cite_at <= case.audit_at else m["captured_after_audit"]).add(f.evidence_id)
        rows = [{**m, "evidence": sorted(m["evidence"]), "captured_after_audit": sorted(m["captured_after_audit"])}
                for m in out.values()]
        return sorted(rows, key=lambda m: (-MATCH_BASE.get((m["kind"], m["origin"]), 0.9), m["mode"], m["identifier"]))

    # ---------- recreate ----------
    def recreation(self, r, a) -> list[dict]:
        paths = []
        open_paths = {x.resource_id: x for x in r.assessments if x.status == "violation" and x.action in ("DISABLE", "BLOCK")}
        for job in self._replication.get(a.resource_id, []):
            if r.case.requested_at < job.event_time <= r.case.audit_at:   # replication after the request, not routine sync
                paths.append({"path": job.target_system, "how": f"replication worker checkpointed this record after the request ({job.reported_result}): a copy path exists",
                              "job": job.activity_id, "at": iso(job.event_time), "path_open": None, "link": "replication job"})
        for job in a.resurrected_by:
            paths.append({"path": job.resource_id, "how": f"{job.event_type} repopulated this record",
                          "job": job.activity_id, "at": iso(job.event_time),
                          "path_open": job.resource_id in open_paths, "link": "recreation job"})
        if a.action in ("DISABLE", "BLOCK"):
            targets = sorted({m for job in self.engine.timeline.recreators.get(a.resource_id, [])
                              if job.event_time <= r.case.audit_at for m in job.mentions})
            how = "connector keeps syncing the subject's data" if a.action == "DISABLE" else "restoring this archive"
            paths.append({"path": a.resource_id, "how": how + (f" (recreated {', '.join(targets)})" if targets else ""),
                          "path_open": True, "link": "this resource"})
        listed = {p["path"] for p in paths}
        for rid, x in sorted(open_paths.items()):
            if rid not in listed and rid != a.resource_id:
                paths.append({"path": rid, "how": ("active sync" if x.action == "DISABLE" else "open restore") +
                              " for the same subject", "path_open": True, "link": "same case (not shown to touch this record)"})
        return paths

    # ---------- confidence ----------
    def match_strength(self, link, matches) -> tuple[float, list[str]]:
        """How surely the record is this person's (identifier evidence or worker-chain assignment)."""
        factors = []
        mode = link.mode if link else "none"
        if mode == "evidence_contested":
            score = CONTESTED
            factors.append(f"contested catalog link kept as fail-safe x{CONTESTED}")
        elif mode in ("chain_elimination", "chain_soft"):
            if mode == "chain_elimination":
                score = CHAIN_ELIMINATION
                factors.append(f"chain-linked: only feasible owner of worker event x{CHAIN_ELIMINATION}")
            else:
                lo, hi = CHAIN_SOFT_RANGE
                margin = max(0.0, link.margin or 0.0)
                score = round(lo + (hi - lo) * min(1.0, margin / CHAIN_SOFT_FULL_MARGIN), 3)
                factors.append(f"chain-linked by global assignment, margin {link.margin} -> {score}")
        else:
            content = [m for m in matches if m["mode"] != "catalog-link"]
            if content:
                best = content[0]
                score = MATCH_BASE.get((best["kind"], best["origin"]), 0.9)
                factors.append(f"direct identifier ({best['identifier']}, {best['mode']}) {score}")
                if best["mode"] == "normalized":
                    score *= NORMALIZED_FACTOR
                    factors.append(f"matched after normalisation x{NORMALIZED_FACTOR}")
                files = {e for m in content for e in m["evidence"] + m.get("captured_after_audit", [])}
                if len(files) > 1:
                    bonus = min(0.03, CORROBORATION_BONUS * (len(files) - 1))
                    score = min(0.99, score + bonus)
                    factors.append(f"{len(files)} independent sources agree +{bonus:.2f}")
            elif matches:
                score = CATALOG_ONLY
                factors.append(f"catalog link only, no content match x{CATALOG_ONLY}")
            else:
                score = UNCITED
                factors.append(f"no identifier match found x{UNCITED}")
        return score, factors

    def confidence(self, link, matches, cited, a, audit_at: datetime) -> tuple[float, list[str]]:
        score, factors = self.match_strength(link, matches)
        if cited is None:
            score *= UNCITED
            factors.append(f"no citable pre-audit evidence x{UNCITED}")
        else:
            if cited.source in ("resurrection", "recreation_job"):
                score *= RECREATION_ONLY
                factors.append(f"state shown by a recreation job, not a record readback x{RECREATION_ONLY}")
            if a.action == "BLOCK" and a.reason.startswith("archive present"):
                score *= INFERRED_RESTORE
                factors.append(f"restore risk inferred from archive presence x{INFERRED_RESTORE}")
            age = (audit_at - cited.observed_at).days
            if age > STALE_DAYS:
                score *= STALE_FACTOR
                factors.append(f"cited observation {age} days before audit_at x{STALE_FACTOR}")
        return round(min(0.99, score), 3), factors

    # ---------- one card ----------
    def card(self, r, step) -> dict:
        case = r.case
        a = next(x for x in r.assessments if x.resource_id == step.resource_id)
        link = r.links.resources.get(step.resource_id) if r.links else None
        cited = next((o for o in a.proof if o.evidence_id == step.evidence_id), None) if step.evidence_id else None
        matches = self.matches(case, step.resource_id)
        chain = None
        if link and link.mode.startswith("chain"):
            chain = {"mode": link.mode, "margin": link.margin, "worker_events": list(link.evidence)}
            if link.mode != "chain_pinned":
                matches = matches or []
                matches.append({"identifier": "worker-chain link", "kind": "chain", "origin": "-",
                                "mode": "chain-linked", "evidence": list(link.evidence)})
        conf, factors = self.confidence(link, [m for m in matches if m["kind"] != "chain"], cited, a, case.audit_at)
        locations = sorted({l for o in a.proof if o.exists for l in o.locations}) if a.proof else []
        state = None
        if cited is not None:
            state = {"evidence_id": cited.evidence_id, "observed_at": iso(cited.observed_at), "file_captured_at": iso(cited.cite_at),
                     "exists": cited.exists, "exposed": sorted(cited.exposed & (set(DIRECT) | {"user_ref"})),
                     "locations": list(cited.locations), "absent_in": list(cited.absent_locations), "source": cited.source}
        return {
            "case_id": case.case_id, "step_no": step.step_no, "operation": step.operation,
            "where": {"store_type": store_of(a.system_id, locations), "system_id": a.system_id,
                      "resource_id": a.resource_id, "locations": locations},
            "why": {"link_mode": link.mode if link else None, "matches": matches, "chain": chain},
            "state_at_audit": {"audit_at": iso(case.audit_at), "verdict": a.reason, "rule_id": a.rule_id,
                               "category": a.category, "category_source": a.category_source, "cited": state,
                               "evidence_chain": [o.evidence_id for o in a.proof]},
            "confidence": conf, "confidence_factors": factors,
            "could_recreate": self.recreation(r, a),
        }

    def link_confidence(self, r, rid: str) -> tuple[float, str]:
        """Match strength alone for any emitted resource (used to calibrate chain links, which only verify)."""
        link = r.links.resources.get(rid) if r.links else None
        score, _ = self.match_strength(link, self.matches(r.case, rid))
        return round(min(0.99, score), 3), (link.mode if link else "none")

    def cards(self, results, ids) -> list[dict]:
        out = []
        for cid in ids:
            r = results[cid]
            out += [self.card(r, s) for s in r.steps if s.phase == "FINDING"]
        return out
