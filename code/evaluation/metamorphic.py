"""USP7: metamorphic robustness + mutation generator. No labels needed: each relation states how the
output MUST change (or not) under a controlled mutation of the inputs.

R1 email normalisation   : upper-casing / padding the request email leaves every row identical.
R2 active flow injection : adding an enabled connector for the subject turns COMPLETE into INCOMPLETE
                           with a REPORT_ACTIVE_DATA_FLOW finding for that connector.
R3 post-audit evidence   : evidence captured after audit_at "proving" deletion changes nothing.
R4 decoy injection       : a near-miss ('.jr') look-alike record changes nothing.
R5 audit-time cut        : generated scenarios (seeded) where a deleted search entry is later repopulated
                           by a sync: auditing before the resurrection -> COMPLETE, after -> INCOMPLETE.

    python code/evaluation/metamorphic.py
"""
from __future__ import annotations

import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from audit.util import iso, read_csv  # noqa: E402
from evaluation.custom_cases import Scenario, lookup_log  # noqa: E402
from evaluation.overlay import build_overlay, bundle, cleanup  # noqa: E402


def _rows(results, ids):
    return {cid: (results[cid].status, results[cid].steps_json()) for cid in ids}


def _ids():
    return [r["case_id"] for r in read_csv(DATASET_DIR / "sample_deletion_requests.csv")] + \
           [r["case_id"] for r in read_csv(DATASET_DIR / "deletion_requests.csv")]


def r1_normalisation(base):
    def mutate(row):
        row["email"] = "  " + row["email"].upper() + " "
        return row
    mutated = _rows(AuditEngine(DATASET_DIR).run(transform=mutate), list(base))
    ok = sum(mutated[c] == base[c] for c in base)
    return ok, len(base), [c for c in base if mutated[c] != base[c]][:5]


def _overlay_run(evidence):
    root = build_overlay(evidence=evidence)
    try:
        return AuditEngine(root).run()
    finally:
        cleanup(root)


def r2_flow_injection(engine, results):
    targets = [r for r in results.values() if r.status == "COMPLETE"]
    users = {}
    for r in results.values():
        users.setdefault(r.case.user_id, []).append(r)
    targets = [r for r in targets if len(users[r.case.user_id]) == 1]   # single-case subjects only
    evidence, flows = [], {}
    for i, r in enumerate(targets):
        fl = f"data_flow_88{i:04d}"
        flows[r.case.case_id] = fl
        email = sorted(engine.identity.subjects[r.case.user_id].emails())[0]
        at = iso(r.case.audit_at - timedelta(hours=1))
        evidence.append({"file_id": f"evidence_m2{i:04d}", "file_path": f"evidence/records/mutation_flow_{i}.json",
                         "captured_at": at, "content": bundle(at, ("integration_service", "connector_configurations",
                                                                   [{"resource_id": fl, "subject_selector": email,
                                                                     "enabled": True, "mode": "continuous_sync"}]))})
    mutated = _overlay_run(evidence)
    fails = []
    for r in targets:
        m = mutated[r.case.case_id]
        if not (m.status == "INCOMPLETE" and any(s.operation == "REPORT_ACTIVE_DATA_FLOW" and s.resource_id == flows[r.case.case_id]
                                                 for s in m.steps)):
            fails.append(r.case.case_id)
    return len(targets) - len(fails), len(targets), fails[:5]


def r3_post_audit(results, base):
    targets = [r for r in results.values() if r.status == "INCOMPLETE"]
    evidence = []
    for i, r in enumerate(targets):
        at = iso(r.case.audit_at + timedelta(days=1))
        lines = [(at, "account_service" if a.system_id == "account_service" else a.system_id, "profile_lookup",
                  a.resource_id, r.case.user_id, "rows=0 http_status=404")
                 for a in r.assessments if a.status == "violation"]
        evidence.append({"file_id": f"evidence_m3{i:04d}", "file_path": f"evidence/logs/mutation_post_{i}.log",
                         "captured_at": at, "content": lookup_log(lines)})
    mutated = _rows(_overlay_run(evidence), list(base))
    ok = [r.case.case_id for r in targets if mutated[r.case.case_id] == base[r.case.case_id]]
    return len(ok), len(targets), [r.case.case_id for r in targets if r.case.case_id not in ok][:5]


def r4_decoys(engine, results, base):
    targets = [r for r in results.values() if r.status != "NOT_APPLICABLE"]
    evidence = []
    for i, r in enumerate(targets):
        email = sorted(engine.identity.subjects[r.case.user_id].emails())[0]
        local, dom = email.split("@")
        at = iso(r.case.audit_at - timedelta(hours=1))
        evidence.append({"file_id": f"evidence_m4{i:04d}", "file_path": f"evidence/records/mutation_decoy_{i}.json",
                         "captured_at": at, "content": bundle(at, ("search_service", "customer_search_documents",
                                                                   [{"resource_id": f"search_77{i:04d}", "index_name": "customer_directory_v3",
                                                                     "document": {"display_name": None, "email": f"{local}.jr@{dom}",
                                                                                  "customer_reference": None}}]))})
    mutated = _rows(_overlay_run(evidence), list(base))
    ok = [r.case.case_id for r in targets if mutated[r.case.case_id] == base[r.case.case_id]]
    return len(ok), len(targets), [r.case.case_id for r in targets if r.case.case_id not in ok][:5]


def r5_audit_cut(n: int = 20, seed: int = 7):
    """Mutation generator: seeded resurrection scenarios, each audited twice (before / after the sync)."""
    rng = random.Random(seed)
    scs, expect = [], {}
    for k in range(n):
        for when in ("before", "after"):
            s = Scenario(100 + 2 * k + (when == "after"), f"resurrection_{when}", "generated")
            s.case_id = f"mutation_{k:02d}_{when}"
            acc, srch, fl = s.rid("account"), s.rid("search"), s.rid("data_flow")
            s.account_chain(acc)
            gone = s.reported + timedelta(hours=rng.randint(2, 20))
            sync = gone + timedelta(hours=rng.randint(6, 40))
            seen = sync + timedelta(hours=rng.randint(1, 10))
            s.file(lookup_log([(iso(gone), "account_service", "profile_lookup", acc, s.email, "rows=0 http_status=404"),
                               (iso(gone), "search_service", "index_query", srch, s.email, "result=miss total_hits=0 email=null"),
                               (iso(gone), "integration_service", "connector_config_read", fl, s.email,
                                f"enabled=false last_delivery_status=stopped customer_email={s.email}")]), "logs", "log",
                   hours=(gone - s.audit).total_seconds() / 3600)
            s.activity("SYNC_RECORD", "search_service", fl, "SUCCESS", f"Active connector repopulated downstream resource {srch}.",
                       source="integration_service", at=iso(sync))
            s.file(bundle(iso(seen), ("search_service", "customer_search_documents",
                                      [{"resource_id": srch, "index_name": "customer_directory_v3",
                                        "document": {"display_name": None, "email": s.email, "customer_reference": None}}])),
                   hours=(seen - s.audit).total_seconds() / 3600)
            # evidence keeps its absolute times; only the audit cut moves
            s.audit = (gone + (sync - gone) / 2) if when == "before" else seen + timedelta(hours=2)
            scs.append(s)
            expect[s.case_id] = "COMPLETE" if when == "before" else "INCOMPLETE"
    root = build_overlay(identities=[r for s in scs for r in s.identities], activities=[r for s in scs for r in s.activities],
                         evidence=[e for s in scs for e in s.evidence], requests=[s.request() for s in scs])
    try:
        res = AuditEngine(root).run()
    finally:
        cleanup(root)
    fails = [cid for cid, st in expect.items() if res[cid].status != st]
    return len(expect) - len(fails), len(expect), fails[:5]


def run(verbose: bool = True) -> dict:
    engine = AuditEngine(DATASET_DIR)
    results = engine.run()
    ids = _ids()
    base = _rows(results, ids)
    out = {}
    for name, fn in [("R1 email case/whitespace invariance", lambda: r1_normalisation(base)),
                     ("R2 injected active flow flips COMPLETE->INCOMPLETE", lambda: r2_flow_injection(engine, results)),
                     ("R3 post-audit evidence ignored", lambda: r3_post_audit(results, base)),
                     ("R4 near-miss decoy injection ignored", lambda: r4_decoys(engine, results, base)),
                     ("R5 audit before/after resurrection (generated)", lambda: r5_audit_cut())]:
        ok, n, fails = fn()
        out[name] = {"passed": ok, "total": n, "pass_rate": round(ok / n, 4) if n else None, "first_failures": fails}
        if verbose:
            print(f"{name:52s} {ok}/{n}  failures={fails}")
    return out


if __name__ == "__main__":
    run()
