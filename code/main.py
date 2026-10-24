"""Ghost Data Still Exists — deletion audit agent.

    python code/main.py              # writes <repo>/output.csv + sidecars in code/out/, validates
    python code/main.py --no-sidecars

Deterministic and offline. An LLM is never needed; if AUDIT_LLM_PROVIDER is set it is only used as a
cached fallback for low-confidence intent classification (see audit/llm.py).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit.config import DATASET_DIR, OUT_DIR, REPO_ROOT  # noqa: E402
from audit.llm import build_llm  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from audit.util import case_sort_key, read_csv  # noqa: E402
from audit.validator import validate_file  # noqa: E402


def write_output(results, request_ids: list[str], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid in sorted(request_ids, key=case_sort_key):
            r = results[cid]
            w.writerow([cid, r.status, r.steps_json()])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(REPO_ROOT / "output.csv"))
    ap.add_argument("--no-sidecars", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    llm = build_llm()
    engine = AuditEngine(DATASET_DIR, llm=llm)
    results = engine.run()
    request_ids = [r["case_id"] for r in read_csv(DATASET_DIR / "deletion_requests.csv")]
    out = Path(args.output)
    write_output(results, request_ids, out)
    errors = validate_file(out, DATASET_DIR)
    sim_fail = [cid for cid in request_ids if results[cid].sim and not results[cid].sim.ok]
    counts = {}
    for cid in request_ids:
        counts[results[cid].status] = counts.get(results[cid].status, 0) + 1
    print(f"wrote {out} rows={len(request_ids)} statuses={counts} in {time.time() - t0:.1f}s")
    print(f"simulation failures: {len(sim_fail)} {sim_fail[:5]}")
    if not args.no_sidecars:
        from audit.sidecars import write_sidecars
        write_sidecars(engine, results, OUT_DIR, llm)
        print(f"sidecars -> {OUT_DIR}")
    if errors:
        print(f"VALIDATION FAILED ({len(errors)}):")
        for e in errors[:30]:
            print("  ", e)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
