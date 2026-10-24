"""Decision 2: choose the citation rule empirically.

For every gold step that cites evidence, enumerate every observation that proves the same state for
the same resource (including post-audit ones, which no rule may pick), then score candidate rules
by how many gold citations each reproduces.

    python code/evaluation/citation_study.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from evaluation.metrics import load_rows  # noqa: E402

FAR = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _pre(c, audit):
    return [o for o in c if o.cite_at <= audit and o.observed_at <= audit]


RULES = {
    "latest_pre_audit": lambda c, audit, rep, dele: max(_pre(c, audit), key=lambda o: (o.observed_at, o.cite_at), default=None),
    "latest_pre_audit_explicit_first": lambda c, audit, rep, dele: max(
        _pre(c, audit), key=lambda o: (o.source != "coverage", o.evidence_id.startswith("evidence_"), o.observed_at, o.cite_at), default=None),
    "earliest_pre_audit": lambda c, audit, rep, dele: min(_pre(c, audit), key=lambda o: (o.observed_at, o.cite_at), default=None),
    "nearest_reported_at": lambda c, audit, rep, dele: min(_pre(c, audit), key=lambda o: abs((o.observed_at - rep).total_seconds()), default=None),
    "first_after_delete_activity": lambda c, audit, rep, dele: min(
        [o for o in _pre(c, audit) if dele is None or o.observed_at >= dele] or _pre(c, audit),
        key=lambda o: (o.observed_at, o.cite_at), default=None),
    "latest_file_manifest_time": lambda c, audit, rep, dele: max(_pre(c, audit), key=lambda o: (o.cite_at, o.observed_at), default=None),
    "prefer_snapshot_types": lambda c, audit, rep, dele: max(
        _pre(c, audit), key=lambda o: (o.source in ("sql_topology", "sql_typed", "snapshot_bundle", "coverage"), o.observed_at), default=None),
}


def study(engine=None, results=None):
    engine = engine or AuditEngine(DATASET_DIR)
    results = results or engine.run()
    gold = load_rows(DATASET_DIR / "sample_output.csv")
    scores = {name: 0 for name in RULES}
    total, unreachable, rows = 0, 0, []
    for cid, (_, steps) in gold.items():
        r = results[cid]
        case = r.case
        dele = r.links.account_event.event_time if r.links and r.links.account_event else None
        assess = {a.resource_id: a for a in r.assessments}
        for s in steps:
            if not s["evidence_id"]:
                continue
            total += 1
            a = assess.get(s["resource_id"])
            if a is None:
                unreachable += 1
                rows.append((cid, s["resource_id"], s["evidence_id"], "resource not linked", []))
                continue
            full = engine.timeline.state(a.resource_id, a.system_id, FAR)
            cands = engine.policy._proof(full, a.status, a.action, set(a.proof[-1].exposed) if a.proof else set())
            cand_ids = [(o.evidence_id, o.observed_at.strftime("%m-%d"), "pre" if o in _pre(cands, case.audit_at) else "POST")
                        for o in cands]
            hit_any = False
            for name, rule in RULES.items():
                o = rule(cands, case.audit_at, case.reported_at, dele)
                ok = o is not None and o.evidence_id == s["evidence_id"]
                scores[name] += ok
                hit_any |= ok
            rows.append((cid, s["resource_id"], s["evidence_id"], "ok" if hit_any else "no rule", cand_ids))
    return scores, total, unreachable, rows


def main():
    scores, total, unreachable, rows = study()
    print(f"cited gold steps: {total} (resource not linked: {unreachable})\n")
    for name, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {name:34s} {sc}/{total}")
    print("\nper-step candidates (gold citation, candidates with time and pre/POST audit):")
    for cid, rid, gold_ev, note, cands in rows:
        print(f"  {cid} {rid:22s} gold={gold_ev:12s} {note:18s} {cands}")


if __name__ == "__main__":
    main()
