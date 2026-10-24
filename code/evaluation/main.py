"""Evaluation entry point: run the engine and score it against sample_output.csv.

    python code/evaluation/main.py            # sample metrics + diffs
    python code/evaluation/main.py --json     # machine-readable metrics
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from evaluation.metrics import load_rows, score  # noqa: E402


def evaluate_samples(engine: AuditEngine | None = None, results=None) -> dict:
    engine = engine or AuditEngine(DATASET_DIR)
    results = results or engine.run()
    gold = load_rows(DATASET_DIR / "sample_output.csv")
    pred = {cid: (r.status, [s.as_json() for s in r.steps]) for cid, r in results.items() if cid in gold}
    return score(pred, gold)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--diffs", type=int, default=40)
    args = ap.parse_args()
    m = evaluate_samples()
    if args.json:
        print(json.dumps(m, indent=2))
        return
    print(f"cases={m['cases']} status_accuracy={m['status_accuracy']} exact={m['exact_case_match']} "
          f"ordering={m['ordering_accuracy']}")
    print("per_status:", m["per_status"])
    print("confusion:", m["confusion"])
    print("step strict:", m["step_strict"])
    print("step ignoring evidence:", m["step_ignoring_evidence"])
    print("field accuracy:", m["field_accuracy_on_aligned_steps"])
    for d in m["diffs"][: args.diffs]:
        print(f"\n{d['case_id']} gold={d['gold_status']} pred={d['pred_status']}")
        for s in d["missing"]:
            print("   - missing", s["phase"][:5], s["operation"], s["system_id"], s["resource_id"], repr(s["evidence_id"]))
        for s in d["extra"]:
            print("   + extra  ", s["phase"][:5], s["operation"], s["system_id"], s["resource_id"], repr(s["evidence_id"]))


if __name__ == "__main__":
    main()
