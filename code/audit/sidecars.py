"""Explainability sidecars (USPs). They read engine results and NEVER influence output.csv.

decision_trace.jsonl  USP1  why every emitted step exists (rule, category, evidence chain, agent)
lie_report.json       USP2  reported_status vs reconstructed truth, failure-mode counts
confidence.json       USP3  per-case 0-1 confidence; review_queue.json lists low-confidence cases and every
                            ambiguous (guessed) chain link
lineage.json          USP4  resurrection / recreation paths for INCOMPLETE cases
conflicts.jsonl       USP5  contradictory source pairs and which side was trusted
risk_scores.json      USP6  transparent exposure heuristic ("fix these first"), not a financial estimate
decoys.json           USP8  near-miss identifiers met and rejected
cases.json            UI    compact per-case bundle for the dashboard
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .config import RISK_WEIGHTS, REVIEW_CONFIDENCE_THRESHOLD
from .util import case_sort_key, iso, read_csv


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def _jsonl(path: Path, rows) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


# ---------------- USP3 ----------------
AMBIGUOUS_ACCOUNT_MARGIN = 0.3     # account chain link whose runner-up is this close is a guess
AMBIGUOUS_RESOURCE_MARGIN = 0.05   # identifier-free record tied with another case


def ambiguous_links(r) -> list[dict]:
    """Chain links (worker timing / clock, no identifier) that another assignment explains about as well."""
    if not r.links:
        return []
    out = []
    cl = r.links
    if cl.account_mode == "chain_soft" and (cl.account_margin or 0) < AMBIGUOUS_ACCOUNT_MARGIN:
        out.append({"resource_id": cl.account_event.resource_id, "kind": "account", "margin": cl.account_margin})
    emitted = {s.resource_id for s in r.steps}
    for l in cl.resources.values():
        if l.resource_id in emitted and l.mode == "chain_soft" and not l.resource_id.startswith("account_") \
                and (l.margin or 0) < AMBIGUOUS_RESOURCE_MARGIN:
            out.append({"resource_id": l.resource_id, "kind": "identifier_free_tie", "margin": l.margin})
    return out


def confidence(r) -> tuple[float, list[str]]:
    if r.status == "NOT_APPLICABLE":
        return round(r.case.intent.confidence, 3), ([] if r.case.intent.confidence >= 0.8 else ["intent uncertain"])
    reasons, score = [], 1.0
    cl = r.links
    mode_w = {"chain_pinned": 1.0, "evidence": 1.0, "chain_elimination": 0.9, "chain_soft": 0.75, "none": 0.6}
    score *= mode_w.get(cl.account_mode, 0.6)
    if cl.account_mode in ("chain_soft", "none"):
        reasons.append(f"account linked by {cl.account_mode}" + (f" (margin {cl.account_margin})" if cl.account_margin is not None else ""))
    amb = ambiguous_links(r)
    if any(x["kind"] == "account" for x in amb):
        score *= 0.85
    weak = [x for x in amb if x["kind"] == "identifier_free_tie"]
    if weak:
        score *= 0.8 ** len(weak)
        reasons.append(f"{len(weak)} identifier-free resource(s) assigned with ~zero margin")
    if r.status == "COMPLETE" and not r.steps:
        score *= 0.5
        reasons.append("COMPLETE without any citable verification")
    if any(a.drift for a in r.assessments):
        score *= 0.95
        reasons.append("primary/replica drift observed")
    if cl.conflicts:
        score *= 0.9
        reasons.append("catalog/content conflict")
    if r.sim and not r.sim.ok:
        score *= 0.5
        reasons.append("simulation failed: " + "; ".join(r.sim.failures[:2]))
    unknown = [a.resource_id for a in r.assessments if a.status == "unknown" and a.action == "RETAIN"]
    if unknown:
        reasons.append(f"retained record(s) not observed: {unknown}")
    return round(score, 3), reasons


# ---------------- USP2 ----------------
def failure_modes(r) -> list[str]:
    modes = set()
    for a in r.assessments:
        if a.status != "violation":
            if a.action == "RETAIN" and a.status == "unknown":
                modes.add("over_deletion_risk")
            continue
        if a.drift:
            modes.add("hidden_replica_drift")
        if a.resurrected_by:
            modes.add("sync_or_restore_resurrection")
        if a.action == "BLOCK":
            modes.add("restore_risk")
        if a.action == "DISABLE":
            modes.add("active_data_flow")
        if a.system_id == "account_service":
            modes.add("primary_record_remaining")
        if a.category == "ACCOUNT_TOMBSTONE":
            modes.add("tombstone_leaking_identifiers")
            if "hash" in (a.proof[-1].exposed if a.proof else ()):
                modes.add("tombstone_leaking_hash")
        if a.system_id in ("search_service", "support_platform", "analytics_platform", "export_service",
                           "email_delivery_service") and a.action in ("DELETE", "REDACT", "ANONYMIZE"):
            modes.add("identifier_leakage_" + a.system_id)
    return sorted(modes)


def lie_report(results, ids) -> dict:
    rows, verdicts, modes = [], Counter(), Counter()
    by_claim = defaultdict(Counter)
    for cid in ids:
        r = results[cid]
        if r.status == "NOT_APPLICABLE":
            continue
        claim = r.case.reported_status
        truth = r.status
        if claim == "COMPLETE" and truth == "INCOMPLETE":
            v = "false_COMPLETE"
        elif claim == "NOT_STARTED" and truth == "COMPLETE":
            v = "false_NOT_STARTED_actually_complete"
        elif claim == "PARTIALLY_COMPLETE" and truth == "COMPLETE":
            v = "understated_PARTIAL_actually_complete"
        elif claim == "COMPLETE" and truth == "COMPLETE":
            v = "accurate_COMPLETE"
        else:
            v = f"{claim}_and_{truth}"
        fm = failure_modes(r) if truth == "INCOMPLETE" else []
        verdicts[v] += 1
        by_claim[claim][truth] += 1
        for m in fm:
            modes[m] += 1
        rows.append({"case_id": cid, "reported_status": claim, "reconstructed": truth, "verdict": v, "failure_modes": fm})
    n = len(rows)
    claimed_complete = sum(by_claim["COMPLETE"].values())
    return {
        "deletion_cases": n,
        "headline": {
            "reported_COMPLETE_but_incomplete_pct": round(100 * by_claim["COMPLETE"]["INCOMPLETE"] / claimed_complete, 1) if claimed_complete else None,
            "reported_COMPLETE_cases": claimed_complete,
            "status_claim_wrong_pct": round(100 * sum(c for v, c in verdicts.items() if not v.startswith("accurate") and v not in
                                                      ("PARTIALLY_COMPLETE_and_INCOMPLETE", "NOT_STARTED_and_INCOMPLETE")) / n, 1) if n else None,
        },
        "claim_vs_truth": {k: dict(v) for k, v in by_claim.items()},
        "verdicts": dict(verdicts),
        "failure_modes": {m: {"cases": c, "pct_of_incomplete": round(100 * c / max(1, sum(1 for x in rows if x["reconstructed"] == "INCOMPLETE")), 1)}
                          for m, c in modes.most_common()},
        "cases": rows,
    }


# ---------------- USP4 ----------------
def lineage(engine, r) -> dict:
    nodes, edges = {}, []
    linked = set(r.links.resources) if r.links else set()
    for a in engine.ev.activities:
        if a.event_time > r.case.audit_at:
            continue
        if "repopulated downstream resource" in a.details:
            for dst in a.mentions:
                if dst in linked or a.resource_id in linked:
                    edges.append({"from": a.resource_id, "via": a.activity_id, "kind": a.event_type, "to": dst,
                                  "at": iso(a.event_time)})
        elif "Replication worker" in a.details and a.resource_id in linked:
            edges.append({"from": "account_service:primary", "via": a.activity_id, "kind": "REPLICATION",
                          "to": f"{a.target_system}:{a.resource_id}", "at": iso(a.event_time)})
    for x in r.assessments:
        if x.status == "violation" and x.action in ("DISABLE", "BLOCK"):
            dest = (x.proof[-1].attrs.get("destination") or x.proof[-1].attrs.get("connector_name")) if x.proof else None
            edges.append({"from": "subject", "via": x.resource_id, "kind": "ACTIVE_" + x.action, "to": dest or x.system_id,
                          "at": iso(x.proof[-1].observed_at) if x.proof else None})
    for e in edges:
        for k in ("from", "to"):
            nodes.setdefault(e[k], {"id": e[k]})
    return {"nodes": list(nodes.values()), "edges": edges}


# ---------------- USP5 ----------------
def conflicts(engine, results, ids) -> list[dict]:
    out = []
    for cid in ids:
        r = results[cid]
        if not r.links:
            continue
        for c in r.links.conflicts:
            out.append({"case_id": cid, **c})
        for a in r.assessments:
            for o in a.drift:
                out.append({"case_id": cid, "type": "primary_vs_replica", "resource_id": a.resource_id,
                            "present_in": list(o.locations), "absent_in": list(o.absent_locations),
                            "evidence": o.evidence_id, "trusted": "presence", "why": "any surviving copy is a remaining record"})
            for w in r.links.worker_events:
                if w.resource_id != a.resource_id:
                    continue
                if w.reported_result == "SUCCESS" and a.status == "violation":
                    out.append({"case_id": cid, "type": "claimed_result_vs_evidence", "resource_id": a.resource_id,
                                "claim": {"activity": w.activity_id, "result": w.reported_result, "op": w.event_type},
                                "evidence": [o.evidence_id for o in a.proof[-1:]], "trusted": "evidence",
                                "why": "operation results are claims; later evidence still shows the violation"})
        for d in r.links.decoys:
            out.append({"case_id": cid, "type": "decoy_rejected", **d, "trusted": "exact identity match",
                        "why": "near-miss identifier is not the subject's"})
    return out


# ---------------- USP6 ----------------
def risk(r) -> dict:
    w = RISK_WEIGHTS
    viol = [a for a in r.assessments if a.status == "violation"]
    sens = sum(w["category_sensitivity"].get(a.category, 1) for a in viol if a.action in ("DELETE", "REDACT", "ANONYMIZE"))
    systems = {a.system_id for a in viol}
    flows = sum(1 for a in viol if a.action == "DISABLE")
    restore = any(a.action == "BLOCK" for a in viol)
    score = sens + w["per_extra_system"] * max(0, len(systems) - 1) + w["active_flow"] * flows + (w["restore_path"] if restore else 0)
    return {"score": round(score, 2), "exposed_systems": sorted(systems), "active_flows": flows, "restore_path": restore,
            "sensitivity_sum": sens}


def write_sidecars(engine, results, out_dir: Path, llm=None, ids: list[str] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if ids is None:
        ids = sorted((r["case_id"] for r in read_csv(engine.dataset_dir / "deletion_requests.csv")), key=case_sort_key)
    all_ids = sorted(results, key=case_sort_key)

    trace = []
    for cid in all_ids:
        r = results[cid]
        for s in r.steps:
            link = r.links.resources.get(s.resource_id) if r.links else None
            trace.append({"case_id": cid, "step_no": s.step_no, "operation": s.operation, "resource_id": s.resource_id,
                          "evidence_id": s.evidence_id, "link_mode": link.mode if link else None, **s.trace})
    _jsonl(out_dir / "decision_trace.jsonl", trace)

    _dump(out_dir / "lie_report.json", lie_report(results, ids))

    conf, queue = {}, []
    for cid in all_ids:
        score, reasons = confidence(results[cid])
        amb = ambiguous_links(results[cid])
        conf[cid] = {"confidence": score, "reasons": reasons, "ambiguous_links": amb}
        no_account = results[cid].links is not None and results[cid].links.account_mode == "none"
        # every guessed (ambiguous) chain link is queued, as are deletion cases with no account evidence at all,
        # plus anything below the confidence threshold
        if cid in ids and (score < REVIEW_CONFIDENCE_THRESHOLD or amb or no_account):
            queue.append({"case_id": cid, "confidence": score, "status": results[cid].status, "reasons": reasons,
                          "ambiguous_links": amb})
    _dump(out_dir / "confidence.json", conf)
    _dump(out_dir / "review_queue.json", {
        "threshold": REVIEW_CONFIDENCE_THRESHOLD,
        "rule": "queued if confidence < threshold OR the case has an ambiguous chain link "
                f"(account margin < {AMBIGUOUS_ACCOUNT_MARGIN}, identifier-free tie margin < {AMBIGUOUS_RESOURCE_MARGIN}) "
                "OR no account evidence exists for a deletion case",
        "no_account_evidence_cases": [q["case_id"] for q in queue if any("account linked by none" in r for r in q["reasons"])],
        "ambiguous_account_links": sum(1 for q in queue for x in q["ambiguous_links"] if x["kind"] == "account"),
        "ambiguous_identifier_free_ties": sum(1 for q in queue for x in q["ambiguous_links"] if x["kind"] == "identifier_free_tie"),
        "cases": queue})

    _dump(out_dir / "lineage.json", {cid: lineage(engine, results[cid]) for cid in ids if results[cid].status == "INCOMPLETE"})
    _jsonl(out_dir / "conflicts.jsonl", conflicts(engine, results, ids))
    risks = {cid: risk(results[cid]) for cid in ids if results[cid].status == "INCOMPLETE"}
    _dump(out_dir / "risk_scores.json", {"note": "transparent heuristic (weights in audit/config.py), not a financial estimate",
                                         "ranking": sorted(({"case_id": k, **v} for k, v in risks.items()),
                                                           key=lambda x: (-x["score"], case_sort_key(x["case_id"])))})
    emitted_decoys = []
    decoys = []
    for cid in ids:
        r = results[cid]
        if not r.links:
            continue
        emitted = {s.resource_id for s in r.steps}
        for d in r.links.decoys:
            decoys.append({"case_id": cid, **d})
            if d["resource_id"] in emitted:
                emitted_decoys.append({"case_id": cid, **d})
    _dump(out_dir / "decoys.json", {"near_miss_decoys_encountered": len(decoys),
                                    "decoys_emitted_as_subject_records": len(emitted_decoys),
                                    "false_exposures_avoided": len(decoys) - len(emitted_decoys),
                                    "decoys": decoys, "violations": emitted_decoys})
    bundle = []
    for cid in all_ids:
        r = results[cid]
        c = r.case
        bundle.append({
            "case_id": cid, "set": "eval" if cid in ids else "sample", "email": c.email, "user_id": c.user_id,
            "identity_match": c.resolution.match, "requested_at": iso(c.requested_at), "reported_at": iso(c.reported_at),
            "audit_at": iso(c.audit_at), "reported_status": c.reported_status, "status": r.status,
            "intent": c.intent.reason, "request_text": c.request_text, "confidence": conf[cid]["confidence"],
            "steps": [s.as_json() for s in r.steps],
            "assessments": [{"resource_id": a.resource_id, "system_id": a.system_id, "category": a.category,
                             "rule_id": a.rule_id, "status": a.status, "reason": a.reason,
                             "observations": [{"evidence_id": o.evidence_id, "at": iso(o.observed_at), "exists": o.exists,
                                               "source": o.source, "exposed": sorted(o.exposed)} for o in (
                                 engine.timeline.state(a.resource_id, a.system_id, c.audit_at).observations[-6:])],
                             "link": (r.links.resources[a.resource_id].mode if r.links and a.resource_id in r.links.resources else None)}
                            for a in r.assessments],
            "sim": {"ok": r.sim.ok, "before": r.sim.before, "after": r.sim.after, "failures": r.sim.failures} if r.sim else None,
            "identifiers": sorted(f"{i.kind}:{i.value}" for i in engine.identity.subjects[c.user_id].identifiers
                                  if i.kind in ("email", "user", "phone")) if c.user_id else [],
        })
    _dump(out_dir / "cases.json", bundle)
    return {"trace_steps": len(trace), "review_queue": len(queue)}
