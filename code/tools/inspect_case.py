"""Debug view of one or more cases: links, assessments, observations, steps.

    python code/tools/inspect_case.py case_53 case_55
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402


def main(ids: list[str]) -> None:
    engine = AuditEngine(DATASET_DIR)
    results = engine.run()
    for cid in ids:
        r = results[cid]
        c = r.case
        print(f"\n===== {cid} {c.email} -> {c.user_id} ({c.resolution.match}) claim={c.reported_status} "
              f"req={c.requested_at:%m-%d %H:%M} rep={c.reported_at:%m-%d %H:%M} audit={c.audit_at:%m-%d %H:%M} -> {r.status}")
        print("   text:", c.request_text[:140])
        if r.links:
            print(f"   account: {r.links.account_mode} {r.links.account_event.resource_id if r.links.account_event else None} margin={r.links.account_margin}")
            for d in r.links.decoys:
                print("   decoy:", d)
            for x in r.links.conflicts:
                print("   conflict:", x)
        for a in r.assessments:
            link = r.links.resources.get(a.resource_id)
            print(f"   [{a.status:9s}] {a.resource_id:20s} {a.category:20s} {a.action:9s} via={link.mode if link else '?'}"
                  f" {a.reason} proof={[o.evidence_id for o in a.proof][-3:]}")
            for o in engine.timeline.state(a.resource_id, a.system_id, c.audit_at).observations[-4:]:
                print(f"        {o.observed_at:%m-%d %H:%M} {o.evidence_id:13s} exists={o.exists} exp={sorted(o.exposed)} "
                      f"{ {k: v for k, v in o.attrs.items() if k in ('enabled', 'restore_allowed', 'download_available')} } {o.source} {o.locations}")
        for s in r.steps:
            print("   step", s.step_no, s.phase, s.operation, s.resource_id, repr(s.evidence_id))


if __name__ == "__main__":
    main(sys.argv[1:])
