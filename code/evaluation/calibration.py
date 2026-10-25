"""Reliability of the evidence-card confidences on the 32 public samples (the only labels we have).

    python code/evaluation/calibration.py          # prints both reliability tables
    python code/evaluation/calibration.py --json

Table A: every FINDING card; correct = the finding (phase, system, resource, operation) is in sample_output.csv.
Table B: every resource the engine emitted a step for, scored by match strength alone (identifier evidence or the
worker-chain assignment); correct = sample_output.csv has a step on that resource for that case. Chain links only
ever produce verifications, so table B is where the lower-confidence links are tested.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit.config import DATASET_DIR  # noqa: E402
from audit.evidence_cards import CardBuilder  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from evaluation.metrics import load_rows  # noqa: E402

BINS = [(0.0, 0.6), (0.6, 0.75), (0.75, 0.9), (0.9, 0.95), (0.95, 1.01)]


def table(items: list[tuple[float, bool, str]]) -> dict:
    rows = []
    for lo, hi in BINS:
        xs = [(c, ok) for c, ok, _ in items if lo <= c < hi]
        if xs:
            rows.append({"bin": f"{lo:.2f}-{min(hi, 1.0):.2f}", "n": len(xs), "mean_conf": round(sum(c for c, _ in xs) / len(xs), 3),
                         "accuracy": round(sum(ok for _, ok in xs) / len(xs), 3)})
    by_mode = defaultdict(list)
    for c, ok, mode in items:
        by_mode[mode].append((c, ok))
    n = len(items)
    ece = sum(abs(r["mean_conf"] - r["accuracy"]) * r["n"] for r in rows) / n if n else None
    return {"n": n, "accuracy": round(sum(ok for _, ok, _ in items) / n, 4) if n else None,
            "mean_conf": round(sum(c for c, _, _ in items) / n, 4) if n else None,
            "ece": round(ece, 4) if ece is not None else None, "bins": rows,
            "by_mode": {m: {"n": len(v), "mean_conf": round(sum(c for c, _ in v) / len(v), 3),
                            "accuracy": round(sum(ok for _, ok in v) / len(v), 3)} for m, v in sorted(by_mode.items())}}


def calibrate(engine: AuditEngine | None = None, results=None) -> dict:
    engine = engine or AuditEngine(DATASET_DIR)
    results = results or engine.run()
    gold = load_rows(DATASET_DIR / "sample_output.csv")
    builder = CardBuilder(engine)
    findings, links, missed = [], [], 0
    for cid, (_, gsteps) in sorted(gold.items()):
        r = results[cid]
        gkeys = {(s["phase"], s["system_id"], s["resource_id"], s["operation"]) for s in gsteps}
        gres = {s["resource_id"] for s in gsteps}
        for s in r.steps:
            if s.phase == "FINDING":
                card = builder.card(r, s)
                mode = card["why"]["matches"][0]["mode"] if card["why"]["matches"] else "none"
                findings.append((card["confidence"], (s.phase, s.system_id, s.resource_id, s.operation) in gkeys, mode))
        emitted = sorted({s.resource_id for s in r.steps})
        for rid in emitted:
            conf, mode = builder.link_confidence(r, rid)
            links.append((conf, rid in gres, mode))
        missed += len(gres - set(emitted))
    return {"findings": table(findings), "resource_links": table(links), "gold_resources_never_emitted": missed}


def fmt(t: dict, title: str) -> str:
    lines = [f"{title}: n={t['n']} accuracy={t['accuracy']} mean_conf={t['mean_conf']} ECE={t['ece']}",
             "  bin          n   mean_conf  accuracy"]
    lines += [f"  {b['bin']:10s} {b['n']:4d}   {b['mean_conf']:.3f}      {b['accuracy']:.3f}" for b in t["bins"]]
    lines += ["  by mode: " + ", ".join(f"{m} n={v['n']} conf={v['mean_conf']} acc={v['accuracy']}" for m, v in t["by_mode"].items())]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    m = calibrate()
    if args.json:
        print(json.dumps(m, indent=2))
        return
    print(fmt(m["findings"], "A. finding cards (samples)"))
    print(fmt(m["resource_links"], "B. every emitted resource, match strength only (samples)"))
    print(f"gold resources the engine never emitted (no confidence to calibrate): {m['gold_resources_never_emitted']}")


if __name__ == "__main__":
    main()
