"""Score the lead-following investigator on the 32 samples against sample_output.csv (status + findings).

    python code/evaluation/investigator_eval.py

The investigator emits no steps of its own (it only discovers resources and assesses them), so it is scored on
case status and on FINDING identity (operation, system, resource), the part of a plan its discovery decides.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from evaluation.metrics import load_rows  # noqa: E402
from exorcist.investigator.controller import Investigation  # noqa: E402
from exorcist.investigator.tools import Tools  # noqa: E402


def evaluate(engine: AuditEngine | None = None, results=None) -> dict:
    engine = engine or AuditEngine(DATASET_DIR)
    results = results or engine.run()
    gold = load_rows(DATASET_DIR / "sample_output.csv")
    tools = Tools(engine)
    status_ok = tp = fp = fn = 0
    eng_tp = eng_fp = eng_fn = 0
    for cid, (gstatus, gsteps) in sorted(gold.items()):
        r = results[cid]
        g = {(s["operation"], s["system_id"], s["resource_id"]) for s in gsteps if s["phase"] == "FINDING"}
        if r.status == "NOT_APPLICABLE":
            status_ok += gstatus == "NOT_APPLICABLE"
            continue
        inv = Investigation(tools, engine, r.case).run()
        status_ok += inv.status == gstatus
        tp += len(inv.findings & g); fp += len(inv.findings - g); fn += len(g - inv.findings)
        e = {(s.operation, s.system_id, s.resource_id) for s in r.steps if s.phase == "FINDING"}
        eng_tp += len(e & g); eng_fp += len(e - g); eng_fn += len(g - e)
    n = len(gold)
    prf = lambda t, p, f: {"precision": round(t / (t + p), 4) if t + p else None, "recall": round(t / (t + f), 4) if t + f else None,
                           "tp": t, "fp": p, "fn": f}
    return {"cases": n, "investigator_status_accuracy": round(status_ok / n, 4),
            "investigator_findings_vs_gold": prf(tp, fp, fn), "engine_findings_vs_gold": prf(eng_tp, eng_fp, eng_fn)}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
