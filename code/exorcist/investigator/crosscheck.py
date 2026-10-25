"""Run the investigator on every deletion case and cross-check it against the main engine (sidecars only).

    python code/main.py crosscheck

Writes code/out/investigation_traces.jsonl (every step) and code/out/crosscheck.json (agreement, second-hop
discoveries, disagreement categories), and merges each disagreement into code/out/conflicts.jsonl and
code/out/review_queue.json (entries tagged source=investigator, replaced on every run). It never touches
output.csv and uses no gold labels (sample scoring lives in evaluation/investigator_eval.py).
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from audit.util import case_sort_key, read_csv

from .controller import Investigation
from .tools import Tools

CHAIN_MODES = ("chain_soft", "chain_elimination")
EXPECTED = {"engine_only_chain_link"}   # structural: identifier-free worker-chain links are out of reach by design


def engine_findings(r) -> set:
    return {(s.operation, s.system_id, s.resource_id) for s in r.steps if s.phase == "FINDING"}


def classify(r, inv) -> list[dict]:
    """Every difference between the engine and the investigator for one case, with a category and reason."""
    out = []
    eng_res = r.links.resources if r.links else {}
    for rid in sorted(set(eng_res) - set(inv.resources)):
        mode = eng_res[rid].mode
        if mode in CHAIN_MODES:
            cat = "engine_only_chain_link"
            why = "linked by deletion-worker timing (no identifier), which a lead-following search cannot reach"
        elif mode == "evidence_contested":
            cat = "engine_only_contested"
            why = "engine kept a contested catalog record as fail-safe; the investigator found other evidence and dropped it"
        else:
            cat = "engine_only_identifier_link"
            why = "engine tied it by an identifier the investigator's queries did not surface"
        out.append({"category": cat, "resource_id": rid, "engine_mode": mode, "why": why})
    for rid in sorted(set(inv.resources) - set(eng_res)):
        f = inv.resources[rid]
        out.append({"category": f"investigator_only_{f.how.replace('-', '_')}", "resource_id": rid, "hop": f.hop,
                    "why": f"investigator reached it via {f.how}: {f.lead}"})
    ef = engine_findings(r)
    for op, system, rid in sorted(inv.findings - ef):
        out.append({"category": "investigator_only_finding", "resource_id": rid, "operation": op,
                    "why": f"investigator assessed {rid} as a violation; the engine did not report it"})
    for op, system, rid in sorted(ef - inv.findings):
        out.append({"category": "engine_only_finding", "resource_id": rid, "operation": op,
                    "why": f"engine reported {op} on {rid}; the investigator did not reach or flag it"})
    if r.status != inv.status:
        out.append({"category": "status_disagreement", "engine": r.status, "investigator": inv.status,
                    "why": "different violation sets"})
    return out


def run(engine, results, out_dir: Path | None = None, verbose=True) -> dict:
    t0 = time.time()
    tools = Tools(engine)
    eval_ids = {r["case_id"] for r in read_csv(engine.dataset_dir / "deletion_requests.csv")}
    cases = [results[cid] for cid in sorted(results, key=case_sort_key) if results[cid].status != "NOT_APPLICABLE"]
    invs, traces, per_case = {}, [], {}
    for r in cases:
        inv = Investigation(tools, engine, r.case).run()
        invs[r.case.case_id] = inv
        traces += inv.trace
        per_case[r.case.case_id] = classify(r, inv)

    def agreement(ids):
        ids = [i for i in ids if i in invs]
        n = len(ids)
        status = sum(results[i].status == invs[i].status for i in ids)
        exact = sum(engine_findings(results[i]) == invs[i].findings for i in ids)
        e = sum(len(engine_findings(results[i])) for i in ids)
        v = sum(len(invs[i].findings) for i in ids)
        both = sum(len(engine_findings(results[i]) & invs[i].findings) for i in ids)
        return {"cases": n, "status_agreement": round(status / n, 4) if n else None,
                "identical_finding_sets": round(exact / n, 4) if n else None,
                "engine_findings": e, "investigator_findings": v, "shared_findings": both,
                "finding_overlap_vs_engine": round(both / e, 4) if e else None}

    all_ids = list(invs)
    hop2 = [(cid, f) for cid, inv in invs.items() for f in inv.resources.values() if f.hop == 2]
    hop2_viol = [(cid, f) for cid, f in hop2 if any(a.resource_id == f.resource_id and a.status == "violation"
                                                     for a in invs[cid].assessments)]
    hop2_eval = [(cid, f) for cid, f in hop2 if cid in eval_ids]
    ghost_after_lead = [(cid, f) for cid, f in hop2_viol if cid in eval_ids]
    cats = Counter(d["category"] for cid in all_ids for d in per_case[cid])
    cats_eval = Counter(d["category"] for cid in all_ids if cid in eval_ids for d in per_case[cid])
    trace_text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in traces)
    summary = {
        "trace_sha256": hashlib.sha256(trace_text.encode("utf-8")).hexdigest(),
        "note": "investigator = independent lead-following discovery; state/policy reuse the engine's Timeline/Policy agents",
        "seconds": round(time.time() - t0, 1),
        "agreement": {"all_deletion_cases": agreement(all_ids), "evaluation": agreement([i for i in all_ids if i in eval_ids]),
                      "samples": agreement([i for i in all_ids if i not in eval_ids])},
        "steps": {"total": len(traces), "mean_per_case": round(len(traces) / len(invs), 1),
                  "max_per_case": max(i.steps for i in invs.values()), "frontier_exhausted_all": all(i.exhausted for i in invs.values())},
        "second_hop": {
            "discoveries_all": len(hop2), "discoveries_evaluation": len(hop2_eval),
            "by_lead_type_evaluation": dict(Counter(f.how for _, f in hop2_eval)),
            "also_linked_by_engine_evaluation": sum(1 for cid, f in hop2_eval if f.resource_id in results[cid].links.resources),
            "ghosts_found_only_after_a_lead_evaluation": len(ghost_after_lead),
            "ghosts_found_only_after_a_lead_by_type": dict(Counter(f.how for _, f in ghost_after_lead)),
        },
        "identifiers_discovered_in_files": sum(len(i.identifiers_discovered) for i in invs.values()),
        "tool_calls": dict(sorted(Counter(t["tool"] if not (t["tool"] == "query_snapshot" and "resources" in t["args"])
                                          else "query_snapshot(destination)" for t in traces).items())),
        "leads_followed": dict(sorted(Counter(
            "trace" if t["tool"] == "search_logs" and "trace" in t["args"] else
            "destination" if t["tool"] == "query_snapshot" and "resources" in t["args"] else t["tool"]
            for t in traces if t["chosen_because"].startswith("follow a lead")).items())),
        "material_disagreement_cases_evaluation": sum(1 for cid in all_ids if cid in eval_ids and
                                                       any(d["category"] not in EXPECTED for d in per_case[cid])),
        "disagreement_categories_all": dict(sorted(cats.items())),
        "disagreement_categories_evaluation": dict(sorted(cats_eval.items())),
        "cases_with_any_disagreement_evaluation": sum(1 for cid in all_ids if cid in eval_ids and per_case[cid]),
        "per_case": {cid: {"engine": results[cid].status, "investigator": invs[cid].status, "differences": d}
                     for cid, d in per_case.items() if d},
    }
    if out_dir is not None:
        write(out_dir, trace_text, summary, eval_ids)
    if verbose:
        a = summary["agreement"]
        print(f"investigator: {len(invs)} cases, {len(traces)} steps in {summary['seconds']} s")
        for k in ("all_deletion_cases", "evaluation", "samples"):
            print(f"  {k}: {a[k]}")
        print("  second hop:", summary["second_hop"])
        print("  disagreement categories (evaluation):", summary["disagreement_categories_evaluation"])
    return summary


def write(out_dir: Path, trace_text: str, summary, eval_ids):
    with open(out_dir / "investigation_traces.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(trace_text)
    (out_dir / "crosscheck.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    # merge disagreements into the conflict ledger and review queue (replace earlier investigator entries)
    conf_path = out_dir / "conflicts.jsonl"
    rows = [json.loads(l) for l in conf_path.read_text(encoding="utf-8").splitlines() if l.strip()] if conf_path.exists() else []
    rows = [x for x in rows if x.get("source") != "investigator"]
    for cid, pc in summary["per_case"].items():
        if cid not in eval_ids:
            continue
        for d in pc["differences"]:
            rows.append({"case_id": cid, "type": "engine_vs_investigator", "source": "investigator", **d,
                         "trusted": "engine (output.csv unchanged)", "engine_status": pc["engine"],
                         "investigator_status": pc["investigator"]})
    with open(conf_path, "w", encoding="utf-8", newline="\n") as fh:
        for x in rows:
            fh.write(json.dumps(x, ensure_ascii=False, default=str) + "\n")
    q_path = out_dir / "review_queue.json"
    if q_path.exists():
        q = json.loads(q_path.read_text(encoding="utf-8"))
        q["cases"] = [c for c in q["cases"] if not c.get("added_by_investigator")]
        listed = []
        for cid, pc in sorted(summary["per_case"].items(), key=lambda kv: case_sort_key(kv[0])):
            if cid not in eval_ids:
                continue
            cats = sorted({d["category"] for d in pc["differences"]})
            material = any(c not in EXPECTED for c in cats)
            listed.append({"case_id": cid, "categories": cats, "material": material})
            if material:   # a real disagreement (finding, status or identifier link) joins the queue itself
                q["cases"].append({"case_id": cid, "status": pc["engine"], "added_by_investigator": True,
                                   "reasons": ["engine and investigator disagree: " + ", ".join(cats)], "ambiguous_links": []})
        q["cases"].sort(key=lambda c: case_sort_key(c["case_id"]))
        q["investigator_disagreements"] = {
            "rule": "every evaluation case where the lead-following investigator differs from the engine; only material "
                    "differences (anything but engine_only_chain_link, which is out of reach by design and already "
                    "margin-flagged above) are added to `cases`",
            "cases": listed}
        q_path.write_text(json.dumps(q, indent=1, ensure_ascii=False), encoding="utf-8")
