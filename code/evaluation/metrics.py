"""Scoring of predicted rows against canonical rows (sample_output.csv or custom cases)."""
from __future__ import annotations

import json
from collections import Counter

FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def _key(s):  # identity of a step without its citation
    return (s["phase"], s["system_id"], s["resource_id"], s["operation"])


def _full(s):
    return tuple(s[f] for f in FIELDS)


def score(pred: dict[str, tuple[str, list]], gold: dict[str, tuple[str, list]]) -> dict:
    statuses = sorted({g[0] for g in gold.values()} | {p[0] for p in pred.values()})
    conf = Counter()
    tp = fp = fn = 0
    ktp = kfp = kfn = 0
    field_hits, field_tot = Counter(), 0
    exact = ordered_ok = ordered_tot = 0
    diffs = []
    for cid, (gstatus, gsteps) in sorted(gold.items()):
        pstatus, psteps = pred.get(cid, ("MISSING", []))
        conf[(gstatus, pstatus)] += 1
        gf, pf = Counter(map(_full, gsteps)), Counter(map(_full, psteps))
        tp += sum((gf & pf).values()); fp += sum((pf - gf).values()); fn += sum((gf - pf).values())
        gk, pk = Counter(map(_key, gsteps)), Counter(map(_key, psteps))
        ktp += sum((gk & pk).values()); kfp += sum((pk - gk).values()); kfn += sum((gk - pk).values())
        gmap = {_key(s): s for s in gsteps}
        for s in psteps:  # field accuracy over steps aligned by identity
            g = gmap.get(_key(s))
            if g:
                field_tot += 1
                for f in FIELDS:
                    field_hits[f] += s[f] == g[f]
        same = [_full(s) for s in psteps] == [_full(s) for s in gsteps]
        exact += same and pstatus == gstatus
        if gk == pk and gsteps:
            ordered_tot += 1
            ordered_ok += [_key(s) for s in psteps] == [_key(s) for s in gsteps]
        if not same or pstatus != gstatus:
            diffs.append({"case_id": cid, "gold_status": gstatus, "pred_status": pstatus,
                          "missing": [s for s in gsteps if _full(s) not in pf],
                          "extra": [s for s in psteps if _full(s) not in gf]})
    n = len(gold)

    def prf(t, p_, n_):
        p = t / (t + p_) if t + p_ else 0.0
        r = t / (t + n_) if t + n_ else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}

    per_status = {}
    for st in statuses:
        t = conf[(st, st)]
        predicted = sum(v for (g, p), v in conf.items() if p == st)
        actual = sum(v for (g, p), v in conf.items() if g == st)
        per_status[st] = {"precision": round(t / predicted, 4) if predicted else None,
                          "recall": round(t / actual, 4) if actual else None, "support": actual}
    return {
        "cases": n,
        "status_accuracy": round(sum(conf[(s, s)] for s in statuses) / n, 4) if n else 0.0,
        "per_status": per_status,
        "confusion": {f"{g}->{p}": v for (g, p), v in sorted(conf.items())},
        "step_strict": prf(tp, fp, fn) | {"tp": tp, "fp": fp, "fn": fn},
        "step_ignoring_evidence": prf(ktp, kfp, kfn) | {"tp": ktp, "fp": kfp, "fn": kfn},
        "field_accuracy_on_aligned_steps": {f: round(field_hits[f] / field_tot, 4) if field_tot else None for f in FIELDS},
        "aligned_steps": field_tot,
        "exact_case_match": round(exact / n, 4) if n else 0.0,
        "ordering_accuracy": round(ordered_ok / ordered_tot, 4) if ordered_tot else None,
        "diffs": diffs,
    }


def load_rows(path) -> dict[str, tuple[str, list]]:
    import csv
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}
