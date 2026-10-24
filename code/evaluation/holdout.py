"""Overfitting check: tune the free knobs on half of the samples, score on the other half (both directions,
several seeded splits). Knobs = linker cost constants + citation rule; everything else is a spec convention.

    python code/evaluation/holdout.py
"""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit.linker as L  # noqa: E402
from audit.config import DATASET_DIR  # noqa: E402
from audit.parsers import load_evidence  # noqa: E402
from audit.pipeline import AuditEngine  # noqa: E402
from audit.planner import PlannerAgent  # noqa: E402
from evaluation.citation_study import RULES  # noqa: E402
from evaluation.metrics import load_rows, score  # noqa: E402

GRID = {"COOCCURRENCE_BONUS": [0.0, 0.5, 1.0], "PHASE_WEIGHT": [0.0, 1.0, 2.0],
        "ACCOUNT_EXPECTED_OFFSET_H": [-0.5, -1.0, -1.5], "DUMMY_COST": [2.0, 4.0, 8.0]}
DEFAULT = {"COOCCURRENCE_BONUS": 0.5, "PHASE_WEIGHT": 1.0, "ACCOUNT_EXPECTED_OFFSET_H": -1.0, "DUMMY_COST": 4.0,
           "cite": "latest_pre_audit_explicit_first"}


def _cite(rule):
    return lambda proof, audit_at, reported_at=None, **_: rule(proof, audit_at, reported_at, None)


def predictions(ev, gold):
    """config -> {case_id: (status, steps)} for every knob combination and citation rule."""
    out = {}
    keys = list(GRID)
    for values in itertools.product(*GRID.values()):
        for k, v in zip(keys, values):
            setattr(L, k, v)
        eng = AuditEngine(DATASET_DIR, evidence=ev)
        res = eng.run()
        for name, rule in RULES.items():
            planner = PlannerAgent(cite=_cite(rule))
            pred = {}
            for cid in gold:
                r = res[cid]
                if r.status == "NOT_APPLICABLE":
                    pred[cid] = ("NOT_APPLICABLE", [])
                else:
                    st, steps = planner.plan(r.assessments, r.case.audit_at, r.case.reported_at)
                    pred[cid] = (st, [s.as_json() for s in steps])
            out[tuple(values) + (name,)] = pred
    for k in keys:
        setattr(L, k, DEFAULT[k])
    return out


def _f1(pred, gold, ids):
    m = score({c: pred[c] for c in ids}, {c: gold[c] for c in ids})
    return m["step_strict"]["f1"], m["status_accuracy"]


def run(seeds=(1, 2, 3, 4, 5), verbose=True) -> dict:
    gold = load_rows(DATASET_DIR / "sample_output.csv")
    ev = load_evidence(DATASET_DIR)
    preds = predictions(ev, gold)
    default_key = tuple(DEFAULT[k] for k in GRID) + (DEFAULT["cite"],)
    rows = []
    for seed in seeds:
        ids = sorted(gold)
        random.Random(seed).shuffle(ids)
        halves = (sorted(ids[:16]), sorted(ids[16:]))
        for train, test in (halves, halves[::-1]):
            train_scores = {k: _f1(preds[k], gold, train) for k in preds}
            best = max(preds, key=lambda k: (train_scores[k], k == default_key))
            tied = sum(1 for k in preds if train_scores[k] == train_scores[best])
            tr, te = _f1(preds[best], gold, train), _f1(preds[best], gold, test)
            dtr, dte = _f1(preds[default_key], gold, train), _f1(preds[default_key], gold, test)
            rows.append({"seed": seed, "tuned_config": dict(zip(list(GRID) + ["cite"], best)), "tied_best_configs": tied,
                         "train_f1": tr[0], "test_f1": te[0], "train_status": tr[1], "test_status": te[1],
                         "default_train_f1": dtr[0], "default_test_f1": dte[0]})
            if verbose:
                print(f"seed {seed}: tuned train F1 {tr[0]:.4f} / test F1 {te[0]:.4f} (status {tr[1]:.3f}/{te[1]:.3f}); "
                      f"default {dtr[0]:.4f}/{dte[0]:.4f}; tuned={rows[-1]['tuned_config']}")
    gaps = [r["train_f1"] - r["test_f1"] for r in rows]
    summary = {"folds": len(rows), "mean_train_f1": round(sum(r["train_f1"] for r in rows) / len(rows), 4),
               "mean_test_f1": round(sum(r["test_f1"] for r in rows) / len(rows), 4),
               "mean_gap": round(sum(gaps) / len(gaps), 4), "max_gap": round(max(gaps), 4),
               "configs_searched": len(preds)}
    if verbose:
        print(json.dumps(summary))
    return {"rows": rows, "summary": summary}


if __name__ == "__main__":
    run()
